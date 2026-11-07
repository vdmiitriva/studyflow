from uuid import uuid4

import pytest

from studyflow.dependencies.csrf import require_csrf
from studyflow.main import app
from studyflow.models import User
from studyflow.security import create_csrf_token
from studyflow.services.sessions import create_session, revoke_session
from studyflow.settings import settings

TASK_URL = "/api/v1/tasks/"
SUBJECT_URL = "/api/v1/subjects/"

MUTATING_REQUESTS = [
    ("post", TASK_URL, {"title": "Task"}),
    ("patch", f"{TASK_URL}{uuid4()}", {"title": "New"}),
    ("delete", f"{TASK_URL}{uuid4()}", None),
    ("post", SUBJECT_URL, {"name": "Subject"}),
    ("patch", f"{SUBJECT_URL}{uuid4()}", {"name": "New"}),
    ("delete", f"{SUBJECT_URL}{uuid4()}", None),
    ("patch", "/api/v1/auth/me", {"timezone": "Europe/Moscow"}),
]


@pytest.fixture
def real_csrf_client(client):
    """Client with the real CSRF check turned back on."""
    app.dependency_overrides.pop(require_csrf, None)
    return client


def log_in(client, db_session) -> str:
    user = User(email=f"{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()
    _, session_token = create_session(db_session, user.id)
    client.cookies.set("studyflow_session", session_token)
    return session_token


def good_headers(session_token: str) -> dict[str, str]:
    return {
        "Origin": settings.app_origin,
        "X-CSRF-Token": create_csrf_token(session_token),
    }


def send(client, method, url, body, headers):
    return client.request(method, url, json=body, headers=headers)


@pytest.mark.parametrize(("method", "url", "body"), MUTATING_REQUESTS)
def test_mutating_request_without_csrf_token_returns_403(
    real_csrf_client, db_session, method, url, body
):
    log_in(real_csrf_client, db_session)
    headers = {"Origin": settings.app_origin}

    response = send(real_csrf_client, method, url, body, headers)

    assert response.status_code == 403


@pytest.mark.parametrize(("method", "url", "body"), MUTATING_REQUESTS)
def test_mutating_request_with_invalid_csrf_token_returns_403(
    real_csrf_client, db_session, method, url, body
):
    log_in(real_csrf_client, db_session)
    headers = {"Origin": settings.app_origin, "X-CSRF-Token": "not-a-real-token"}

    response = send(real_csrf_client, method, url, body, headers)

    assert response.status_code == 403


@pytest.mark.parametrize(("method", "url", "body"), MUTATING_REQUESTS)
def test_mutating_request_with_foreign_origin_returns_403(
    real_csrf_client, db_session, method, url, body
):
    session_token = log_in(real_csrf_client, db_session)
    headers = good_headers(session_token)
    headers["Origin"] = "https://evil.example"

    response = send(real_csrf_client, method, url, body, headers)

    assert response.status_code == 403


@pytest.mark.parametrize(("method", "url", "body"), MUTATING_REQUESTS)
def test_mutating_request_without_origin_returns_403(
    real_csrf_client, db_session, method, url, body
):
    session_token = log_in(real_csrf_client, db_session)
    headers = good_headers(session_token)
    del headers["Origin"]

    response = send(real_csrf_client, method, url, body, headers)

    assert response.status_code == 403


@pytest.mark.parametrize(("method", "url", "body"), MUTATING_REQUESTS)
def test_mutating_request_without_session_returns_401(
    real_csrf_client, method, url, body
):
    response = send(real_csrf_client, method, url, body, {})

    assert response.status_code == 401


def test_create_task_with_valid_csrf_token_returns_201(real_csrf_client, db_session):
    session_token = log_in(real_csrf_client, db_session)

    response = real_csrf_client.post(
        TASK_URL,
        json={"title": "Prepare project"},
        headers=good_headers(session_token),
    )

    assert response.status_code == 201


def test_create_subject_with_valid_csrf_token_returns_201(real_csrf_client, db_session):
    session_token = log_in(real_csrf_client, db_session)

    response = real_csrf_client.post(
        SUBJECT_URL,
        json={"name": "Math"},
        headers=good_headers(session_token),
    )

    assert response.status_code == 201


def test_read_requests_do_not_need_csrf_token(real_csrf_client, db_session):
    log_in(real_csrf_client, db_session)

    tasks = real_csrf_client.get(TASK_URL)
    subjects = real_csrf_client.get(SUBJECT_URL)

    assert tasks.status_code == 200
    assert subjects.status_code == 200


@pytest.mark.parametrize(("method", "url", "body"), MUTATING_REQUESTS)
def test_mutating_request_with_unknown_session_returns_401(
    real_csrf_client, method, url, body
):
    real_csrf_client.cookies.set("studyflow_session", "unknown-session-token")
    headers = good_headers("unknown-session-token")

    response = send(real_csrf_client, method, url, body, headers)

    assert response.status_code == 401


def test_mutating_request_with_revoked_session_returns_401(
    real_csrf_client, db_session
):
    user = User(email=f"{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()
    user_session, session_token = create_session(db_session, user.id)
    revoke_session(db_session, user_session)
    real_csrf_client.cookies.set("studyflow_session", session_token)

    response = real_csrf_client.post(
        TASK_URL,
        json={"title": "Prepare project"},
        headers=good_headers(session_token),
    )

    assert response.status_code == 401
