"""Prompt inspector API (roadmap S215).

POST /api/v1/debug/prompt-inspect composes a hypothetical prompt from
stored data and returns its S214 Prompt Trace. Read-only; the trace
never contains prompt content or secrets (S214 safety contract).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends.capabilities import (
    backend_truth_dict,
    capability_matrix,
)
from runmal.db.deps import get_owner_id, get_session
from runmal.prompt.inspect import inspect_prompt
from runmal.prompt.manager import default_layout, layout_to_data
from runmal.prompt.instruct import list_templates, template_to_data
from runmal.prompt.service import resolve_template, template_echo

router = APIRouter(tags=["debug"])


class InspectRequest(BaseModel):
    character_id: str | None = None
    chat_id: str | None = None
    persona_character_id: str | None = None
    lorebook_ids: list[str] = Field(default_factory=list)
    include_activation_inspection: bool = False
    messages: list[str] = Field(default_factory=list)
    context_limit: int = Field(default=4096, ge=64)
    reserve_response: int = Field(default=512, ge=0)
    prompt_layout: dict | None = None
    model_id: str | None = None
    instruct_template: dict | str | None = None


@router.post("/debug/prompt-inspect")
async def prompt_inspect(
    body: InspectRequest,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
) -> dict:
    try:
        result = await inspect_prompt(
            session,
            owner_id,
            character_id=body.character_id,
            chat_id=body.chat_id,
            persona_character_id=body.persona_character_id,
            lorebook_ids=body.lorebook_ids,
            include_activation_inspection=body.include_activation_inspection,
            messages=body.messages,
            context_limit=body.context_limit,
            reserve_response=body.reserve_response,
            prompt_layout=body.prompt_layout,
            model_id=body.model_id,
            instruct_template=body.instruct_template,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="character or lorebook not found",
        )
    return result


@router.get("/debug/prompt-manager/default")
async def prompt_manager_default() -> dict:
    return {"blocks": layout_to_data(default_layout())["blocks"], "source": "default"}


@router.get("/debug/instruct-templates")
async def instruct_templates() -> dict:
    return {"templates": [template_to_data(t) for t in list_templates()]}


@router.get("/debug/instruct-templates/default")
async def instruct_template_default(model: str | None = None) -> dict:
    template, source = resolve_template(None, model)
    return {"template": template_echo(template, source), "model": model}


@router.get("/debug/backend-capabilities")
async def backend_capabilities() -> dict:
    """Per-backend capability truth for every chat backend (P-053).

    The UI renders sampler greying from these rows and nothing else:
    ``available`` controls may be offered enabled, ``greyed`` controls
    are shown disabled with their reason, and nothing else is offered
    at all. A non-empty ``audit`` list means a truth source drifted;
    it is reported as data in this payload, never hidden.
    """
    return capability_matrix()


@router.get("/debug/backend-capabilities/{backend_key}")
async def backend_capability(backend_key: str,
                             aesir_route: str = "openai-chat") -> dict:
    """Capability truth for one backend's default model (P-053)."""
    try:
        return backend_truth_dict(backend_key, aesir_route=aesir_route)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
