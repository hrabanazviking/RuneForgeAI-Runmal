"""Hub-side browse (P-188, Part XII - DERIVED).

P-187 landed the hub registry: an owner-scoped index of
the pack artefacts an owner holds, data only - it opens
no pack. Its record named hub-side browse over entry
contents open for a later Part XII slice. This is that
slice: an inspect-shaped, READ-ONLY view over one
registered entry's pack contents.

The browse composes each pack layer's OWN verified
inspect road verbatim - it never parses a pack itself:

- lorebook_pack -> runmal.lorebooks.packs.inspect_pack
- prompt_pack -> runmal.presets.packs.inspect_pack
  (the P-063 prompt-pack layer lives in presets.packs)
- scenario_pack -> runmal.scenarios.packs.inspect_pack
- preset_bundle -> runmal.presets.bundles.parse_share,
  that layer's own verified share road (the function its
  import uses first); the inspection document is built
  only from parse_share's outputs plus the envelope
  manifest fields parse_share just verified.

Honest boundaries: browse reads the file at the entry's
locator and nothing else; it imports nothing, installs
nothing, copies nothing, writes nothing (the registry
file is untouched) and grants nothing. The locator
state is judged live (the P-187 law): a locator that is
not ready makes the browse ``unavailable`` - data at
200, never an error. Contents the owning road refuses
make the browse ``invalid``, with that road's own
refusal carried verbatim - never dressed as success.
The entry's stored checksum stays the caller's CLAIM:
browse reports the road's verified checksum beside it
and a plain match verdict, and never upgrades the
claim. Signing and exchange transport stay declined -
no key or transport machinery is banked (see the
scout); content stays data, never code (P-027).
"""

from __future__ import annotations

import json
from pathlib import Path

from runmal.hub import registry as hub_registry
from runmal.hub.registry import HubEntry
from runmal.lorebooks import packs as lorebook_packs
from runmal.presets import bundles as preset_bundles
from runmal.presets import packs as prompt_packs
from runmal.scenarios import packs as scenario_packs

BROWSE_SCHEMA = "runmal-p188-hub-browse-v1"

BROWSE_INSPECTED = "inspected"
BROWSE_UNAVAILABLE = "unavailable"
BROWSE_INVALID = "invalid"
BROWSE_STATES = frozenset({
    BROWSE_INSPECTED, BROWSE_UNAVAILABLE, BROWSE_INVALID,
})

MAX_BROWSE_BYTES = 16 * 1024 * 1024

NOTES = (
    "Browse is read-only: it reads the file at the "
    "entry's locator through the owning pack layer's own "
    "verified inspect road, and it imports nothing, "
    "installs nothing, copies nothing, writes nothing "
    "and grants nothing.",
    "The inspection document is the owning layer's own "
    "road's output verbatim; this surface parses no pack "
    "itself and never forks an inspect law.",
    "A locator that is not ready makes the browse "
    "unavailable, and contents the owning road refuses "
    "make it invalid with that road's own refusal as the "
    "error - both are data, never errors dressed as "
    "success and never successes dressed over a refusal.",
    "The entry's content checksum stays the caller's "
    "claim; the verified checksum here is the one the "
    "owning road itself checked, and checksum_match "
    "compares the two as data - the claim is never "
    "upgraded to verified.",
    "A bare preset bundle carries no envelope checksum: "
    "its road verifies none, verified_content_sha256 is "
    "empty and checksum_match is null, stated plainly "
    "rather than filled in.",
)


def _bundle_inspection(data: object) -> dict:
    """The preset-bundle inspection document, built only
    from parse_share's own verified outputs."""
    bundle, report = preset_bundles.parse_share(data)
    manifest: dict = {}
    if isinstance(data, dict) and isinstance(data.get("manifest"), dict):
        manifest = data["manifest"]
    verified = ""
    if report.get("checksum_verified"):
        candidate = manifest.get("content_sha256")
        if isinstance(candidate, str):
            verified = candidate
    return {
        "schema": preset_bundles.BUNDLE_SCHEMA,
        "valid": True,
        "format": preset_bundles.SHARE_FORMAT,
        "bundle_name": bundle.get("name", ""),
        "content_sha256": verified,
        "checksum_verified": bool(report.get("checksum_verified")),
        "report": report,
        "manifest": manifest,
    }


def _inspect(entry: HubEntry, raw: bytes) -> dict:
    """Dispatch to the owning layer's own verified road."""
    if entry.kind == hub_registry.KIND_LOREBOOK_PACK:
        return lorebook_packs.inspect_pack(raw)
    if entry.kind == hub_registry.KIND_PROMPT_PACK:
        return prompt_packs.inspect_pack(raw)
    if entry.kind == hub_registry.KIND_SCENARIO_PACK:
        return scenario_packs.inspect_pack(raw)
    if entry.kind == hub_registry.KIND_PRESET_BUNDLE:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise preset_bundles.BundleError(
                "pack file is not valid JSON: " + str(exc)) from None
        return _bundle_inspection(data)
    raise hub_registry.HubError("unknown hub kind: " + entry.kind)


def browse_document(entry: HubEntry) -> dict:
    """The browse document for one registered entry.

    Locator state judged live at this call; the pack is
    opened only when the locator is ready, and only
    through its own layer's verified road.
    """
    state = hub_registry.locator_state(entry.locator)
    doc: dict = {
        "schema": BROWSE_SCHEMA,
        "entry": entry.to_dict(),
        "locator_state": state,
        "browse_state": BROWSE_UNAVAILABLE,
        "inspection": None,
        "verified_content_sha256": "",
        "checksum_match": None,
        "error": "",
        "notes": list(NOTES),
    }
    if state != hub_registry.LOCATOR_READY:
        return doc
    try:
        size = Path(entry.locator).stat().st_size
    except OSError as exc:
        doc["browse_state"] = BROWSE_INVALID
        doc["error"] = "locator could not be read: " + str(exc)
        return doc
    if size > MAX_BROWSE_BYTES:
        doc["browse_state"] = BROWSE_INVALID
        doc["error"] = "pack file too large to browse"
        return doc
    try:
        raw = Path(entry.locator).read_bytes()
    except OSError as exc:
        doc["browse_state"] = BROWSE_INVALID
        doc["error"] = "locator could not be read: " + str(exc)
        return doc
    try:
        inspection = _inspect(entry, raw)
    except (ValueError, TypeError) as exc:
        doc["browse_state"] = BROWSE_INVALID
        doc["error"] = str(exc)
        return doc
    verified = inspection.get("content_sha256")
    if not isinstance(verified, str):
        verified = ""
    claimed = entry.content_sha256 or ""
    doc["browse_state"] = BROWSE_INSPECTED
    doc["inspection"] = inspection
    doc["verified_content_sha256"] = verified
    doc["checksum_match"] = (
        (claimed == verified) if (claimed and verified) else None)
    return doc
