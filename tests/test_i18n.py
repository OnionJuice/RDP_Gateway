from rdp_gateway.config_file import merge_defaults
from rdp_gateway.gui import LANG_EN, LANG_ZH, TEXT, resolve_language


def test_default_config_language_is_auto():
    config = merge_defaults({})

    assert config["app"]["language"] == "auto"
    assert config["app"]["keep_in_menu_bar"] is False


def test_resolve_language_accepts_explicit_values():
    assert resolve_language(LANG_EN) == LANG_EN
    assert resolve_language(LANG_ZH) == LANG_ZH
    assert resolve_language("auto") in {LANG_EN, LANG_ZH}
    assert resolve_language(None) in {LANG_EN, LANG_ZH}


def test_gui_translations_cover_same_keys():
    assert set(TEXT[LANG_EN]) == set(TEXT[LANG_ZH])
