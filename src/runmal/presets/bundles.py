"""Preset bundles (P-054): sampler+prompt bundles, shared honestly.

Roadmap line: *Presets: save/load/share sampler+prompt bundles;
per-character and per-chat overrides.*

Until P-054 a Rúnmál preset was a sampler bag plus a template
reference (S207). The prompt side lived elsewhere as data with no
stored home: a layout (P-049), an instruct selection (P-050) and
a context selection (P-051) could each be supplied per request
but never saved together, never shared, and never overridden per
character or per chat. A bundle is that gathering, as validated
data:

- ``sampler`` — the S207/P-052 parameter bag, validated by
  :func:`runmal.presets.service.validate_params` (canonical keys
  type/range-checked; unknown keys preserved verbatim).
- ``prompt_layout`` — a P-049 layout, validated by
  ``layout_from_data`` and stored in its normalised complete
  form (``layout_to_data``), or None.
- ``instruct_template`` / ``context_template`` — a SELECTION:
  ``{"kind": "builtin", "name": ...}`` (the registry stays the
  truth for the template's data; only the name is carried), or
  ``{"kind": "custom", "template": {...}}`` carrying the full
  validated data form, or for context templates also
  ``{"kind": "story_string", "text": ...}``. None = no
  selection in play.
- ``template_ref`` — the legacy S207 prompt-template reference,
  carried for compatibility.
- ``structured_output`` — a P-061 structured-output declaration,
  validated by ``structured_from_data`` and stored in its
  normalised form (``structured_to_data``), or None.
- ``prompts`` / ``prompt_order`` — the P-021 carriage, verbatim.
- ``extensions`` — every OTHER top-level key of an incoming
  bundle, preserved verbatim. Foreign fields are carried, never
  silently dropped (the campaign's standing honesty lesson);
  they ride save/load and share round trips untouched.

Malformed KNOWN sections refuse cleanly (ValueError): a bad
sampler value, an unknown layout block, an unknown builtin name
or a malformed custom template is a bundle that would lie about
what it carries, so it is never stored. Normalisation is a fixed
point: validating a validated bundle returns it unchanged, and
storage uses canonical JSON (sorted keys, compact separators),
so a loaded bundle is value-identical to what was saved.

Overrides: a :class:`PresetOverride` row assigns one bundle to
one character or chat with a PARTIAL delta (any subset of the
bundle's sections). Resolution layers bundle base < character
delta < chat delta. The sampler merges key-wise (a delta key set
to null DELETES the base key — an explicit, recorded removal);
structural selections replace wholesale when present (null
clears the selection). The resolved view reports the SOURCE of
every field — provenance is data, never silent.

Sharing: :func:`build_share` wraps a bundle in the P-045-style
envelope (manifest + SHA-256 over the canonical normalised
bundle + provenance with unknown facts omitted, never
fabricated); :func:`parse_share` re-normalises and verifies the
checksum before anything is stored, so a tampered or truncated
share refuses instead of importing a quietly different bundle.

Persistence is migration 0033 (this slice owns it, per the
P-049/P-051 follow-up note): bundles and overrides are durable
named user data, so they live in tables, not only in files; the
share envelope is the file form of the same canonical bundle.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends.structured import structured_from_data, structured_to_data
from runmal.db.models import Character, Chat, PresetBundle, PresetOverride
from runmal.presets.service import validate_params
from runmal.prompt.context import context_from_data, get_context_template
from runmal.prompt.instruct import get_template, template_from_data
from runmal.prompt.manager import layout_from_data, layout_to_data

__all__ = [
    "BUNDLE_SCHEMA", "SHARE_FORMAT", "SHARE_VERSION",
    "SCOPE_CHARACTER", "SCOPE_CHAT", "SCOPE_KINDS",
    "BundleError", "canonical_json", "validate_bundle",
    "validate_overrides", "merge_bundle", "build_share",
    "parse_share", "bundle_to_dict", "override_to_dict",
    "create_bundle", "list_bundles", "get_bundle",
    "update_bundle", "delete_bundle", "import_bundle",
    "set_override", "get_override", "list_overrides",
    "delete_override", "resolve_effective",
]

BUNDLE_SCHEMA = "runmal-p054-preset-bundle-v1"
SHARE_FORMAT = "runmal-preset-bundle"
SHARE_VERSION = 1
SCOPE_CHARACTER = "character"
SCOPE_CHAT = "chat"
SCOPE_KINDS = frozenset({SCOPE_CHARACTER, SCOPE_CHAT})

_KNOWN_KEYS = frozenset({
    "name", "sampler", "prompt_layout", "instruct_template",
    "context_template", "template_ref", "prompts", "prompt_order",
    "extensions", "structured_output",
})
_SECTION_KEYS = (
    "sampler", "prompt_layout", "instruct_template",
    "context_template", "template_ref", "structured_output",
)


class BundleError(ValueError):
    """A bundle, override or share envelope is malformed."""


def _now() -> datetime:
    return datetime.now(UTC)


def canonical_json(data: object) -> str:
    """Canonical JSON: sorted keys, compact separators."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _json_safe(value: object, what: str) -> object:
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise BundleError(f"{what} is not JSON-serializable") from exc
    return copy.deepcopy(value)


