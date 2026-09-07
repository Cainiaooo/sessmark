import asyncio
import json
import os
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import pytest
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput

from sessmark import Locator, Store
from sessmark.config import Config
from sessmark.ui import (
    config_dialog,
    context_command,
    format_card,
    mark_dialog,
    open_config_file,
    session_card,
    tag_editor,
    viewer,
)


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
def test_open_config_uses_physical_path_for_external_editor(tmp_path, monkeypatch, platform):
    logical = tmp_path / "Roaming" / "sessmark" / "templates.toml"
    physical = tmp_path / "LocalCache" / "词表 with space.toml"
    physical.parent.mkdir()
    physical.write_text("schema = 1\n", encoding="utf-8")
    original_resolve = Path.resolve

    def resolve(path, strict=False):
        if path == logical:
            assert strict
            return physical
        return original_resolve(path, strict=strict)

    opened = []
    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setattr("sessmark.ui.sys.platform", platform)
    monkeypatch.setattr("sessmark.ui.os.startfile", opened.append, raising=False)
    monkeypatch.setattr("sessmark.ui.subprocess.Popen", opened.append)
    open_config_file(logical)
    expected = physical if platform == "win32" else [
        "open" if platform == "darwin" else "xdg-open", str(physical)
    ]
    assert opened == [expected]
    assert not logical.parent.exists(), "Opening a file must not create a second config tree"


def test_open_config_missing_path_does_not_launch_or_create_directory(tmp_path, monkeypatch):
    from sessmark import SessmarkError

    missing = tmp_path / "missing" / "templates.toml"
    opened = []
    monkeypatch.setattr("sessmark.ui.os.startfile", opened.append, raising=False)
    monkeypatch.setattr("sessmark.ui.subprocess.Popen", opened.append)
    with pytest.raises(SessmarkError, match="Config file is missing"):
        open_config_file(missing)
    assert opened == []
    assert not missing.parent.exists()


@pytest.mark.parametrize(
    "screen,scripts",
    [
        ("mark", [("n", ""), ("review:ux\tnew prompt\r", "\tnote\r")]),
        ("mark", [("e", ""), ("n", " \tnote\r"), ("review:ux\tnew prompt\r", "q")]),
        ("config", [("n", ""), ("review:ux\tnew prompt\r", "q")]),
        ("config", [("\r", ""), ("\x01\x0bnew prompt\r", "q")]),
        ("viewer", [("e", ""), ("\r", "yq"), ("\x01\x0bnew prompt\r", "q")]),
        ("mark", [("n", ""), ("\x03", " \tnote\r")]),
    ],
)
def test_nested_dialogs_return_to_parent(tmp_path, monkeypatch, screen, scripts):
    from sessmark import ui

    cfg = Config()
    cfg.ensure_user_file()
    copied = []
    monkeypatch.setattr(ui, "copy_command", copied.append)
    original_application = ui._application
    created = []

    with Store(tmp_path / "db", cfg) as store, create_pipe_input() as pipe:

        def application(*args, **kwargs):
            app = original_application(*args, **kwargs)
            initial, after = scripts[len(created)]
            created.append(app)
            original_run = app.run_async

            async def run_script(*args, **kwargs):
                kwargs["pre_run"] = lambda: pipe.send_text(initial)
                result = await asyncio.wait_for(original_run(*args, **kwargs), timeout=5)
                if after:
                    asyncio.get_running_loop().call_soon(pipe.send_text, after)
                return result

            def fail_fast(loop, context):
                app.exit(exception=context["exception"])

            app.run_async = run_script
            app._handle_exception = fail_fast
            return app

        monkeypatch.setattr(ui, "_application", application)
        if screen == "mark":
            row = mark_dialog(
                store,
                {"locator": Locator("grok", "nested"), "cwd": str(tmp_path)},
                input=pipe,
                output=DummyOutput(),
            )
            assert store.get(row["id"])[1][0]["text"] == "note"
            if scripts[0][0] == "n" and scripts[1][0] != "\x03":
                assert row["tags"] == ["review:ux"]
        elif screen == "config":
            config_dialog(cfg, input=pipe, output=DummyOutput())
        else:
            store.mark(
                locator=Locator("grok", "nested"), cwd=str(tmp_path), tags=["review:problem"]
            )
            viewer(store, input=pipe, output=DummyOutput())
            assert "new prompt" in copied[0]

    assert len(created) == len(scripts)
    reloaded = Config(cfg.path)
    if any("review:ux" in initial for initial, _ in scripts):
        assert reloaded.prompt(["review:ux"])["text"] == "new prompt"
    elif screen in ("config", "viewer"):
        assert reloaded.prompt(["review:problem"])["text"] == "new prompt"
    else:
        assert "review:ux" not in reloaded.tags


