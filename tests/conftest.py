from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import Session

from studyflow.settings import settings


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    test_url = URL.create(
        drivername="postgresql+psycopg",
        username=settings.postgres_user,
        password=settings.postgres_password,
        host="127.0.0.1",
        port=5432,
        database="studyflow_test",
    )

    if test_url.database != "studyflow_test":
        raise RuntimeError("Tests must use studyflow_test database")

    engine = create_engine(test_url, pool_pre_ping=True)

    try:
        with engine.connect() as connection:
            database_name = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()

            if database_name != "studyflow_test":
                raise RuntimeError(
                    f"Unexpected test database: {database_name}"
                )

        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(test_engine: Engine) -> Iterator[Session]:
    with test_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
        )

        try:
            yield session
        finally:
            session.close()
            transaction.rollback()
