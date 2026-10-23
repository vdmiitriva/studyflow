
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from studyflow.database import get_db
from studyflow.main import app
from studyflow.models.user import User
from studyflow.security import create_csrf_token, verify_csrf_token
from studyflow.services.sessions import create_session


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_get_csrf_token_requires_authentication(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/auth/csrf")

    assert response.status_code == 401


def test_get_csrf_token_for_authenticated_user(
    client: TestClient,
    db_session: Session,
) -> None:
    user = User(email=f"csrf-test-{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()

    _, session_token = create_session(db_session, user.id)
    client.cookies.set("studyflow_session", session_token)

    response = client.get("/api/v1/auth/csrf")

    assert response.status_code == 200

    csrf_token = response.json()["csrf_token"]

    assert isinstance(csrf_token, str)
    assert verify_csrf_token(session_token, csrf_token)


def test_logout_rejects_request_without_csrf_token(
    client: TestClient,
    db_session: Session,
) -> None:
    user = User(email=f"logout-test-{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()

    user_session, session_token = create_session(db_session, user.id)
    client.cookies.set("studyflow_session", session_token)

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://127.0.0.1:8000"},
    )

    assert response.status_code == 403

    db_session.refresh(user_session)
    assert user_session.revoked_at is None


def test_logout_rejects_invalid_csrf_token(
    client: TestClient,
    db_session: Session,
) -> None:
    user = User(email=f"logout-invalid-{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()

    user_session, session_token = create_session(db_session, user.id)
    client.cookies.set("studyflow_session", session_token)

    response = client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": "http://127.0.0.1:8000",
            "X-CSRF-Token": "invalid-token",
        },
    )

    assert response.status_code == 403

    db_session.refresh(user_session)
    assert user_session.revoked_at is None


def test_logout_rejects_invalid_origin(
    client: TestClient,
    db_session: Session,
) -> None:
    user = User(email=f"logout-origin-{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()

    user_session, session_token = create_session(db_session, user.id)
    client.cookies.set("studyflow_session", session_token)

    csrf_token = create_csrf_token(session_token)

    response = client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": "https://example.com",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 403

    db_session.refresh(user_session)
    assert user_session.revoked_at is None



def test_logout_succeeds_with_valid_csrf_token(
    client: TestClient,
    db_session: Session,
) -> None:
    user = User(email=f"logout-success-{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()

    user_session, session_token = create_session(db_session, user.id)
    client.cookies.set("studyflow_session", session_token)

    csrf_token = create_csrf_token(session_token)

    response = client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": "http://127.0.0.1:8000",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 204

    db_session.refresh(user_session)
    assert user_session.revoked_at is not None

    set_cookie = response.headers.get("set-cookie", "")
    assert "studyflow_session=" in set_cookie
    assert "Max-Age=0" in set_cookie
