from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from studyflow.database import get_db
from studyflow.dependencies.auth import get_current_user
from studyflow.models.user import User
from studyflow.schemas.subjects import (
    SubjectCreate,
    SubjectResponse,
    SubjectUpdate,
)
from studyflow.services.subjects import create_subject as create_subject_service
from studyflow.services.subjects import delete_subject as delete_subject_service
from studyflow.services.subjects import get_subject as get_subject_service
from studyflow.services.subjects import get_subjects as get_subjects_service
from studyflow.services.subjects import update_subject as update_subject_service

router = APIRouter(prefix="/subjects", tags=["Subjects"])


@router.post(
    "/",
    response_model=SubjectResponse,
    status_code=201,
)
def create_subject(
    data: SubjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubjectResponse:
    subject = create_subject_service(db=db, user_id=user.id, data=data)
    return subject


@router.get(
    "/",
    response_model=list[SubjectResponse],
)
def get_subjects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SubjectResponse]:
    subjects = get_subjects_service(db=db, user_id=user.id)
    return subjects


@router.get(
    "/{subject_id}",
    response_model=SubjectResponse,
)
def get_subject(
    subject_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubjectResponse:
    subject = get_subject_service(
        db=db,
        user_id=user.id,
        subject_id=subject_id,
    )

    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found",
        )

    return subject


@router.patch(
    "/{subject_id}",
    response_model=SubjectResponse,
)
def update_subject(
    subject_id: UUID,
    data: SubjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubjectResponse:
    subject = update_subject_service(
        db=db,
        user_id=user.id,
        subject_id=subject_id,
        data=data,
    )

    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found",
        )

    return subject


@router.delete(
    "/{subject_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_subject(
    subject_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    try:
        deleted = delete_subject_service(
            db=db,
            user_id=user.id,
            subject_id=subject_id,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a subject that has tasks",
        ) from None

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found",
        )
