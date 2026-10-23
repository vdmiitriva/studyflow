from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from studyflow.models.user import User
from studyflow.services.sessions import (
    create_session,
    get_valid_session,
    hash_session_token,
    revoke_session,
)


def test_create_session(db_session: Session) -> None:
    user = User(
        email=f"session-test-{uuid4()}@example.com",
    )
    db_session.add(user)
    db_session.flush()

    user_session, token = create_session(db_session, user.id)

    assert user_session.user_id == user.id
    assert user_session.token_hash == hash_session_token(token)
    assert user_session.token_hash != token
    assert len(user_session.token_hash) == 64
    assert user_session.revoked_at is None
    assert user_session.expires_at > user_session.created_at

def test_get_valid_session(db_session: Session) -> None:
    user = User(
        email=f"valid-session-{uuid4()}@example.com",
    )
    db_session.add(user)
    db_session.flush()

    created_session, token = create_session(db_session, user.id)

    found_session = get_valid_session(db_session, token)

    assert found_session is not None
    assert found_session.id == created_session.id
    assert found_session.user_id == user.id
    assert found_session.revoked_at is None

def test_expired_session_is_rejected(db_session: Session) -> None:
    user = User(
        email=f"expired-session-{uuid4()}@example.com",
    )
    db_session.add(user)
    db_session.flush()

    user_session, token = create_session(db_session, user.id)

    user_session.expires_at = datetime.now(UTC) - timedelta(
        minutes=1
    )
    db_session.commit()

    found_session = get_valid_session(db_session, token)

    assert found_session is None

def test_revoked_session_is_rejected(db_session: Session) -> None:
    user = User(
        email=f"revoked-session-{uuid4()}@example.com",
    )
    db_session.add(user)
    db_session.flush()

    user_session, token = create_session(db_session, user.id)

    user_session.revoked_at = datetime.now(UTC)
    db_session.commit()

    found_session = get_valid_session(db_session, token)

    assert found_session is None

def test_unknown_session_token_is_rejected(db_session: Session) -> None:
    unknown_token = "this-token-does-not-exist"

    found_session = get_valid_session(db_session, unknown_token)

    assert found_session is None

def test_revoke_session(db_session: Session) -> None:
    user = User(email=f"revoke-session-{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()

    user_session, token = create_session(db_session, user.id)

    revoke_session(db_session, user_session)

    assert user_session.revoked_at is not None
    assert get_valid_session(db_session, token) is None