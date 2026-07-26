from datetime import datetime

from wp_auto_poster.content.prompts import (
    CONTACT_SECTION,
    DEFAULT_COMPANY_NAME,
    PROMPT_PART1,
    PROMPT_PART2,
    format_contact_section,
    format_prompt,
    get_company_name,
    get_contact_section_template,
    get_custom_prompt,
    safe_format,
)


def test_default_templates_have_no_leftover_placeholders():
    for template in (PROMPT_PART1, PROMPT_PART2):
        filled = format_prompt(template, "Tiêu đề", "từ khóa", {})
        assert "{title}" not in filled
        assert "{keyword}" not in filled
        assert "{company}" not in filled
        assert "{year}" not in filled


def test_prompt_uses_configured_company_name():
    filled = format_prompt(
        PROMPT_PART1,
        "Bó hoa cưới",
        "hoa cưới",
        {"company_name": "HOA TƯƠI TRĂNG KHUYẾT"},
    )

    assert "HOA TƯƠI TRĂNG KHUYẾT" in filled
    assert "KENZO" not in filled


def test_prompt_falls_back_to_default_company():
    filled = format_prompt(PROMPT_PART1, "T", "k", {})

    assert DEFAULT_COMPANY_NAME in filled


def test_blank_company_name_falls_back_to_default():
    filled = format_prompt(PROMPT_PART1, "T", "k", {"company_name": "   "})

    assert DEFAULT_COMPANY_NAME in filled


def test_prompt_year_is_current_not_hardcoded():
    filled = format_prompt(PROMPT_PART1, "T", "k", {})

    assert f"năm {datetime.now().year}" in filled
    assert "năm 2025" not in filled or datetime.now().year == 2025


def test_contact_section_can_be_overridden_per_site():
    custom = "<h2>Liên hệ {company}</h2><p>Về {keyword}</p>"

    rendered = format_contact_section(
        "hoa cưới",
        {"company_name": "SHOP HOA", "contact_section_html": custom},
    )

    assert rendered == "<h2>Liên hệ SHOP HOA</h2><p>Về hoa cưới</p>"
    # The elevator company's address must not leak into another site.
    assert "thanhtienelevator" not in rendered


def test_contact_section_defaults_to_builtin_block():
    assert get_contact_section_template({}) == CONTACT_SECTION
    assert get_contact_section_template({"contact_section_html": "  "}) == CONTACT_SECTION


def test_get_company_name_handles_missing_config():
    assert get_company_name(None) == DEFAULT_COMPANY_NAME
    assert get_company_name({}) == DEFAULT_COMPANY_NAME


# ---------------------------------------------------------------------------
# Custom prompt selection
# ---------------------------------------------------------------------------


def test_custom_prompt_requires_both_placeholders():
    assert get_custom_prompt({"gemini_prompt": "Viết về {title} và {keyword}"})
    assert get_custom_prompt({"gemini_prompt": "Chỉ có {title}"}) is None
    assert get_custom_prompt({"gemini_prompt": ""}) is None
    assert get_custom_prompt(None) is None


# ---------------------------------------------------------------------------
# safe_format robustness
# ---------------------------------------------------------------------------


def test_safe_format_leaves_unknown_placeholders_intact():
    result = safe_format("{title} - {unknown}", title="A")

    assert result == "A - {unknown}"


def test_safe_format_survives_stray_brace_in_user_prompt():
    """A stray brace in a config-supplied prompt must not kill a run."""
    result = safe_format("Viết về {keyword} với style { lạ", keyword="hoa")

    assert "hoa" in result
