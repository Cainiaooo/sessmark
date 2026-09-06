import json
import subprocess
import sys

import pytest

from sessmark import SessmarkError
from sessmark.config import Config


def cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "sessmark", *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_standalone_lifecycle_utf8_and_formats(tmp_path):
    result = cli("tag", "review:problem", "--harness", "grok", "--session-id", "native-a", "--json")
    assert result.returncode == 0, result.stderr
    row = json.loads(result.stdout)
    id = row["id"]
    assert cli("note", "工具超时后死循环", "--id", id).returncode == 0
    result = cli("list", "--tag", "review:problem", "--since", "today", "--json")
    rows = json.loads(result.stdout)
    assert len(rows) == 1 and rows[0]["notes_preview"] == "工具超时后死循环"
    assert json.loads(cli("list", "--jsonl").stdout)["id"] == id
    context = json.loads(cli("context", id, "--json").stdout)
    assert context["prompt"]["template_id"] == "review-problem"
    resume = json.loads(cli("resume", id, "--dry-run").stdout)
    assert resume["argv"] == ["grok", "--resume", "native-a"]
    assert cli("untag", "review:problem", "--id", id).returncode == 0
    assert json.loads(cli("list", "--tag", "review:problem", "--json").stdout) == []


def test_failure_stdout_is_empty_and_target_is_never_guessed(monkeypatch):
    monkeypatch.setenv("HERDR_PANE_ID", "not-a-session")
    result = cli("tag", "keep")
    assert result.returncode == 2 and result.stdout == ""
    result = cli("tag", "unknown", "--harness", "grok", "--session-id", "a", "--json")
    assert result.returncode == 2 and result.stdout == ""
    assert json.loads(cli("list", "--json").stdout) == []


def test_environment_and_explicit_override(monkeypatch):
    monkeypatch.setenv("SESSMARK_HARNESS", "grok")
    monkeypatch.setenv("SESSMARK_SESSION_ID", "a")
    a = cli("tag", "keep").stdout.strip()
    monkeypatch.setenv("SESSMARK_ID", a)
    result = cli("note", "second native", "--harness", "grok", "--session-id", "b")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() != a


def test_config_init_no_overwrite_and_custom_routes(tmp_path):
    config = tmp_path / "templates.toml"
    missing = cli("config", "--config", config)
    assert missing.returncode == 2 and missing.stdout == ""
    assert cli("config", "--init", "--config", config).returncode == 0
    assert cli("config", "--init", "--config", config).returncode == 2
    assert len(Config(config).tags) == 6
    with pytest.raises(SessmarkError, match="Cannot read config"):
        Config(tmp_path / "missing.toml")


def test_core_import_never_loads_adapter_or_ui():
    script = "import sessmark.cli, sys; assert 'sessmark_herdr' not in sys.modules; assert 'prompt_toolkit' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
