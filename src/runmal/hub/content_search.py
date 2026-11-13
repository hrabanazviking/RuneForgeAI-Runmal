"""Hub pack-content search (P-191, Part XII - DERIVED).

P-190 landed hub search over the registry's own entry
data and named pack-content search open verbatim: the
registry holds metadata only, so a content search would
need its own slice with its own cost law. This module
is that slice: a literal text search over the verified
payload contents of the owner's registered packs.

- Composition, verbatim roads only - never a second
  parser. Bytes are read once per ready entry, under
  P-188's own locator law (registry.locator_state,
  judged live) and P-188's own size bound
  (MAX_BROWSE_BYTES, imported: one bound law), then
  dispatched by kind to the owning layer's OWN verified
  parse road - the road each layer's inspect_pack
  itself stands on (inspect_pack calls parse_pack
  first in all three pack layers), and for the preset
  bundle the parse_share road P-188's browse composes:
  lorebook_pack -> lorebooks.packs.parse_pack, payload
  member lorebook; prompt_pack -> presets.packs.
  parse_pack, payload member items; scenario_pack ->
  scenarios.packs.parse_pack, payload member scenario;
  preset_bundle -> presets.bundles.parse_share, whose
  returned bundle is the payload. Each parse road
  validates format, manifest against payload, the
  content checksum and the payload itself before any
  text is searched: only a VERIFIED pack is searched.
  Inspection documents alone were not enough - they
  carry names and manifests, never payload bodies (see
  the scout) - so this search composes the parse roads
  the inspections stand on, and interprets nothing
  inside a payload beyond a generic string-value walk.
- A match is a LITERAL match only: the query,
  casefolded, as a substring of a searched string
  value's casefolded form (the P-178 match law). The
  searched text is every STRING VALUE in the verified
  payload (dict values and list items, in document
  order). Never searched, stated plainly: dict keys
  (structure, not content), the pack envelope
  (manifest and provenance live outside the payload
  member), any value under a content_sha256 key (the
  pack's identity, not its content - P-190's checksum
  exclusion carried in), and registry metadata (title,
  locator, note, kind and format stay on P-190's road
  and are not re-searched here). There is no fuzzy,
  semantic, ranked or scored matching: no such
  machinery is banked, and none is faked.
- No silent omission (the P-180 law): every considered
  entry ends as searched, or as a named skip -
  unavailable (the locator is not ready; no read
  attempted) or invalid (unreadable at read time, over
  the size bound, not valid JSON on the bundle road,
  or the owning layer's own parse road refused it,
  its refusal carried verbatim) - under the closed
  OUTCOMES law, and coverage_complete carries the
  truth as data: any skip makes it false, and
  entries_considered always equals entries_searched
  plus the skip count.
- Cap honesty (the P-190 law): at most MAX_MATCHES
  rows are returned; total_matches carries the true
  total and truncated names a capped answer,
  classified matches_truncated under the closed
  SEARCH_STATES law, never dressed as complete.
- The COST LAW, stated plainly: a content search
  reads and verifies every ready pack in the
  (kind-narrowed) estate, each under the 16 MiB
  bound - O(estate bytes). That is the price of
  searching contents the registry does not hold, and
  it is why P-190's metadata search stays the cheap
  road. An oversize, corrupt or wrong-kind pack is a
  named skip, never a search failure.

Honest boundaries: the search writes nothing, imports
nothing, installs nothing, copies nothing and grants
nothing; the registry file and every pack file are
byte-unchanged by a search. Each row's
verified_content_sha256 is the checksum the owning
road itself verified (empty for a bare preset bundle,
whose road verifies none - stated plainly, as at
P-188); the entry's registered checksum stays the
caller's claim and is never searched or upgraded
here. Signing and friend-instance exchange stay
declined - no key or transport machinery is banked.
There is no central store, no catalogue and no
creator profile here (VX-59). No migration: head
stays 0041.
"""

from __future__ import annotations

import json
from pathlib import Path

from runmal.hub import browse as hub_browse
from runmal.hub import registry as hub_registry
from runmal.hub.registry import HubEntry
from runmal.lorebooks import packs as lorebook_packs
from runmal.presets import bundles as preset_bundles
from runmal.presets import packs as prompt_packs
from runmal.scenarios import packs as scenario_packs

CONTENT_SEARCH_SCHEMA = "runmal-p191-hub-content-search-v1"

MAX_MATCHES = 100  # P-190's match cap, carried verbatim
EXCERPT_CONTEXT = 40  # chars either side of a first match (P-180)
MAX_BROWSE_BYTES = hub_browse.MAX_BROWSE_BYTES  # P-188's bound: one law

