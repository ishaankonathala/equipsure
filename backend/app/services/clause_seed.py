import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PolicyClause

SOURCE_REFERENCE = (
    "Paraphrased from SBI General Machinery Breakdown Insurance policy wording "
    "(public reference supplied by you); fictional, non-binding demo clause."
)

DEMO_CLAUSES: tuple[dict[str, str], ...] = (
    {
        "clause_id": "DEMO-COV-01",
        "category": "COVERAGE",
        "title": "Sudden physical damage",
        "summary": "Sudden, unforeseen physical damage to listed equipment is covered, subject to the sum insured and the policy terms.",
    },
    {
        "clause_id": "DEMO-EXC-01",
        "category": "EXCLUSION",
        "title": "Wear and tear",
        "summary": "Wear and tear and gradual deterioration of parts are not covered.",
    },
    {
        "clause_id": "DEMO-EXC-02",
        "category": "EXCLUSION",
        "title": "Failure to maintain",
        "summary": "Loss arising from failure to maintain equipment in efficient working order or to follow the manufacturer's operating and maintenance instructions is not covered.",
    },
    {
        "clause_id": "DEMO-EXC-03",
        "category": "EXCLUSION",
        "title": "Consequential loss",
        "summary": "Consequential loss, such as loss of use of the business or other indirect loss, is not covered.",
    },
    {
        "clause_id": "DEMO-REP-01",
        "category": "REPORTING",
        "title": "Prompt notification",
        "summary": "The insured must notify the insurer promptly after an occurrence and provide a completed claim form within fourteen days, otherwise the insurer may not be liable.",
    },
    {
        "clause_id": "DEMO-LIM-01",
        "category": "LIMIT",
        "title": "Minor repairs",
        "summary": "Repairs of minor damage up to Rs. 2,500 may proceed after notification, without prejudice to the insurer's right to inspect the damage.",
    },
)


def seed_demo_clauses(session: Session) -> int:
    inserted = 0
    for clause in DEMO_CLAUSES:
        existing = session.execute(
            select(PolicyClause).where(PolicyClause.clause_id == clause["clause_id"])
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                PolicyClause(
                    id=uuid.uuid4(),
                    **clause,
                    source_reference=SOURCE_REFERENCE,
                    is_fictional=True,
                )
            )
            inserted += 1

    session.flush()
    return inserted