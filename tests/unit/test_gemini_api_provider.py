"""Tests for the google-genai based Gemini API provider (no network)."""

import sys
import types

import pytest

from wp_auto_poster.providers import gemini_api


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)


class FakeClient:
    def __init__(self, script):
        self.models = FakeModels(script)


@pytest.fixture
def logger():
    logs = []
    return logs, lambda message, level: logs.append((message, level))


@pytest.fixture
def patched_sdk(monkeypatch):
    """Install a fake genai module so no real client is constructed."""
    created = {}

    def make(script):
        client = FakeClient(script)
        created["client"] = client
        fake_genai = types.SimpleNamespace(Client=lambda api_key: client)
        monkeypatch.setattr(gemini_api, "genai", fake_genai)
        monkeypatch.setattr(gemini_api, "GEMINI_AVAILABLE", True)
        monkeypatch.setattr(
            gemini_api,
            "genai_types",
            types.SimpleNamespace(
                GenerateContentConfig=lambda **kwargs: kwargs,
            ),
        )
        return client

    return make


def test_missing_api_key_fails_fast(logger, patched_sdk):
    logs, log = logger
    patched_sdk([])

    result = gemini_api.generate_content_gemini("T", "k", "", log)

    assert result is None
    assert logs[-1][1] == "error"


def test_unavailable_sdk_reports_install_hint(monkeypatch, logger):
    logs, log = logger
    monkeypatch.setattr(gemini_api, "GEMINI_AVAILABLE", False)

    assert gemini_api.generate_content_gemini("T", "k", "key", log) is None
    assert "google-genai" in logs[-1][0]


def test_two_part_flow_appends_contact_section(logger, patched_sdk):
    logs, log = logger
    client = patched_sdk(["<p>part one</p>", "<p>part two</p>"])

    result = gemini_api.generate_content_gemini(
        "Tiêu đề",
        "từ khóa",
        "key",
        log,
        config={"company_name": "CÔNG TY A"},
    )

    assert "part one" in result
    assert "part two" in result
    assert "Liên hệ CÔNG TY A" in result
    assert len(client.models.calls) == 2


def test_custom_prompt_is_used_and_skips_contact_block(logger, patched_sdk):
    """A per-site prompt must not get the built-in contact block appended."""
    logs, log = logger
    client = patched_sdk(["<p>bài viết riêng</p>"])

    result = gemini_api.generate_content_gemini(
        "Bó hoa cưới",
        "hoa cưới",
        "key",
        log,
        config={
            "gemini_prompt": "Viết về {title} với từ khóa {keyword}",
            "company_name": "SHOP HOA",
        },
    )

    assert result == "<p>bài viết riêng</p>"
    assert len(client.models.calls) == 1
    sent = client.models.calls[0]["contents"]
    assert "Bó hoa cưới" in sent and "hoa cưới" in sent
    # The elevator company's details must not reach a flower shop's article.
    assert "thanhtienelevator" not in result


def test_markdown_code_fence_is_stripped(logger, patched_sdk):
    logs, log = logger
    patched_sdk(["```html\n<p>x</p>\n```"])

    result = gemini_api.generate_content_gemini(
        "T", "k", "key", log,
        config={"gemini_prompt": "{title} {keyword}"},
    )

    assert result == "<p>x</p>"


def test_non_rate_limit_error_returns_none_without_retrying(logger, patched_sdk):
    logs, log = logger
    client = patched_sdk([RuntimeError("boom"), "unused"])

    result = gemini_api.generate_content_gemini(
        "T", "k", "key", log,
        config={"gemini_prompt": "{title} {keyword}"},
    )

    assert result is None
    assert len(client.models.calls) == 1
    assert logs[-1][1] == "error"


def test_rate_limit_is_retried(monkeypatch, logger, patched_sdk):
    logs, log = logger
    monkeypatch.setattr(gemini_api.time, "sleep", lambda seconds: None)
    client = patched_sdk([RuntimeError("429 RESOURCE_EXHAUSTED"), "<p>ok</p>"])

    result = gemini_api.generate_content_gemini(
        "T", "k", "key", log,
        config={"gemini_prompt": "{title} {keyword}"},
    )

    assert result == "<p>ok</p>"
    assert len(client.models.calls) == 2
    assert any(level == "warning" for _, level in logs)


def test_model_is_configurable(logger, patched_sdk):
    logs, log = logger
    client = patched_sdk(["<p>ok</p>"])

    gemini_api.generate_content_gemini(
        "T", "k", "key", log,
        config={"gemini_prompt": "{title} {keyword}", "gemini_model": "gemini-3-pro"},
    )

    assert client.models.calls[0]["model"] == "gemini-3-pro"


def test_old_sdk_is_no_longer_imported():
    """google-generativeai is discontinued and must not be a dependency."""
    assert "google.generativeai" not in sys.modules
