from __future__ import annotations

from types import SimpleNamespace

import pytest

from delivery_reports.chat_dump import extractor as ce
from delivery_reports.chat_dump.extractor import extract_facts
from delivery_reports.llm.errors import LLMInvalidResponse
from delivery_reports.llm.provider import AnthropicProvider


def _fake_anthropic_client_good():
    payload = {
        "facts": [
            {
                "type": "done",
                "text": "Merged PR #12",
                "confidence": 0.95,
                "project_hint": "Core",
                "suggested_project_id": None,
            }
        ],
        "skipped": [{"reason": "greeting", "snippet": "Привет"}],
    }

    def create(**_kwargs):
        block = SimpleNamespace(type="tool_use", input=payload)
        return SimpleNamespace(content=[block])

    return SimpleNamespace(messages=SimpleNamespace(create=create))


def _fake_anthropic_client_bad_shape():
    def create(**_kwargs):
        block = SimpleNamespace(type="tool_use", input={"foo": 1})
        return SimpleNamespace(content=[block])

    return SimpleNamespace(messages=SimpleNamespace(create=create))


def test_extract_facts_success_assigns_tmp_client_ids(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    prov = AnthropicProvider(api_key="test", client=_fake_anthropic_client_good())
    result = extract_facts("some cleaned text", provider=prov)
    assert result.used_llm is True
    assert result.fallback_reason is None
    assert len(result.facts) == 1
    assert result.facts[0].client_id == "tmp_1"
    assert result.facts[0].type == "done"
    assert result.facts[0].text == "Merged PR #12"
    assert result.facts[0].confidence == 0.95
    assert result.facts[0].project_hint == "Core"
    assert result.skipped[0].reason == "greeting"


def test_extract_facts_no_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = extract_facts("hello world here")
    assert result.used_llm is False
    assert result.fallback_reason == "no_api_key"


def test_extract_facts_timeout(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")

    def create(**_kwargs):
        raise TimeoutError()

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    prov = AnthropicProvider(api_key="test", client=client)
    result = extract_facts("hello world here enough len", provider=prov)
    assert result.used_llm is False
    assert result.fallback_reason == "timeout"


def test_extract_facts_invalid_json_payload(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    prov = AnthropicProvider(api_key="test", client=_fake_anthropic_client_bad_shape())
    result = extract_facts("hello world here enough len", provider=prov)
    assert result.used_llm is False
    assert result.fallback_reason == "invalid_json"


def test_extract_facts_empty_cleaned():
    result = extract_facts("   ")
    assert result.used_llm is False
    assert result.fallback_reason == "invalid_json"


def test_extract_facts_filters_malformed_fact_entries(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    payload = {
        "facts": [
            {
                "type": "done",
                "text": "ok",
                "confidence": 0.9,
                "project_hint": None,
                "suggested_project_id": None,
            },
            {
                "type": "invalid_type",
                "text": "nope",
                "confidence": 0.5,
                "project_hint": None,
                "suggested_project_id": None,
            },
        ],
        "skipped": [],
    }

    def create(**_kwargs):
        block = SimpleNamespace(type="tool_use", input=payload)
        return SimpleNamespace(content=[block])

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    prov = AnthropicProvider(api_key="test", client=client)
    result = extract_facts("hello world long enough", provider=prov)
    assert result.used_llm is True
    assert len(result.facts) == 1
    assert result.facts[0].text == "ok"
