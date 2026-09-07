"""Optional terminal UI. Host behavior is supplied as callbacks."""

import os
import shlex
import sqlite3
import subprocess
import sys
from datetime import datetime

from .config import default_route
from .i18n import t
from .model import SessmarkError, since_time
from .resume import execute, native_command, plan


def require_ui():
    try:
        import prompt_toolkit

        return prompt_toolkit
    except ImportError as exc:
        raise SessmarkError('Install UI support: pip install "sessmark[ui]"') from exc


def local_stamp(value: str) -> str:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    if moment.tzinfo is not None:
        moment = moment.astimezone()
    return moment.strftime("%m-%d %H:%M")


def format_card(session, notes, prompts=()):
    locator = session.get("locator") or {}
    resume = [str(part) for part in (locator.get("resume_cmd") or [])]
    if not resume:
        resume = list(
            native_command(
                session.get("agent") or locator.get("harness"),
                locator.get("session_id"),
                locator.get("transcript_path"),
            )
        )
    lines = [
        f"id          {session['id']}",
        f"agent       {session.get('agent') or locator.get('harness') or '—'}",
        f"tags        {', '.join(session.get('tags') or ()) or '—'}",
        f"updated     {local_stamp(session.get('updated_at') or '')}",
        f"cwd         {session.get('cwd') or '—'}",
        f"session     {locator.get('session_id') or '(pending)'}",
        f"transcript  {locator.get('transcript_path') or '—'}",
        f"resume      {' '.join(resume) if resume else '—'}",
        "",
        "notes",
    ]
    if notes:
        lines.extend(f"  {local_stamp(note['ts'])}  {note['text']}" for note in notes)
    else:
        lines.append("  (none)")
    for name, text in prompts:
        lines.extend(["", f"prompt · {name}", f"  {text}"])
    return "\n".join(lines)


def session_prompts(store, tags):
    seen = []
    for tag in tags:
        template = store.config.routes.get(tag)
        if template and template not in seen:
            seen.append(template)
            yield template, store.config.templates[template]["text"]


def session_card(store, id):
    session, notes = store.get(id)
    return format_card(session, notes, tuple(session_prompts(store, session["tags"])))


def context_command(store, id):
    # Keep the interpreter's venv path (do not resolve symlinks on macOS/Linux).
    argv = [
        os.path.abspath(sys.executable),
        "-m",
        "sessmark",
        "--db",
        str(store.path.resolve()),
        "context",
        id,
        "--json",
    ]
    if store.config.path.exists():
        argv.extend(["--config", str(store.config.path.resolve())])
    if os.name == "nt":
        return "& " + " ".join("'" + arg.replace("'", "''") + "'" for arg in argv)
    return shlex.join(argv)


def copy_command(text):
    if sys.platform == "win32":
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


def _style():
    from prompt_toolkit.styles import Style

    return Style.from_dict(
        {
            "": "bg:#101820 #dce5eb",
            "title": "bg:#203549 #78dce8 bold",
            "status": "bg:#203549 #dce5eb",
            "hint": "#a8b9c7",
            "accent": "#78dce8 bold",
            "frame.border": "#405366",
            "frame.label": "#a8b9c7 bold",
            "focused frame.border": "#78dce8",
            "focused frame.label": "#78dce8 bold",
            "checkbox": "",
            "checkbox-selected": "bg:#294459 bold",
            "checkbox-checked": "#a8e6a3 bold",
            "radio": "",
            "radio-selected": "bg:#294459 bold",
            "radio-checked": "",
            "cursor-line": "bg:#294459",
            "text-area": "",
            "text-area.prompt": "#78dce8 bold",
            "button": "bg:#203549 #dce5eb",
            "button.focused": "bg:#78dce8 #101820 bold",
            "scrollbar.background": "#405366",
            "scrollbar.button": "#78dce8",
            "label": "",
        }
    )


def _application(container, keys, focused, input, output):
    from prompt_toolkit.application import Application
    from prompt_toolkit.layout import Layout

    return Application(
        layout=Layout(container, focused_element=focused),
        key_bindings=keys,
        full_screen=True,
        mouse_support=True,
        style=_style(),
        include_default_pygments_style=False,
        input=input,
        output=output,
    )


