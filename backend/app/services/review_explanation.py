import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.ai.provider import AIProvider, AIProviderError
from app.services.review import ReviewSummary, evaluate_claim


class ReviewExplanationError(Exception):
    """Raised when review explanation output cannot be used."""


class ReviewExplanation(BaseModel):
    model_config = {"extra": "forbid"}

    summary: str = Field(min_length=1, max_length=1500)
    checks_commentary: list[str] = Field(default_factory=list, max_length=10)
    stated_amount: str
    advisory_only: bool

    @field_validator("advisory_only")
    @classmethod
    def require_advisory_only(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("advisory_only must be true")
        return value


def build_review_prompt(summary: ReviewSummary, claim_reference: str) -> str:
    lines = [
        "Explain the policy review for a human officer. Reply with JSON only. You do not decide the claim."
    ]
    for check in summary.checks:
        status = "PASS" if check.passed else "FAIL"
        lines.append(f"{status} {check.name}: {check.detail}")
    lines.append("Suggested amount: " + str(summary.suggested_amount))
    lines.append("Claim reference: " + claim_reference)
    return "\n".join(lines)


def build_review_schema_hint() -> str:
    return (
        "Respond with a JSON object with keys: summary (string, 1-1500 chars), "
        "checks_commentary (list of strings, max 10), stated_amount (string), "
        "advisory_only (must be true)."
    )


def request_review_explanation(
    provider: AIProvider,
    session_summary: ReviewSummary,
    claim_reference: str,
) -> ReviewExplanation:
    prompt = build_review_prompt(session_summary, claim_reference)
    schema_hint = build_review_schema_hint()
    response = provider.complete(prompt, schema_hint)

    try:
        data: Any = json.loads(response.text)
    except Exception:
        raise ReviewExplanationError("Explanation output is not valid JSON") from None

    if not isinstance(data, dict):
        raise ReviewExplanationError("Explanation output failed validation") from None

    try:
        model = ReviewExplanation.model_validate(data)
    except ValidationError:
        raise ReviewExplanationError("Explanation output failed validation") from None

    if model.stated_amount != str(session_summary.suggested_amount):
        raise ReviewExplanationError(
            "Explanation stated a different amount than the computed figure"
        ) from None

    return model

