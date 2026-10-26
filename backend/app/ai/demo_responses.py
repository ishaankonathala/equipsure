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
    if "Assess the claim as an advisory reviewer" in prompt:
        return {prompt: DEMO_ASSESSMENT_JSON}

    assistant_marker = "Answer the question using ONLY the clauses below."
    if assistant_marker not in prompt:
        return {}

    for line in prompt.splitlines():
        if line.startswith("Question: "):
            break
        if not line.startswith("DEMO-"):
            continue
        clause_id, separator, remainder = line.partition(" (")
        if not separator:
            continue
        _, details_separator, clause_text = remainder.partition("): ")
        if not details_separator or not clause_text:
            continue
        response = json.dumps(
            {
                "answer": "The retrieved fictional demo clause states: " + clause_text,
                "cited_clause_ids": [clause_id],
                "advisory_only": True,
            }
        )
        return {prompt: response}

    return {}