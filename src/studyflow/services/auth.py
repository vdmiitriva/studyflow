from sqlalchemy import select
from sqlalchemy.orm import Session

from studyflow.models.user import User
from studyflow.schemas.auth import RegisterRequest
from studyflow.security import hash_password, verify_password


def register_user(db: Session, data: RegisterRequest) -> User:
    existing_user = db.scalar(select(User).where(User.email == str(data.email)))

    if existing_user is not None:
        raise ValueError("Email is already registered")

    user = User(
        email=str(data.email),
        password_hash=hash_password(data.password),
    )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise

    return user


def authenticate_user(
    db: Session,
    email: str,
    password: str,
) -> User | None:
    user = db.scalar(select(User).where(User.email == email))

    if user is None or user.password_hash is None:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user
