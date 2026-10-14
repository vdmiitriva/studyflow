
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from studyflow.database import engine
from studyflow.models import Base
from studyflow.settings import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

x_args = context.get_x_argument(as_dictionary=True)

if x_args.get("test_db") == "true":
    test_url = URL.create(
        drivername="postgresql+psycopg",
        username=settings.postgres_user,
        password=settings.postgres_password,
        host="127.0.0.1",
        port=5432,
        database="studyflow_test",
    )

    migration_engine = create_engine(
        test_url,
        pool_pre_ping=True,
    )
else:
    migration_engine = engine


def run_migrations_offline() -> None:
    """Generate migrations without opening a database connection."""
    url = migration_engine.url.render_as_string(hide_password=True)

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using a live database connection."""
    with migration_engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
