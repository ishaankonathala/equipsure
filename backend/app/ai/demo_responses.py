import json

DEMO_ASSESSMENT_JSON = json.dumps(
    {
        "summary": "Refrigerator reported stopped cooling; the claim is consistent with a sudden breakdown, subject to review.",
        "cited_clause_ids": ["DEMO-COV-01", "DEMO-REP-01"],
        "missing_items": ["Repair estimate"],
        "inconsistencies": [],
        "recommendation": "Request the repair estimate and confirm the incident date before review.",
        "advisory_only": True,
    }
)

DEMO_PROMPT_MATCH = ""


def demo_response_for(prompt: str) -> dict[str, str]:
    if "Assess the claim as an advisory reviewer" not in prompt:
        return {}
    return {prompt: DEMO_ASSESSMENT_JSON}