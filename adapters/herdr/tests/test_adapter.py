import json
import os
import subprocess
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
from sessmark_herdr.adapter import Herdr

from sessmark import SessmarkError, Store


def pane(tmp_path, native="a"):
    result = {
        "pane_id": "w1:p1",
        "terminal_id": "terminal-uuid",
        "workspace_id": "w1",
        "tab_id": "w1:t1",
        "agent": "grok",
        "cwd": str(tmp_path),
    }
    if native:
        result["agent_session"] = {
            "source": "herdr:grok",
            "agent": "grok",
            "kind": "id",
            "value": native,
        }
    return result


def host_for(p, env=None):
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        data = {"type": "pane_info", "pane": p}
        if argv[1:3] == ["pane", "list"]:
            data = {"type": "pane_list", "panes": [p]}
        return SimpleNamespace(
            returncode=0, stdout=json.dumps({"id": "cli", "result": data}), stderr=""
        )

    env = {
        "HERDR_BIN_PATH": str(Path(p["cwd"]) / "Herdr Space/herdr.exe"),
        "HERDR_SESSION": "test",
        **(env or {}),
    }
    return Herdr(env, runner), calls


def test_popup_context_wins_and_cli_does_not_pass_unsupported_json(tmp_path):
    host, calls = host_for(
        pane(tmp_path),
        {"HERDR_PANE_ID": "overlay", "HERDR_PLUGIN_CONTEXT_JSON": '{"focused_pane_id":"w1:p1"}'},
    )
    selected = host.current()
    assert selected["locator"].session_id == "a"
    assert calls[0][0][1:] == ["pane", "get", "w1:p1"]
    assert calls[0][1]["shell"] is False
    assert "--json" not in calls[0][0]


def test_current_without_environment_and_malformed_response(tmp_path):
    host, calls = host_for(pane(tmp_path))
    host.current()
    assert calls[0][0][1:] == ["pane", "current"]
    host.runner = lambda *a, **k: SimpleNamespace(returncode=0, stdout="not json", stderr="")
    with pytest.raises(SessmarkError, match="invalid JSON"):
        host.current()


@pytest.mark.parametrize("mode", ["mark", "ui", "config"])
def test_popup_uses_active_placement_and_only_pins_mark_target_in_env(tmp_path, mode):
    host, calls = host_for(pane(tmp_path))
    host.open_popup(mode)
    argv = calls[-1][0]
    assert argv[1:4] == ["plugin", "pane", "open"]
    assert argv[argv.index("--placement") + 1] == "popup"
    assert "--target-pane" not in argv
    assert argv[argv.index("--width") + 1] == ("132" if mode == "ui" else "120")
    assert argv[argv.index("--height") + 1] == ("36" if mode == "ui" else "32")
    if mode == "mark":
        assert calls[0][0][1:3] == ["pane", "current"]
        assert argv[argv.index("--env") + 1] == "SESSMARK_TARGET_PANE=w1:p1"
    else:
        assert len(calls) == 1
        assert "--env" not in argv


def test_popup_rejects_missing_agent_before_opening(tmp_path):
    p = pane(tmp_path, None)
    p.pop("agent")
    host, calls = host_for(p)
    with pytest.raises(SessmarkError, match="No detected agent"):
        host.open_popup("mark")
    assert len(calls) == 1


def test_guard_allows_pending_promotion_but_rejects_replacement(tmp_path):
    p = pane(tmp_path, None)
    host, _calls = host_for(p)
    selected = host.current()
    p.update(pane(tmp_path, "a"))
    promoted = host.guard(selected)
    assert promoted["locator"].session_id == "a"
    p["agent_session"]["value"] = "b"
    with pytest.raises(SessmarkError, match="changed"):
        host.guard(promoted)
    p["terminal_id"] = "replacement"
    with pytest.raises(SessmarkError, match="changed"):
        host.guard(selected)


def test_sync_only_marked_sessions_without_moving_annotation_time(tmp_path):
    p = pane(tmp_path, None)
    host, calls = host_for(p)
    with Store(tmp_path / "db") as store:
        assert host.sync(store) == []
        assert calls == []
        marked = store.mark(**host.current(), tags=["keep"])
        p.update(pane(tmp_path, "a"))
        assert host.sync(store) == [marked["id"]]
        row = store.get(marked["id"])[0]
        assert row["updated_at"] == marked["updated_at"]
        assert row["locator"]["session_id"] == "a"


def test_focus_only_same_live_native_and_resume_replacement_in_new_tab(tmp_path):
    p = pane(tmp_path)
    host, calls = host_for(p)
    with Store(tmp_path / "db") as store:
        row = store.mark(**host.current(), tags=["keep"])
        assert host.open_session(store, row["id"])["action"] == "focus"
        assert calls[-1][0][1:] == ["agent", "focus", "w1:p1"]
        p["agent_session"]["value"] = "other"
        assert host.open_session(store, row["id"])["action"] == "resume"
        assert "--placement" in calls[-1][0]
        assert "tab" in calls[-1][0]
        assert f"SESSMARK_RESUME_ID={row['id']}" in calls[-1][0]


def test_grok_locator_uses_reported_path_and_never_invents_slug(tmp_path):
    p = pane(tmp_path)
    path = tmp_path / ".grok/sessions/D--work-proj/a/chat_history.jsonl"
    p["agent_session"]["transcript_path"] = str(path)
    host, _ = host_for(p)
    loc = host.current()["locator"]
    assert loc.transcript_path == str(path)
    assert loc.resume_cmd == ("grok", "--resume", "a")
    del p["agent_session"]["transcript_path"]
    assert host.current()["locator"].transcript_path is None


def test_manifest_has_unique_platform_ids_and_no_unix_shell_on_windows():
    root = Path(__file__).resolve().parents[3]
    manifest = tomllib.loads((root / "plugins/herdr/herdr-plugin.toml").read_text("utf-8"))
    assert "windows" in manifest["platforms"]
    assert {hook["on"] for hook in manifest["events"]} == {
        "pane.agent_detected",
        "pane.agent_status_changed",
    }
    for section in ("panes", "actions"):
        ids = [item["id"] for item in manifest[section]]
        assert len(ids) == len(set(ids))
    for item in manifest["panes"] + manifest["actions"] + manifest["events"]:
        if "windows" in item["platforms"]:
            assert item["command"][0] == "powershell.exe"
            assert "HERDR_PLUGIN_ROOT" in item["command"][-1]


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell launcher")
def test_windows_launcher_accepts_herdr_extended_path(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[3]
    plugin = root / "plugins/herdr"
    manifest = tomllib.loads((plugin / "herdr-plugin.toml").read_text("utf-8"))
    command = next(hook["command"] for hook in manifest["events"] if "windows" in hook["platforms"])
    monkeypatch.setenv("HERDR_PLUGIN_ROOT", "\\\\?\\" + str(plugin))
    monkeypatch.setenv("HERDR_PLUGIN_EVENT_JSON", "{}")
    monkeypatch.setenv("SESSMARK_DB", str(tmp_path / "launcher.sqlite"))
    # In a wheel/CI installation the launcher falls back to the installed entrypoint.
    result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    assert not result.stderr
