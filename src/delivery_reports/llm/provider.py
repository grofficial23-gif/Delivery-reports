from __future__ import annotations

from abc import ABC, abstractmethod
import json
import os
from typing import Any

from .errors import LLMInvalidResponse, LLMUnavailable


class LLMProvider(ABC):
    @abstractmethod
    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
        max_output_tokens: int = 2000,
        temperature: float = 0.1,
    ) -> dict:
        """Return parsed JSON or raise LLMInvalidResponse / LLMUnavailable."""


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not self.api_key and client is None:
            raise LLMUnavailable("no_api_key")
        self.model = model or os.getenv("LLM_MODEL", "claude-haiku-4-5").strip() or "claude-haiku-4-5"
        self.timeout_seconds = timeout_seconds or _env_float("LLM_TIMEOUT_SECONDS", 30)
        if client is not None:
            self.client = client
        else:
            try:
                from anthropic import Anthropic
            except Exception as exc:  # pragma: no cover - exercised with fake modules in tests.
                raise LLMUnavailable("anthropic_sdk_missing") from exc
            self.client = Anthropic(api_key=self.api_key, timeout=self.timeout_seconds)

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
        max_output_tokens: int = 2000,
        temperature: float = 0.1,
    ) -> dict:
        tool = {
            "name": "compose_report",
            "description": "Return report composition JSON.",
            "input_schema": json_schema,
        }
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_output_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                tools=[tool],
                tool_choice={"type": "tool", "name": "compose_report"},
            )
        except TimeoutError:
            raise
        except Exception as exc:
            raise LLMUnavailable(str(exc)) from exc

        payload = _extract_anthropic_payload(response)
        _validate_compose_json(payload, json_schema)
        return payload


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "").strip()
        if not self.api_key and client is None:
            raise LLMUnavailable("no_api_key")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        self.timeout_seconds = timeout_seconds or _env_float("LLM_TIMEOUT_SECONDS", 30)
        if client is not None:
            self.client = client
        else:
            try:
                from openai import OpenAI
            except Exception as exc:  # pragma: no cover - exercised with fake modules in tests.
                raise LLMUnavailable("openai_sdk_missing") from exc
            self.client = OpenAI(api_key=self.api_key, timeout=self.timeout_seconds)

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
        max_output_tokens: int = 2000,
        temperature: float = 0.1,
    ) -> dict:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                max_tokens=max_output_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "report_compose",
                        "strict": True,
                        "schema": json_schema,
                    },
                },
            )
        except TimeoutError:
            raise
        except Exception as exc:
            raise LLMUnavailable(str(exc)) from exc

        payload = _extract_openai_payload(response)
        _validate_compose_json(payload, json_schema)
        return payload


def get_llm_provider() -> LLMProvider:
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower() or "anthropic"
    if provider == "anthropic":
        return AnthropicProvider()
    if provider == "openai":
        return OpenAIProvider()
    raise LLMUnavailable("unknown_provider")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _extract_anthropic_payload(response: Any) -> dict:
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", "") == "tool_use":
            payload = getattr(block, "input", None)
            if isinstance(payload, dict):
                return payload
        payload = getattr(block, "text", None)
        if payload:
            return _parse_json_text(str(payload))
    raise LLMInvalidResponse("missing_json")


def _extract_openai_payload(response: Any) -> dict:
    try:
        message = response.choices[0].message
    except Exception as exc:
        raise LLMInvalidResponse("missing_choice") from exc
    parsed = getattr(message, "parsed", None)
    if isinstance(parsed, dict):
        return parsed
    content = getattr(message, "content", None)
    if not content:
        raise LLMInvalidResponse("missing_content")
    return _parse_json_text(str(content))


def _parse_json_text(text: str) -> dict:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMInvalidResponse("non_json") from exc
    if not isinstance(payload, dict):
        raise LLMInvalidResponse("json_not_object")
    return payload


def _validate_compose_json(payload: dict, schema: dict) -> None:
    if not isinstance(payload, dict):
        raise LLMInvalidResponse("schema_violation")
    if set(payload.keys()) != {"kept", "excluded"}:
        raise LLMInvalidResponse("schema_violation")
    if not isinstance(payload["kept"], list) or not isinstance(payload["excluded"], list):
        raise LLMInvalidResponse("schema_violation")

    for item in payload["kept"]:
        if not isinstance(item, dict) or set(item.keys()) != {"project_id", "type", "text", "source_ids", "salience"}:
            raise LLMInvalidResponse("schema_violation")
        if item["project_id"] is not None and not isinstance(item["project_id"], int):
            raise LLMInvalidResponse("schema_violation")
        if item["type"] not in schema["properties"]["kept"]["items"]["properties"]["type"]["enum"]:
            raise LLMInvalidResponse("schema_violation")
        if not isinstance(item["text"], str) or len(item["text"]) > 500:
            raise LLMInvalidResponse("schema_violation")
        if not isinstance(item["source_ids"], list) or not item["source_ids"]:
            raise LLMInvalidResponse("schema_violation")
        if any(not isinstance(source_id, int) for source_id in item["source_ids"]):
            raise LLMInvalidResponse("schema_violation")
        if not isinstance(item["salience"], (int, float)) or not 0 <= float(item["salience"]) <= 1:
            raise LLMInvalidResponse("schema_violation")

    allowed_reasons = set(schema["properties"]["excluded"]["items"]["properties"]["reason"]["enum"])
    for item in payload["excluded"]:
        if not isinstance(item, dict):
            raise LLMInvalidResponse("schema_violation")
        if not {"source_id", "reason"}.issubset(item.keys()):
            raise LLMInvalidResponse("schema_violation")
        if set(item.keys()) - {"source_id", "reason", "duplicate_of", "note"}:
            raise LLMInvalidResponse("schema_violation")
        if not isinstance(item["source_id"], int):
            raise LLMInvalidResponse("schema_violation")
        if item["reason"] not in allowed_reasons:
            raise LLMInvalidResponse("schema_violation")
        duplicate_of = item.get("duplicate_of")
        if duplicate_of is not None and not isinstance(duplicate_of, int):
            raise LLMInvalidResponse("schema_violation")
        note = item.get("note")
        if note is not None and (not isinstance(note, str) or len(note) > 100):
            raise LLMInvalidResponse("schema_violation")
