from uuid import uuid4

from sqlalchemy.orm import Session

from studyflow.models import Subject, User


def test_user_can_have_subject(db_session: Session) -> None:
    user = User(
        email=f"model-test-{uuid4()}@example.com",
    )
    subject = Subject(
        name="Математика",
        user=user,
    )

    db_session.add(user)
    db_session.add(subject)
    db_session.flush()

    assert subject.user_id == user.id
    assert subject.user is user
    assert subject in user.subjects
