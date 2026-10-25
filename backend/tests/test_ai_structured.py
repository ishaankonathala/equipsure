import pytest

from app.ai.fake_provider import FakeAIProvider
from app.ai.provider import AIProviderError, AIResponse
from app.ai.structured import (
    IncidentSummary,
    StructuredOutputError,
    parse_structured,
    request_structured,
)

VALID = '{"equipment_type": "refrigerator", "incident_summary": "Stopped cooling overnight.", "confidence": 0.8}'


def test_valid_json_is_parsed():
    result = parse_structured(AIResponse(provider="fake", text=VALID), IncidentSummary)

    assert isinstance(result, IncidentSummary)
    assert result.equipment_type == "refrigerator"


def test_invalid_json_is_rejected():
    with pytest.raises(StructuredOutputError, match="not valid JSON"):
        parse_structured(AIResponse(provider="fake", text="not json"), IncidentSummary)


def test_non_object_json_is_rejected():
    with pytest.raises(StructuredOutputError, match="must be a JSON object"):
        parse_structured(AIResponse(provider="fake", text="[1, 2]"), IncidentSummary)


def test_missing_field_is_rejected():
    text = '{"equipment_type": "refrigerator"}'

    with pytest.raises(
        StructuredOutputError,
        match="does not match the expected schema",
    ):
        parse_structured(AIResponse(provider="fake", text=text), IncidentSummary)


def test_extra_field_is_rejected():
    text = VALID[:-1] + ', "approved": true}'

    with pytest.raises(
        StructuredOutputError,
        match="does not match the expected schema",
    ):
        parse_structured(AIResponse(provider="fake", text=text), IncidentSummary)


def test_confidence_out_of_range_is_rejected():
    text = VALID.replace('"confidence": 0.8', '"confidence": 1.5')

    with pytest.raises(StructuredOutputError):
        parse_structured(AIResponse(provider="fake", text=text), IncidentSummary)


def test_request_structured_uses_provider():
    provider = FakeAIProvider({"p": VALID})

    result = request_structured(provider, "p", "s", IncidentSummary)

    assert result.confidence == 0.8


def test_provider_error_propagates_unchanged():
    provider = FakeAIProvider()

    with pytest.raises(AIProviderError, match="No canned response"):
        request_structured(provider, "p", "s", IncidentSummary)


def test_error_message_does_not_echo_response_text():
    response = AIResponse(provider="fake", text="secret-leak-value not json")

    with pytest.raises(StructuredOutputError) as exc_info:
        parse_structured(response, IncidentSummary)

    assert "secret-leak-value" not in str(exc_info.value)