def _title(text):
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.layout import Window
    from prompt_toolkit.layout.controls import FormattedTextControl

    return Window(
        FormattedTextControl(lambda: FormattedText([("class:title", f"  {text}")])),
        style="class:title",
        height=1,
        dont_extend_height=True,
    )


def _status(label):
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.layout import Window
    from prompt_toolkit.layout.controls import FormattedTextControl

    return Window(
        FormattedTextControl(lambda: FormattedText([("class:status", f"  {label.text}  ")])),
        style="class:status",
        height=1,
        dont_extend_height=True,
    )


def _stretch(widget):
    from prompt_toolkit.filters import to_filter

    widget.window.dont_extend_height = to_filter(False)
    if hasattr(widget, "_selected_index"):
        widget.window.cursorline = to_filter(True)
    return widget


def _tag_label(config, tag):
    return f"{tag}   {t('tag.pipeline') if tag in config.routes else t('tag.lookup')}"


def _tag_detail(config, tag):
    if not tag:
        return t("tag.empty_detail")
    route = config.routes.get(tag)
    if not route:
        return t("tag.lookup_detail", tag=tag)
    return t(
        "tag.pipeline_detail", tag=tag, route=route, text=config.templates[route]["text"]
    )


def _tag_matches(config, tag, query):
    route = config.routes.get(tag, "")
    body = config.templates.get(route, {}).get("text", "")
    text = f"{tag} {route} {body}".casefold()
    return all(word in text for word in query.casefold().split())


def _selected(rows):
    return rows.values[rows._selected_index][0]


def _set_rows(rows, values, select=None):
    chosen = select or _selected(rows)
    rows.values = values or [("", t("empty_rows"))]
    ids = [id for id, _ in rows.values]
    rows._selected_index = ids.index(chosen) if chosen in ids else 0
    rows.current_value = _selected(rows)


def _panel(widget, title):
    from prompt_toolkit.filters import has_focus
    from prompt_toolkit.layout import HSplit
    from prompt_toolkit.widgets import Frame

    return HSplit(
        [Frame(widget, title=title)], style=lambda: "class:focused" if has_focus(widget)() else ""
    )


def _columns(left, right):
    from prompt_toolkit.application import get_app
    from prompt_toolkit.layout import DynamicContainer, HSplit, VSplit
    from prompt_toolkit.layout.dimension import Dimension as D

    wide = VSplit(
        [HSplit([left], width=D(weight=2)), HSplit([right], width=D(weight=3))], padding=1
    )
    narrow = HSplit(
        [HSplit([left], height=D(min=4, weight=2)), HSplit([right], height=D(min=4, weight=3))]
    )
    return DynamicContainer(lambda: wide if get_app().output.get_size().columns >= 100 else narrow)


def _detail_box():
    from prompt_toolkit.widgets import TextArea

    return _stretch(TextArea(read_only=True, scrollbar=True, wrap_lines=True))


def _search_keys(keys, search, rows, typing=()):
    from prompt_toolkit.filters import has_focus

    shortcut = ~has_focus(search)
    for field in typing:
        shortcut &= ~has_focus(field)

    @keys.add("c-f")
    @keys.add("/", eager=True, filter=shortcut)
    def focus(event):
        event.app.layout.focus(search)

    @keys.add("c-l")
    def clear(event):
        search.text = ""

    @keys.add("down", filter=has_focus(search))
    @keys.add("enter", eager=True, filter=has_focus(search))
    def results(event):
        event.app.layout.focus(rows)


def _tabs(keys):
    from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous

    keys.add("tab")(focus_next)
    keys.add("s-tab")(focus_previous)


def _detail_keys(keys, rows, detail):
    @keys.add("f4")
    def focus_detail(event):
        event.app.layout.focus(rows if event.app.layout.has_focus(detail) else detail)


