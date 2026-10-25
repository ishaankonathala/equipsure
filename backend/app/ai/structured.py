import json

from pydantic import BaseModel, Field, ValidationError

from app.ai.provider import AIProvider, AIProviderError, AIResponse


class StructuredOutputError(Exception):
    """Raised when AI output is not valid JSON or does not match the expected schema."""


class IncidentSummary(BaseModel):
    model_config = {"extra": "forbid"}

    equipment_type: str = Field(min_length=1, max_length=100)
    incident_summary: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0.0, le=1.0)


def parse_structured(
    response: AIResponse, model_type: type[BaseModel]
) -> BaseModel:
    try:
        data = json.loads(response.text)
    except json.JSONDecodeError:
        raise StructuredOutputError("AI output is not valid JSON") from None

    if not isinstance(data, dict):
        raise StructuredOutputError("AI output must be a JSON object")

    try:
        return model_type.model_validate(data)
    except ValidationError:
        raise StructuredOutputError(
            "AI output does not match the expected schema"
        ) from None


def request_structured(
    provider: AIProvider,
    prompt: str,
    schema_hint: str,
    model_type: type[BaseModel],
) -> BaseModel:
    response = provider.complete(prompt, schema_hint)
    return parse_structured(response, model_type)