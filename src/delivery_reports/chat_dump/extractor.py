"""LLM-based fact extraction from preprocessed chat dumps."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from ..llm.errors import LLMInvalidResponse, LLMUnavailable
from ..llm.provider import AnthropicProvider, OpenAIProvider

from .prompts import DUMP_OUTPUT_SCHEMA, FACT_TYPES, system_prompt, user_prompt

_log = logging.getLogger(__name__)


@dataclass
class ExtractedFact:
    client_id: str
    type: str
    text: str
    confidence: float
    project_hint: str | None
    suggested_project_id: int | None


@dataclass
class SkippedFragment:
    reason: str
    snippet: str | None


@dataclass
class ExtractionResult:
    facts: list[ExtractedFact]
    skipped: list[SkippedFragment]
    warnings: list[str]
    used_llm: bool
    fallback_reason: str | None


def extract_facts(
    cleaned_text: str,
    user_lang: str = "ru",
    *,
    provider: Any | None = None,
) -> ExtractionResult:
    warnings: list[str] = []
    if not cleaned_text.strip():
        return ExtractionResult([], [], warnings, False, "invalid_json")

    prov = provider
    if prov is None:
        try:
            prov = _make_dump_provider()
        except LLMUnavailable:
            return ExtractionResult([], [], warnings, False, "no_api_key")

    sys_p = system_prompt()
    usr_p = user_prompt(cleaned_text=cleaned_text, user_lang=user_lang)
    try:
        payload = _invoke_dump_llm(prov, sys_p, usr_p)
    except TimeoutError:
        return ExtractionResult([], [], warnings, False, "timeout")
    except LLMInvalidResponse:
        return ExtractionResult([], [], warnings, False, "invalid_json")
    except LLMUnavailable:
        return ExtractionResult([], [], warnings, False, "no_api_key")
    except Exception as exc:
        _log.warning("chat_dump extract failed: %s", exc)
        return ExtractionResult([], [], warnings, False, "invalid_json")

    try:
        raw_facts, skipped = _parse_payload(payload)
    except ValueError:
        return ExtractionResult([], [], warnings, False, "invalid_json")

    facts = [
        ExtractedFact(
            client_id=f"tmp_{i + 1}",
            type=f.type,
            text=f.text,
            confidence=f.confidence,
            project_hint=f.project_hint,
            suggested_project_id=f.suggested_project_id,
        )
        for i, f in enumerate(raw_facts)
    ]
    return ExtractionResult(facts, skipped, warnings, True, None)


def _make_dump_provider() -> Any:
    kind = os.getenv("LLM_PROVIDER", "anthropic").strip().lower() or "anthropic"
    timeout = float(os.getenv("CHAT_DUMP_TIMEOUT_SECONDS", "30"))
    if kind == "anthropic":
        return AnthropicProvider(timeout_seconds=timeout)
    if kind == "openai":
        return OpenAIProvider(timeout_seconds=timeout)
    raise LLMUnavailable("unknown_provider")


def _invoke_dump_llm(provider: Any, system_prompt_s: str, user_prompt_s: str) -> dict[str, Any]:
    schema = DUMP_OUTPUT_SCHEMA
    if isinstance(provider, AnthropicProvider):
        tool = {
            "name": "chat_dump_extract",
            "description": "Extract atomic facts from chat dump JSON.",
            "input_schema": schema,
        }
        resp = provider.client.messages.create(
            model=provider.model,
            max_tokens=2000,
            temperature=0.1,
            system=system_prompt_s,
            messages=[{"role": "user", "content": user_prompt_s}],
            tools=[tool],
            tool_choice={"type": "tool", "name": "chat_dump_extract"},
        )
        return _anthropic_tool_payload(resp)
    if isinstance(provider, OpenAIProvider):
        resp = provider.client.chat.completions.create(
            model=provider.model,
            temperature=0.1,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": system_prompt_s},
                {"role": "user", "content": user_prompt_s},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "chat_dump_extract",
                    "strict": True,
                    "schema": schema,
                },
            },
        )
        return _openai_message_payload(resp)
    raise LLMUnavailable("unknown_provider")


def _anthropic_tool_payload(resp: Any) -> dict[str, Any]:
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", "") == "tool_use":
            payload = getattr(block, "input", None)
            if isinstance(payload, dict):
                return payload
    raise LLMInvalidResponse("no_tool_use")


def _openai_message_payload(resp: Any) -> dict[str, Any]:
    try:
        msg = resp.choices[0].message
    except Exception as exc:
        raise LLMInvalidResponse("no_choice") from exc
    parsed = getattr(msg, "parsed", None)
    if isinstance(parsed, dict):
        return parsed
    content = getattr(msg, "content", None) or ""
    if not content:
        raise LLMInvalidResponse("empty")
    try:
        data = json.loads(str(content))
    except json.JSONDecodeError as exc:
        raise LLMInvalidResponse("bad_json") from exc
    if not isinstance(data, dict):
        raise LLMInvalidResponse("not_object")
    return data


@dataclass
class _RawFact:
    type: str
    text: str
    confidence: float
    project_hint: str | None
    suggested_project_id: int | None


def _parse_payload(data: dict[str, Any]) -> tuple[list[_RawFact], list[SkippedFragment]]:
    if "facts" not in data or "skipped" not in data:
        raise ValueError("shape")
    facts_raw = data["facts"]
    skipped_raw = data["skipped"]
    if not isinstance(facts_raw, list) or not isinstance(skipped_raw, list):
        raise ValueError("shape")
    facts: list[_RawFact] = []
    for item in facts_raw:
        if not isinstance(item, dict):
            continue
        t = item.get("type")
        text = (item.get("text") or "").strip()
        conf = item.get("confidence")
        if t not in FACT_TYPES or not text or not isinstance(conf, (int, float)):
            continue
        conf_f = float(conf)
        if not 0 <= conf_f <= 1:
            continue
        ph = item.get("project_hint")
        sid = item.get("suggested_project_id")
        ph_out: str | None
        if ph is None or (isinstance(ph, str) and not ph.strip()):
            ph_out = None
        else:
            ph_out = str(ph).strip()
        sid_out: int | None
        if isinstance(sid, int):
            sid_out = sid
        elif sid is None:
            sid_out = None
        else:
            sid_out = None
        facts.append(
            _RawFact(
                type=str(t),
                text=text[:2000],
                confidence=conf_f,
                project_hint=ph_out,
                suggested_project_id=sid_out,
            )
        )
    skipped: list[SkippedFragment] = []
    for item in skipped_raw:
        if not isinstance(item, dict):
            continue
        reason = (item.get("reason") or "").strip()
        if not reason:
            continue
        snip = item.get("snippet")
        skipped.append(
            SkippedFragment(
                reason=reason[:500],
                snippet=str(snip)[:500] if snip is not None else None,
            )
        )
    return facts, skipped