def open_config_file(path):
    # Store Python can transparently redirect AppData reads/writes. ShellExecute
    # runs outside that virtualization, so give the editor the physical filename.
    try:
        path = path.expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise SessmarkError(f"Config file is missing: {path}") from exc
    if not path.is_file():
        raise SessmarkError(f"Config file is missing: {path}")
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def tag_editor(config, tag=None, *, input=None, output=None):
    """Create or edit one vocabulary entry. Returns the tag on save, otherwise None."""
    return _tag_editor_app(config, tag, input=input, output=output).run()


async def _run_dialog(app):
    from prompt_toolkit.application import in_terminal

    # Suspend the parent's renderer and input while the child uses the same loop.
    async with in_terminal():
        return await app.run_async()


def _tag_editor_app(config, tag=None, *, input=None, output=None):
    require_ui()
    from prompt_toolkit.application import get_app
    from prompt_toolkit.filters import has_focus
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, VSplit
    from prompt_toolkit.widgets import Button, Label, TextArea

    creating = tag is None
    existing = ""
    if tag and tag in config.routes:
        existing = config.templates[config.routes[tag]]["text"]
    name = TextArea(
        height=1,
        prompt="  ",
        text="" if creating else tag,
        multiline=False,
        read_only=not creating,
    )
    prompt = _stretch(
        TextArea(prompt="  ", text=existing, multiline=True, scrollbar=True, wrap_lines=True)
    )
    status = Label(t("editor.status"))
    keys = KeyBindings()
    _tabs(keys)

    def save():
        try:
            chosen = name.text.strip()
            body = prompt.text.strip()
            if creating:
                config.add_tag(
                    chosen,
                    route=None if not body else default_route(chosen),
                    text=None if not body else body,
                )
            else:
                config.set_prompt(tag, body)
                chosen = tag
            return chosen
        except (SessmarkError, OSError) as exc:
            status.text = str(exc)
            return None

    @keys.add("escape", "enter", eager=True)
    def newline(event):
        event.app.layout.focus(prompt)
        prompt.buffer.insert_text("\n")

    @keys.add("enter", eager=True, filter=has_focus(name) | has_focus(prompt))
    @keys.add("c-s")
    def commit(event=None):
        chosen = save()
        if chosen:
            get_app().exit(result=chosen)

    @keys.add("escape")
    @keys.add("c-c")
    def cancel(event=None):
        get_app().exit()

    title = t("editor.title_new") if creating else t("editor.title_edit", tag=tag)
    body = HSplit(
        [
            _title(title),
            Label(t("editor.hint"), style="class:hint"),
            _panel(name, t("editor.panel_name")),
            _panel(prompt, t("editor.panel_prompt")),
            VSplit(
                [
                    Button(t("btn.save"), handler=commit, width=16),
                    Button(t("btn.cancel"), handler=cancel),
                ],
                padding=1,
                height=1,
            ),
            _status(status),
        ]
    )
    return _application(body, keys, name if creating else prompt, input, output)


def config_dialog(config, *, input=None, output=None):
    return _config_dialog_app(config, input=input, output=output).run()


