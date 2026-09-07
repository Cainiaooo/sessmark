from importlib.resources import files

import pytest

from sessmark import Locator, SessmarkError, Store
from sessmark.config import Config, default_route


def test_default_route_replaces_colon():
    assert default_route("review:ux") == "review-ux"
    assert default_route("keep") == "keep"


def test_set_prompt_and_remove_tag(tmp_path):
    path = tmp_path / "templates.toml"
    path.write_text(files("sessmark").joinpath("defaults.toml").read_text(encoding="utf-8"), encoding="utf-8")
    cfg = Config(path)
    cfg.add_tag("later")
    assert "later" not in cfg.routes
    cfg.set_prompt("later", "以后回看这条流水线")
    assert cfg.routes["later"] == "later"
    assert cfg.templates["later"]["text"] == "以后回看这条流水线"
    cfg.set_prompt("later", "")
    assert "later" not in cfg.routes
    assert "later" not in cfg.templates
    cfg.remove_tag("later")
    assert "later" not in cfg.tags
    reloaded = Config(path)
    assert "later" not in reloaded.tags
    assert "review:problem" in reloaded.tags


def test_prompt_ignores_unknown_session_tags(tmp_path):
    path = tmp_path / "templates.toml"
    path.write_text(files("sessmark").joinpath("defaults.toml").read_text(encoding="utf-8"), encoding="utf-8")
    cfg = Config(path)
    with Store(tmp_path / "db", cfg) as store:
        row = store.mark(
            locator=Locator("grok", "a"),
            cwd=str(tmp_path),
            tags=["keep"],
        )
    cfg.remove_tag("keep")
    with Store(tmp_path / "db", cfg) as store:
        package = store.context(row["id"])
    assert package["session"]["tags"] == ["keep"]
    assert package["prompt"] is None


@pytest.mark.parametrize("bad_config", ["schema = [", "schema = 2\nallowed_tags = ['keep']", None])
def test_reload_failure_preserves_config_and_can_retry(bad_config):
    cfg = Config()
    cfg.ensure_user_file()
    original = cfg.path.read_text("utf-8")
    original_data = cfg.data.copy()
    if bad_config is None:
        cfg.path.unlink()
    else:
        cfg.path.write_text(bad_config, encoding="utf-8")
    with pytest.raises(SessmarkError):
        cfg.reload()
    assert cfg.data == original_data
    cfg.path.write_text(original.replace('schema = 1', 'schema = 1\n# repaired'), encoding="utf-8")
    cfg.reload()
    assert cfg.data == original_data
