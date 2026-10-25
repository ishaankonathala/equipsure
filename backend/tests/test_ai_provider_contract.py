from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.ai.provider import (
    AIProvider,
    AIProviderError,
    AIResponse,
    KNOWN_PROVIDERS,
)


def test_response_requires_provider():
    with pytest.raises(ValueError, match="provider is required"):
        AIResponse(provider="", text="x")
    with pytest.raises(ValueError, match="provider is required"):
        AIResponse(provider=" \t\n ", text="x")


def test_response_allows_empty_text():
    response = AIResponse(provider="fake", text="")

    assert response.text == ""


def test_response_is_immutable():
    response = AIResponse(provider="fake", text="raw output")

    with pytest.raises(FrozenInstanceError):
        response.text = "changed"


def test_known_providers():
    assert KNOWN_PROVIDERS == {"fake", "gemini"}


def test_provider_error_is_exception():
    assert issubclass(AIProviderError, Exception) is True

    with pytest.raises(AIProviderError, match="provider unavailable"):
        raise AIProviderError("provider unavailable")


def test_protocol_declares_complete():
    assert hasattr(AIProvider, "complete") is True


def test_provider_module_has_no_heavy_imports():
    source_path = Path(__file__).resolve().parents[1] / "app" / "ai" / "provider.py"
    source = source_path.read_text().lower()

    for forbidden_import in ("sqlalchemy", "fastapi", "httpx", "google"):
        assert forbidden_import not in source