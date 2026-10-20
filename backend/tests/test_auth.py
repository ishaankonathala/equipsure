import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.main import app
from app.models import User

PASSWORD = "correct-horse-battery"


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def active_user(session, business):
    user = User(
        id=uuid.uuid4(),
        email="login-user@example.com",
        password_hash=hash_password(PASSWORD),
        full_name="Login User",
        role="POLICYHOLDER",
        business_id=business.id,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def test_password_is_hashed_not_stored_plain():
    hashed = hash_password(PASSWORD)
    assert hashed != PASSWORD
    assert verify_password(PASSWORD, hashed)
    assert not verify_password("wrong", hashed)


def test_login_returns_token(client, active_user):
    response = client.post(
        "/api/auth/login",
        json={"email": "login-user@example.com", "password": PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.access_token_minutes * 60
    assert body["access_token"]


def test_login_wrong_password_returns_401(client, active_user):
    response = client.post(
        "/api/auth/login",
        json={"email": "login-user@example.com", "password": "wrong"},
    )
    assert response.status_code == 401


def test_login_unknown_email_returns_same_401_as_wrong_password(client, active_user):
    wrong_password = client.post(
        "/api/auth/login",
        json={"email": "login-user@example.com", "password": "wrong"},
    )
    unknown_email = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": PASSWORD},
    )
    assert unknown_email.status_code == 401
    assert unknown_email.json() == wrong_password.json()


def test_login_inactive_user_returns_401(client, session, business):
    session.add(User(
        id=uuid.uuid4(),
        email="inactive@example.com",
        password_hash=hash_password(PASSWORD),
        full_name="Inactive",
        role="POLICYHOLDER",
        business_id=business.id,
        is_active=False,
    ))
    session.flush()
    response = client.post(
        "/api/auth/login",
        json={"email": "inactive@example.com", "password": PASSWORD},
    )
    assert response.status_code == 401


def test_me_without_token_returns_401(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_valid_token_returns_user(client, active_user):
    token = create_access_token(
        user_id=str(active_user.id),
        role=active_user.role,
        business_id=str(active_user.business_id),
    )
    response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "login-user@example.com"
    assert "password_hash" not in body


def test_me_with_expired_token_returns_401(client, active_user):
    expired = jwt.encode(
        {
            "sub": str(active_user.id),
            "role": active_user.role,
            "business_id": str(active_user.business_id),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_me_with_tampered_token_returns_401(client, active_user):
    token = create_access_token(
        user_id=str(active_user.id),
        role=active_user.role,
        business_id=str(active_user.business_id),
    )
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert response.status_code == 401


def test_me_with_token_for_deactivated_user_returns_401(client, session, active_user):
    token = create_access_token(
        user_id=str(active_user.id),
        role=active_user.role,
        business_id=str(active_user.business_id),
    )
    active_user.is_active = False
    session.flush()
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401