def _config_dialog_app(config, *, input=None, output=None):
    require_ui()
    from prompt_toolkit.application import get_app
    from prompt_toolkit.filters import has_focus
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, VSplit
    from prompt_toolkit.widgets import Button, Label, RadioList, TextArea

    config.ensure_user_file()
    search = TextArea(height=1, prompt=" / ", multiline=False)
    rows = _stretch(
        RadioList(
            values=[("", "")],
            select_on_focus=True,
            open_character="",
            select_character="›",
            close_character="",
        )
    )
    detail = _detail_box()
    count = Label("", style="class:hint")
    status = Label(t("config.status"))
    keys = KeyBindings()
    _search_keys(keys, search, rows)
    _tabs(keys)
    _detail_keys(keys, rows, detail)

    def show_detail():
        detail.text = _tag_detail(config, _selected(rows))

    def refresh(select=None):
        values = [
            (tag, _tag_label(config, tag))
            for tag in config.tags
            if _tag_matches(config, tag, search.text)
        ]
        _set_rows(rows, values, select)
        count.text = t("config.count", shown=len(values), total=len(config.tags))
        show_detail()

    @keys.add("n", eager=True, filter=has_focus(rows))
    async def add(event=None):
        created = await _run_dialog(_tag_editor_app(config, input=input, output=output))
        if created:
            search.text = ""
        refresh(created)

    @keys.add("enter", eager=True, filter=has_focus(rows))
    async def edit(event=None):
        tag = _selected(rows)
        if tag:
            await _run_dialog(_tag_editor_app(config, tag, input=input, output=output))
            refresh(tag)

    @keys.add("d", eager=True, filter=has_focus(rows))
    def delete(event=None):
        tag = _selected(rows)
        if tag:
            try:
                config.remove_tag(tag)
                refresh()
                status.text = t("config.deleted", tag=tag)
            except (SessmarkError, OSError) as exc:
                status.text = str(exc)

    @keys.add("o", eager=True, filter=has_focus(rows))
    def open_file(event=None):
        try:
            config.ensure_user_file()
            open_config_file(config.path)
            status.text = t("config.opened_file")
        except (SessmarkError, OSError) as exc:
            status.text = str(exc)

    @keys.add("r", eager=True, filter=has_focus(rows))
    def reload(event=None):
        try:
            config.reload()
            refresh()
            status.text = t("config.reloaded")
        except SessmarkError as exc:
            status.text = str(exc)

    @keys.add("q", eager=True, filter=~has_focus(search))
    @keys.add("c-c")
    def close(event=None):
        get_app().exit()

    @keys.add("escape")
    def back(event):
        if event.app.layout.has_focus(rows):
            close()
        else:
            event.app.layout.focus(rows)

    actions = VSplit(
        [
            Button(t("config.add"), handler=lambda: get_app().create_background_task(add())),
            Button(
                t("config.edit"), handler=lambda: get_app().create_background_task(edit()), width=16
            ),
            Button(t("config.open_file"), handler=open_file, width=16),
            Button(t("config.back"), handler=close),
        ],
        padding=1,
        height=1,
    )
    body = HSplit(
        [
            _title(t("config.title")),
            _panel(search, t("config.search")),
            count,
            _columns(_panel(rows, t("config.panel_tags")), _panel(detail, t("config.panel_detail"))),
            actions,
            _status(status),
        ]
    )
    search.buffer.on_text_changed += lambda _: refresh()
    refresh()
    app = _application(body, keys, rows, input, output)

    def update_detail(_):
        tag = _selected(rows)
        if tag != getattr(update_detail, "last", None):
            update_detail.last = tag
            show_detail()

    app.before_render += update_detail
    return app