def test_mark_dialog_keyboard_saves_tags_and_note(tmp_path):
    with Store(tmp_path / "db") as store, create_pipe_input() as pipe:
        pipe.send_text(" \t中文 note\r")
        row = mark_dialog(
            store,
            {"locator": Locator("grok", "a"), "cwd": str(tmp_path)},
            input=pipe,
            output=DummyOutput(),
        )
        assert row["tags"] == ["review:problem"]
        assert store.get(row["id"])[1][0]["text"] == "中文 note"


def test_mark_search_preserves_hidden_selections_and_note_shortcuts(tmp_path):
    with Store(tmp_path / "db") as store, create_pipe_input() as pipe:
        pipe.send_text(" /harvest:asset\r /\x0cfix:tool\r \tn/e note\r")
        row = mark_dialog(
            store,
            {"locator": Locator("grok", "filtered"), "cwd": str(tmp_path)},
            input=pipe,
            output=DummyOutput(),
        )
        assert row["tags"] == ["fix:tool", "harvest:asset", "review:problem"]
        assert store.get(row["id"])[1][0]["text"] == "n/e note"


def test_mark_empty_search_result_cannot_be_selected(tmp_path):
    with Store(tmp_path / "db") as store, create_pipe_input() as pipe:
        pipe.send_text("/no-such-tag\r \tonly note\r")
        row = mark_dialog(
            store,
            {"locator": Locator("grok", "empty"), "cwd": str(tmp_path)},
            input=pipe,
            output=DummyOutput(),
        )
        assert row["tags"] == []


def test_viewer_search_keeps_slashes_and_typing_shortcuts(tmp_path, monkeypatch):
    copied = []
    monkeypatch.setattr("sessmark.ui.copy_command", copied.append)
    with Store(tmp_path / "db") as store, create_pipe_input() as pipe:
        wanted = store.mark(
            locator=Locator("grok", "native"),
            cwd=str(tmp_path),
            note="older path/to/query",
            tags=["keep"],
        )
        store.mark(id=wanted["id"], note="latest")
        store.mark(locator=Locator("grok", "different"), cwd=str(tmp_path), note="unrelated")
        pipe.send_text("/path/to/query\ryq")
        viewer(store, input=pipe, output=DummyOutput())
        assert wanted["id"] in copied[0]


def test_viewer_time_agent_filters_and_clear(tmp_path, monkeypatch):
    copied = []
    monkeypatch.setattr("sessmark.ui.copy_command", copied.append)
    with Store(tmp_path / "db") as store, create_pipe_input() as pipe:
        old = store.mark(locator=Locator("codex", "old"), cwd=str(tmp_path), note="old")
        store.db.execute("UPDATE sessions SET updated_at='2000-01-01' WHERE id=?", (old["id"],))
        recent = store.mark(locator=Locator("grok", "new"), cwd=str(tmp_path), note="new")
        # Today, then codex (empty), then grok, then clear all filters.
        pipe.send_text("\x1bOQy\x1bORy\x1bORy\x0cyq")
        viewer(store, input=pipe, output=DummyOutput())
        assert len(copied) == 3
        assert all(recent["id"] in card for card in copied)


def test_tag_editor_accepts_multiline_prompt(tmp_path):
    cfg = Config()
    with create_pipe_input() as pipe:
        pipe.send_text("review:lines\tfirst\x1b\rsecond\r")
        tag_editor(cfg, input=pipe, output=DummyOutput())
    assert Config(cfg.path).prompt(["review:lines"])["text"] == "first\nsecond"


def test_tag_editor_cancel_button_does_not_save():
    cfg = Config()
    with create_pipe_input() as pipe:
        pipe.send_text("later\tnote\t\t\r")
        assert tag_editor(cfg, input=pipe, output=DummyOutput()) is None
    assert not cfg.path.exists()


