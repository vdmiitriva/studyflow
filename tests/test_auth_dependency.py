from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from studyflow.dependencies.auth import get_current_user
from studyflow.models.user import User
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