def mark_dialog(store, selected, before_save=None, *, input=None, output=None):
    require_ui()
    from prompt_toolkit.application import get_app
    from prompt_toolkit.filters import has_focus
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, VSplit
    from prompt_toolkit.widgets import Button, CheckboxList, Label, TextArea

    locator = selected.get("locator")
    identity = getattr(locator, "session_id", None) or t("mark.pending_id")
    search = TextArea(height=1, prompt=" / ", multiline=False)
    chips = _stretch(CheckboxList(values=[("", "")]))
    # The empty-results row is a placeholder, never a real tag (including mouse clicks).
    toggle = chips._handle_enter
    chips._handle_enter = lambda: toggle() if _selected(chips) else None
    detail = _detail_box()
    note = TextArea(height=1, prompt="  ", multiline=False)
    selected_label = Label("", style="class:accent", wrap_lines=False)
    count = Label("", style="class:hint")
    status = Label(t("mark.status"))
    keys = KeyBindings()
    _search_keys(keys, search, chips, typing=(note,))
    _detail_keys(keys, chips, detail)

    def refresh_chips(select=None):
        if select and select not in chips.current_values:
            chips.current_values.append(select)
        chips.current_values = [tag for tag in chips.current_values if tag in store.config.tags]
        values = [
            (tag, _tag_label(store.config, tag))
            for tag in store.config.tags
            if _tag_matches(store.config, tag, search.text)
        ]
        _set_rows(chips, values, select)
        count.text = t("mark.count", shown=len(values), total=len(store.config.tags))

    @keys.add("n", eager=True, filter=has_focus(chips))
    async def add_tag(event=None):
        created = await _run_dialog(_tag_editor_app(store.config, input=input, output=output))
        if created:
            search.text = ""
            refresh_chips(created)
            status.text = t("mark.added_tag", tag=created)

    @keys.add("e", eager=True, filter=has_focus(chips))
    async def edit_vocab(event=None):
        await _run_dialog(_config_dialog_app(store.config, input=input, output=output))
        refresh_chips()

    def save():
        text = note.text.strip()
        if not chips.current_values and not text:
            status.text = t("mark.need_input")
            return
        try:
            actual = before_save() if before_save else selected
            result = store.mark(**actual, tags=chips.current_values, note=text or None)
            get_app().exit(result=result)
        except (SessmarkError, OSError) as exc:
            status.text = str(exc)

    @keys.add("enter", eager=True, filter=has_focus(chips) | has_focus(note))
    @keys.add("c-s")
    def commit(event):
        save()

    def cancel():
        get_app().exit()

    @keys.add("escape")
    def back(event):
        if event.app.layout.has_focus(search) or event.app.layout.has_focus(detail):
            event.app.layout.focus(chips)
        else:
            cancel()

    @keys.add("c-c")
    def abort(event):
        cancel()

    save_button = Button(t("btn.save"), handler=save, width=16)
    cancel_button = Button(t("btn.cancel"), handler=cancel)
    actions = VSplit(
        [
            save_button,
            Button(t("mark.add"), handler=lambda: get_app().create_background_task(add_tag())),
            Button(t("mark.vocab"), handler=lambda: get_app().create_background_task(edit_vocab())),
            cancel_button,
        ],
        padding=1,
        height=1,
    )

    @keys.add("tab")
    @keys.add("s-tab")
    def switch(event):
        order = [chips, note, search, detail, *actions.children]
        index = next((i for i, widget in enumerate(order) if event.app.layout.has_focus(widget)), 0)
        step = -1 if event.key_sequence[0].key == "s-tab" else 1
        event.app.layout.focus(order[(index + step) % len(order)])

    body = HSplit(
        [
            _title(t("mark.title")),
            Label(
                f"  {getattr(locator, 'harness', '')}  ·  {identity}",
                style="class:hint",
                wrap_lines=False,
            ),
            _panel(search, t("mark.search")),
            count,
            _columns(
                _panel(chips, t("mark.panel_tags")), _panel(detail, t("mark.panel_detail"))
            ),
            selected_label,
            _panel(note, t("mark.note")),
            actions,
            _status(status),
        ]
    )
    search.buffer.on_text_changed += lambda _: refresh_chips()
    refresh_chips()
    app = _application(body, keys, chips, input, output)

    def update_detail(_):
        tag = _selected(chips)
        value = _tag_detail(store.config, tag)
        if detail.text != value:
            detail.text = value
        picked = [tag for tag in store.config.tags if tag in chips.current_values]
        hidden = len(set(picked) - {tag for tag, _ in chips.values})
        suffix = t("mark.hidden", hidden=hidden) if hidden else ""
        selected_label.text = t(
            "mark.selected",
            count=len(picked),
            suffix=suffix,
            tags=" · ".join(picked) or t("mark.none"),
        )

    app.before_render += update_detail
    return app.run()


def _row_label(session):
    project = session["cwd"].replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    note = session["notes_preview"] or t("row.tags_only")
    return f"{local_stamp(session['updated_at'])}  {session['agent']} · {project}  {note}"


def _session_detail(store, id):
    session, notes = store.get(id)
    locator = session["locator"]
    lines = [
        f"{session['agent']}  ·  {local_stamp(session['updated_at'])}",
        t("detail.tags", tags=" · ".join(session["tags"]) or t("detail.none")),
        "",
        t("detail.notes"),
    ]
    if notes:
        for note in reversed(notes):
            lines.extend([f"  {note['text']}", f"  {local_stamp(note['ts'])}", ""])
    else:
        lines.extend([t("detail.no_notes"), ""])
    lines.extend(
        [
            t("detail.source"),
            t("detail.cwd", cwd=session["cwd"]),
            t("detail.id", id=session["id"]),
            t(
                "detail.session",
                session=locator.get("session_id") or t("detail.pending_bind"),
            ),
            t(
                "detail.transcript",
                path=locator.get("transcript_path") or t("detail.missing_path"),
            ),
        ]
    )
    for name, prompt in session_prompts(store, session["tags"]):
        lines.extend(["", t("detail.pipeline", name=name), prompt])
    return "\n".join(lines)


