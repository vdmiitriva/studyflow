from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from studyflow.database import get_db
from studyflow.dependencies.auth import get_current_user
from studyflow.models.user import User
from studyflow.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from studyflow.security import create_csrf_token, verify_csrf_token
from studyflow.services.auth import authenticate_user, register_user
from studyflow.services.sessions import (
    create_session,
    get_valid_session,
    revoke_session,
)
from studyflow.settings import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {
            "description": "Email is already registered",
        },
    },
)
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db),
) -> UserResponse:
    try:
        user = register_user(db, data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        ) from exc

    return UserResponse(id=str(user.id), email=user.email)


@router.post(
    "/login",
    response_model=UserResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Invalid email or password",
        },
    },
)
def login(
    data: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> UserResponse:
    user = authenticate_user(
        db=db,
        email=str(data.email),
        password=data.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    _, token = create_session(db, user.id)

    response.set_cookie(
        key="studyflow_session",
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        max_age=30 * 24 * 60 * 60,
    )

    return UserResponse(id=str(user.id), email=user.email)

@router.get("/me", response_model=UserResponse)
def read_current_user(
    user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
    )

@router.get("/csrf")
def get_csrf_token(
    studyflow_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if studyflow_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user_session = get_valid_session(db, studyflow_session)

    if user_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    csrf_token = create_csrf_token(studyflow_session)

    return {"csrf_token": csrf_token}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    studyflow_session: str | None = Cookie(default=None),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    origin: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Response:
    if studyflow_session is not None:
        user_session = get_valid_session(db, studyflow_session)

        if user_session is not None:
            if origin != settings.app_origin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid origin",
                )

            if csrf_token is None or not verify_csrf_token(
                studyflow_session,
                csrf_token,
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid CSRF token",
                )

            revoke_session(db, user_session)

    response.delete_cookie(
        key="studyflow_session",
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )

    response.status_code = status.HTTP_204_NO_CONTENT
    return response
