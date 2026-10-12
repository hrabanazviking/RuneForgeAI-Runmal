"""Prompt tools API (S213): compose preview + session driver.

Impossible prompt states and invalid state-machine transitions surface as
422s with readable detail -- the tools UI shows them verbatim.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from runmal.generation.modes import InvalidTransitionError, PromptChangedError
from runmal.prompt import ImpossiblePromptError
from runmal.tools import service

router = APIRouter(tags=["tools"])


class ComposeIn(BaseModel):
    system: str = ""
    persona: str = ""
    history: list[str] = []
    authors_note: str = ""
    note_depth: int = 0
    context_limit: int = 4096
    reserve_response: int = 512


class SessionActionIn(BaseModel):
    action: str
    session: dict | None = None
    mode: str = "normal"
    messages: list[dict] = []
    content: str = ""
    delta: int = 0


def _visible(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
    )


@router.post("/tools/compose")
async def compose_tool(body: ComposeIn):
    try:
        return service.compose_preview(
            system=body.system,
            persona=body.persona,
            history=body.history,
            authors_note=body.authors_note,
            note_depth=body.note_depth,
            context_limit=body.context_limit,
            reserve_response=body.reserve_response,
        )
    except (ImpossiblePromptError, ValueError) as exc:
        raise _visible(exc) from exc


@router.post("/tools/session")
async def session_tool(body: SessionActionIn):
    try:
        return service.drive_session(
            action=body.action,
            session_data=body.session,
            mode=body.mode,
            messages=body.messages,
            content=body.content,
            delta=body.delta,
        )
    except (InvalidTransitionError, PromptChangedError, ValueError, KeyError) as exc:
        raise _visible(exc) from exc