@pytest.mark.parametrize("confirm_keys,deleted", [("\r", False), ("\x03", False), ("\t\r", True)])
def test_viewer_delete_confirmation_and_filtered_refresh(
    tmp_path, monkeypatch, confirm_keys, deleted
):
    from sessmark import ui

    original_application = ui._application
    created = []
    copied = []
    monkeypatch.setattr(ui, "copy_command", copied.append)
    with Store(tmp_path / "db") as store, create_pipe_input() as pipe:
        other = store.mark(locator=Locator("grok", "other"), cwd=str(tmp_path), note="unrelated")
        target = store.mark(locator=Locator("grok", "target"), cwd=str(tmp_path), note="needle")

        def application(*args, **kwargs):
            app = original_application(*args, **kwargs)
            is_child = bool(created)
            created.append(app)
            original_run = app.run_async

            async def run_script(*args, **kwargs):
                kwargs["pre_run"] = lambda: pipe.send_text(
                    confirm_keys if is_child else "/needle\rd"
                )
                result = await asyncio.wait_for(original_run(*args, **kwargs), timeout=5)
                if is_child:
                    asyncio.get_running_loop().call_soon(pipe.send_text, "yq")
                return result

            app.run_async = run_script
            app._handle_exception = lambda loop, context: app.exit(exception=context["exception"])
            return app

        monkeypatch.setattr(ui, "_application", application)
        viewer(store, input=pipe, output=DummyOutput())
        assert len(created) == 2
        assert store.get(other["id"])[1][0]["text"] == "unrelated"
        if deleted:
            assert store.list(query="needle") == []
            assert copied == []  # Keep the filter; do not select an unrelated remaining row.
        else:
            assert target["id"] in copied[0]
            assert len(store.list()) == 2


@pytest.mark.parametrize("size", [(120, 32), (132, 36), (80, 24), (64, 20)])
@pytest.mark.parametrize("screen", ["mark", "viewer", "config", "editor", "delete"])
@pytest.mark.parametrize("lang", ["zh", "en"])
def test_popup_layout_keeps_actions_visible(tmp_path, monkeypatch, size, screen, lang):
    from prompt_toolkit.data_structures import Size

    from sessmark import ui

    columns, height = size

    class Output(DummyOutput):
        def get_size(self):
            return Size(rows=height, columns=columns)

    captured = []
    original_application = ui._application

    def application(*args, **kwargs):
        app = original_application(*args, **kwargs)

        def rendered(_):
            if captured:
                return
            buffer = app.renderer.last_rendered_screen.data_buffer
            captured.extend(
                "".join(buffer[y][x].char for x in range(columns)) for y in range(height)
            )
            app.exit()

        app.after_render += rendered
        return app

    monkeypatch.setenv("SESSMARK_LANG", lang)
    monkeypatch.setattr(ui, "_application", application)
    with Store(tmp_path / "db") as store, create_pipe_input() as pipe:
        options = {"input": pipe, "output": Output()}
        if screen == "mark":
            mark_dialog(
                store, {"locator": Locator("codex", "preview"), "cwd": str(tmp_path)}, **options
            )
        elif screen == "viewer":
            store.mark(locator=Locator("codex", "preview"), cwd=str(tmp_path), note="needle")
            viewer(store, **options)
        elif screen == "config":
            config_dialog(store.config, **options)
        elif screen == "delete":
            row = store.mark(locator=Locator("codex", "preview"), cwd=str(tmp_path), note="needle")
            session, notes = store.get(row["id"])
            ui._delete_dialog_app(session, notes, **options).run()
        else:
            tag_editor(store.config, **options)
    screen_text = "\n".join(captured)
    titles = {
        "mark": {"zh": "标记当前 Session", "en": "Mark this session"},
        "viewer": {"zh": "已标记的 Session", "en": "Marked sessions"},
        "config": {"zh": "标签与流水线", "en": "Tags and pipelines"},
        "editor": {"zh": "新标签", "en": "New tag"},
        "delete": {"zh": "删除这条 Session 的标注", "en": "Delete marks for this session"},
    }
    assert "sessmark" in captured[0]
    assert titles[screen][lang] in screen_text
    assert "Esc" in captured[-1]
    assert "<" in captured[-2] and ">" in captured[-2], "action buttons must remain visible"
    assert "Window too small" not in screen_text


def test_cancel_does_not_register(tmp_path):
    with Store(tmp_path / "db") as store, create_pipe_input() as pipe:
        pipe.send_text("\x03")
        assert (
            mark_dialog(
                store,
                {"locator": Locator("grok", "a"), "cwd": str(tmp_path)},
                input=pipe,
                output=DummyOutput(),
            )
            is None
        )
        assert store.list() == []


