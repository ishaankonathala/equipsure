import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models import AIAssessment, PolicyClause


def _make_clause(clause_id="TEST-CL-1", **overrides):
    values = {
        "clause_id": clause_id,
        "category": "COVERAGE",
        "title": "Test clause",
        "summary": "Synthetic test summary.",
        "source_reference": "test-reference",
        "is_fictional": True,
    }
    values.update(overrides)
    return PolicyClause(**values)


def _make_assessment(claim, policyholder_user, **overrides):
    values = {
        "claim_id": claim.id,
        "requested_by_user_id": policyholder_user.id,
        "provider": "fake",
        "prompt_version": "v1",
        "validation_status": "VALID",
        "advisory_only": True,
        "result_json": {},
        "cited_clause_ids": [],
    }
    values.update(overrides)
    return AIAssessment(**values)


def test_clause_insert_succeeds(session, business):
    clause = _make_clause()
    session.add(clause)
    session.flush()

    assert clause.id is not None


def test_clause_id_is_unique(session, business):
    session.add(_make_clause())
    session.flush()

    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(_make_clause())
            session.flush()


def test_clause_rejects_invalid_category(session, business):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(_make_clause(category="OPINION"))
            session.flush()


def test_clause_rejects_non_fictional(session, business):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(_make_clause(is_fictional=False))
            session.flush()


def test_clause_rejects_blank_source_reference(session, business):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(_make_clause(source_reference="   "))
            session.flush()


def test_assessment_insert_succeeds(
    session, business, policy, equipment, claim, policyholder_user
):
    assessment = _make_assessment(claim, policyholder_user)
    session.add(assessment)
    session.flush()

    assert assessment.id is not None


def test_assessment_rejects_advisory_false(
    session, business, policy, equipment, claim, policyholder_user
):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(_make_assessment(claim, policyholder_user, advisory_only=False))
            session.flush()


def test_assessment_rejects_unknown_provider(
    session, business, policy, equipment, claim, policyholder_user
):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(_make_assessment(claim, policyholder_user, provider="openai"))
            session.flush()


def test_assessment_rejects_invalid_validation_status(
    session, business, policy, equipment, claim, policyholder_user
):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(
                _make_assessment(
                    claim,
                    policyholder_user,
                    validation_status="MAYBE",
                )
            )
            session.flush()


def test_assessment_update_is_rejected(
    session, business, policy, equipment, claim, policyholder_user
):
    assessment = _make_assessment(claim, policyholder_user)
    session.add(assessment)
    session.flush()

    with pytest.raises(DBAPIError) as exc_info:
        with session.begin_nested():
            session.execute(
                text(
                    "UPDATE ai_assessments SET validation_status = 'INVALID' "
                    "WHERE id = :id"
                ),
                {"id": assessment.id},
            )
    assert "ai_assessments is append-only" in str(exc_info.value)


def test_assessment_delete_is_rejected(
    session, business, policy, equipment, claim, policyholder_user
):
    assessment = _make_assessment(claim, policyholder_user)
    session.add(assessment)
    session.flush()

    with pytest.raises(DBAPIError) as exc_info:
        with session.begin_nested():
            session.execute(
                text("DELETE FROM ai_assessments WHERE id = :id"),
                {"id": assessment.id},
            )
    assert "ai_assessments is append-only" in str(exc_info.value)


def test_assessment_requires_existing_claim(
    session, business, policy, equipment, policyholder_user
):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(
                _make_assessment(
                    type("ClaimId", (), {"id": uuid.uuid4()})(),
                    policyholder_user,
                )
            )
            session.flush()