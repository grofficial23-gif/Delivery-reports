"""Tests for TranscriptionService.

Covers:
- disabled mode → ok=False, reason="disabled"
- mock mode     → ok=True,  reason="ok", sensible text
- no whisper    → ok=False, reason="no_whisper"
- whisper error → ok=False, reason="whisper_error"
- empty result  → ok=False, reason="empty_result"
- success       → ok=True,  reason="ok", text returned
- Result is never a raw string (regression guard against old API)
- Technical details (file_id, "transcription failed") never appear
  in TranscriptionResult.text
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from delivery_reports.services.transcription import TranscriptionResult, TranscriptionService


DUMMY_PATH = Path("/tmp/test_voice.ogg")


# ── helpers ─────────────────────────────────────────────────────────────────

def _svc(mode: str = "local_whisper", whisper_model: str = "base") -> TranscriptionService:
    return TranscriptionService(mode=mode, whisper_model=whisper_model)


def _assert_no_technical_garbage(result: TranscriptionResult) -> None:
    """Ensure polluting strings never appear in user-facing text."""
    for forbidden in ("transcription failed", "file_id=", "voice-note:"):
        assert forbidden not in result.text, (
            f"Technical text {forbidden!r} leaked into TranscriptionResult.text"
        )


# ── return type ─────────────────────────────────────────────────────────────

def test_transcribe_returns_result_object() -> None:
    svc = _svc(mode="disabled")
    result = svc.transcribe(DUMMY_PATH)
    assert isinstance(result, TranscriptionResult), (
        "transcribe() must return TranscriptionResult, not a plain string"
    )


# ── disabled mode ───────────────────────────────────────────────────────────

def test_disabled_mode_returns_not_ok() -> None:
    result = _svc(mode="disabled").transcribe(DUMMY_PATH)
    assert result.ok is False
    assert result.reason == "disabled"
    assert result.text == ""
    _assert_no_technical_garbage(result)


# ── mock mode ────────────────────────────────────────────────────────────────

def test_mock_mode_returns_ok() -> None:
    result = _svc(mode="mock").transcribe(DUMMY_PATH)
    assert result.ok is True
    assert result.reason == "ok"
    assert result.text  # non-empty
    _assert_no_technical_garbage(result)


def test_mock_mode_text_contains_filename() -> None:
    result = _svc(mode="mock").transcribe(DUMMY_PATH)
    assert DUMMY_PATH.name in result.text


# ── whisper not installed ────────────────────────────────────────────────────

def test_no_whisper_returns_not_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate ImportError when whisper is not installed."""
    # Remove whisper from sys.modules and block future imports
    monkeypatch.setitem(sys.modules, "whisper", None)  # type: ignore[arg-type]
    result = _svc(mode="local_whisper").transcribe(DUMMY_PATH)
    assert result.ok is False
    assert result.reason == "no_whisper"
    assert result.text == ""
    _assert_no_technical_garbage(result)


# ── whisper runtime error ────────────────────────────────────────────────────

def test_whisper_error_returns_not_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate whisper raising during transcription."""
    mock_whisper = MagicMock()
    mock_whisper.load_model.side_effect = RuntimeError("GPU OOM")
    monkeypatch.setitem(sys.modules, "whisper", mock_whisper)

    result = _svc(mode="local_whisper").transcribe(DUMMY_PATH)
    assert result.ok is False
    assert result.reason == "whisper_error"
    assert result.text == ""
    _assert_no_technical_garbage(result)


# ── empty transcript ─────────────────────────────────────────────────────────

def test_empty_whisper_output_returns_not_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whisper runs successfully but returns blank text."""
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"text": "   "}
    mock_whisper = MagicMock()
    mock_whisper.load_model.return_value = mock_model
    monkeypatch.setitem(sys.modules, "whisper", mock_whisper)

    svc = _svc(mode="local_whisper")
    result = svc.transcribe(DUMMY_PATH)
    assert result.ok is False
    assert result.reason == "empty_result"
    assert result.text == ""
    _assert_no_technical_garbage(result)


# ── successful transcription ─────────────────────────────────────────────────

def test_successful_transcription(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"text": "  Завершили интеграцию с Jira.  "}
    mock_whisper = MagicMock()
    mock_whisper.load_model.return_value = mock_model
    monkeypatch.setitem(sys.modules, "whisper", mock_whisper)

    svc = _svc(mode="local_whisper")
    result = svc.transcribe(DUMMY_PATH)
    assert result.ok is True
    assert result.reason == "ok"
    assert result.text == "Завершили интеграцию с Jira."
    _assert_no_technical_garbage(result)
