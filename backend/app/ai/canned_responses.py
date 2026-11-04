"""Fixed, reviewed answers for the fake AI provider.

These are deterministic, simulated responses. They are not model output.
Only assessment and assistant prompts are answered; anything else returns None.
"""

import json
import re

ASSESSMENT_MARKER = "Assess the claim as an advisory reviewer"
ASSISTANT_MARKER = "Answer the question using ONLY the clauses below"
REVIEW_MARKER = "Explain the policy review for a human officer"
CLAUSE_LINE = re.compile(r"^(DEMO-[A-Z]{3}-\d{2}) \(([A-Z]+)\): ", re.MULTILINE)
SUGGESTED_AMOUNT_LINE = re.compile(r"^Suggested amount:\s*(\S+)", re.MULTILINE)

ASSESSMENT_ANSWER = json.dumps(
    {
        "summary": "Refrigerator reported stopped cooling; the claim is consistent with a sudden breakdown, subject to review.",
        "cited_clause_ids": ["DEMO-COV-01", "DEMO-REP-01"],
        "missing_items": ["Repair estimate"],
        "inconsistencies": [],
        "recommendation": "Request the repair estimate and confirm the incident date before review.",
        "advisory_only": True,
    }
)


def _clause_section(prompt: str) -> str:
    # Only the generated clause lines, before the untrusted question.
    return prompt.split("Question:", 1)[0]


def canned_response_for(prompt: str) -> str | None:
    if ASSESSMENT_MARKER in prompt:
        return ASSESSMENT_ANSWER
    if ASSISTANT_MARKER in prompt:
        match = CLAUSE_LINE.search(_clause_section(prompt))
        if match is None:
            return None
        clause_id = match.group(1)
        return json.dumps(
            {
                "answer": f"The retrieved fictional demo clause {clause_id} is the most relevant to this question. Read it for the stated position.",
                "cited_clause_ids": [clause_id],
                "advisory_only": True,
            }
        )
    if REVIEW_MARKER in prompt:
        match = SUGGESTED_AMOUNT_LINE.search(prompt)
        stated_amount = match.group(1) if match else "0.00"
        checks = [
            line.strip()
            for line in prompt.splitlines()
            if line.startswith("PASS ") or line.startswith("FAIL ")
        ]
        return json.dumps(
            {
                "summary": "Policy review completed. Equipment coverage, active period, billing standing, and required documentation were verified.",
                "checks_commentary": checks[:10] if checks else ["All policy eligibility checks completed."],
                "stated_amount": stated_amount,
                "advisory_only": True,
            }
        )
    return None