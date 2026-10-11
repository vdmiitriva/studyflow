from sqlalchemy import select
from sqlalchemy.orm import Session

from studyflow.models.user import User
from studyflow.schemas.auth import RegisterRequest
from studyflow.security import hash_password


def register_user(db: Session, data: RegisterRequest) -> User:
    existing_user = db.scalar(
        select(User).where(User.email == str(data.email))
    )

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