import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from studyflow.models.user_session import UserSession


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)

def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def create_session(db: Session, user_id: UUID) -> tuple[UserSession, str]:
    now = datetime.now(UTC)
    token = generate_session_token()
    token_hash = hash_session_token(token)

    user_session = UserSession(
        user_id=user_id,
        token_hash=token_hash,
        created_at = now,
        last_activity_at = now,
        expires_at = now + timedelta(days=4)
    )

    db.add(user_session)
    db.commit()
    db.refresh(user_session)

    return user_session, token

def get_valid_session(db: Session, token: str) -> UserSession | None:
    token_hash = hash_session_token(token)

    user_session = db.scalar(
        select(UserSession).where(UserSession.token_hash == token_hash)
    )

    if user_session is None:
        return None

    if user_session.revoked_at is not None:
        return None

    now = datetime.now(UTC)

    if (
        now >= user_session.expires_at
        or now >= user_session.created_at + timedelta(days=30)
    ):
        return None

    user_session.last_activity_at = now
    user_session.expires_at = min(
        now + timedelta(days=4),
        user_session.created_at + timedelta(days=30),
    )

    db.commit()

    return user_session

def revoke_session(db: Session, user_session: UserSession) -> None:
    if user_session.revoked_at is not None:
        return

    user_session.revoked_at = datetime.now(UTC)
    db.commit()

