from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput

from sessmark import Locator, Store
from sessmark.ui import mark_dialog, viewer


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
