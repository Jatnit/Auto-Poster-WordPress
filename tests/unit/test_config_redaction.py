from wp_auto_poster.state.redaction import (
    SECRET_KEYS,
    merge_config_update,
    redact_config,
    redact_preset,
)


def test_redact_config_removes_secrets_and_reports_flags():
    config = {
        "wp_username": "admin",
        "wp_password": "hunter2",
        "gemini_api_key": "",
        "posts_per_day": 2,
    }

    redacted = redact_config(config)

    for key in SECRET_KEYS:
        assert key not in redacted
    assert redacted["wp_password_set"] is True
    assert redacted["gemini_api_key_set"] is False
    assert redacted["wp_username"] == "admin"
    assert redacted["posts_per_day"] == 2


def test_redact_config_does_not_mutate_input():
    config = {"wp_password": "hunter2"}

    redact_config(config)

    assert config == {"wp_password": "hunter2"}


def test_redact_config_treats_whitespace_as_unset():
    assert redact_config({"wp_password": "   "})["wp_password_set"] is False


def test_merge_keeps_stored_secret_when_incoming_is_blank():
    current = {"wp_password": "hunter2", "gemini_api_key": "key-123"}
    incoming = {"wp_password": "", "gemini_api_key": None, "posts_per_day": 3}

    merged = merge_config_update(current, incoming)

    assert merged["wp_password"] == "hunter2"
    assert merged["gemini_api_key"] == "key-123"
    assert merged["posts_per_day"] == 3


def test_merge_applies_new_secret_when_provided():
    current = {"wp_password": "old"}
    incoming = {"wp_password": "new"}

    assert merge_config_update(current, incoming)["wp_password"] == "new"


def test_merge_drops_blank_secret_when_nothing_is_stored():
    merged = merge_config_update({}, {"wp_password": ""})

    # Nothing stored and nothing supplied: do not write an empty secret back.
    assert "wp_password" not in merged


def test_merge_leaves_untouched_keys_alone():
    current = {"wp_password": "hunter2"}
    incoming = {"posts_per_day": 5}

    merged = merge_config_update(current, incoming)

    assert merged == {"posts_per_day": 5}


def test_redact_preset_hides_password():
    preset = {"wp_username": "admin", "wp_password": "hunter2"}

    redacted = redact_preset(preset)

    assert "wp_password" not in redacted
    assert redacted["wp_password_set"] is True
