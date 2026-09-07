"""Optional terminal UI. Host behavior is supplied as callbacks."""

import os
import shlex
import sqlite3
import subprocess
import sys
from datetime import datetime

from .config import default_route
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
    return f"{tag}   {'→ 流水线' if tag in config.routes else '· 仅检索'}"


def _tag_detail(config, tag):
    if not tag:
        return "没有匹配的标签。\n\n换个关键词，或按 Ctrl+L 清空搜索。"
    route = config.routes.get(tag)
    if not route:
        return f"{tag}\n\n仅检索\n\n用于收藏和查找，不触发流水线。"
    return f"{tag}\n流水线 · {route}\n\n{config.templates[route]['text']}"


def _tag_matches(config, tag, query):
    route = config.routes.get(tag, "")
    body = config.templates.get(route, {}).get("text", "")
    text = f"{tag} {route} {body}".casefold()
    return all(word in text for word in query.casefold().split())


def _selected(rows):
    return rows.values[rows._selected_index][0]


def _set_rows(rows, values, select=None):
    chosen = select or _selected(rows)
    rows.values = values or [("", "没有匹配结果 · Ctrl+L 清空")]
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
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
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
    status = Label("Enter / Ctrl+S 保存 · Alt+Enter 换行 · Tab 切换 · Esc 取消")
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

    title = "sessmark  ·  新标签" if creating else f"sessmark  ·  编辑  {tag}"
    body = HSplit(
        [
            _title(title),
            Label("  留空 Prompt = 仅用于检索；填写 Prompt = 进入对应流水线。", style="class:hint"),
            _panel(name, "标签名 · 例如 review:ux / keep / harvest:wiki"),
            _panel(prompt, "流水线 Prompt · 支持多行"),
            VSplit(
                [
                    Button("保存 Enter", handler=commit, width=16),
                    Button("取消 Esc", handler=cancel),
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
    status = Label("Enter 编辑 · / 搜索 · F4 详情 · d 删除 · Esc 返回")
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
        count.text = f"  {len(values)} / {len(config.tags)} 个标签 · 搜索标签名、流水线或 Prompt"
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
                status.text = f"已删除 {tag} · 历史标注仍保留"
            except (SessmarkError, OSError) as exc:
                status.text = str(exc)

    @keys.add("o", eager=True, filter=has_focus(rows))
    def open_file(event=None):
        try:
            config.ensure_user_file()
            open_config_file(config.path)
            status.text = "已打开配置文件 · 保存后按 r 重新加载"
        except (SessmarkError, OSError) as exc:
            status.text = str(exc)

    @keys.add("r", eager=True, filter=has_focus(rows))
    def reload(event=None):
        try:
            config.reload()
            refresh()
            status.text = "已重新加载配置"
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
            Button("新增 n", handler=lambda: get_app().create_background_task(add())),
            Button(
                "编辑 Enter", handler=lambda: get_app().create_background_task(edit()), width=16
            ),
            Button("打开文件 o", handler=open_file, width=16),
            Button("返回 Esc", handler=close),
        ],
        padding=1,
        height=1,
    )
    body = HSplit(
        [
            _title("sessmark  /  标签与流水线"),
            _panel(search, "搜索 · Ctrl+L 清空"),
            count,
            _columns(_panel(rows, "标签"), _panel(detail, "用途 / 完整 Prompt")),
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
    identity = getattr(locator, "session_id", None) or "等待 Session ID"
    search = TextArea(height=1, prompt=" / ", multiline=False)
    chips = _stretch(CheckboxList(values=[("", "")]))
    # The empty-results row is a placeholder, never a real tag (including mouse clicks).
    toggle = chips._handle_enter
    chips._handle_enter = lambda: toggle() if _selected(chips) else None
    detail = _detail_box()
    note = TextArea(height=1, prompt="  ", multiline=False)
    selected_label = Label("", style="class:accent", wrap_lines=False)
    count = Label("", style="class:hint")
    status = Label("Space 选 · Tab 备注 · Enter 保存 · F4 详情 · Esc 取消")
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
        count.text = (
            f"  {len(values)} / {len(store.config.tags)} 个标签 · F4 查看详情 · 筛选保留勾选"
        )

    @keys.add("n", eager=True, filter=has_focus(chips))
    async def add_tag(event=None):
        created = await _run_dialog(_tag_editor_app(store.config, input=input, output=output))
        if created:
            search.text = ""
            refresh_chips(created)
            status.text = f"已勾选 {created} · 可继续添加标签或填写备注"

    @keys.add("e", eager=True, filter=has_focus(chips))
    async def edit_vocab(event=None):
        await _run_dialog(_config_dialog_app(store.config, input=input, output=output))
        refresh_chips()

    def save():
        text = note.text.strip()
        if not chips.current_values and not text:
            status.text = "请先勾选标签或填写备注 · / 搜索标签，Tab 填备注"
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

    save_button = Button("保存 Enter", handler=save, width=16)
    cancel_button = Button("取消 Esc", handler=cancel)
    actions = VSplit(
        [
            save_button,
            Button("新增 n", handler=lambda: get_app().create_background_task(add_tag())),
            Button("词表 e", handler=lambda: get_app().create_background_task(edit_vocab())),
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
            _title("sessmark  /  标记当前 Session"),
            Label(
                f"  {getattr(locator, 'harness', '')}  ·  {identity}",
                style="class:hint",
                wrap_lines=False,
            ),
            _panel(search, "搜索标签 / Prompt · Ctrl+L 清空"),
            count,
            _columns(_panel(chips, "标签 · Space 多选"), _panel(detail, "用途 / 完整 Prompt")),
            selected_label,
            _panel(note, "备注 · 写下以后回看时最需要知道的事"),
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
        suffix = f" · {hidden} 项在筛选结果外" if hidden else ""
        selected_label.text = f"  已选 {len(picked)}{suffix}  " + (" · ".join(picked) or "尚未勾选")

    app.before_render += update_detail
    return app.run()


def _row_label(session):
    project = session["cwd"].replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    note = session["notes_preview"] or "（仅标签，无备注）"
    return f"{local_stamp(session['updated_at'])}  {session['agent']} · {project}  {note}"


def _session_detail(store, id):
    session, notes = store.get(id)
    locator = session["locator"]
    lines = [
        f"{session['agent']}  ·  {local_stamp(session['updated_at'])}",
        "标签  " + (" · ".join(session["tags"]) or "无"),
        "",
        "备注",
    ]
    if notes:
        for note in reversed(notes):
            lines.extend([f"  {note['text']}", f"  {local_stamp(note['ts'])}", ""])
    else:
        lines.extend(["  暂无备注", ""])
    lines.extend(
        [
            "来源",
            f"  目录  {session['cwd']}",
            f"  ID    {session['id']}",
            f"  Session  {locator.get('session_id') or '等待绑定'}",
            f"  Transcript  {locator.get('transcript_path') or '未提供'}",
        ]
    )
    for name, prompt in session_prompts(store, session["tags"]):
        lines.extend(["", f"流水线 · {name}", prompt])
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

    cancel_button = Button("取消", handler=cancel)
    delete_button = Button("删除标注", handler=lambda: get_app().exit(result=True), width=16)
    detail = _detail_box()
    locator = session["locator"]
    detail.text = "\n".join(
        [
            f"{session['agent']}  ·  {local_stamp(session['updated_at'])}",
            f"ID       {session['id']}",
            f"Session  {locator.get('session_id') or '等待绑定'}",
            f"目录     {session['cwd']}",
            "",
            "标签  " + (" · ".join(session["tags"]) or "无"),
            "",
            "备注",
            *[f"  {note['text']}" for note in notes],
        ]
    )
    body = HSplit(
        [
            _title("sessmark  /  删除这条 Session 的标注？"),
            Label(f"  将删除 {len(session['tags'])} 个标签、{len(notes)} 条备注。此操作不可撤销。"),
            Label("  原始 Session / transcript 文件保留。", style="class:hint"),
            _panel(detail, "确认删除对象"),
            VSplit([cancel_button, delete_button], padding=1, height=1),
            _status(Label("Tab 切换 · Enter 确认所选按钮 · Esc 取消")),
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
    status = Label("Enter 打开 · F4 详情 · / 搜索 · d 删除 · Esc 关闭")
    keys = KeyBindings()
    _search_keys(keys, search, rows)
    _tabs(keys)
    _detail_keys(keys, rows, detail)
    windows = [("全部", None), ("今天", "today"), ("近 7 天", "7d")]
    period = 0
    agent = None
    agents = sorted({row["agent"] for row in store.list()})

    def show_detail():
        id = _selected(rows)
        detail.text = (
            _session_detail(store, id)
            if id
            else (
                "没有匹配的 Session\n\n试试更短的关键词，或清空时间 / Agent 筛选。\n\n"
                "搜索会覆盖所有备注、标签、工作目录及 Session ID。\n"
                "例如：工具 超时   或   tag:review:problem"
            )
        )

    def refresh(event=None):
        since = since_time(windows[period][1]) if windows[period][1] else None
        sessions = store.list(since=since, query=search.text, agent=agent)
        _set_rows(rows, [(session["id"], _row_label(session)) for session in sessions])
        count.text = f"  {len(sessions)} 条结果 · {windows[period][0]} · {agent or '全部 Agent'} · 最新标注在前"
        show_detail()

    @keys.add("f2")
    def cycle_time(event=None):
        nonlocal period
        period = (period + 1) % len(windows)
        time_button.text = f"时间 {windows[period][0]} F2"
        refresh()

    @keys.add("f3")
    def cycle_agent(event=None):
        nonlocal agent
        choices = [None, *agents]
        agent = choices[(choices.index(agent) + 1) % len(choices)]
        agent_button.text = f"Agent {agent or '全部'} F3"
        refresh()

    @keys.add("c-l", eager=True)
    def clear(event=None):
        nonlocal period, agent
        period, agent = 0, None
        time_button.text, agent_button.text = "时间 全部 F2", "Agent 全部 F3"
        search.text = ""
        refresh()

    @keys.add("r", eager=True, filter=has_focus(rows))
    @keys.add("c-r")
    def reload(event=None):
        agents[:] = sorted({row["agent"] for row in store.list()})
        if agent and agent not in agents:
            agents.append(agent)
        refresh()
        status.text = "已刷新标注 · / 搜索 · Enter 打开 · y 复制摘要"

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
                status.text = "已删除该 Session 的标注 · 原始对话文件保留"
            get_app().layout.focus(rows)
        except (SessmarkError, sqlite3.Error, OSError) as exc:
            status.text = str(exc)

    @keys.add("y", eager=True, filter=~has_focus(search))
    def copy(event=None):
        if id := _selected(rows):
            try:
                copy_command(session_card(store, id))
                status.text = "已复制摘要：标签、备注、来源和流水线 Prompt"
            except (OSError, subprocess.SubprocessError) as exc:
                status.text = f"无法写入剪贴板: {exc}"

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

    time_button = Button("时间 全部 F2", handler=cycle_time, width=18)
    agent_button = Button("Agent 全部 F3", handler=cycle_agent, width=20)
    filters = VSplit(
        [
            time_button,
            agent_button,
            Button("清空", handler=clear, width=10),
            Button("刷新", handler=reload, width=10),
        ],
        padding=1,
        height=1,
    )
    actions = VSplit(
        [
            Button("打开", handler=open_selected, width=10),
            Button("复制 y", handler=copy, width=12),
            Button(
                "词表 e", handler=lambda: get_app().create_background_task(edit_vocab()), width=12
            ),
            Button(
                "删除 d",
                handler=lambda: get_app().create_background_task(delete_selected()),
                width=12,
            ),
            Button("关闭", handler=close, width=10),
        ],
        padding=1,
        height=1,
    )
    body = HSplit(
        [
            _title("sessmark  /  已标记的 Session"),
            _panel(search, "搜索备注 / 标签 / 路径 / ID · tag:keep 精确筛选"),
            filters,
            count,
            _columns(_panel(rows, "Session"), _panel(detail, "备注 / 来源 / 流水线")),
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
