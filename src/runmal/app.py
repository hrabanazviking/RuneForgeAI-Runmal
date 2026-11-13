"""FastAPI application shell.

Public:  /healthz, /launcher/bootstrap
Protected (bearer local credential or signed browser session): /api/v1/*
"""

from __future__ import annotations

import hmac

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runmal import __version__
from runmal.auth import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    consume_bootstrap_nonce,
    create_browser_session,
    get_or_create_credential,
    verify_browser_session,
    verify_credential,
)
from runmal.assets.router import router as assets_router
from runmal.backups.router import router as backups_router
from runmal.bridge.router import admin_router as bridge_admin_router
from runmal.bridge.router import router as bridge_router
from runmal.characters.router import router as characters_router
from runmal.chats.router import router as chats_router
from runmal.connections.router import router as connections_router
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.generation.router import router as generation_router
from runmal.groupchat.router import router as group_router
from runmal.hub.router import router as hub_router
from runmal.inspector.router import router as inspector_router
from runmal.library.router import router as library_router
from runmal.lorebooks.router import router as lorebooks_router
from runmal.memory.router import memories_browser_page
from runmal.memory.router import router as memories_router
from runmal.plugins import service as plugin_service
from runmal.plugins.router import router as plugins_router
from runmal.presets.router import router as presets_router
from runmal.prompt.router import router as prompt_router
from runmal.scenarios.router import router as scenarios_router
from runmal.tools.router import router as tools_router
from runmal.voice.router import router as voice_router
from runmal.voice.live import LiveVoiceController
from runmal.voice.live_router import router as live_router
from runmal.voice.projection_router import router as projection_router
from runmal.voice.autoproject_router import router as autoproject_router
from runmal.voice.mishearing_router import router as mishearing_router
from runmal.voice.repeat_router import router as repeat_router
from runmal.voice.router import voice_page
from runmal.vision.router import router as vision_router
from runmal.faces.router import router as faces_router
from runmal.faces.roster_router import router as faces_roster_router
from runmal.faces.speaking_router import router as faces_speaking_router
from runmal.faces.history_router import router as faces_history_router
from runmal.faces.speaking_roster_router import router as faces_speaking_roster_router
from runmal.faces.chats_router import router as faces_chats_router
from runmal.faces.speaking_history_router import router as faces_speaking_history_router
from runmal.faces.character_history_router import router as faces_character_history_router
from runmal.faces.character_speaking_history_router import (
    router as faces_character_speaking_history_router,
)
from runmal.faces.census_router import router as faces_census_router
from runmal.faces.history_census_router import router as faces_history_census_router
from runmal.faces.speaking_chats_router import router as faces_speaking_chats_router
from runmal.faces.speaking_census_router import router as faces_speaking_census_router
from runmal.workspaces.router import router as workspaces_router
from runmal.workspaces.census_router import router as workspaces_census_router
from runmal.workspaces.history_router import router as workspaces_history_router
from runmal.workspaces.folder_census_router import router as workspaces_folder_census_router
from runmal.workspaces.tree_router import router as workspaces_tree_router
from runmal.workspaces.history_census_router import router as workspaces_history_census_router
from runmal.workspaces.search_router import router as workspaces_search_router
from runmal.workspaces.content_search_router import router as workspaces_content_search_router
from runmal.workspaces.tree_census_router import router as workspaces_tree_census_router
from runmal.workspaces.unified_search_router import router as workspaces_unified_search_router
from runmal.workspaces.content_census_router import router as workspaces_content_census_router
from runmal.workspaces.unified_search_census_router import router as workspaces_unified_search_census_router
from runmal.web.router import _HERE as _WEB_DIR
from runmal.web.router import router as web_router

bearer_scheme = HTTPBearer(auto_error=False)
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _same_origin(request: Request) -> bool:
    """Return True only when an unsafe browser request names this exact origin."""
    origin = request.headers.get("origin", "")
    host = request.headers.get("host", "")
    if not origin or not host:
        return False
    expected = f"{request.url.scheme}://{host}"
    return hmac.compare_digest(origin.rstrip("/").lower(), expected.rstrip("/").lower())


def require_local_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    """Accept the original bearer credential or a signed browser session.

    Bearer clients retain the original API contract. Cookie-authenticated browser
    requests get an additional same-origin check for state-changing methods.
    """
    expected = get_or_create_credential()
    presented = credentials.credentials if credentials else ""
    if verify_credential(presented, expected):
        return

    browser_session = request.cookies.get(SESSION_COOKIE_NAME, "")
    if verify_browser_session(browser_session):
        if request.method.upper() in _UNSAFE_METHODS and not _same_origin(request):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid browser origin",
            )
        return

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
    _reg = plugin_service.build_registry()
    _live_controller = LiveVoiceController()
    _live_controller.attach_app(app)
    app.state.live_voice_controller = _live_controller
    plugin_service.set_default_registry(_reg)
    app.state.plugin_registry = _reg

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/launcher/bootstrap")
    def launcher_bootstrap(
        request: Request,
        nonce: str = Query(min_length=32, max_length=256),
    ) -> RedirectResponse:
        """Exchange a one-use launcher nonce for an HttpOnly browser session."""
        if not consume_bootstrap_nonce(nonce):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or expired launcher bootstrap",
            )
        response = RedirectResponse(url="/chat", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=create_browser_session(),
            max_age=SESSION_TTL_SECONDS,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            path="/",
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/v1/status", dependencies=[Depends(require_local_auth)])
    def api_status() -> dict[str, str]:
        return {"status": "ok", "version": __version__, "auth": "local"}

    app.include_router(
        characters_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        assets_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        chats_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        lorebooks_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        library_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        presets_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        scenarios_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        connections_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        tools_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        hub_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        group_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        backups_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        generation_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        memories_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.get("/memories", response_class=HTMLResponse)(memories_browser_page)
    app.include_router(
        voice_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.get("/voice", response_class=HTMLResponse)(voice_page)
    app.include_router(
        live_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        autoproject_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        projection_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        mishearing_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        repeat_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        vision_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        faces_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        faces_roster_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        faces_speaking_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        faces_history_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        faces_speaking_roster_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        faces_chats_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        faces_speaking_history_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        faces_character_history_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        faces_character_speaking_history_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        faces_census_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        faces_history_census_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        faces_speaking_chats_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        faces_speaking_census_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        workspaces_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        workspaces_census_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        workspaces_history_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        workspaces_folder_census_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        workspaces_tree_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        workspaces_history_census_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        workspaces_search_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        workspaces_content_search_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        workspaces_tree_census_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        workspaces_unified_search_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        workspaces_content_census_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        workspaces_unified_search_census_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        prompt_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        inspector_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        plugins_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    app.include_router(
        bridge_admin_router,
        prefix="/api/v1",
        dependencies=[Depends(require_local_auth)],
    )
    # Bridge-facing API: authenticated by scoped bridge tokens only,
    # never by the local credential (S601, INV-029).
    app.include_router(bridge_router, prefix="/api/v1")
    # Browser UI pages contain no permanent secret. API calls remain auth-gated.
    app.include_router(web_router)
    app.mount("/static", StaticFiles(directory=_WEB_DIR / "static"), name="static")
    return app