OUTCOME_SEARCHED = "searched"
OUTCOME_UNAVAILABLE = "unavailable"
OUTCOME_INVALID = "invalid"
OUTCOMES = frozenset({
    OUTCOME_SEARCHED, OUTCOME_UNAVAILABLE, OUTCOME_INVALID,
})

SEARCH_STATE_NO_MATCHES = "no_matches"
SEARCH_STATE_MATCHES = "matches"
SEARCH_STATE_MATCHES_TRUNCATED = "matches_truncated"
SEARCH_STATES = frozenset({
    SEARCH_STATE_NO_MATCHES, SEARCH_STATE_MATCHES,
    SEARCH_STATE_MATCHES_TRUNCATED,
})

NOTES = (
    "Pure read, owner scoped: only the caller's own "
    "entries are searched; this search stores, "
    "registers, removes, imports, installs, copies "
    "and writes nothing.",
    "Cost law: a content search reads and verifies "
    "every ready pack in the searched estate, each "
    "through its own layer's verified parse road and "
    "each under the browse size bound (max_browse_"
    "bytes in this document) - the price of searching "
    "contents the registry does not hold. P-190's "
    "search over registry metadata stays the cheap "
    "road and is not repeated here.",
    "A match is a literal match only: the query, "
    "casefolded, as a substring of a string value in "
    "the pack's verified payload. Dict keys, the pack "
    "envelope (manifest and provenance), values under "
    "a content_sha256 key and registry metadata are "
    "never searched, and there is no fuzzy, semantic, "
    "ranked or scored matching here.",
    "No silent omission: every considered entry was "
    "searched or is named in skipped_entries with its "
    "outcome - unavailable (its locator is not ready) "
    "or invalid (its own layer's road refused it, it "
    "could not be read, or it exceeds the size bound). "
    "coverage_complete is false whenever any entry "
    "was skipped, and a capped answer is named by "
    "truncated; neither is dressed as complete.",
    "verified_content_sha256 on a match row is the "
    "checksum the owning layer's own road verified "
    "(empty for a bare preset bundle, whose road "
    "verifies none). An entry's registered checksum "
    "stays the caller's claim: it is never searched "
    "and never upgraded here.",
    "Signing and friend-instance exchange stay "
    "declined: no key or transport machinery is "
    "banked, and this search invents none. There is "
    "no central store, no catalogue and no creator "
    "profile on this road (the VX-59 sovereign "
    "shape).",
)


class HubContentSearchError(ValueError):
    """A hub content search request the law forbids."""


def _normalise_query(query) -> str:
    if not isinstance(query, str):
        raise HubContentSearchError(
            "a hub content search query is required")
    cleaned = query.strip()
    if not cleaned:
        raise HubContentSearchError(
            "a hub content search query is required")
    return cleaned


def _parse_payload(entry: HubEntry, raw: bytes):
    """Dispatch to the owning layer's own verified parse
    road; returns (payload, verified_content_sha256)."""
    if entry.kind == hub_registry.KIND_LOREBOOK_PACK:
        pack = lorebook_packs.parse_pack(raw)
        return pack["lorebook"], pack["manifest"]["content_sha256"]
    if entry.kind == hub_registry.KIND_PROMPT_PACK:
        pack = prompt_packs.parse_pack(raw)
        return pack["items"], pack["manifest"]["content_sha256"]
    if entry.kind == hub_registry.KIND_SCENARIO_PACK:
        pack = scenario_packs.parse_pack(raw)
        return pack["scenario"], pack["manifest"]["content_sha256"]
    if entry.kind == hub_registry.KIND_PRESET_BUNDLE:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise preset_bundles.BundleError(
                "pack file is not valid JSON: " + str(exc)) from None
        bundle, report = preset_bundles.parse_share(data)
        verified = ""
        if report.get("checksum_verified"):
            manifest = data.get("manifest") if isinstance(data, dict) else None
            if isinstance(manifest, dict):
                candidate = manifest.get("content_sha256")
                if isinstance(candidate, str):
                    verified = candidate
        return bundle, verified
    raise hub_registry.HubError("unknown hub kind: " + entry.kind)


def _string_values(node, _skip: bool = False):
    """Every string value in a verified payload, in
    document order. A value under a content_sha256 key
    is the pack's identity, not its content, and its
    subtree is never searched."""
    if _skip:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _string_values(value, key == "content_sha256")
    elif isinstance(node, list):
        for item in node:
            yield from _string_values(item)
    elif isinstance(node, str):
        yield node


