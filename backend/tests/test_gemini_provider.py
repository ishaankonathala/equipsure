from types import SimpleNamespace

import pytest
from google import genai

from app.ai.gemini_provider import GeminiProvider
from app.ai.provider import AIProviderError, AIResponse


class FakeModels:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def generate_content(self, *, model, contents):
        self.calls.append((model, contents))
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, models):
        self.models = models


def _patch_client(monkeypatch, fake_client):
    monkeypatch.setattr(genai, "Client", lambda *, api_key: fake_client)


def test_missing_key_raises():
    for api_key in ("", "   "):
        with pytest.raises(AIProviderError, match="GEMINI_API_KEY is not configured"):
            GeminiProvider(api_key=api_key)


def test_name_is_gemini():
    assert GeminiProvider.name == "gemini"


def test_complete_wraps_fake_client_text(monkeypatch):
    fake_models = FakeModels(response=SimpleNamespace(text="ok"))
    _patch_client(monkeypatch, FakeClient(fake_models))
    provider = GeminiProvider(api_key="test-key")

    result = provider.complete("p", "s")

    assert isinstance(result, AIResponse)
    assert result.provider == "gemini"
    assert result.text == "ok"


def test_request_text_combines_schema_hint_and_prompt(monkeypatch):
    fake_models = FakeModels(response=SimpleNamespace(text="ok"))
    _patch_client(monkeypatch, FakeClient(fake_models))
    provider = GeminiProvider(api_key="test-key")

    provider.complete("p", "s")

    assert fake_models.calls == [("gemini-2.5-flash", "s\n\np")]


def test_sdk_error_is_wrapped_without_message(monkeypatch):
    fake_models = FakeModels(error=RuntimeError("secret prompt text"))
    _patch_client(monkeypatch, FakeClient(fake_models))
    provider = GeminiProvider(api_key="test-key")

    with pytest.raises(AIProviderError) as exc_info:
        provider.complete("p", "s")

    assert str(exc_info.value) == "Gemini request failed"
    assert "secret prompt text" not in str(exc_info.value)


def test_empty_sdk_text_becomes_empty_string(monkeypatch):
    fake_models = FakeModels(response=SimpleNamespace(text=None))
    _patch_client(monkeypatch, FakeClient(fake_models))
    provider = GeminiProvider(api_key="test-key")

    result = provider.complete("p", "s")

    assert result.text == ""


def test_key_not_exposed_in_public_attributes(monkeypatch):
    fake_models = FakeModels(response=SimpleNamespace(text="ok"))
    _patch_client(monkeypatch, FakeClient(fake_models))
    provider = GeminiProvider(api_key="test-key")

    assert all(
        name.startswith("_") or value != "test-key"
        for name, value in vars(provider).items()
    )