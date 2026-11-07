"""Prompt inspector API (roadmap S215).

POST /api/v1/debug/prompt-inspect composes a hypothetical prompt from
stored data and returns its S214 Prompt Trace. Read-only; the trace
never contains prompt content or secrets (S214 safety contract).

Prompt preview (P-059): POST /api/v1/debug/prompt-preview returns the
same inspect result plus an explicit ``prompt_preview`` payload; the
``prompt-inspect`` endpoint can also include it via ``include_preview``.
The preview is a separate owner-scoped payload — the trace itself
still carries no content.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends.capabilities import (
    backend_truth_dict,
    capability_matrix,
)
from runmal.backends.structured import (
    MODES,
    audit_structured_truth,
    structured_matrix,
)
from runmal.db.deps import get_owner_id, get_session
from runmal.prompt.context import (
    context_to_data,
    default_context_template,
    list_context_templates,
    to_story_string,
)
from runmal.prompt.governor import default_policy, policy_to_data
from runmal.prompt.inspect import inspect_prompt
from runmal.prompt.instruct import list_templates, template_to_data
from runmal.prompt.manager import default_layout, layout_to_data
from runmal.prompt.model_profiles import (
    PROFILE_SCHEMA,
    diff_profiles,
    get_profile,
    list_profiles,
    profile_from_data,
    profile_to_data,
)
from runmal.prompt.service import (
    context_echo,
    resolve_context_template,
    resolve_template,
    template_echo,
)

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
    context_template: dict | str | None = None
    context_preset: dict | None = None
    budget_policy: dict | None = None
    structured_output: dict | None = None
    include_preview: bool = False
    backend_key: str | None = None
    model_profile: dict | str | None = None


@router.post("/debug/prompt-inspect")
async def prompt_inspect(
    body: InspectRequest,
    request: Request,
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
            context_template=body.context_template,
            context_preset=body.context_preset,
            budget_policy=body.budget_policy,
            structured_output=body.structured_output,
            include_preview=body.include_preview,
            backend_key=body.backend_key,
            model_profile=body.model_profile,
            plugin_registry=getattr(request.app.state, "plugin_registry", None),
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


@router.post("/debug/prompt-preview")
async def prompt_preview_endpoint(
    body: InspectRequest,
    request: Request,
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
            context_template=body.context_template,
            context_preset=body.context_preset,
            include_preview=True,
            backend_key=body.backend_key,
            budget_policy=body.budget_policy,
            structured_output=body.structured_output,
            model_profile=body.model_profile,
            plugin_registry=getattr(request.app.state, "plugin_registry", None),
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


@router.get("/debug/budget-policy/default")
async def budget_policy_default() -> dict:
    return {"policy": policy_to_data(default_policy()), "source": "default"}


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


@router.get("/debug/context-templates")
async def context_templates() -> dict:
    return {
        "templates": [context_to_data(t) for t in list_context_templates()]
    }


@router.get("/debug/context-templates/default")
async def context_template_default() -> dict:
    template, source = resolve_context_template(None)
    active = template if template is not None else default_context_template()
    return {
        "template": context_echo(active, source),
        "story_string": to_story_string(active),
    }


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


_MODE_FIELDS = {
    "off": [],
    "json_object": [],
    "json_schema": ["schema", "name", "strict"],
    "grammar": ["grammar"],
}


@router.get("/debug/structured-modes")
async def structured_modes() -> dict:
    """Structured-output catalogue + per-backend truth (P-061).

    Metadata only: no declaration is an input to this endpoint,
    so no schema or grammar content can appear in its payload
    (S214). A non-empty ``audit`` list means a truth source
    drifted; it is reported as data, never hidden.
    """
    return {
        "modes": [{"mode": m, "fields": _MODE_FIELDS[m]} for m in MODES],
        "backends": structured_matrix()["backends"],
        "audit": audit_structured_truth(),
    }
@router.get("/debug/model-profiles")
async def model_profiles() -> dict:
    """Builtin model profiles in data form (P-062)."""
    return {
        "schema": PROFILE_SCHEMA,
        "profiles": [profile_to_data(p) for p in list_profiles()],
    }


class ProfileDiffRequest(BaseModel):
    from_profile: dict | str
    to_profile: dict | str


def _coerce_profile(value):
    if isinstance(value, str):
        return get_profile(value)
    return profile_from_data(value)


@router.post("/debug/model-profile-diff")
async def model_profile_diff(body: ProfileDiffRequest) -> dict:
    """What switching between two profiles changes / carries (P-062)."""
    try:
        before = _coerce_profile(body.from_profile)
        after = _coerce_profile(body.to_profile)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return diff_profiles(before, after)