def _delete_dialog_app(session, notes, *, input=None, output=None):
    from prompt_toolkit.application import get_app
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, VSplit
    from prompt_toolkit.widgets import Button, Label

    keys = KeyBindings()
    _tabs(keys)

    @keys.add("escape")
    @keys.add("c-c")
    def cancel(event=None):
        get_app().exit(result=False)

    cancel_button = Button(t("delete.cancel"), handler=cancel)
    delete_button = Button(
        t("delete.confirm"), handler=lambda: get_app().exit(result=True), width=16
    )
    detail = _detail_box()
    locator = session["locator"]
    detail.text = "\n".join(
        [
            f"{session['agent']}  ·  {local_stamp(session['updated_at'])}",
            f"ID       {session['id']}",
            f"Session  {locator.get('session_id') or t('detail.pending_bind')}",
            t("delete.cwd", cwd=session["cwd"]),
            "",
            t("detail.tags", tags=" · ".join(session["tags"]) or t("detail.none")),
            "",
            t("detail.notes"),
            *[f"  {note['text']}" for note in notes],
        ]
    )
    body = HSplit(
        [
            _title(t("delete.title")),
            Label(t("delete.body", tags=len(session["tags"]), notes=len(notes))),
            Label(t("delete.keep_files"), style="class:hint"),
            _panel(detail, t("delete.panel")),
            VSplit([cancel_button, delete_button], padding=1, height=1),
            _status(Label(t("delete.status"))),
        ]
    )
    return _application(body, keys, cancel_button, input, output)


