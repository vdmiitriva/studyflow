from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from studyflow.settings import settings


DATABASE_URL = (
    f"postgresql+psycopg://{settings.postgres_user}:"
    f"{settings.postgres_password}@127.0.0.1:5432/"
    f"{settings.postgres_db}"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


from collections.abc import Generator

from sqlalchemy.orm import Session


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