def _excerpt(value: str, needle: str, query_len: int) -> str:
    at = value.casefold().find(needle)
    start = max(0, at - EXCERPT_CONTEXT)
    end = min(len(value), at + query_len + EXCERPT_CONTEXT)
    return value[start:end]


def content_search_document(
    entries: list[HubEntry],
    query: str,
    kind: str | None = None,
) -> dict:
    """The hub pack-content search document for one
    owner's entries.

    ``entries`` is the owner's own entry list (the
    router hands over HubStore.list_for_owner for the
    caller; a foreign owner's entries are never in
    it). ``kind``, when given, narrows the estate
    before searching (P-190's filter law); an unknown
    kind raises HubContentSearchError, as does an
    empty or blank query - refused plainly, never
    treated as match-everything. Every considered
    entry is searched through its own layer's verified
    parse road or named in skipped_entries; matches
    keep store order and are capped at MAX_MATCHES
    with the true total carried alongside.
    """
    cleaned = _normalise_query(query)
    cleaned_kind = None
    if kind is not None:
        cleaned_kind = kind.strip() if isinstance(kind, str) else kind
        if cleaned_kind not in hub_registry.HUB_KINDS:
            raise HubContentSearchError(
                "unknown hub kind: " + str(cleaned_kind or "(empty)"))
    needle = cleaned.casefold()
    considered = [
        entry for entry in entries
        if cleaned_kind is None or entry.kind == cleaned_kind]
    matched: list[tuple[HubEntry, int, str, str]] = []
    skipped: list[dict] = []
    searched = 0
    for entry in considered:
        state = hub_registry.locator_state(entry.locator)
        base = {
            "id": entry.id, "title": entry.title,
            "kind": entry.kind, "locator_state": state,
        }
        if state != hub_registry.LOCATOR_READY:
            skipped.append({**base, "outcome": OUTCOME_UNAVAILABLE,
                            "error": ""})
            continue
        try:
            size = Path(entry.locator).stat().st_size
        except OSError as exc:
            skipped.append({**base, "outcome": OUTCOME_INVALID,
                            "error": "locator could not be read: "
                            + str(exc)})
            continue
        if size > MAX_BROWSE_BYTES:
            skipped.append({**base, "outcome": OUTCOME_INVALID,
                            "error": "pack file too large to search"})
            continue
        try:
            raw = Path(entry.locator).read_bytes()
        except OSError as exc:
            skipped.append({**base, "outcome": OUTCOME_INVALID,
                            "error": "locator could not be read: "
                            + str(exc)})
            continue
        try:
            payload, verified = _parse_payload(entry, raw)
        except (ValueError, TypeError) as exc:
            skipped.append({**base, "outcome": OUTCOME_INVALID,
                            "error": str(exc)})
            continue
        searched += 1
        occurrences = 0
        excerpt = ""
        for value in _string_values(payload):
            hits = value.casefold().count(needle)
            if hits:
                if not excerpt:
                    excerpt = _excerpt(value, needle, len(cleaned))
                occurrences += hits
        if occurrences:
            matched.append((entry, occurrences, excerpt, verified))
    total = len(matched)
    truncated = total > MAX_MATCHES
    capped = matched[:MAX_MATCHES]
    list_doc = hub_registry.list_document([row for row, *_ in capped])
    detail_by_id = {
        entry.id: (occ, exc, ver) for entry, occ, exc, ver in capped}
    rows = []
    for row in list_doc["entries"]:
        out = dict(row)
        occ, exc, ver = detail_by_id.get(row["id"], (0, "", ""))
        out["occurrences"] = occ
        out["excerpt"] = exc
        out["verified_content_sha256"] = ver
        rows.append(out)
    if total == 0:
        search_state = SEARCH_STATE_NO_MATCHES
    elif truncated:
        search_state = SEARCH_STATE_MATCHES_TRUNCATED
    else:
        search_state = SEARCH_STATE_MATCHES
    return {
        "schema": CONTENT_SEARCH_SCHEMA,
        "query": cleaned,
        "kind": cleaned_kind,
        "search_state": search_state,
        "matches": rows,
        "match_count": len(rows),
        "total_matches": total,
        "truncated": truncated,
        "entries_considered": len(considered),
        "entries_searched": searched,
        "skipped_entries": skipped,
        "coverage_complete": not skipped,
        "max_browse_bytes": MAX_BROWSE_BYTES,
        "list": list_doc,
        "kind_formats": dict(hub_registry.KIND_FORMATS),
        "notes": list(NOTES),
    }
