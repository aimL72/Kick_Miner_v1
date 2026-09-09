from kickminer import i18n


def test_default_is_english():
    i18n.load_language("en")
    assert i18n.current_language() == "en"
    assert i18n.t("yes") == "yes"


def test_german_alternative():
    active = i18n.load_language("de")
    assert active == "de"
    assert i18n.t("yes") == "ja"


def test_unknown_language_falls_back_to_english():
    active = i18n.load_language("xx")
    assert active == "en"


def test_placeholder_substitution():
    i18n.load_language("en")
    out = i18n.t("app_restarting", seconds=5, reason="test")
    assert "5" in out and "test" in out


def test_missing_key_returns_key():
    i18n.load_language("en")
    assert i18n.t("this_key_does_not_exist") == "this_key_does_not_exist"


def test_available_languages():
    langs = i18n.available_languages()
    assert "en" in langs and "de" in langs
