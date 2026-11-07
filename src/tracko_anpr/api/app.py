"""The FastAPI application: one process serving the API and, mounted on it, the NiceGUI dashboard.

`create_app` builds the app for a given settings object and (optionally) an engine, so the
tests can run it on SQLite with a temporary storage folder. The engine and session factory
live on `app.state`; routes get a session through `get_session`, one transaction per request.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from tracko_anpr.config import Settings, get_settings
from tracko_anpr.db.session import make_engine, make_session_factory

API_TITLE = "tracko-anpr"


def create_app(settings: Settings | None = None, engine: Engine | None = None, dashboard: bool = True) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(
        title=API_TITLE, version="0.1.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)

    from tracko_anpr.api.routes import router

    app.include_router(router)

    if dashboard:
        from tracko_anpr.dashboard.app import mount_dashboard

        mount_dashboard(app)
    return app


def get_settings_dependency(request: Request) -> Settings:
    return request.app.state.settings


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


def get_session(request: Request) -> Iterator[Session]:
    """One database transaction per request: committed on success, rolled back on an error."""
    session: Session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


SettingsDep = Depends(get_settings_dependency)
SessionDep = Depends(get_session)
EngineDep = Depends(get_engine)
