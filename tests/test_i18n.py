from sessmark.config import Config
from sessmark.i18n import EN, ZH, language, packaged_defaults, t


def test_catalogs_have_the_same_keys():
    assert set(EN) == set(ZH)


def test_language_env_selects_ui_and_packaged_defaults(monkeypatch):
    monkeypatch.setenv("SESSMARK_LANG", "en")
    assert language() == "en"
    assert packaged_defaults() == "defaults.en.toml"
    assert t("mark.title") == "sessmark  /  Mark this session"
    monkeypatch.setenv("SESSMARK_LANG", "zh-CN")
    assert language() == "zh"
    assert packaged_defaults() == "defaults.toml"
    assert t("mark.title") == "sessmark  /  标记当前 Session"


def test_packaged_defaults_follow_language(monkeypatch):
    monkeypatch.setenv("SESSMARK_LANG", "en")
    english = Config().templates["review-problem"]["text"]
    assert english.startswith("You are doing a deferred problem review")
    monkeypatch.setenv("SESSMARK_LANG", "zh")
    chinese = Config().templates["review-problem"]["text"]
    assert "延后问题复盘" in chinese
    assert english != chinese


def test_c_locale_falls_through_to_system(monkeypatch):
    monkeypatch.delenv("SESSMARK_LANG", raising=False)
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    monkeypatch.setenv("LC_MESSAGES", "C")
    monkeypatch.setenv("LANG", "C.UTF-8")
    assert language() in {"en", "zh"}