def viewer(store, tags=(), on_open=None, *, input=None, output=None):
    require_ui()
    from prompt_toolkit.application import get_app
    from prompt_toolkit.filters import has_focus
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, VSplit
    from prompt_toolkit.widgets import Button, Label, RadioList, TextArea

    store.config.validate_tags(tags)
    search = TextArea(
        height=1, text=" ".join(f"tag:{tag}" for tag in tags), prompt=" / ", multiline=False
    )
    rows = _stretch(
        RadioList(
            values=[("", "")],
            select_on_focus=True,
            open_character="",
            select_character="›",
            close_character="",
        )
    )
    detail = _detail_box()
    count = Label("", style="class:hint")
    status = Label(t("viewer.status"))
    keys = KeyBindings()
    _search_keys(keys, search, rows)
    _tabs(keys)
    _detail_keys(keys, rows, detail)
    windows = [(t("viewer.all"), None), (t("viewer.today"), "today"), (t("viewer.week"), "7d")]
    period = 0
    agent = None
    agents = sorted({row["agent"] for row in store.list()})

    def show_detail():
        id = _selected(rows)
        detail.text = (
            _session_detail(store, id)
            if id
            else t("viewer.empty")
        )

    def refresh(event=None):
        since = since_time(windows[period][1]) if windows[period][1] else None
        sessions = store.list(since=since, query=search.text, agent=agent)
        _set_rows(rows, [(session["id"], _row_label(session)) for session in sessions])
        count.text = t(
            "viewer.count",
            n=len(sessions),
            window=windows[period][0],
            agent=agent or t("viewer.all_agents"),
        )
        show_detail()

    @keys.add("f2")
    def cycle_time(event=None):
        nonlocal period
        period = (period + 1) % len(windows)
        time_button.text = t("viewer.time_button", window=windows[period][0])
        refresh()

    @keys.add("f3")
    def cycle_agent(event=None):
        nonlocal agent
        choices = [None, *agents]
        agent = choices[(choices.index(agent) + 1) % len(choices)]
        agent_button.text = t("viewer.agent_button", agent=agent or t("viewer.all"))
        refresh()

    @keys.add("c-l", eager=True)
    def clear(event=None):
        nonlocal period, agent
        period, agent = 0, None
        time_button.text = t("viewer.time_button", window=t("viewer.all"))
        agent_button.text = t("viewer.agent_button", agent=t("viewer.all"))
        search.text = ""
        refresh()

    @keys.add("r", eager=True, filter=has_focus(rows))
    @keys.add("c-r")
    def reload(event=None):
        agents[:] = sorted({row["agent"] for row in store.list()})
        if agent and agent not in agents:
            agents.append(agent)
        refresh()
        status.text = t("viewer.reloaded")

    @keys.add("enter", eager=True, filter=has_focus(rows))
    def open_selected(event=None):
        if id := _selected(rows):
            get_app().exit(result=id)

    @keys.add("e", eager=True, filter=has_focus(rows))
    async def edit_vocab(event=None):
        await _run_dialog(_config_dialog_app(store.config, input=input, output=output))
        refresh()

    @keys.add("d", eager=True, filter=has_focus(rows))
    async def delete_selected(event=None):
        id = _selected(rows)
        if not id:
            return
        try:
            session, notes = store.get(id)
            confirmed = await _run_dialog(
                _delete_dialog_app(session, notes, input=input, output=output)
            )
            if confirmed:
                index = rows._selected_index
                store.delete(id, expected_updated_at=session["updated_at"])
                refresh()
                rows._selected_index = min(index, len(rows.values) - 1)
                rows.current_value = _selected(rows)
                show_detail()
                status.text = t("viewer.deleted")
            get_app().layout.focus(rows)
        except (SessmarkError, sqlite3.Error, OSError) as exc:
            status.text = str(exc)

    @keys.add("y", eager=True, filter=~has_focus(search))
    def copy(event=None):
        if id := _selected(rows):
            try:
                copy_command(session_card(store, id))
                status.text = t("viewer.copied")
            except (OSError, subprocess.SubprocessError) as exc:
                status.text = t("viewer.clipboard_error", exc=exc)

    @keys.add("q", eager=True, filter=~has_focus(search))
    @keys.add("c-c")
    def close(event=None):
        get_app().exit()

    @keys.add("escape")
    def back(event):
        if event.app.layout.has_focus(rows):
            close()
        else:
            event.app.layout.focus(rows)

    time_button = Button(
        t("viewer.time_button", window=t("viewer.all")), handler=cycle_time, width=18
    )
    agent_button = Button(
        t("viewer.agent_button", agent=t("viewer.all")), handler=cycle_agent, width=20
    )
    filters = VSplit(
        [
            time_button,
            agent_button,
            Button(t("viewer.clear"), handler=clear, width=10),
            Button(t("viewer.refresh"), handler=reload, width=10),
        ],
        padding=1,
        height=1,
    )
    actions = VSplit(
        [
            Button(t("viewer.open"), handler=open_selected, width=10),
            Button(t("viewer.copy"), handler=copy, width=12),
            Button(
                t("viewer.vocab"),
                handler=lambda: get_app().create_background_task(edit_vocab()),
                width=12,
            ),
            Button(
                t("viewer.delete"),
                handler=lambda: get_app().create_background_task(delete_selected()),
                width=12,
            ),
            Button(t("viewer.close"), handler=close, width=10),
        ],
        padding=1,
        height=1,
    )
    body = HSplit(
        [
            _title(t("viewer.title")),
            _panel(search, t("viewer.search")),
            filters,
            count,
            _columns(
                _panel(rows, t("viewer.panel_list")), _panel(detail, t("viewer.panel_detail"))
            ),
            actions,
            _status(status),
        ]
    )
    search.buffer.on_text_changed += lambda _: refresh()
    refresh()
    app = _application(body, keys, rows, input, output)

    def update_detail(_):
        id = _selected(rows)
        if id != getattr(update_detail, "last", None):
            update_detail.last = id
            show_detail()

    app.before_render += update_detail
    id = app.run()
    if id:
        return on_open(id) if on_open else execute(plan(store.get(id)[0]))
