"""Web routes (S109).

The chat page itself is public: it carries no secrets (per ADR-0003 the
loopback bind is the boundary; every /api/v1/* route stays bearer-gated).
The page only shows the credential *file path* as a hint — never the secret.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from runmal.auth import CREDENTIAL_FILENAME, data_dir

_HERE = Path(__file__).parent
templates = Jinja2Templates(directory=_HERE / "templates")

router = APIRouter(tags=["web"])


@router.get("/", include_in_schema=False)
async def index():
    return RedirectResponse(url="/chat")


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse(
        request,
        "chat.html",
        {"credential_hint": str(data_dir() / CREDENTIAL_FILENAME)},
    )


@router.get("/connections", response_class=HTMLResponse)
async def connections_page(request: Request):
    return templates.TemplateResponse(
        request,
        "connections.html",
        {"credential_hint": str(data_dir() / CREDENTIAL_FILENAME)},
    )


@router.get("/editor", response_class=HTMLResponse)
async def editor_page(request: Request):
    return templates.TemplateResponse(
        request,
        "editor.html",
        {"credential_hint": str(data_dir() / CREDENTIAL_FILENAME)},
    )


@router.get("/tools", response_class=HTMLResponse)
async def tools_page(request: Request):
    return templates.TemplateResponse(
        request,
        "tools.html",
        {"credential_hint": str(data_dir() / CREDENTIAL_FILENAME)},
    )


@router.get("/gallery", response_class=HTMLResponse)
async def gallery_page(request: Request):
    return templates.TemplateResponse(
        request,
        "gallery.html",
        {"credential_hint": str(data_dir() / CREDENTIAL_FILENAME)},
    )


@router.get("/lorebooks", response_class=HTMLResponse)
async def lorebooks_page(request: Request):
    return templates.TemplateResponse(
        request,
        "lorebooks.html",
        {"credential_hint": str(data_dir() / CREDENTIAL_FILENAME)},
    )
