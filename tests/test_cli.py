import json
import subprocess
import sys

import pytest

from sessmark import SessmarkError
from sessmark.config import Config, data_path


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
    assert len(Config(config).tags) == 11
    with pytest.raises(SessmarkError, match="Cannot read config"):
        Config(tmp_path / "missing.toml")


def test_export_today_and_soft_prompt_for_multiple_routes(tmp_path):
    tagged = cli(
        "tag",
        "review:problem",
        "harvest:doc",
        "--harness",
        "grok",
        "--session-id",
        "native-export",
        "--json",
    )
    assert tagged.returncode == 0, tagged.stderr
    result = cli("export", "--json")
    assert result.returncode == 0, result.stderr
    packages = json.loads(result.stdout)
    assert len(packages) == 1
    assert packages[0]["schema"] == "sessmark.context.v1"
    assert packages[0]["prompt"] is None
    human = cli("export")
    assert human.returncode == 0, human.stderr
    assert packages[0]["session"]["id"] in human.stdout
    assert "python.exe" not in human.stdout


@pytest.mark.parametrize(
    "tags,expected",
    [
        (["review:problem"], "review-problem"),
        (["keep", "review:problem"], "review-problem"),
        (["keep"], None),
        (["review:problem", "harvest:doc"], None),
    ],
)
def test_export_selects_prompts_from_filter_tags(tags, expected):
    tagged = cli(
        "tag",
        "review:problem",
        "harvest:doc",
        "keep",
        "--harness",
        "grok",
        "--session-id",
        "selected-export",
        "--json",
    )
    assert tagged.returncode == 0, tagged.stderr
    filters = [part for tag in tags for part in ("--tag", tag)]
    for format in ("--json", "--jsonl"):
        result = cli("export", *filters, format)
        assert result.returncode == 0, result.stderr
        package = json.loads(result.stdout)
        if format == "--json":
            package = package[0]
        assert package["session"]["tags"] == ["harvest:doc", "keep", "review:problem"]
        prompt = package["prompt"]
        assert (prompt["template_id"] if prompt else None) == expected
    human = cli("export", *filters)
    assert human.returncode == 0, human.stderr
    assert ("prompt · review-problem" in human.stdout) == ("review:problem" in tags)
    assert ("prompt · harvest-doc" in human.stdout) == ("harvest:doc" in tags)


def test_untag_removed_vocabulary_entry(tmp_path):
    cfg = Config()
    cfg.ensure_user_file()
    tagged = cli("tag", "keep", "--harness", "grok", "--session-id", "historical", "--json")
    assert tagged.returncode == 0, tagged.stderr
    id = json.loads(tagged.stdout)["id"]
    cfg.remove_tag("keep")
    assert cli("tag", "keep", "--id", id).returncode == 2
    assert cli("untag", "typo", "--id", id).returncode == 2
    result = cli("untag", "keep", "--id", id, "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["tags"] == []


def test_delete_requires_confirmation_and_removes_one_mark():
    result = cli("tag", "keep", "--harness", "grok", "--session-id", "delete-cli", "--json")
    assert result.returncode == 0, result.stderr
    id = json.loads(result.stdout)["id"]
    refused = cli("delete", id, "--json")
    assert refused.returncode == 2 and refused.stdout == ""
    assert cli("context", id, "--json").returncode == 0
    deleted = cli("delete", id, "--yes", "--json")
    assert deleted.returncode == 0, deleted.stderr
    assert json.loads(deleted.stdout) == {"deleted": id}
    assert json.loads(cli("export", "--all", "--json").stdout) == []
    assert cli("delete", id, "--yes").returncode == 2


def test_config_add_tag_keep_and_pipeline(tmp_path):
    config = tmp_path / "templates.toml"
    keep = cli("config", "--config", config, "--add-tag", "later")
    assert keep.returncode == 0, keep.stderr
    body = json.loads(keep.stdout)
    assert "later" in body["allowed_tags"]
    assert "later" not in body["routes"]
    pipeline = cli(
        "config",
        "--config",
        config,
        "--add-tag",
        "review:ux",
        "--route",
        "review-ux",
        "--text",
        "审这次交互问题",
    )
    assert pipeline.returncode == 0, pipeline.stderr
    cfg = Config(config)
    assert "review:ux" in cfg.tags
    assert cfg.routes["review:ux"] == "review-ux"
    assert cfg.templates["review-ux"]["text"] == "审这次交互问题"
    duplicate = cli("config", "--config", config, "--add-tag", "later")
    assert duplicate.returncode == 2 and duplicate.stdout == ""


def test_store_python_localcache_migrates_to_real_appdata(tmp_path, monkeypatch):
    home = tmp_path / "user"
    cache = (
        home / "AppData/Local/Packages/PythonSoftwareFoundation.Python.3.12_abc/LocalCache/Local"
    )
    real = home / "AppData/Local"
    (cache / "sessmark").mkdir(parents=True)
    real.mkdir(parents=True, exist_ok=True)
    (cache / "sessmark/index.sqlite").write_bytes(b"sidecar")
    monkeypatch.delenv("SESSMARK_DB", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(cache))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr("sessmark.config.sys.platform", "win32")
    path = data_path()
    assert path == real / "sessmark/index.sqlite"
    assert path.read_bytes() == b"sidecar"


def test_core_import_never_loads_adapter_or_ui():
    script = "import sessmark.cli, sys; assert 'sessmark_herdr' not in sys.modules; assert 'prompt_toolkit' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
