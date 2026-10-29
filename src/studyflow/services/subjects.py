from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from studyflow.models.subject import Subject
from studyflow.schemas.subjects import SubjectCreate, SubjectUpdate


def create_subject(db: Session, user_id: UUID, data: SubjectCreate) -> Subject:
    subject: Subject = Subject(
        user_id=user_id,
        name=data.name,
    )

    db.add(subject)
    try:
        db.commit()
        db.refresh(subject)
    except Exception:
        db.rollback()
        raise

    return subject


def get_subjects(db: Session, user_id: UUID) -> list[Subject]:
    statement = select(Subject).where(Subject.user_id == user_id)
    subjects = db.scalars(statement).all()

    return list(subjects)


def get_subject(
    db: Session,
    user_id: UUID,
    subject_id: UUID,
) -> Subject | None:
    statement = select(Subject).where(
        Subject.id == subject_id,
        Subject.user_id == user_id,
    )
    return db.scalar(statement)


def update_subject(
    db: Session,
    user_id: UUID,
    subject_id: UUID,
    data: SubjectUpdate,
) -> Subject | None:
    subject = get_subject(db, user_id, subject_id)

    if subject is None:
        return None

    if "name" in data.model_fields_set:
        if data.name is None:
            raise ValueError("Name cannot be null")
        subject.name = data.name

    try:
        db.commit()
        db.refresh(subject)
    except Exception:
        db.rollback()
        raise

    return subject


def delete_subject(
    db: Session,
    user_id: UUID,
    subject_id: UUID,
) -> bool:
    subject = get_subject(db, user_id, subject_id)

    if subject is None:
        return False

    try:
        db.delete(subject)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return True
