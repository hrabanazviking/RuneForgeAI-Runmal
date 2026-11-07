"""Prompt import/export packs (P-063): prompt bundles portable
across installs, with Part XII sharing.

Roadmap line: *Prompt import/export packs (with Part XII
sharing).*

Until P-063 Rúnmál could share exactly one prompt artefact at
a time: one P-054 bundle through its share envelope, one
preset through the P-021 file shapes. A player's whole prompt
workshop -- several bundles, plain presets, a hand-tuned custom
instruct template, a context template, a prompt layout -- had
no single portable form: nothing that gathers many prompt
artefacts into one file another install can verify, inspect,
and import piece by piece with honest per-item outcomes.

A prompt pack is that gathering, built in the P-045 lorebook
pack discipline (the pack Part XII's sovereign hub,
P-187..P-202, will carry unchanged, exactly as it carries
lorebook packs):

- ONE JSON envelope -- format ``runmal-prompt-pack``, version
  1, schema ``runmal-p063-prompt-pack-v1`` -- with a manifest,
  a provenance record, and an ``items`` list. A pack is a
  file/data-layer artefact: this slice takes NO migration
  (head stays 0035).
- Item kinds, each validated and normalised by its OWN
  existing validator, never a parallel one:
  ``bundle`` (a P-054 bundle, ``bundles.validate_bundle``),
  ``preset`` (an S207 sampler preset with its P-021 carriage:
  params validated by ``presets.service.validate_params``,
  ``raw`` / ``prompts`` / ``prompt_order`` carried verbatim),
  ``instruct_template`` (P-050 data form, strict),
  ``context_template`` (P-051 data form, strict), and
  ``prompt_layout`` (P-049 data form). Normalisation is a
  fixed point for every kind.
- Checksums: each item carries the SHA-256 of the canonical
  JSON (sorted keys, compact separators) of its NORMALISED
  payload, and the pack's ``content_sha256`` is the SHA-256
  of the canonical form of the pack name plus the normalised
  item list IN CARRIED ORDER. Item order is therefore part
  of pack identity -- a pack is an authored list, and a file
  whose items were reordered or altered in transit refuses,
  it does not silently pass. Cosmetic re-serialisation of
  the pack file (whitespace, key order) never invalidates:
  identity is defined over normalised content, never raw
  bytes (the P-045 rule).
- Provenance (the P-029 honesty rules): unknown facts are
  OMITTED, never fabricated. A caller ``note`` and the source
  item names ride only when known. Provenance is not stored
  on any row; its carriers are the pack and the import
  report, which returns it verbatim. Unknown keys in an
  incoming pack's provenance, and unknown top-level pack
  keys (a future hub may annotate a pack it carries), are
  preserved in the report / under pack ``extensions`` --
  carried, never interpreted, never dropped.

What a pack carries, and what import does with it -- stated
plainly, because a pack that overclaims is a pack that lies:

- ``bundle`` and ``preset`` items have stored homes (the
  P-054 bundle table, migration 0033; the S207 preset table)
  and import stores them through those existing services.
- ``instruct_template``, ``context_template`` and
  ``prompt_layout`` items have NO library table: P-049,
  P-050 and P-051 each deliberately deferred that
  persistence to a migration-owning follow-up, and none has
  landed. Import therefore validates them and returns them
  in the report as portable data (status
  ``validated_not_stored``, the deferral named) for the
  receiver to use per-request or fold into a bundle. They
  are never reported as stored and never silently dropped.
  Inside their payloads, unknown fields REFUSE (their own
  strict contracts) rather than riding along; unknown-field
  carriage exists exactly where the owning layer already
  provides it -- bundle ``extensions`` and the preset bag /
  ``raw`` carriage (the P-019 file-layer honesty rule).

Collision discipline (never silently overwriting, P-025 /
P-045): import never merges into or overwrites an owned
bundle or preset.

- Exact duplicate (an owned item value-identical to the
  normalised payload, name included): nothing is written;
  the item is reported ``duplicate_exact``.
- Same name, different contents: with the default
  ``on_conflict="create_new"`` the item is stored under the
  first free derived name (``"<name> (imported)"``, then
  ``"<name> (imported 2)"``, ...) and reported ``renamed``
  with both names; with ``on_conflict="reject"`` the item
  is written nowhere and reported ``rejected`` with the
  reason. A pack is multi-item, so collision outcomes are
  PER ITEM (a divergence from P-045's single-book refusal,
  stated here rather than hidden): the remaining items
  still import, and the report is the whole truth.
- A malformed pack -- bad envelope, version, manifest,
  checksum, or ANY malformed item -- refuses WHOLE in
  :func:`parse_pack`, before any write exists.

Safety: byte/str input is decoded with
``runmal.safety.safe_json_loads`` under a 16 MiB cap (a
local cap, named as local) and a 500-item cap;
already-decoded input is checked with ``validate_json_tree``.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from runmal import __version__
from runmal.presets import bundles as _bundles
from runmal.presets import service as _preset_service
from runmal.safety import SafetyError, safe_json_loads, validate_json_tree

PACK_FORMAT = "runmal-prompt-pack"
PACK_VERSION = 1
PACK_KIND = "prompt_pack"
PACK_SCHEMA = "runmal-p063-prompt-pack-v1"
PROVENANCE_VERSION = 1
PROVENANCE_SOURCE_KIND = "prompt_pack_export"
MAX_PACK_BYTES = 16 * 1024 * 1024
MAX_ITEMS = 500

KIND_BUNDLE = "bundle"
KIND_PRESET = "preset"
KIND_INSTRUCT = "instruct_template"
KIND_CONTEXT = "context_template"
KIND_LAYOUT = "prompt_layout"
ITEM_KINDS = frozenset(
    {KIND_BUNDLE, KIND_PRESET, KIND_INSTRUCT, KIND_CONTEXT, KIND_LAYOUT}
)
STORED_KINDS = frozenset({KIND_BUNDLE, KIND_PRESET})
NOT_STORED_REASON = "no_library_home_p049_p050_p051_deferred_persistence"

CONFLICT_CREATE_NEW = "create_new"
CONFLICT_REJECT = "reject"
CONFLICT_MODES = frozenset({CONFLICT_CREATE_NEW, CONFLICT_REJECT})

_PRESET_FORMATS = frozenset({"native", "st-text", "st-chat"})
_ITEM_KEYS = frozenset({"kind", "name", "content_sha256", "payload", "extensions"})

__all__ = [
    "CONFLICT_CREATE_NEW", "CONFLICT_MODES", "CONFLICT_REJECT",
    "ITEM_KINDS", "KIND_BUNDLE", "KIND_CONTEXT", "KIND_INSTRUCT",
    "KIND_LAYOUT", "KIND_PRESET", "MAX_ITEMS", "MAX_PACK_BYTES",
    "NOT_STORED_REASON", "PACK_FORMAT", "PACK_KIND", "PACK_SCHEMA",
    "PACK_VERSION", "PROVENANCE_SOURCE_KIND", "PROVENANCE_VERSION",
    "STORED_KINDS", "PackError", "build_pack", "canonical_json",
    "export_library_pack", "import_pack", "inspect_pack",
    "normalise_item", "pack_to_bytes", "parse_pack",
]


class PackError(ValueError):
    """A prompt pack is malformed, tampered with, or refused."""


def canonical_json(data: object) -> str:
    """Canonical JSON: sorted keys, compact separators."""
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _canonical_bytes(data: object) -> bytes:
    return canonical_json(data).encode("utf-8")


def _sha(data: object) -> str:
    return hashlib.sha256(_canonical_bytes(data)).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _json_safe(value: object, what: str) -> object:
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise PackError(f"{what} is not JSON-serializable") from exc
    return copy.deepcopy(value)


# ---------------- item normalisation ----------------

def _normalise_preset(payload: object) -> dict:
    """Validate + normalise a preset item payload.

    The payload is the stored-preset data form (what
    ``presets.service.preset_to_dict`` exposes, minus the
    row's id/timestamps): the S207 bag validated by
    ``validate_params`` (unknown bag keys preserved), the
    P-021 carriage (``raw`` / ``prompts`` / ``prompt_order``)
    carried verbatim.
    """
    if not isinstance(payload, dict):
        raise PackError("preset payload must be an object")
    unknown = set(payload) - {
        "name", "params", "template_ref", "source_format",
        "raw", "prompts", "prompt_order",
    }
    if unknown:
        raise PackError(f"preset payload has unknown keys: {sorted(unknown)}")
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise PackError("preset payload name must be a non-empty string")
    try:
        params = _preset_service.validate_params(payload.get("params") or {})
    except ValueError as exc:
        raise PackError(str(exc)) from exc
    template_ref = payload.get("template_ref", "")
    if not isinstance(template_ref, str):
        raise PackError("preset template_ref must be a string")
    source_format = payload.get("source_format", "native")
    if source_format not in _PRESET_FORMATS:
        raise PackError(f"preset source_format is unknown: {source_format!r}")
    raw = payload.get("raw")
    if raw is not None and not isinstance(raw, dict):
        raise PackError("preset raw carriage must be an object or null")
    prompts = payload.get("prompts", [])
    prompt_order = payload.get("prompt_order", [])
    if not isinstance(prompts, list) or not isinstance(prompt_order, list):
        raise PackError("preset prompts and prompt_order must be lists")
    return {
        "name": name,
        "params": params,
        "template_ref": template_ref,
        "source_format": source_format,
        "raw": _json_safe(raw, "preset raw"),
        "prompts": _json_safe(prompts, "preset prompts"),
        "prompt_order": _json_safe(prompt_order, "preset prompt_order"),
    }


def _normalise_payload(kind: str, payload: object) -> tuple[dict, str | None]:
    """(normalised payload, payload-derived name or None)."""
    if kind == KIND_BUNDLE:
        try:
            out = _bundles.validate_bundle(payload)
        except ValueError as exc:
            raise PackError(str(exc)) from exc
        return out, out["name"]
    if kind == KIND_PRESET:
        out = _normalise_preset(payload)
        return out, out["name"]
    if kind == KIND_INSTRUCT:
        from runmal.prompt.instruct import template_from_data, template_to_data
        try:
            out = template_to_data(template_from_data(payload))
        except ValueError as exc:
            raise PackError(str(exc)) from exc
        return out, out["name"]
    if kind == KIND_CONTEXT:
        from runmal.prompt.context import context_from_data, context_to_data
        try:
            out = context_to_data(context_from_data(payload))
        except ValueError as exc:
            raise PackError(str(exc)) from exc
        return out, out["name"]
    if kind == KIND_LAYOUT:
        from runmal.prompt.manager import layout_from_data, layout_to_data
        try:
            out = layout_to_data(layout_from_data(payload))
        except ValueError as exc:
            raise PackError(str(exc)) from exc
        return out, None
    raise PackError(f"unknown pack item kind: {kind!r}")


def normalise_item(item: object) -> dict:
    """Validate + normalise one pack item; return its canonical form.

    The envelope ``name`` must equal the payload-derived name
    wherever the payload carries one (a layout payload carries
    none, so its envelope name is the only name). ``extensions``
    (item-level unknown carriage) rides verbatim.
    """
    if not isinstance(item, dict):
        raise PackError("pack item must be an object")
    unknown = set(item) - _ITEM_KEYS
    if unknown:
        raise PackError(f"pack item has unknown keys: {sorted(unknown)}")
    kind = item.get("kind")
    if kind not in ITEM_KINDS:
        raise PackError(f"unknown pack item kind: {kind!r}")
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        raise PackError("pack item name must be a non-empty string")
    if "payload" not in item:
        raise PackError(f"pack item {name!r} is missing its payload")
    payload, derived = _normalise_payload(kind, item["payload"])
    if derived is not None and derived != name:
        raise PackError(
            f"pack item name {name!r} does not match payload name {derived!r}"
        )
    extensions = item.get("extensions", {})
    if not isinstance(extensions, dict):
        raise PackError(f"pack item {name!r} extensions must be an object")
    out: dict = {
        "kind": kind,
        "name": name,
        "content_sha256": _sha(payload),
        "payload": payload,
    }
    if extensions:
        out["extensions"] = _json_safe(extensions, f"item {name!r} extensions")
    return out


def _identity(pack_name: str, items: list[dict]) -> dict:
    """The content-identity form a pack checksum is taken over."""
    return {
        "pack_name": pack_name,
        "items": [
            {
                "kind": it["kind"],
                "name": it["name"],
                "content_sha256": it["content_sha256"],
                "payload": it["payload"],
            }
            for it in items
        ],
    }


# ---------------- build / parse / inspect ----------------

def build_pack(
    pack_name: str,
    items: list,
    *,
    exported_at: str | None = None,
    note: str | None = None,
) -> dict:
    """Build a pack from raw item dicts (validates everything).

    ``items`` are ``{"kind", "name", "payload"[, "extensions"]}``
    dicts; any ``content_sha256`` a caller supplies is ignored
    and recomputed over the normalised payload. Facts the
    caller does not have are omitted from provenance, never
    fabricated.
    """
    if not isinstance(pack_name, str) or not pack_name.strip():
        raise PackError("pack name must be a non-empty string")
    if not isinstance(items, list) or not items:
        raise PackError("a prompt pack needs at least one item")
    if len(items) > MAX_ITEMS:
        raise PackError(f"a prompt pack carries at most {MAX_ITEMS} items")
    normalised = [normalise_item(item) for item in items]
    seen: set[tuple[str, str]] = set()
    for it in normalised:
        key = (it["kind"], it["name"])
        if key in seen:
            raise PackError(
                f"pack carries two {it['kind']} items named {it['name']!r}"
            )
        seen.add(key)
    stamp = exported_at if exported_at is not None else _now_iso()
    digest = _sha(_identity(pack_name, normalised))
    kind_counts: dict[str, int] = {}
    for it in normalised:
        kind_counts[it["kind"]] = kind_counts.get(it["kind"], 0) + 1
    manifest = {
        "pack_name": pack_name,
        "item_count": len(normalised),
        "kind_counts": kind_counts,
        "content_sha256": digest,
        "canonical_bytes": len(_canonical_bytes(_identity(pack_name, normalised))),
        "exported_at": stamp,
        "app_version": __version__,
    }
    provenance: dict = {
        "provenance_version": PROVENANCE_VERSION,
        "source_kind": PROVENANCE_SOURCE_KIND,
        "pack_name": pack_name,
        "exported_at": stamp,
        "app_version": __version__,
        "content_sha256": digest,
        "source_item_names": [it["name"] for it in normalised],
    }
    if note is not None:
        provenance["note"] = note
    return {
        "format": PACK_FORMAT,
        "pack_version": PACK_VERSION,
        "kind": PACK_KIND,
        "schema": PACK_SCHEMA,
        "manifest": manifest,
        "provenance": provenance,
        "items": normalised,
    }


def pack_to_bytes(pack: dict) -> bytes:
    """Serialise a pack for sharing (human-inspectable JSON).

    The checksums cover canonical normalised content, not
    these bytes, so re-serialisation never invalidates a pack.
    """
    return json.dumps(pack, ensure_ascii=False, indent=2).encode("utf-8")


def _coerce_to_dict(data: bytes | str | dict) -> dict:
    if isinstance(data, dict):
        return copy.deepcopy(data)
    if isinstance(data, (bytes, bytearray, str)):
        try:
            parsed = safe_json_loads(data, limit=MAX_PACK_BYTES)
        except SafetyError as exc:
            raise PackError(str(exc)) from exc
        if not isinstance(parsed, dict):
            raise PackError("prompt pack must be a JSON object")
        return parsed
    raise PackError(
        f"prompt pack must be bytes, str or dict, got {type(data).__name__}"
    )


_TOP_KEYS = frozenset(
    {"format", "pack_version", "kind", "schema", "manifest",
     "provenance", "items", "extensions"}
)


def parse_pack(data: bytes | str | dict) -> dict:
    """Validate a pack end to end; return its NORMALISED form.

    Every check runs before any write exists: envelope shape,
    format and version, every item through its own validator,
    per-item checksums, the pack checksum, and the manifest
    cross-checked against the normalised contents (name,
    counts, canonical length). Unknown top-level keys are
    collected under ``extensions`` (a future hub may annotate
    a pack it carries); unknown keys inside an item refuse
    (items are authored data, not a carrier surface).
    """
    pack = _coerce_to_dict(data)
    try:
        validate_json_tree(pack)
    except SafetyError as exc:
        raise PackError(str(exc)) from exc
    if pack.get("format") != PACK_FORMAT:
        raise PackError(f"pack format is not {PACK_FORMAT!r}")
    version = pack.get("pack_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise PackError(f"pack_version must be an integer, got {version!r}")
    if version != PACK_VERSION:
        raise PackError(
            f"unsupported prompt pack version {version} (this build "
            f"supports {PACK_VERSION}); upgrade Runmal or re-export "
            "with a supported version"
        )
    if pack.get("kind") != PACK_KIND:
        raise PackError(f"pack kind is not {PACK_KIND!r}")
    manifest = pack.get("manifest")
    if not isinstance(manifest, dict):
        raise PackError("pack manifest missing or not an object")
    provenance = pack.get("provenance")
    if not isinstance(provenance, dict) or not provenance:
        raise PackError("pack provenance missing or not an object")
    raw_items = pack.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise PackError("pack items missing, not a list, or empty")
    if len(raw_items) > MAX_ITEMS:
        raise PackError(f"a prompt pack carries at most {MAX_ITEMS} items")
    items: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_items:
        item = normalise_item(raw)
        key = (item["kind"], item["name"])
        if key in seen:
            raise PackError(
                f"pack carries two {item['kind']} items named {item['name']!r}"
            )
        seen.add(key)
        declared = raw.get("content_sha256") if isinstance(raw, dict) else None
        if declared is not None and declared != item["content_sha256"]:
            raise PackError(
                f"item {item['name']!r} checksum mismatch: its payload "
                "was altered or corrupted in transit"
            )
        items.append(item)
    pack_name = manifest.get("pack_name")
    if not isinstance(pack_name, str) or not pack_name.strip():
        raise PackError("manifest pack_name must be a non-empty string")
    identity = _identity(pack_name, items)
    digest = _sha(identity)
    if manifest.get("content_sha256") != digest:
        raise PackError(
            "pack checksum mismatch: contents do not match the "
            "manifest content_sha256 (the pack was altered or "
            "corrupted in transit)"
        )
    if manifest.get("item_count") != len(items):
        raise PackError(
            f"manifest item_count {manifest.get('item_count')!r} does "
            f"not match payload item count {len(items)}"
        )
    kind_counts: dict[str, int] = {}
    for it in items:
        kind_counts[it["kind"]] = kind_counts.get(it["kind"], 0) + 1
    if manifest.get("kind_counts") != kind_counts:
        raise PackError(
            f"manifest kind_counts {manifest.get('kind_counts')!r} do "
            f"not match payload kind counts {kind_counts!r}"
        )
    canonical_len = len(_canonical_bytes(identity))
    if manifest.get("canonical_bytes") != canonical_len:
        raise PackError(
            f"manifest canonical_bytes {manifest.get('canonical_bytes')!r} "
            f"does not match canonical content length {canonical_len}"
        )
    prov_sha = provenance.get("content_sha256")
    if prov_sha is not None and prov_sha != digest:
        raise PackError(
            "provenance content_sha256 does not match the manifest "
            "checksum (the provenance record was altered or forged)"
        )
    extensions: dict = {}
    raw_ext = pack.get("extensions", {})
    if not isinstance(raw_ext, dict):
        raise PackError("pack extensions must be an object")
    extensions.update(_json_safe(raw_ext, "pack extensions"))
    for key, value in pack.items():
        if key not in _TOP_KEYS:
            extensions[key] = _json_safe(value, f"pack extension {key!r}")
    out = {
        "format": PACK_FORMAT,
        "pack_version": PACK_VERSION,
        "kind": PACK_KIND,
        "schema": PACK_SCHEMA,
        "manifest": copy.deepcopy(manifest),
        "provenance": copy.deepcopy(provenance),
        "items": items,
    }
    if extensions:
        out["extensions"] = extensions
    return out


def inspect_pack(data: bytes | str | dict) -> dict:
    """Validate a pack and report on it WITHOUT importing.

    The Part XII hub's pre-flight, after P-045: a receiver can
    see what a pack carries, where it says it came from, that
    its contents are intact, and -- per item -- whether an
    import would STORE it or return it as portable data,
    before deciding to import anything.
    """
    pack = parse_pack(data)
    manifest = pack["manifest"]
    return {
        "schema": PACK_SCHEMA,
        "valid": True,
        "format": pack["format"],
        "pack_version": pack["pack_version"],
        "kind": pack["kind"],
        "pack_name": manifest["pack_name"],
        "item_count": manifest["item_count"],
        "kind_counts": copy.deepcopy(manifest["kind_counts"]),
        "content_sha256": manifest["content_sha256"],
        "checksum_verified": True,
        "items": [
            {
                "kind": it["kind"],
                "name": it["name"],
                "content_sha256": it["content_sha256"],
                "stored_on_import": it["kind"] in STORED_KINDS,
            }
            for it in pack["items"]
        ],
        "manifest": copy.deepcopy(manifest),
        "provenance": copy.deepcopy(pack["provenance"]),
    }


# ---------------- export from the library ----------------

def _preset_payload(row) -> dict:
    data = _preset_service.preset_to_dict(row)
    carriage = _preset_service.interop_data(row)
    return {
        "name": data["name"],
        "params": data["params"],
        "template_ref": data["template_ref"],
        "source_format": data["source_format"],
        "raw": carriage.get("raw"),
        "prompts": data["prompts"],
        "prompt_order": data["prompt_order"],
    }


async def export_library_pack(
    session: AsyncSession,
    user_id: str,
    pack_name: str,
    *,
    bundle_ids: list[str] | None = None,
    preset_ids: list[str] | None = None,
    extra_items: list | None = None,
    exported_at: str | None = None,
    note: str | None = None,
) -> dict:
    """Build a pack from owned bundles/presets plus extra items.

    ``bundle_ids`` / ``preset_ids`` of None export EVERY owned
    bundle / preset; an explicit list exports exactly those
    (an id that is not the caller's raises PackError -- an
    export must never silently carry less than was asked).
    ``extra_items`` are raw item dicts (standalone templates,
    layouts, or caller-built payloads), validated by
    :func:`build_pack` like everything else.
    """
    items: list[dict] = []
    if bundle_ids is None:
        bundle_rows = await _bundles.list_bundles(session, user_id)
    else:
        bundle_rows = []
        for bundle_id in bundle_ids:
            row = await _bundles.get_bundle(session, user_id, bundle_id)
            if row is None:
                raise PackError(f"bundle not found: {bundle_id!r}")
            bundle_rows.append(row)
    for row in bundle_rows:
        payload = _bundles.bundle_to_dict(row)["bundle"]
        items.append(
            {"kind": KIND_BUNDLE, "name": payload["name"], "payload": payload}
        )
    if preset_ids is None:
        preset_rows = await _preset_service.list_presets(session, user_id)
    else:
        preset_rows = []
        for preset_id in preset_ids:
            row = await _preset_service.get_preset(
                session, user_id=user_id, preset_id=preset_id
            )
            if row is None:
                raise PackError(f"preset not found: {preset_id!r}")
            preset_rows.append(row)
    for row in preset_rows:
        payload = _preset_payload(row)
        items.append(
            {"kind": KIND_PRESET, "name": payload["name"], "payload": payload}
        )
    items.extend(extra_items or [])
    return build_pack(
        pack_name, items, exported_at=exported_at, note=note
    )


# ---------------- import ----------------

def _free_name(taken: set[str], name: str) -> str:
    candidate = f"{name} (imported)"
    n = 2
    while candidate in taken:
        candidate = f"{name} (imported {n})"
        n += 1
    return candidate


async def import_pack(
    session: AsyncSession,
    user_id: str,
    data: bytes | str | dict,
    *,
    on_conflict: str = CONFLICT_CREATE_NEW,
) -> dict:
    """Import a pack; return the import report (never raises for
    per-item collisions -- those are report rows).

    The pack is fully validated by :func:`parse_pack` before
    any write exists. Bundle and preset items are stored
    through their existing services under the collision
    discipline in the module docstring; template and layout
    items are validated and returned as portable data with
    status ``validated_not_stored``. The report carries the
    pack's manifest and provenance verbatim -- provenance's
    carriers are the pack and this report; it is stored on
    no row.
    """
    if on_conflict not in CONFLICT_MODES:
        raise PackError(
            f"unknown on_conflict mode: {on_conflict!r} "
            f"(valid: {sorted(CONFLICT_MODES)})"
        )
    pack = parse_pack(data)
    manifest = pack["manifest"]
    owned_bundles: dict[str, dict] = {}
    for row in await _bundles.list_bundles(session, user_id):
        view = _bundles.bundle_to_dict(row)
        owned_bundles[view["bundle"]["name"]] = view["bundle"]
    owned_presets: dict[str, dict] = {}
    for row in await _preset_service.list_presets(session, user_id):
        payload = _preset_payload(row)
        owned_presets[payload["name"]] = payload
    rows: list[dict] = []
    counts = {"created": 0, "duplicate_exact": 0, "renamed": 0,
              "rejected": 0, "validated_not_stored": 0}
    for item in pack["items"]:
        kind, name, payload = item["kind"], item["name"], item["payload"]
        base_row = {"kind": kind, "name": name,
                    "content_sha256": item["content_sha256"]}
        if kind not in STORED_KINDS:
            counts["validated_not_stored"] += 1
            rows.append({**base_row, "status": "validated_not_stored",
                         "stored": False, "reason": NOT_STORED_REASON,
                         "payload": copy.deepcopy(payload)})
            continue
        owned = owned_bundles if kind == KIND_BUNDLE else owned_presets
        existing = owned.get(name)
        if existing is not None and existing == payload:
            counts["duplicate_exact"] += 1
            rows.append({**base_row, "status": "duplicate_exact",
                         "stored": False, "stored_name": name})
            continue
        stored_name = name
        status = "created"
        if existing is not None:
            if on_conflict == CONFLICT_REJECT:
                counts["rejected"] += 1
                rows.append({**base_row, "status": "rejected",
                             "stored": False, "reason": "name_collision"})
                continue
            stored_name = _free_name(set(owned), name)
            status = "renamed"
        if kind == KIND_BUNDLE:
            new_payload = _bundles.validate_bundle(
                {**payload, "name": stored_name}
            )
            row = await _bundles.create_bundle(session, user_id, new_payload)
            owned[stored_name] = _bundles.bundle_to_dict(row)["bundle"]
            stored_id = row.id
        else:
            from runmal.presets.interop import ImportedPreset
            imported = ImportedPreset(
                name=stored_name,
                params=copy.deepcopy(payload["params"]),
                template_ref=payload["template_ref"],
                source_format=payload["source_format"],
                raw=copy.deepcopy(payload["raw"]),
                prompts=copy.deepcopy(payload["prompts"]),
                prompt_order=copy.deepcopy(payload["prompt_order"]),
            )
            row = await _preset_service.import_preset(session, user_id, imported)
            owned[stored_name] = _preset_payload(row)
            stored_id = row.id
        counts[status] += 1
        out_row = {**base_row, "status": status, "stored": True,
                   "stored_name": stored_name, "stored_id": stored_id}
        if status == "renamed":
            out_row["original_name"] = name
        rows.append(out_row)
    return {
        "schema": PACK_SCHEMA,
        "pack_name": manifest["pack_name"],
        "content_sha256": manifest["content_sha256"],
        "checksum_verified": True,
        "on_conflict": on_conflict,
        "manifest": copy.deepcopy(manifest),
        "provenance": copy.deepcopy(pack["provenance"]),
        "items": rows,
        "counts": counts,
        "imported_at": _now_iso(),
    }
