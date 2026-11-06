from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from studyflow.database import get_db
from studyflow.security import verify_csrf_token
from studyflow.services.sessions import get_valid_session
from studyflow.settings import settings


def require_csrf(
    studyflow_session: str | None = Cookie(default=None),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    origin: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> None:
    """Reject state-changing requests that do not prove they come from our site."""
    if studyflow_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    if get_valid_session(db, studyflow_session) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    if origin != settings.app_origin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid origin",
        )

    if csrf_token is None or not verify_csrf_token(studyflow_session, csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token",
        )
