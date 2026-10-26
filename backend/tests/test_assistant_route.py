import uuid

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.ai.fake_provider import FakeAIProvider
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Business, ClaimDocument, ClaimEvent, User
from app.services.assistant import build_assistant_prompt, build_assistant_schema_hint
from app.services.assistant_retrieval import retrieve_clauses


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_user(session, email, role, business_id):
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("assistant-route-password"),
        full_name=email,
        role=role,
        business_id=business_id,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _token_for(user):
    return create_access_token(
        user_id=str(user.id),
        role=user.role,
        business_id=str(user.business_id) if user.business_id else None,
    )


def _patch_fake_provider(monkeypatch, question, response_text):
    clauses = retrieve_clauses(question)
    prompt = build_assistant_prompt(question, clauses)
    schema_hint = build_assistant_schema_hint()
    provider = FakeAIProvider({prompt: response_text})
    monkeypatch.setattr(
        "app.api.routes.assistant.build_provider",
        lambda: provider,
    )
    return provider


def _row_count(session, model, claim):
    return session.execute(
        select(func.count()).select_from(model).where(model.claim_id == claim.id)
    ).scalar_one()


def test_signed_in_user_gets_cited_answer(
    client, session, claim, monkeypatch
):
    question = "Is wear and tear covered?"
    provider = _patch_fake_provider(
        monkeypatch,
        question,
        '{"answer":"Wear and tear is not covered.",'
        '"cited_clause_ids":["DEMO-EXC-01"],"advisory_only":true}',
    )
    user = _make_user(session, "assistant-owner@example.com", "OPS", None)

    response = client.post(
        "/api/assistant/ask",
        json={"question": question},
        headers={"Authorization": f"Bearer {_token_for(user)}"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["cited_clause_ids"] == ["DEMO-EXC-01"]
    assert response.json()["advisory_only"] is True
    assert len(provider.calls) == 1


def test_unretrieved_citation_rejected(client, session, claim, monkeypatch):
    question = "Is wear and tear covered?"
    _patch_fake_provider(
        monkeypatch,
        question,
        '{"answer":"Covered.","cited_clause_ids":["DEMO-REP-01"],'
        '"advisory_only":true}',
    )
    user = _make_user(session, "assistant-citation@example.com", "OPS", None)

    response = client.post(
        "/api/assistant/ask",
        json={"question": question},
        headers={"Authorization": f"Bearer {_token_for(user)}"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_advisory_false_rejected(client, session, claim, monkeypatch):
    question = "Is wear and tear covered?"
    _patch_fake_provider(
        monkeypatch,
        question,
        '{"answer":"No.","cited_clause_ids":["DEMO-EXC-01"],'
        '"advisory_only":false}',
    )
    user = _make_user(session, "assistant-advisory@example.com", "OPS", None)

    response = client.post(
        "/api/assistant/ask",
        json={"question": question},
        headers={"Authorization": f"Bearer {_token_for(user)}"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_no_matching_clauses_returns_422(client, session, claim, monkeypatch):
    provider = FakeAIProvider({})
    monkeypatch.setattr(
        "app.api.routes.assistant.build_provider",
        lambda: provider,
    )
    user = _make_user(session, "assistant-no-match@example.com", "OPS", None)

    response = client.post(
        "/api/assistant/ask",
        json={"question": "Tell me a joke about penguins"},
        headers={"Authorization": f"Bearer {_token_for(user)}"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert provider.calls == []


def test_unauthenticated_rejected(client):
    response = client.post(
        "/api/assistant/ask",
        json={"question": "Is wear and tear covered?"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_provider_failure_returns_503(client, session, claim, monkeypatch):
    provider = FakeAIProvider({})
    monkeypatch.setattr(
        "app.api.routes.assistant.build_provider",
        lambda: provider,
    )
    user = _make_user(session, "assistant-provider-failure@example.com", "OPS", None)

    response = client.post(
        "/api/assistant/ask",
        json={"question": "Is wear and tear covered?"},
        headers={"Authorization": f"Bearer {_token_for(user)}"},
    )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_question_stored_nothing(client, session, claim, monkeypatch):
    question = "Is wear and tear covered?"
    _patch_fake_provider(
        monkeypatch,
        question,
        '{"answer":"Wear and tear is not covered.",'
        '"cited_clause_ids":["DEMO-EXC-01"],"advisory_only":true}',
    )
    user = _make_user(session, "assistant-readonly@example.com", "OPS", None)
    events_before = _row_count(session, ClaimEvent, claim)
    documents_before = _row_count(session, ClaimDocument, claim)

    response = client.post(
        "/api/assistant/ask",
        json={"question": question},
        headers={"Authorization": f"Bearer {_token_for(user)}"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert _row_count(session, ClaimEvent, claim) == events_before
    assert _row_count(session, ClaimDocument, claim) == documents_before