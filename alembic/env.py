import os
import sys
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url
from alembic import context

# Make sure `app` package is importable when running alembic from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Load .env so migrations can access os.environ directly (pydantic-settings
# populates Settings attributes but does not set os.environ).
load_dotenv()

from app.core.config import settings
from app.models.base import Base

# Import every model module so Alembic can see its tables in autogenerate.
# Add new model imports here as you create them.
from app.models import assessment, badge_notification, conversation, exercise, journal, mood, notification_preference, safety_plan, subscription, system_error, thought_record, user, wellness  # noqa: F401

# Alembic Config object — gives access to alembic.ini values
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata Alembic will diff against the DB to detect schema changes
target_metadata = Base.metadata

# Alembic autogenerate is synchronous — it cannot use asyncpg.
# make_url().set() swaps only the driver, leaving credentials/host/db intact.
# The app uses asyncpg at runtime; Alembic uses psycopg2 only here.
sync_url = make_url(settings.DATABASE_URL).set(drivername="postgresql+psycopg2")


def run_migrations_offline() -> None:
    """Run migrations without connecting — just emits SQL to stdout."""
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live DB connection."""
    connectable = create_engine(sync_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
