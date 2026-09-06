import json
import sys

import pytest

from sessmark import Locator, SessmarkError, Store
from sessmark.resume import execute, plan


@pytest.mark.parametrize(
    "harness, argv",
    [
        ("grok", ["grok", "--resume", "abc"]),
        ("claude", ["claude", "--resume", "abc"]),
        ("codex", ["codex", "resume", "abc"]),
        ("opencode", ["opencode", "--session", "abc"]),
        ("pi", ["pi", "--session", "abc"]),
    ],
)
def test_native_plans(tmp_path, harness, argv):
    with Store(tmp_path / "db") as store:
        row = store.mark(locator=Locator(harness, "abc"), cwd=str(tmp_path), tags=["keep"])
        assert plan(row)["argv"] == argv


def test_explicit_command_is_literal_argv_and_keeps_cwd(tmp_path, capfd):
    payload = 'space 中文 & echo injected; $(whoami) `name` "quote"'
    command = (
        sys.executable,
        "-c",
        "import os,sys,json;print(json.dumps([os.getcwd(), sys.argv[1]]))",
        payload,
    )
    with Store(tmp_path / "db") as store:
        row = store.mark(
            locator=Locator("grok", "abc", resume_cmd=command), cwd=str(tmp_path), tags=["keep"]
        )
        assert plan(row)["argv"] == list(command)
        assert execute(plan(row)) == 0
    cwd, received = json.loads(capfd.readouterr().out)
    assert cwd == str(tmp_path) and received == payload


def test_option_like_native_id_rejected():
    with pytest.raises(SessmarkError, match="cannot start"):
        Locator("codex", "--last")


def test_missing_resume_is_explicit_error(tmp_path):
    with Store(tmp_path / "db") as store:
        row = store.mark(locator=Locator("custom", "abc"), cwd=str(tmp_path), tags=["keep"])
        with pytest.raises(SessmarkError, match="No resume"):
            plan(row)
