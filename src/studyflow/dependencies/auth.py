from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from studyflow.database import get_db
from studyflow.models.user import User
from studyflow.services.sessions import get_valid_session


def get_current_user(
    studyflow_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )

    if studyflow_session is None:
        raise credentials_exception

    user_session = get_valid_session(db, studyflow_session)

    if user_session is None:
        raise credentials_exception

    user = db.get(User, user_session.user_id)

    if user is None:
        raise credentials_exception

    return user
