from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from delivery_reports.llm.errors import LLMInvalidResponse, LLMUnavailable
from delivery_reports.llm.prompts import COMPOSE_JSON_SCHEMA
from delivery_reports.llm.provider import AnthropicProvider, OpenAIProvider, get_llm_provider


def _valid_payload() -> dict:
    return {
        "kept": [
            {
                "project_id": 1,
                "type": "done",
                "text": "Закрыл API",
                "source_ids": [101],
                "salience": 0.7,
            }
        ],
        "excluded": [],
    }


def test_factory_returns_anthropic_provider_when_env_set(monkeypatch):
    class FakeAnthropic:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.messages = SimpleNamespace(create=lambda **_call: SimpleNamespace(content=[]))

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    monkeypatch.setitem(__import__("sys").modules, "anthropic", SimpleNamespace(Anthropic=FakeAnthropic))

    provider = get_llm_provider()

    assert isinstance(provider, AnthropicProvider)


def test_factory_raises_unavailable_when_no_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(LLMUnavailable):
        get_llm_provider()


def test_factory_raises_unavailable_for_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "unknown")

    with pytest.raises(LLMUnavailable):
        get_llm_provider()


def test_anthropic_provider_calls_sdk_with_expected_args():
    calls = {}

    class Messages:
        def create(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="tool_use", input=_valid_payload())]
            )

    client = SimpleNamespace(messages=Messages())
    provider = AnthropicProvider(api_key="key", model="claude-test", client=client)

    result = provider.complete_json("system", "user", COMPOSE_JSON_SCHEMA)

    assert result["kept"][0]["source_ids"] == [101]
    assert calls["model"] == "claude-test"
    assert calls["system"] == "system"
    assert calls["messages"][0]["content"] == "user"
    assert calls["tools"][0]["input_schema"] == COMPOSE_JSON_SCHEMA


def test_openai_provider_calls_sdk_with_expected_args():
    calls = {}

    class Completions:
        def create(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(_valid_payload())))]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    provider = OpenAIProvider(api_key="key", model="gpt-test", client=client)

    result = provider.complete_json("system", "user", COMPOSE_JSON_SCHEMA)

    assert result["kept"][0]["text"] == "Закрыл API"
    assert calls["model"] == "gpt-test"
    assert calls["messages"][0]["role"] == "system"
    assert calls["response_format"]["type"] == "json_schema"


def test_provider_raises_invalid_response_on_non_json():
    class Completions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))])

    provider = OpenAIProvider(api_key="key", client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())))

    with pytest.raises(LLMInvalidResponse):
        provider.complete_json("system", "user", COMPOSE_JSON_SCHEMA)


def test_provider_raises_invalid_response_on_schema_violation():
    class Completions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"kept": []}'))])

    provider = OpenAIProvider(api_key="key", client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())))

    with pytest.raises(LLMInvalidResponse):
        provider.complete_json("system", "user", COMPOSE_JSON_SCHEMA)
