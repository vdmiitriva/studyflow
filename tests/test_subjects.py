from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from studyflow.models import Subject, Task, User
from studyflow.services.sessions import create_session


def authenticate(
    client: TestClient,
    db_session: Session,
    user: User,
) -> None:
    """Authenticate a user through a server-side session."""
    _, session_token = create_session(db_session, user.id)
    client.cookies.set("studyflow_session", session_token)


def create_user(db_session: Session) -> User:
    """Create a user for an API test."""
    user = User(email=f"user-{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()
    return user


def create_subject(
    db_session: Session,
    user: User,
    name: str = "Математика",
) -> Subject:
    """Create a subject for an API test."""
    subject = Subject(name=name, user_id=user.id)
    db_session.add(subject)
    db_session.flush()
    return subject


# CREATE


def test_create_subject_returns_created_subject(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    authenticate(client, db_session, user)

    response = client.post(
        "/api/v1/subjects/",
        json={"name": "Математика"},
    )

    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Математика"
    assert data["user_id"] == str(user.id)
    assert data["status"] == "active"
    assert "id" in data
    assert "created_at" in data


def test_create_subject_without_authentication_returns_401(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/subjects/",
        json={"name": "Математика"},
    )

    assert response.status_code == 401


def test_create_subject_with_empty_name_returns_422(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    authenticate(client, db_session, user)

    response = client.post(
        "/api/v1/subjects/",
        json={"name": ""},
    )

    assert response.status_code == 422


def test_create_subject_with_name_longer_than_150_chars_returns_422(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    authenticate(client, db_session, user)

    response = client.post(
        "/api/v1/subjects/",
        json={"name": "x" * 151},
    )

    assert response.status_code == 422


def test_create_subject_without_name_returns_422(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    authenticate(client, db_session, user)

    response = client.post("/api/v1/subjects/", json={})

    assert response.status_code == 422


# LIST


def test_list_subjects_returns_only_current_users_subjects(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    another_user = create_user(db_session)

    own_subject = create_subject(db_session, user, "Математика")
    create_subject(db_session, another_user, "Физика")

    authenticate(client, db_session, user)

    response = client.get("/api/v1/subjects/")

    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(own_subject.id)
    assert data[0]["name"] == "Математика"


def test_list_subjects_returns_empty_list_when_user_has_no_subjects(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    authenticate(client, db_session, user)

    response = client.get("/api/v1/subjects/")

    assert response.status_code == 200
    assert response.json() == []


def test_list_subjects_without_authentication_returns_401(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/subjects/")

    assert response.status_code == 401


# READ ONE


def test_get_subject_returns_subject(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    subject = create_subject(db_session, user)
    authenticate(client, db_session, user)

    response = client.get(f"/api/v1/subjects/{subject.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(subject.id)
    assert response.json()["name"] == "Математика"


def test_get_nonexistent_subject_returns_404(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    authenticate(client, db_session, user)

    response = client.get(f"/api/v1/subjects/{uuid4()}")

    assert response.status_code == 404


def test_get_another_users_subject_returns_404(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session)
    another_user = create_user(db_session)
    subject = create_subject(db_session, owner)

    authenticate(client, db_session, another_user)

    response = client.get(f"/api/v1/subjects/{subject.id}")

    assert response.status_code == 404


def test_get_subject_with_invalid_uuid_returns_422(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    authenticate(client, db_session, user)

    response = client.get("/api/v1/subjects/not-a-uuid")

    assert response.status_code == 422


def test_get_subject_without_authentication_returns_401(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    subject = create_subject(db_session, user)

    response = client.get(f"/api/v1/subjects/{subject.id}")

    assert response.status_code == 401


# UPDATE


def test_update_subject_changes_name(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    subject = create_subject(db_session, user)
    db_session.flush()

    authenticate(client, db_session, user)

    response = client.patch(
        f"/api/v1/subjects/{subject.id}",
        json={"name": "Алгоритмы"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Алгоритмы"

    db_session.refresh(subject)
    assert subject.name == "Алгоритмы"


def test_update_subject_with_empty_name_returns_422(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    subject = create_subject(db_session, user)
    authenticate(client, db_session, user)

    response = client.patch(
        f"/api/v1/subjects/{subject.id}",
        json={"name": ""},
    )

    assert response.status_code == 422


def test_update_subject_with_name_longer_than_150_chars_returns_422(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    subject = create_subject(db_session, user)
    authenticate(client, db_session, user)

    response = client.patch(
        f"/api/v1/subjects/{subject.id}",
        json={"name": "x" * 151},
    )

    assert response.status_code == 422


def test_update_subject_with_empty_body_returns_422(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    subject = create_subject(db_session, user)
    authenticate(client, db_session, user)

    response = client.patch(
        f"/api/v1/subjects/{subject.id}",
        json={},
    )

    assert response.status_code == 422


def test_update_nonexistent_subject_returns_404(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    authenticate(client, db_session, user)

    response = client.patch(
        f"/api/v1/subjects/{uuid4()}",
        json={"name": "Алгоритмы"},
    )

    assert response.status_code == 404


def test_update_another_users_subject_returns_404(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session)
    another_user = create_user(db_session)
    subject = create_subject(db_session, owner)

    authenticate(client, db_session, another_user)

    response = client.patch(
        f"/api/v1/subjects/{subject.id}",
        json={"name": "Изменённый предмет"},
    )

    assert response.status_code == 404

    db_session.refresh(subject)
    assert subject.name == "Математика"


def test_update_subject_without_authentication_returns_401(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    subject = create_subject(db_session, user)

    response = client.patch(
        f"/api/v1/subjects/{subject.id}",
        json={"name": "Алгоритмы"},
    )

    assert response.status_code == 401


# DELETE


def test_delete_subject_succeeds(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    subject = create_subject(db_session, user)
    authenticate(client, db_session, user)

    response = client.delete(f"/api/v1/subjects/{subject.id}")

    assert response.status_code == 204
    assert db_session.get(Subject, subject.id) is None


def test_delete_nonexistent_subject_returns_404(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    authenticate(client, db_session, user)

    response = client.delete(f"/api/v1/subjects/{uuid4()}")

    assert response.status_code == 404


def test_delete_another_users_subject_returns_404(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session)
    another_user = create_user(db_session)
    subject = create_subject(db_session, owner)

    authenticate(client, db_session, another_user)

    response = client.delete(f"/api/v1/subjects/{subject.id}")

    assert response.status_code == 404
    assert db_session.get(Subject, subject.id) is not None


def test_delete_subject_with_tasks_returns_conflict(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    subject = create_subject(db_session, user)

    task = Task(
        user_id=user.id,
        subject_id=subject.id,
        title="Подготовить домашнее задание",
    )
    db_session.add(task)
    db_session.flush()

    authenticate(client, db_session, user)

    response = client.delete(f"/api/v1/subjects/{subject.id}")

    assert response.status_code == 409
    assert db_session.get(Subject, subject.id) is not None


def test_delete_subject_without_authentication_returns_401(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    subject = create_subject(db_session, user)

    response = client.delete(f"/api/v1/subjects/{subject.id}")

    assert response.status_code == 401
