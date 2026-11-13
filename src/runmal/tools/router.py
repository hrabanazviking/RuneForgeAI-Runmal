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


class ResolveIn(BaseModel):
    text: str
    char: str = ""
    user: str = "User"
    last_vision_description: str = ""
    chat_id: str = ""


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


@router.get("/tools/variables")
async def variables_tool():
    """The composer's variable registry (S307): chips for the helper UI."""
    from runmal.prompt.variables import list_variables

    return list_variables()


@router.post("/tools/resolve")
async def resolve_tool(body: ResolveIn):
    """Resolve variables in a preview text; unknown ones are flagged."""
    from runmal.prompt.variables import resolve_variables

    vision_text = body.last_vision_description
    if body.chat_id and not vision_text:
        from runmal.prompt.vision_link import last_description_text

        vision_text = last_description_text(body.chat_id)
    result = resolve_variables(
        body.text, char_name=body.char, user_name=body.user,
        last_vision_description=vision_text)
    return result.to_dict()


class MacroIn(BaseModel):
    text: str
    char: str = ""
    user: str = "User"
    persona: str = ""
    model: str = ""
    chat_id: str = ""
    seed: int | None = None
    strict: bool = False
    variables: dict = {}
    roll_context: str = ""


@router.get("/tools/macros")
async def macros_tool():
    """The macro registry (P-055): chips for the helper UI."""
    from runmal.prompt.macros import list_macros

    return list_macros()


@router.post("/tools/macros/expand")
async def macro_expand_tool(body: MacroIn):
    """Expand macros in a preview text (P-055); strict failures are 422s."""
    from runmal.prompt.macros import MacroContext, MacroError, expand_macros

    try:
        result = expand_macros(
            body.text,
            MacroContext(
                char_name=body.char,
                user_name=body.user,
                persona_name=body.persona,
                model=body.model,
                chat_id=body.chat_id,
                seed=body.seed,
                variables=dict(body.variables),
                roll_context=body.roll_context,
            ),
            strict=body.strict,
        )
    except MacroError as exc:
        raise _visible(exc) from exc
    return result.to_dict()
