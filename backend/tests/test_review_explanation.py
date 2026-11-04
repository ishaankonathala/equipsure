from decimal import Decimal
import json
import pytest

from app.ai.fake_provider import FakeAIProvider
from app.ai.provider import AIProviderError
from app.services.review import ReviewSummary, RuleCheck
from app.services.review_explanation import (
    ReviewExplanation,
    ReviewExplanationError,
    build_review_prompt,
    request_review_explanation,
)


def _make_summary(suggested_amount: str = "700.00") -> ReviewSummary:
    checks = (
        RuleCheck("Policy active on incident date", True, "Period 2026-01-01 to 2027-01-01"),
        RuleCheck("Equipment covered by policy", True, "Linked through policy_equipment"),
    )
    return ReviewSummary(
        checks=checks,
        suggested_amount=Decimal(suggested_amount),
        all_passed=True,
    )


def test_valid_json_matching_stated_amount_returns_model():
    summary = _make_summary("700.00")
    reference = "CLM-TEST-001"
    prompt = build_review_prompt(summary, reference)

    payload = {
        "summary": "Claim is eligible for coverage under the active policy.",
        "checks_commentary": ["Policy is valid and active.", "Equipment is covered."],
        "stated_amount": "700.00",
        "advisory_only": True,
    }
    provider = FakeAIProvider({prompt: json.dumps(payload)})

    result = request_review_explanation(provider, summary, reference)
    assert isinstance(result, ReviewExplanation)
    assert result.summary == payload["summary"]
    assert result.checks_commentary == payload["checks_commentary"]
    assert result.stated_amount == "700.00"
    assert result.advisory_only is True


def test_non_json_raises_review_explanation_error():
    summary = _make_summary("700.00")
    reference = "CLM-TEST-001"
    prompt = build_review_prompt(summary, reference)

    provider = FakeAIProvider({prompt: "This is not JSON text at all."})

    with pytest.raises(ReviewExplanationError, match="not valid JSON"):
        request_review_explanation(provider, summary, reference)


def test_wrong_stated_amount_raises_review_explanation_error():
    summary = _make_summary("700.00")
    reference = "CLM-TEST-001"
    prompt = build_review_prompt(summary, reference)

    payload = {
        "summary": "Claim is eligible.",
        "checks_commentary": ["All checks passed."],
        "stated_amount": "500.00",
        "advisory_only": True,
    }
    provider = FakeAIProvider({prompt: json.dumps(payload)})

    with pytest.raises(ReviewExplanationError, match="different amount"):
        request_review_explanation(provider, summary, reference)


def test_advisory_only_false_raises_review_explanation_error():
    summary = _make_summary("700.00")
    reference = "CLM-TEST-001"
    prompt = build_review_prompt(summary, reference)

    payload = {
        "summary": "Claim is eligible.",
        "checks_commentary": ["All checks passed."],
        "stated_amount": "700.00",
        "advisory_only": False,
    }
    provider = FakeAIProvider({prompt: json.dumps(payload)})

    with pytest.raises(ReviewExplanationError, match="failed validation"):
        request_review_explanation(provider, summary, reference)


def test_provider_error_propagates_as_ai_provider_error():
    summary = _make_summary("700.00")
    reference = "CLM-TEST-001"
    provider = FakeAIProvider({})

    with pytest.raises(AIProviderError):
        request_review_explanation(provider, summary, reference)

