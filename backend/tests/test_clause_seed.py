from sqlalchemy import func, select

from app.models import PolicyClause
from app.services.clause_seed import SOURCE_REFERENCE, seed_demo_clauses


def _clause_count(session):
    return session.execute(
        select(func.count()).select_from(PolicyClause)
    ).scalar_one()


def test_seed_inserts_six_clauses(session):
    before = _clause_count(session)

    inserted = seed_demo_clauses(session)

    assert before == 0
    assert inserted == 6
    assert _clause_count(session) == 6


def test_seed_is_idempotent(session):
    seed_demo_clauses(session)

    inserted = seed_demo_clauses(session)

    assert inserted == 0
    assert _clause_count(session) == 6


def test_seeded_clauses_are_fictional(session):
    seed_demo_clauses(session)

    clauses = session.execute(select(PolicyClause)).scalars().all()

    assert all(clause.is_fictional is True for clause in clauses)


def test_seeded_clauses_carry_source_reference(session):
    seed_demo_clauses(session)

    clauses = session.execute(select(PolicyClause)).scalars().all()

    assert all(clause.source_reference == SOURCE_REFERENCE for clause in clauses)


def test_clause_ids_match_approved_list(session):
    seed_demo_clauses(session)

    clause_ids = set(
        session.execute(select(PolicyClause.clause_id)).scalars().all()
    )

    assert clause_ids == {
        "DEMO-COV-01",
        "DEMO-EXC-01",
        "DEMO-EXC-02",
        "DEMO-EXC-03",
        "DEMO-REP-01",
        "DEMO-LIM-01",
    }


def test_seeding_does_not_change_existing_clause(session):
    existing = PolicyClause(
        clause_id="DEMO-COV-01",
        category="COVERAGE",
        title="Edited locally",
        summary="Local test summary.",
        source_reference=SOURCE_REFERENCE,
        is_fictional=True,
    )
    session.add(existing)
    session.flush()

    seed_demo_clauses(session)

    assert existing.title == "Edited locally"
    assert _clause_count(session) == 6