from __future__ import annotations

from pathlib import Path


class TranscriptionService:
    def __init__(self, mode: str, whisper_model: str):
        self.mode = mode
        self.whisper_model = whisper_model
        self._model = None

    def transcribe(self, audio_path: Path) -> str:
        if self.mode == "disabled":
            return ""
        if self.mode == "mock":
            return f"[voice-note] {audio_path.name}"
        return self._transcribe_whisper(audio_path)

    def _transcribe_whisper(self, audio_path: Path) -> str:
        try:
            import whisper
        except Exception:
            return ""
        try:
            if self._model is None:
                self._model = whisper.load_model(self.whisper_model)
            result = self._model.transcribe(str(audio_path))
        except Exception:
            return ""
        return (result.get("text") or "").strip()

