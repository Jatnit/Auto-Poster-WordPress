"""Secret redaction helpers for config and preset payloads.

The web UI runs on localhost, but the API used to hand out the WordPress
password and Gemini API key in plain text on every ``GET /api/config``.
These helpers keep secrets server-side: reads report only whether a secret
is set, and writes treat an empty incoming secret as "leave unchanged".
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

SECRET_KEYS = ("wp_password", "gemini_api_key")

#: Suffix appended to each secret key to expose a boolean "is it set?" flag.
SET_FLAG_SUFFIX = "_set"


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def redact_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a copy of ``config`` with secrets replaced by boolean flags."""
    redacted = {key: value for key, value in config.items() if key not in SECRET_KEYS}
    for key in SECRET_KEYS:
        redacted[f"{key}{SET_FLAG_SUFFIX}"] = not _is_blank(config.get(key))
    return redacted


def merge_config_update(
    current: Mapping[str, Any],
    incoming: Mapping[str, Any],
) -> Dict[str, Any]:
    """Merge an incoming config update, preserving secrets that were omitted.

    A secret sent as ``""``/``None``/whitespace means "keep what is stored"
    rather than "erase it", so the UI can render an empty password field
    without wiping the saved credentials on the next save.
    """
    merged = dict(incoming)
    for key in SECRET_KEYS:
        if key not in merged:
            continue
        if _is_blank(merged[key]):
            stored = current.get(key)
            if _is_blank(stored):
                merged.pop(key, None)
            else:
                merged[key] = stored
    return merged


def redact_preset(preset: Mapping[str, Any]) -> Dict[str, Any]:
    """Redact secrets in a single site preset."""
    return redact_config(preset)
