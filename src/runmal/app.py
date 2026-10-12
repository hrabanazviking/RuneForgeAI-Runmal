"""FastAPI application shell (S102).

Public:  /healthz
Protected (bearer local credential): /api/v1/*
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from runmal import __version__
from runmal.auth import get_or_create_credential, verify_credential

bearer_scheme = HTTPBearer(auto_error=False)


def require_local_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),  # noqa: B008  # FastAPI idiom
) -> None:
    expected = get_or_create_credential()
    presented = credentials.credentials if credentials else ""
    if not verify_credential(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid local credential",
        )


def create_app() -> FastAPI:
    app = FastAPI(title="Rúnmál", version=__version__)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/status", dependencies=[Depends(require_local_auth)])
    def api_status() -> dict[str, str]:
        return {"status": "ok", "version": __version__, "auth": "local"}

    return app
