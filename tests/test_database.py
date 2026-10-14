
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from studyflow.models import User


def test_connection_uses_test_database(db_session: Session) -> None:
    database_name = db_session.execute(
        text("SELECT current_database()")
    ).scalar_one()

    assert database_name == "studyflow_test"


def test_database_changes_can_be_rolled_back(
    db_session: Session,
) -> None:
    user = User(email=f"rollback-{uuid4()}@example.com")
    db_session.add(user)
    db_session.flush()

    user_id = user.id

    # До отката запись существует внутри текущей транзакции.
    result_before = db_session.execute(
        select(User.id).where(User.id == user_id)
    ).scalar_one_or_none()

    assert result_before == user_id

    # Откатываем транзакцию с изменением.
    db_session.rollback()

    # После отката запись должна отсутствовать.
    result_after = db_session.execute(
        select(User.id).where(User.id == user_id)
    ).scalar_one_or_none()

    assert result_after is None
