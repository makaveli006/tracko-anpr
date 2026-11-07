"""How dashboard pages reach the service layer.

Pages never touch the database or the files themselves: they call functions from
`tracko_anpr.services` through `query`, which gives the function a session of its own in a
worker thread, so a slow query never blocks the web server's event loop. `settings` and
`engine` are set once, when the dashboard is mounted on the FastAPI app.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import run
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from tracko_anpr.config import Settings
from tracko_anpr.db.session import session_scope


class Runtime:
    settings: Settings
    engine: Engine
    factory: sessionmaker[Session]

    def configure(self, settings: Settings, engine: Engine, factory: sessionmaker[Session]) -> None:
        self.settings = settings
        self.engine = engine
        self.factory = factory


runtime = Runtime()


async def query(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run `fn(session, *args, **kwargs)` in a thread with its own transaction and return its result."""

    def work() -> Any:
        with session_scope(runtime.factory) as session:
            return fn(session, *args, **kwargs)

    return await run.io_bound(work)


async def in_thread(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a blocking function (no session) in a thread."""
    return await run.io_bound(fn, *args, **kwargs)
