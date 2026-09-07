import pytest


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch, tmp_path):
    for name in ("SESSMARK_CONFIG", "SESSMARK_ID", "SESSMARK_HARNESS", "SESSMARK_SESSION_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SESSMARK_LANG", "zh")
    monkeypatch.setenv("SESSMARK_DB", str(tmp_path / "index.sqlite"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
