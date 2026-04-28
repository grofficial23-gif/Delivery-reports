from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptionResult:
    """Outcome of a single transcription attempt.

    Attributes:
        text:   Recognised text, empty string when *ok* is False.
        ok:     True only when transcription succeeded and text is non-empty.
        reason: Machine-readable failure reason for logging / UX branching.
                One of: "ok" | "disabled" | "no_whisper" |
                        "whisper_error" | "empty_result".
    """

    text: str
    ok: bool
    reason: str


class TranscriptionService:
    def __init__(self, mode: str, whisper_model: str):
        self.mode = mode
        self.whisper_model = whisper_model
        self._model = None

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Attempt to transcribe *audio_path*.

        Always returns a :class:`TranscriptionResult`.  Never raises;
        all errors are captured and recorded in *reason*.
        """
        if self.mode == "disabled":
            _log.debug("transcription disabled; skipping %s", audio_path.name)
            return TranscriptionResult(text="", ok=False, reason="disabled")
        if self.mode == "mock":
            text = f"[voice-note] {audio_path.name}"
            return TranscriptionResult(text=text, ok=True, reason="ok")
        return self._transcribe_whisper(audio_path)

    def _transcribe_whisper(self, audio_path: Path) -> TranscriptionResult:
        try:
            import whisper  # type: ignore[import]
        except Exception as exc:
            _log.warning("whisper package not available: %s", exc)
            return TranscriptionResult(text="", ok=False, reason="no_whisper")
        try:
            if self._model is None:
                self._model = whisper.load_model(self.whisper_model)
            result = self._model.transcribe(str(audio_path))
        except Exception as exc:
            _log.error("whisper transcription error for %s: %s", audio_path.name, exc)
            return TranscriptionResult(text="", ok=False, reason="whisper_error")
        text = (result.get("text") or "").strip()
        if not text:
            _log.info("whisper returned empty transcript for %s", audio_path.name)
            return TranscriptionResult(text="", ok=False, reason="empty_result")
        return TranscriptionResult(text=text, ok=True, reason="ok")

