from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from studyflow.models.user import User
from studyflow.schemas.auth import RegisterRequest
from studyflow.security import verify_password
from studyflow.services.auth import authenticate_user, register_user


def test_register_user_success(db_session: Session) -> None:
    email = f"register-{uuid4()}@example.com"
    password = "SecurePassword123!"

    data = RegisterRequest(email=email, password=password)

    user = register_user(db_session, data)

    assert user.email == email
    assert user.password_hash is not None
    assert user.password_hash != password
    assert verify_password(password, user.password_hash)


def test_register_user_duplicate_email(db_session: Session) -> None:
    email = f"duplicate-{uuid4()}@example.com"
    password = "SecurePassword123!"

    data = RegisterRequest(email=email, password=password)
    register_user(db_session, data)

    with pytest.raises(ValueError, match="Email is already registered"):
        register_user(db_session, data)


def test_authenticate_user_success(db_session: Session) -> None:
    email = f"auth-success-{uuid4()}@example.com"
    password = "SecurePassword123!"

    user = register_user(
        db_session,
        RegisterRequest(email=email, password=password),
    )

    authenticated_user = authenticate_user(db_session, email, password)

    assert authenticated_user is not None
    assert authenticated_user.id == user.id


def test_authenticate_user_wrong_password(db_session: Session) -> None:
    email = f"auth-wrong-password-{uuid4()}@example.com"
    password = "SecurePassword123!"

    register_user(
        db_session,
        RegisterRequest(email=email, password=password),
    )

    authenticated_user = authenticate_user(
        db_session,
        email,
        "WrongPassword123!",
    )

    assert authenticated_user is None


def test_authenticate_user_unknown_email(db_session: Session) -> None:
    email = f"unknown-{uuid4()}@example.com"

    authenticated_user = authenticate_user(
        db_session,
        email,
        "SecurePassword123!",
    )

    assert authenticated_user is None


def test_authenticate_user_without_password_hash(
    db_session: Session,
) -> None:
    user = User(
        email=f"no-password-{uuid4()}@example.com",
        password_hash=None,
    )
    db_session.add(user)
    db_session.flush()

    authenticated_user = authenticate_user(
        db_session,
        user.email,
        "SecurePassword123!",
    )

    assert authenticated_user is None


def test_register_user_rolls_back_on_commit_error() -> None:
    db = MagicMock(spec=Session)
    db.scalar.return_value = None
    db.commit.side_effect = RuntimeError("Database error")

    data = RegisterRequest(
        email="rollback@example.com",
        password="SecurePassword123!",
    )

    with pytest.raises(RuntimeError, match="Database error"):
        register_user(db, data)

    db.rollback.assert_called_once()
