import inspect

import pytest

from app.ai.provider import AIProviderError
from app.ai.selection import build_provider, run_ai_completion
from app.core.config import settings


def test_fake_is_selected_by_name():
    assert build_provider("fake").name == "fake"


def test_unknown_provider_is_rejected():
    with pytest.raises(AIProviderError) as exc_info:
        build_provider("openai")

    assert "Unknown AI provider" in str(exc_info.value)
    assert "openai" not in str(exc_info.value)


def test_name_is_normalised():
    assert build_provider("  FAKE ").name == "fake"


def test_settings_default_is_used_when_no_name(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "fake")

    assert build_provider().name == "fake"


def test_unknown_settings_value_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "nonsense")

    with pytest.raises(AIProviderError, match="Unknown AI provider"):
        build_provider()


def test_gemini_without_key_fails_cleanly(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")

    with pytest.raises(AIProviderError, match="GEMINI_API_KEY is not configured"):
        build_provider("gemini")


def test_run_completion_returns_text():
    provider = build_provider("fake", fake_responses={"p": "answer"})

    assert run_ai_completion(provider, "p", "s") == "answer"


def test_run_completion_propagates_provider_error():
    provider = build_provider("fake")

    with pytest.raises(AIProviderError):
        run_ai_completion(provider, "p", "s")


def test_run_completion_does_not_touch_claims():
    assert set(inspect.signature(run_ai_completion).parameters) == {
        "provider",
        "prompt",
        "schema_hint",
    }