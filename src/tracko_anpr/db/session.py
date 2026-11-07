"""Connecting to the database.

The URL comes from `Settings.database_url` (built from the POSTGRES_* variables in `.env`).
`make_engine` is called once per process; `session_scope` gives a transaction that commits on
success and rolls back on an exception.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker


class DatabaseUnavailable(RuntimeError):
    """The database cannot be reached. The message says what to check."""


def make_engine(database_url: str, **kwargs) -> Engine:
    """An engine for the given URL. `pool_pre_ping` drops connections the server has closed."""
    return create_engine(database_url, pool_pre_ping=True, **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """One transaction: committed when the block finishes, rolled back if it raises."""
    session = factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def check_connection(engine: Engine) -> None:
    """Raise `DatabaseUnavailable` with a plain explanation when the database cannot be reached."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as error:
        raise DatabaseUnavailable(
            f"Cannot reach the database at {engine.url.render_as_string(hide_password=True)}. "
            "Is the PostgreSQL container running (docker compose up -d), and does .env hold the right password? "
            f"({error.orig})"
        ) from error


def current_revision(engine: Engine) -> str | None:
    """The Alembic revision the database is at, or None when it has never been migrated."""
    with engine.connect() as connection:
        has_table = engine.dialect.has_table(connection, "alembic_version")
        if not has_table:
            return None
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