def _validate_selection(value: object, kind_label: str) -> dict | None:
    """Validate one template selection; None passes through."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise BundleError(f"{kind_label} selection must be an object or null")
    kind = value.get("kind")
    if kind == "builtin":
        name = value.get("name")
        if not isinstance(name, str) or not name:
            raise BundleError(f"{kind_label} builtin selection needs a name")
        try:
            if kind_label == "instruct_template":
                get_template(name)
            else:
                get_context_template(name)
        except ValueError as exc:
            raise BundleError(str(exc)) from exc
        extra = set(value) - {"kind", "name"}
        if extra:
            raise BundleError(f"{kind_label} builtin selection has unknown keys: {sorted(extra)}")
        return {"kind": "builtin", "name": name}
    if kind == "custom":
        template = value.get("template")
        extra = set(value) - {"kind", "template"}
        if extra:
            raise BundleError(f"{kind_label} custom selection has unknown keys: {sorted(extra)}")
        try:
            if kind_label == "instruct_template":
                from runmal.prompt.instruct import template_to_data
                return {"kind": "custom", "template": template_to_data(template_from_data(template))}
            from runmal.prompt.context import context_to_data
            return {"kind": "custom", "template": context_to_data(context_from_data(template))}
        except ValueError as exc:
            raise BundleError(str(exc)) from exc
    if kind == "story_string" and kind_label == "context_template":
        text = value.get("text")
        if not isinstance(text, str) or "{{" not in text:
            raise BundleError("context story_string selection needs text with a {{placeholder}}")
        extra = set(value) - {"kind", "text"}
        if extra:
            raise BundleError(f"{kind_label} story_string selection has unknown keys: {sorted(extra)}")
        from runmal.prompt.context import from_story_string
        try:
            from_story_string(text)
        except ValueError as exc:
            raise BundleError(str(exc)) from exc
        return {"kind": "story_string", "text": text}
    raise BundleError(f"{kind_label} selection kind is unknown: {kind!r}")


def validate_bundle(data: object) -> dict:
    """Validate + normalise a bundle; return the canonical dict.

    Fixed point: validate_bundle(validate_bundle(x)) == validate_bundle(x).
    Unknown top-level keys are preserved under ``extensions``;
    an explicit ``extensions`` object merges with them (explicit
    extensions win on a key clash, and the clash is still carried,
    never dropped silently — the merged value IS the record).
    """
    if not isinstance(data, dict):
        raise BundleError("bundle must be an object")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise BundleError("bundle name must be a non-empty string")
    try:
        sampler = validate_params(data.get("sampler") or {})
    except ValueError as exc:
        raise BundleError(str(exc)) from exc
    layout = data.get("prompt_layout")
    if layout is not None:
        try:
            layout = layout_to_data(layout_from_data(layout))
        except ValueError as exc:
            raise BundleError(str(exc)) from exc
    structured = data.get("structured_output")
    if structured is not None:
        try:
            structured = structured_to_data(structured_from_data(structured))
        except ValueError as exc:
            raise BundleError(str(exc)) from exc
    instruct = _validate_selection(data.get("instruct_template"), "instruct_template")
    context = _validate_selection(data.get("context_template"), "context_template")
    template_ref = data.get("template_ref", "")
    if not isinstance(template_ref, str):
        raise BundleError("template_ref must be a string")
    prompts = data.get("prompts", [])
    prompt_order = data.get("prompt_order", [])
    if not isinstance(prompts, list) or not isinstance(prompt_order, list):
        raise BundleError("prompts and prompt_order must be lists")
    _json_safe(prompts, "prompts")
    _json_safe(prompt_order, "prompt_order")
    extensions: dict = {}
    raw_ext = data.get("extensions", {})
    if not isinstance(raw_ext, dict):
        raise BundleError("extensions must be an object")
    extensions.update(_json_safe(raw_ext, "extensions"))
    for key, value in data.items():
        if key not in _KNOWN_KEYS:
            extensions[key] = _json_safe(value, f"extension {key!r}")
    return {
        "name": name,
        "sampler": sampler,
        "prompt_layout": layout,
        "instruct_template": instruct,
        "context_template": context,
        "structured_output": structured,
        "template_ref": template_ref,
        "prompts": copy.deepcopy(prompts),
        "prompt_order": copy.deepcopy(prompt_order),
        "extensions": extensions,
    }


def validate_overrides(data: object) -> dict:
    """Validate a partial override delta; return the normalised delta.

    Unlike bundles, overrides are authored against the bundle
    schema: unknown keys REFUSE (a typo must fail loudly, not be
    carried as a phantom extension). A sampler value of null for
    a key is kept as null — merge reads it as an explicit
    deletion of the base key.
    """
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise BundleError("overrides must be an object")
    unknown = set(data) - set(_SECTION_KEYS)
    if unknown:
        raise BundleError(f"unknown override keys: {sorted(unknown)}")
    out: dict = {}
    if "sampler" in data:
        raw = data["sampler"]
        if not isinstance(raw, dict):
            raise BundleError("override sampler must be an object")
        kept: dict = {}
        non_null = {k: v for k, v in raw.items() if v is not None}
        try:
            validated = validate_params(non_null)
        except ValueError as exc:
            raise BundleError(str(exc)) from exc
        for key in raw:
            kept[key] = None if raw[key] is None else validated[key]
        out["sampler"] = kept
    if "prompt_layout" in data:
        layout = data["prompt_layout"]
        if layout is not None:
            try:
                layout = layout_to_data(layout_from_data(layout))
            except ValueError as exc:
                raise BundleError(str(exc)) from exc
        out["prompt_layout"] = layout
    if "structured_output" in data:
        raw_structured = data["structured_output"]
        if raw_structured is not None:
            try:
                raw_structured = structured_to_data(
                    structured_from_data(raw_structured))
            except ValueError as exc:
                raise BundleError(str(exc)) from exc
        out["structured_output"] = raw_structured
    if "instruct_template" in data:
        out["instruct_template"] = _validate_selection(data["instruct_template"], "instruct_template")
    if "context_template" in data:
        out["context_template"] = _validate_selection(data["context_template"], "context_template")
    if "template_ref" in data:
        if not isinstance(data["template_ref"], str):
            raise BundleError("override template_ref must be a string")
        out["template_ref"] = data["template_ref"]
    return out


def merge_bundle(base: dict, *deltas: dict) -> tuple[dict, dict]:
    """Layer validated deltas over a validated bundle.

    Returns (effective_bundle, sources): sources maps each section
    to the layer that last set it ('bundle' | 'character' |
    'chat', positional: deltas are applied in the order given and
    labelled by the caller via merge_layers — this helper labels
    them delta1, delta2...; resolve_effective relabels). Sampler
    sources are per-key.
    """
    effective = copy.deepcopy(base)
    sources: dict = {"sampler": {k: "bundle" for k in base["sampler"]}}
    for key in ("prompt_layout", "instruct_template", "context_template", "template_ref",
     "structured_output"):
        sources[key] = "bundle"
    for idx, delta in enumerate(deltas):
        label = f"delta{idx + 1}"
        if "sampler" in delta:
            for key, value in delta["sampler"].items():
                if value is None:
                    effective["sampler"].pop(key, None)
                    sources["sampler"].pop(key, None)
                else:
                    effective["sampler"][key] = copy.deepcopy(value)
                    sources["sampler"][key] = label
        for key in ("prompt_layout", "instruct_template", "context_template", "template_ref",
     "structured_output"):
            if key in delta:
                effective[key] = copy.deepcopy(delta[key])
                sources[key] = label
    return effective, sources


# ---------------- sharing envelope ----------------

def _content_hash(bundle: dict) -> str:
    return hashlib.sha256(canonical_json(bundle).encode("utf-8")).hexdigest()


def build_share(bundle: dict, *, exported_at: str | None = None, app_version: str | None = None) -> dict:
    """Wrap a bundle in its share envelope (validates first)."""
    normalised = validate_bundle(bundle)
    stamp = exported_at or _now().isoformat()
    digest = _content_hash(normalised)
    manifest = {
        "bundle_name": normalised["name"],
        "content_sha256": digest,
        "canonical_bytes": len(canonical_json(normalised).encode("utf-8")),
        "exported_at": stamp,
    }
    if app_version:
        manifest["app_version"] = app_version
    provenance: dict = {
        "provenance_version": 1,
        "source_kind": "preset_bundle_export",
        "source_bundle_name": normalised["name"],
        "exported_at": stamp,
        "content_sha256": digest,
    }
    if app_version:
        provenance["app_version"] = app_version
    return {
        "format": SHARE_FORMAT,
        "bundle_version": SHARE_VERSION,
        "kind": "preset_bundle",
        "schema": BUNDLE_SCHEMA,
        "manifest": manifest,
        "provenance": provenance,
        "bundle": normalised,
    }


def parse_share(data: object) -> tuple[dict, dict]:
    """Parse a share envelope OR a bare bundle object.

    Returns (normalised_bundle, report). An envelope's checksum
    is verified over the RE-NORMALISED carried bundle: cosmetic
    re-serialisation never invalidates, content tampering always
    refuses. The report names what was preserved (extension keys,
    carriage sizes) so preservation is checkable, not assumed.
    """
    if not isinstance(data, dict):
        raise BundleError("share payload must be an object")
    if data.get("format") == SHARE_FORMAT or "bundle" in data and "manifest" in data:
        if data.get("format") != SHARE_FORMAT:
            raise BundleError(f"unknown share format: {data.get('format')!r}")
        if data.get("bundle_version") != SHARE_VERSION:
            raise BundleError(f"unsupported bundle_version: {data.get('bundle_version')!r}")
        manifest = data.get("manifest")
        if not isinstance(manifest, dict) or not isinstance(manifest.get("content_sha256"), str):
            raise BundleError("share manifest is missing its content_sha256")
        normalised = validate_bundle(data.get("bundle"))
        digest = _content_hash(normalised)
        if digest != manifest["content_sha256"]:
            raise BundleError("share checksum mismatch: bundle content was altered")
        report = {
            "via": "share_envelope",
            "checksum_verified": True,
            "extension_keys": sorted(normalised["extensions"]),
            "prompts_carried": len(normalised["prompts"]),
            "prompt_order_carried": len(normalised["prompt_order"]),
        }
        return normalised, report
    normalised = validate_bundle(data)
    report = {
        "via": "bare_bundle",
        "checksum_verified": False,
        "extension_keys": sorted(normalised["extensions"]),
        "prompts_carried": len(normalised["prompts"]),
        "prompt_order_carried": len(normalised["prompt_order"]),
    }
    return normalised, report


# ---------------- persistence ----------------

def bundle_to_dict(row: PresetBundle) -> dict:
    bundle = json.loads(row.bundle_json)
    return {
        "id": row.id,
        "name": row.name,
        "bundle": bundle,
        "created_at": row.created_at.isoformat() if hasattr(row.created_at, "isoformat") else row.created_at,
        "updated_at": row.updated_at.isoformat() if row.updated_at and hasattr(row.updated_at, "isoformat") else row.updated_at,
    }


def override_to_dict(row: PresetOverride) -> dict:
    return {
        "id": row.id,
        "bundle_id": row.bundle_id,
        "scope_kind": row.scope_kind,
        "owner_id": row.owner_id,
        "overrides": json.loads(row.overrides_json),
        "created_at": row.created_at.isoformat() if hasattr(row.created_at, "isoformat") else row.created_at,
        "updated_at": row.updated_at.isoformat() if row.updated_at and hasattr(row.updated_at, "isoformat") else row.updated_at,
    }


async def _get_owned_bundle(session: AsyncSession, user_id: str, bundle_id: str) -> PresetBundle | None:
    result = await session.execute(
        select(PresetBundle).where(PresetBundle.id == bundle_id, PresetBundle.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def create_bundle(session: AsyncSession, user_id: str, data: object) -> PresetBundle:
    normalised = validate_bundle(data)
    row = PresetBundle(user_id=user_id, name=normalised["name"], bundle_json=canonical_json(normalised))
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise BundleError(f"bundle name already exists: {normalised['name']!r}") from exc
    return row


async def list_bundles(session: AsyncSession, user_id: str) -> list[PresetBundle]:
    result = await session.execute(
        select(PresetBundle).where(PresetBundle.user_id == user_id).order_by(PresetBundle.name)
    )
    return list(result.scalars().all())


async def get_bundle(session: AsyncSession, user_id: str, bundle_id: str) -> PresetBundle | None:
    return await _get_owned_bundle(session, user_id, bundle_id)


async def update_bundle(session: AsyncSession, user_id: str, bundle_id: str, data: object) -> PresetBundle | None:
    row = await _get_owned_bundle(session, user_id, bundle_id)
    if row is None:
        return None
    normalised = validate_bundle(data)
    row.name = normalised["name"]
    row.bundle_json = canonical_json(normalised)
    row.updated_at = _now()
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise BundleError(f"bundle name already exists: {normalised['name']!r}") from exc
    return row


async def delete_bundle(session: AsyncSession, user_id: str, bundle_id: str) -> bool:
    if await _get_owned_bundle(session, user_id, bundle_id) is None:
        return False
    await session.execute(delete(PresetBundle).where(PresetBundle.id == bundle_id))
    await session.commit()
    return True


async def import_bundle(session: AsyncSession, user_id: str, data: object, name: str | None = None) -> tuple[PresetBundle, dict]:
    normalised, report = parse_share(data)
    if name:
        normalised = validate_bundle({**normalised, "name": name})
    row = await create_bundle(session, user_id, normalised)
    return row, report


# ---------------- overrides + resolution ----------------

async def _owner_exists(session: AsyncSession, user_id: str, scope_kind: str, owner_id: str) -> bool:
    model = Character if scope_kind == SCOPE_CHARACTER else Chat
    result = await session.execute(
        select(model.id).where(model.id == owner_id, model.user_id == user_id)
    )
    return result.scalar_one_or_none() is not None


async def set_override(
    session: AsyncSession, user_id: str, scope_kind: str, owner_id: str,
    bundle_id: str, overrides: object,
) -> PresetOverride | None:
    """Assign a bundle to a character/chat with a delta (upsert).

    Returns None when the bundle or the owner is not the caller's
    (indistinguishable from nonexistent, the house pattern).
    """
    if scope_kind not in SCOPE_KINDS:
        raise BundleError(f"unknown scope_kind: {scope_kind!r}")
    normalised = validate_overrides(overrides)
    if await _get_owned_bundle(session, user_id, bundle_id) is None:
        return None
    if not await _owner_exists(session, user_id, scope_kind, owner_id):
        return None
    result = await session.execute(
        select(PresetOverride).where(
            PresetOverride.scope_kind == scope_kind,
            PresetOverride.owner_id == owner_id,
            PresetOverride.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = PresetOverride(
            user_id=user_id, bundle_id=bundle_id, scope_kind=scope_kind,
            owner_id=owner_id, overrides_json=canonical_json(normalised),
        )
        session.add(row)
    else:
        row.bundle_id = bundle_id
        row.overrides_json = canonical_json(normalised)
        row.updated_at = _now()
    await session.commit()
    return row


async def _get_override_row(session: AsyncSession, user_id: str, scope_kind: str, owner_id: str) -> PresetOverride | None:
    result = await session.execute(
        select(PresetOverride).where(
            PresetOverride.scope_kind == scope_kind,
            PresetOverride.owner_id == owner_id,
            PresetOverride.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_override(session: AsyncSession, user_id: str, scope_kind: str, owner_id: str) -> PresetOverride | None:
    if scope_kind not in SCOPE_KINDS:
        raise BundleError(f"unknown scope_kind: {scope_kind!r}")
    return await _get_override_row(session, user_id, scope_kind, owner_id)


async def list_overrides(session: AsyncSession, user_id: str) -> list[PresetOverride]:
    result = await session.execute(
        select(PresetOverride).where(PresetOverride.user_id == user_id)
        .order_by(PresetOverride.scope_kind, PresetOverride.owner_id)
    )
    return list(result.scalars().all())


async def delete_override(session: AsyncSession, user_id: str, scope_kind: str, owner_id: str) -> bool:
    if scope_kind not in SCOPE_KINDS:
        raise BundleError(f"unknown scope_kind: {scope_kind!r}")
    if await _get_override_row(session, user_id, scope_kind, owner_id) is None:
        return False
    await session.execute(
        delete(PresetOverride).where(
            PresetOverride.scope_kind == scope_kind,
            PresetOverride.owner_id == owner_id,
            PresetOverride.user_id == user_id,
        )
    )
    await session.commit()
    return True


async def resolve_effective(
    session: AsyncSession, user_id: str,
    chat_id: str | None = None, character_id: str | None = None,
) -> dict | None:
    """Resolve the effective bundle for a chat and/or character.

    Precedence: chat assignment beats character assignment for
    CHOOSING the bundle; when both rows name the SAME bundle their
    deltas layer (character under chat). When the rows name
    DIFFERENT bundles the chat row wins outright — its bundle and
    its delta — and the shadowed character row is REPORTED in
    ``shadowed``, never silently dropped. With only a chat_id,
    the chat's character is discovered from the chat row. Returns
    None when no assignment applies.
    """
    chat_row = None
    char_row = None
    if chat_id:
        chat_row = await _get_override_row(session, user_id, SCOPE_CHAT, chat_id)
        if character_id is None:
            result = await session.execute(
                select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
            )
            chat = result.scalar_one_or_none()
            if chat is not None:
                character_id = chat.character_id
    if character_id:
        char_row = await _get_override_row(session, user_id, SCOPE_CHARACTER, character_id)
    if chat_row is None and char_row is None:
        return None
    applied: list[dict] = []
    shadowed: list[dict] = []
    if chat_row is not None and char_row is not None and chat_row.bundle_id != char_row.bundle_id:
        bundle_row = await _get_owned_bundle(session, user_id, chat_row.bundle_id)
        if bundle_row is None:
            return None
        base = json.loads(bundle_row.bundle_json)
        delta = json.loads(chat_row.overrides_json)
        effective, sources = merge_bundle(base, delta)
        sources = _relabel(sources, {"delta1": "chat"})
        applied.append({"scope_kind": "chat", "owner_id": chat_row.owner_id, "bundle_id": chat_row.bundle_id})
        shadowed.append({"scope_kind": "character", "owner_id": char_row.owner_id, "bundle_id": char_row.bundle_id, "reason": "chat assignment names a different bundle"})
        return _effective_view(bundle_row, effective, sources, applied, shadowed)
    chosen = chat_row if chat_row is not None else char_row
    assert chosen is not None
    bundle_row = await _get_owned_bundle(session, user_id, chosen.bundle_id)
    if bundle_row is None:
        return None
    base = json.loads(bundle_row.bundle_json)
    deltas: list[dict] = []
    labels: dict[str, str] = {}
    if char_row is not None:
        deltas.append(json.loads(char_row.overrides_json))
        labels[f"delta{len(deltas)}"] = "character"
        applied.append({"scope_kind": "character", "owner_id": char_row.owner_id, "bundle_id": char_row.bundle_id})
    if chat_row is not None:
        deltas.append(json.loads(chat_row.overrides_json))
        labels[f"delta{len(deltas)}"] = "chat"
        applied.append({"scope_kind": "chat", "owner_id": chat_row.owner_id, "bundle_id": chat_row.bundle_id})
    effective, sources = merge_bundle(base, *deltas)
    sources = _relabel(sources, labels)
    return _effective_view(bundle_row, effective, sources, applied, shadowed)


def _relabel(sources: dict, labels: dict[str, str]) -> dict:
    out: dict = {}
    for key, value in sources.items():
        if isinstance(value, dict):
            out[key] = {k: labels.get(v, v) for k, v in value.items()}
        else:
            out[key] = labels.get(value, value)
    return out


def _effective_view(bundle_row: PresetBundle, effective: dict, sources: dict, applied: list, shadowed: list) -> dict:
    return {
        "bundle_id": bundle_row.id,
        "bundle_name": bundle_row.name,
        "effective": effective,
        "sources": sources,
        "applied": applied,
        "shadowed": shadowed,
    }
