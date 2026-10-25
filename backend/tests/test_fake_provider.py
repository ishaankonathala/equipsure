import pytest

from app.ai.fake_provider import FakeAIProvider
from app.ai.provider import AIProviderError, AIResponse


def test_returns_canned_text():
    result = FakeAIProvider({"hello": "world"}).complete("hello", "schema")

    assert isinstance(result, AIResponse)
    assert result.provider == "fake"
    assert result.text == "world"


def test_unknown_prompt_raises():
    with pytest.raises(AIProviderError, match="No canned response"):
        FakeAIProvider().complete("missing", "schema")


def test_records_calls():
    provider = FakeAIProvider({"hello": "world"})
    provider.complete("hello", "schema")

    with pytest.raises(AIProviderError):
        provider.complete("missing", "schema")

    assert provider.calls == [
        ("hello", "schema"),
        ("missing", "schema"),
    ]


def test_constructor_copies_responses():
    responses = {"hello": "original"}
    provider = FakeAIProvider(responses)
    responses["hello"] = "changed"
    responses["new"] = "added"

    assert provider.complete("hello", "schema").text == "original"
    with pytest.raises(AIProviderError):
        provider.complete("new", "schema")


def test_name_is_fake():
    assert FakeAIProvider().name == "fake"


def test_empty_default_raises_on_any_prompt():
    with pytest.raises(AIProviderError):
        FakeAIProvider().complete("x", "y")


def test_satisfies_provider_protocol():
    provider = FakeAIProvider({"hello": "world"})
    result = provider.complete("hello", "schema")

    assert isinstance(result, AIResponse)
    assert callable(provider.complete)