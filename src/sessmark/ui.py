"""Optional terminal UI. Host behavior is supplied as callbacks."""

import json
import os
import shlex
import subprocess
import sys

from .model import SessmarkError
from .resume import execute, plan


def require_ui():
    try:
        import prompt_toolkit

        return prompt_toolkit
    except ImportError as exc:
        raise SessmarkError('Install UI support: pip install "sessmark[ui]"') from exc


def context_command(store, id):
    argv = ["sessmark", "--db", str(store.path.resolve()), "context", id, "--json"]
    if store.config.path.exists():
        argv.extend(["--config", str(store.config.path.resolve())])
    if os.name == "nt":
        return "& " + " ".join("'" + arg.replace("'", "''") + "'" for arg in argv)
    return shlex.join(argv)


def copy_command(text):
    if sys.platform == "win32":
        # Data travels on stdin; PowerShell command text is fixed.
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                (
                    "[Console]::InputEncoding = [Text.Encoding]::UTF8; "
                    "Set-Clipboard -Value ([Console]::In.ReadToEnd())"
                ),
            ],
            input=text.encode("utf-8"),
            check=True,
            capture_output=True,
            timeout=10,
        )
    elif sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=10)
    else:
        import shutil

        argv = ["wl-copy"] if shutil.which("wl-copy") else ["xclip", "-selection", "clipboard"]
        subprocess.run(argv, input=text.encode("utf-8"), check=True, timeout=10)


def mark_dialog(store, selected, before_save=None, *, input=None, output=None):
    require_ui()
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, Layout
    from prompt_toolkit.widgets import CheckboxList, Dialog, Label, TextArea

    chips = CheckboxList(values=[(t, t) for t in store.config.tags])
    note = TextArea(height=1, prompt="Note: ", multiline=False)
    status = Label("Space: toggle tag · Tab: note · Enter: save · Esc: cancel")
    keys = KeyBindings()

    @keys.add("tab")
    def switch(event):
        event.app.layout.focus(note if event.app.layout.has_focus(chips) else chips)

    @keys.add("enter", eager=True)
    def save(event):
        if not chips.current_values and not note.text.strip():
            status.text = "Select a tag or enter a note."
            return
        try:
            actual = before_save() if before_save else selected
            result = store.mark(**actual, tags=chips.current_values, note=note.text or None)
            event.app.exit(result=result)
        except (SessmarkError, OSError) as exc:
            status.text = str(exc)

    @keys.add("escape")
    @keys.add("c-c")
    def cancel(event):
        event.app.exit()

    dialog = Dialog(
        title="sessmark · Add tags and note",
        body=HSplit([chips, note, status]),
        with_background=True,
    )
    app = Application(
        layout=Layout(dialog, focused_element=chips),
        key_bindings=keys,
        full_screen=True,
        input=input,
        output=output,
    )
    return app.run()


def viewer(store, tags=(), on_open=None, *, input=None, output=None):
    require_ui()
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, Layout
    from prompt_toolkit.widgets import Label, RadioList, TextArea

    store.config.validate_tags(tags)
    filter_box = TextArea(height=1, text=" ".join(tags), prompt="Tags (AND): ", multiline=False)
    rows = RadioList(values=[("", "No marked sessions")])
    detail = TextArea(read_only=True, scrollbar=True, height=8)
    status = Label(
        "↑↓: select · Enter: open/resume · /: filter · y: copy context command · q: quit"
    )
    keys = KeyBindings()

    def refresh():
        try:
            sessions = store.list(filter_box.text.split())
            rows.values = [
                (s["id"], f"{s['agent']}  {','.join(s['tags'])}  {s['notes_preview']}")
                for s in sessions
            ] or [("", "No marked sessions")]
            rows._selected_index = 0
            rows.current_value = rows.values[0][0]
            show_detail()
        except SessmarkError as exc:
            status.text = str(exc)

    def selected_id():
        return rows.values[rows._selected_index][0]

    def show_detail():
        id = selected_id()
        detail.text = (
            json.dumps(dict(zip(("session", "notes"), store.get(id))), ensure_ascii=False, indent=2)
            if id
            else ""
        )

    @keys.add("/", eager=True)
    def focus_filter(event):
        event.app.layout.focus(filter_box)

    @keys.add("enter", eager=True)
    def open_selected(event):
        if event.app.layout.has_focus(filter_box):
            refresh()
            event.app.layout.focus(rows)
        elif id := selected_id():
            event.app.exit(result=id)

    @keys.add("y")
    def copy(event):
        if event.app.layout.has_focus(filter_box):
            filter_box.buffer.insert_text("y")
            return
        if id := selected_id():
            try:
                copy_command(context_command(store, id))
                status.text = "Context command copied. For multiple routes add --tag or --template."
            except (OSError, subprocess.SubprocessError) as exc:
                status.text = f"Clipboard unavailable: {exc}"

    @keys.add("q")
    def quit_key(event):
        if event.app.layout.has_focus(filter_box):
            filter_box.buffer.insert_text("q")
        else:
            event.app.exit()

    @keys.add("escape")
    @keys.add("c-c")
    def cancel(event):
        event.app.exit()

    refresh()
    app = Application(
        layout=Layout(HSplit([filter_box, rows, detail, status]), focused_element=rows),
        key_bindings=keys,
        full_screen=True,
        input=input,
        output=output,
    )

    def update_detail(_):
        # Updating TextArea on every invalidation would itself invalidate forever.
        id = selected_id()
        if id != getattr(update_detail, "last", None):
            update_detail.last = id
            show_detail()

    app.before_render += update_detail
    id = app.run()
    if id:
        return on_open(id) if on_open else execute(plan(store.get(id)[0]))
