from pathlib import Path

APP = Path(__file__).parents[1] / "frontend" / "app.js"


def test_frontend_escape_helper_encodes_markup_characters():
    source = APP.read_text(encoding="utf-8")
    assert "escapeHtml" in source
    assert "\\x26amp;" in source
    assert "\\x26lt;" in source
    assert "\\x26gt;" in source
    assert "\\x26quot;" in source
    assert "\\x26#39;" in source


def test_dynamic_html_templates_escape_api_derived_values():
    source = APP.read_text(encoding="utf-8")
    assert "innerHTML" in source
    assert source.count("escapeHtml") >= 10
