"""FastAPI application shell.

Public:  /healthz
Protected (bearer local credential): /api/v1/*
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runmal import __version__
from runmal.auth import get_or_create_credential, verify_credential
from runmal.characters.router import router as characters_router
from runmal.chats.router import router as chats_router
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

bearer_scheme = HTTPBearer(auto_error=False)


def require_local_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    expected = get_or_create_credential()
    presented = credentials.credentials if credentials else ""
    if not verify_credential(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid local credential",
        )


def default_session_factory() -> async_sessionmaker[AsyncSession]:
    migrate_to_head()
    return create_session_factory(create_db_engine())


def create_app(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> FastAPI:
    app = FastAPI(title="Rúnmál", version=__version__)
    app.state.session_factory = session_factory or default_session_factory()

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/status", dependencies=[Depends(require_local_auth)])
    def api_status() -> dict[str, str]:
        return {"status": "ok", "version": __version__, "auth": "local"}

    app.include_router(
        characters_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        chats_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    return app