def test_viewer_enter_opens_selected_session(tmp_path):
    with Store(tmp_path / "db") as store, create_pipe_input() as pipe:
        row = store.mark(locator=Locator("grok", "a"), cwd=str(tmp_path), tags=["keep"])
        seen = []
        pipe.send_text("\r")
        viewer(store, on_open=seen.append, input=pipe, output=DummyOutput())
        assert seen == [row["id"]]


def test_copied_command_runs_without_activation_or_path(tmp_path):
    config = tmp_path / "templates ' 中文.toml"
    config.write_text(
        files("sessmark").joinpath("defaults.toml").read_text("utf-8"), encoding="utf-8"
    )
    with Store(tmp_path / "marks ' 中文.sqlite", Config(config)) as store:
        row = store.mark(
            locator=Locator("grok", "copy-test"),
            cwd=str(tmp_path),
            tags=["review:problem"],
            note="复制后可以直接运行",
        )
        command = context_command(store, row["id"])
    env = dict(os.environ, PATH="")
    env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONPATH", None)
    if os.name == "nt":
        shell = str(
            Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        )
        argv = [
            shell,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + command,
        ]
    else:
        argv = [shutil.which("sh"), "-c", command]
    result = subprocess.run(
        argv, cwd=tmp_path, env=env, capture_output=True, encoding="utf-8", timeout=20, check=False
    )
    assert result.returncode == 0, result.stderr
    package = json.loads(result.stdout)
    assert package["session"]["id"] == row["id"]
    assert package["notes"][0]["text"] == "复制后可以直接运行"


def test_tag_editor_creates_pipeline_and_keep_tags(tmp_path):
    path = tmp_path / "templates.toml"
    path.write_text(
        files("sessmark").joinpath("defaults.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    cfg = Config(path)
    with create_pipe_input() as pipe:
        pipe.send_text("review:ux\t审这次交互\r")
        assert tag_editor(cfg, input=pipe, output=DummyOutput()) == "review:ux"
    assert cfg.routes["review:ux"] == "review-ux"
    assert cfg.templates["review-ux"]["text"] == "审这次交互"
    with create_pipe_input() as pipe:
        pipe.send_text("later\r")
        assert tag_editor(cfg, input=pipe, output=DummyOutput()) == "later"
    assert "later" in cfg.tags and "later" not in cfg.routes


def test_config_dialog_escape_closes(tmp_path):
    path = tmp_path / "templates.toml"
    path.write_text(
        files("sessmark").joinpath("defaults.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    cfg = Config(path)
    with create_pipe_input() as pipe:
        pipe.send_text("\x03")
        config_dialog(cfg, input=pipe, output=DummyOutput())
    assert "review:problem" in cfg.tags


def test_copied_command_preserves_venv_interpreter_path(tmp_path, monkeypatch):
    executable = str(tmp_path / "venv with space/bin/python")
    monkeypatch.setattr(sys, "executable", executable)
    with Store(tmp_path / "db") as store:
        command = context_command(store, "sm_test")
    assert executable in command


def test_session_card_is_human_readable(tmp_path):
    with Store(tmp_path / "db") as store:
        row = store.mark(
            locator=Locator("grok", "native-a"),
            cwd=str(tmp_path),
            tags=["review:problem"],
            note="工具超时后死循环",
        )
        card = session_card(store, row["id"])
    assert "python.exe" not in card
    assert "& " not in card
    assert row["id"] in card
    assert "review:problem" in card
    assert "工具超时后死循环" in card
    assert "grok --resume native-a" in card
    assert "prompt · review-problem" in card


def test_format_card_handles_pending_and_empty_notes():
    session = {
        "id": "sm_x",
        "agent": "grok",
        "tags": ["keep"],
        "updated_at": "2026-09-07T04:00:00+00:00",
        "cwd": "D:\\work",
        "locator": {"session_id": None, "transcript_path": None, "resume_cmd": []},
    }
    card = format_card(session, [])
    assert "(pending)" in card
    assert "(none)" in card


def test_viewer_y_copies_readable_card_not_a_shell_command(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr("sessmark.ui.copy_command", seen.append)
    with Store(tmp_path / "db") as store, create_pipe_input() as pipe:
        row = store.mark(
            locator=Locator("grok", "native-a"),
            cwd=str(tmp_path),
            tags=["review:problem"],
            note="给 Agent 看的是摘要",
        )
        pipe.send_text("yq")
        viewer(store, input=pipe, output=DummyOutput())
    assert seen, "expected y to copy the selected session"
    card = seen[0]
    assert row["id"] in card
    assert "给 Agent 看的是摘要" in card
    assert "python.exe" not in card
    assert "-m" not in card
