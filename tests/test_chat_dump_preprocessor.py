from __future__ import annotations

import pytest

from delivery_reports.chat_dump.preprocessor import preprocess


def test_preprocess_strips_quote_prefixes():
    raw = "> line one\n>> line two"
    assert preprocess(raw) == "line one\nline two"


def test_preprocess_strips_bracket_timestamps_and_nick_prefix():
    raw = "[10:05] Alice: deployed the fix\n[10:06] rest line"
    out = preprocess(raw)
    assert "deployed the fix" in out
    assert "Alice:" not in out
    assert "[10:05]" not in out


def test_preprocess_does_not_strip_structured_risk_label_as_nick():
    raw = "Риск: интеграция может сдвинуться"
    assert preprocess(raw) == "Риск: интеграция может сдвинуться"


def test_preprocess_removes_standalone_section_headers():
    raw = "Что сделано\n\nЗакрыл тикет ABC-1\n\nПланы\nПодготовить релиз"
    out = preprocess(raw)
    assert "Что сделано" not in out
    assert "Планы" not in out
    assert "Закрыл тикет ABC-1" in out
    assert "Подготовить релиз" in out


def test_preprocess_removes_emoji_only_lines():
    raw = "факт есть ✅\n\n🎉🎉🎉\nещё факт"
    out = preprocess(raw)
    assert "факт есть" in out
    assert "ещё факт" in out
    assert "🎉" not in out


def test_preprocess_collapses_multiple_blank_lines():
    raw = "line_one_xxxxxxxx\n\n\n\nline_two_yyyyyyyy"
    assert preprocess(raw) == "line_one_xxxxxxxx\n\nline_two_yyyyyyyy"


def test_preprocess_returns_original_when_cleanup_shorter_than_10_chars():
    raw = "\n".join(["🙂", "✨", "💬"])
    assert preprocess(raw) == raw.strip()


def test_preprocess_returns_original_when_only_section_headers_removed():
    raw = "Планы\nРиски"
    assert preprocess(raw) == raw.strip()


@pytest.mark.parametrize(
    "noise",
    [
        "✅\n✅\n✅",
        "…",
    ],
)
def test_preprocess_falls_back_to_original_on_very_short_cleaned(noise):
    assert preprocess(noise) == noise.strip()


def test_preprocess_truncates_to_max_chars(monkeypatch):
    monkeypatch.setenv("CHAT_DUMP_MAX_INPUT_CHARS", "15")
    raw = "a" * 50
    out = preprocess(raw)
    assert len(out) == 15
    assert out == "a" * 15
