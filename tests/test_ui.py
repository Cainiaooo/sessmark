import json
import os
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput

from sessmark import Locator, Store
from sessmark.config import Config
from sessmark.ui import context_command, mark_dialog, viewer


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


def test_copied_command_preserves_venv_interpreter_path(tmp_path, monkeypatch):
    executable = str(tmp_path / "venv with space/bin/python")
    monkeypatch.setattr(sys, "executable", executable)
    with Store(tmp_path / "db") as store:
        command = context_command(store, "sm_test")
    assert executable in command
