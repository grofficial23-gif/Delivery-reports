"""LLM provider / compose errors."""


class LLMUnavailable(Exception):
    """No API key, unknown provider, or SDK missing."""


class LLMInvalidResponse(Exception):
    """Non-JSON, schema violation, or empty model output."""
