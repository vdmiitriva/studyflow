from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from studyflow.dependencies.auth import get_current_user
from studyflow.models.user import User
from studyflow.schemas.auth import RegisterRequest
from studyflow.services.auth import register_user
from studyflow.services.sessions import create_session


def test_get_current_user_without_cookie(db_session: Session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(studyflow_session=None, db=db_session)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Not authenticated"


def test_get_current_user_with_invalid_session(
    db_session: Session,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(
            studyflow_session="invalid-session-token",
            db=db_session,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Not authenticated"


def test_get_current_user_with_valid_session(
    db_session: Session,
) -> None:
    user = User(email=f"dependency-{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()

    _, session_token = create_session(db_session, user.id)

    current_user = get_current_user(
        studyflow_session=session_token,
        db=db_session,
    )

    assert current_user.id == user.id
    assert current_user.email == user.email


def test_get_current_user_when_user_does_not_exist(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(email=f"deleted-user-{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()

    _, session_token = create_session(db_session, user.id)

    monkeypatch.setattr(
        db_session,
        "get",
        lambda model, user_id: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(
            studyflow_session=session_token,
            db=db_session,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Not authenticated"


def test_register_route_success(client: TestClient) -> None:
    email = f"register-route-{uuid4()}@example.com"
    password = "SecurePassword123!"

    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )

    assert response.status_code == 201
    assert response.json()["email"] == email
    assert "id" in response.json()


def test_register_route_duplicate_email(client: TestClient) -> None:
    email = f"duplicate-route-{uuid4()}@example.com"
    payload = {
        "email": email,
        "password": "SecurePassword123!",
    }

    first_response = client.post(
        "/api/v1/auth/register",
        json=payload,
    )
    second_response = client.post(
        "/api/v1/auth/register",
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Email is already registered"


def test_register_route_integrity_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_integrity_error(*args: object, **kwargs: object) -> None:
        raise IntegrityError(
            "INSERT INTO users",
            {},
            Exception("duplicate key"),
        )

    monkeypatch.setattr(
        "studyflow.routers.auth.register_user",
        raise_integrity_error,
    )

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"integrity-{uuid4()}@example.com",
            "password": "SecurePassword123!",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Email is already registered"


def test_login_route_rejects_wrong_password(
    client: TestClient,
    db_session: Session,
) -> None:
    email = f"login-wrong-{uuid4()}@example.com"
    password = "SecurePassword123!"

    register_user(
        db_session,
        RegisterRequest(email=email, password=password),
    )

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert "studyflow_session" not in response.cookies


def test_login_route_success(
    client: TestClient,
    db_session: Session,
) -> None:
    email = f"login-success-{uuid4()}@example.com"
    password = "SecurePassword123!"

    user = register_user(
        db_session,
        RegisterRequest(email=email, password=password),
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )

    assert response.status_code == 200
    assert response.json()["email"] == email
    assert response.json()["id"] == str(user.id)

    cookie = response.headers["set-cookie"]
    assert "studyflow_session=" in cookie
    assert "httponly" in cookie.lower()
    assert "samesite=lax" in cookie.lower()
    assert response.cookies.get("studyflow_session")


def test_read_current_user_route(
    client: TestClient,
    db_session: Session,
) -> None:
    email = f"me-route-{uuid4()}@example.com"
    password = "SecurePassword123!"

    user = register_user(
        db_session,
        RegisterRequest(email=email, password=password),
    )

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)
    assert response.json()["email"] == email


def test_get_csrf_token_rejects_invalid_session(
    client: TestClient,
) -> None:
    client.cookies.set(
        "studyflow_session",
        "invalid-session-token",
    )

    response = client.get("/api/v1/auth/csrf")

    assert response.status_code == 401
