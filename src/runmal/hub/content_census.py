"""Hub content census (P-193, Part XII - DERIVED).

P-189 landed the hub census over the registry estate:
it composes P-187's list document and P-188's browse
verdicts and answers whether packs inspect and how the
callers' checksum claims stand. It measures nothing
inside a verified pack - no banked document states how
much verified CONTENT an owner's estate holds: how many
string values its packs carry (the exact text P-191's
content search can search), how many characters that
text runs to, or how the volume splits by kind. P-191's
record names this census open (the house order: content
search before its census, P-180 before P-183), and the
P-192 scout fixes its honest shape. This module is
that census, in the house census pattern: a pure
aggregate composing the owning surfaces verbatim,
classified under a closed law, counts summed from the
composed reads' own values.

- Composition, verbatim roads only - never a second
  parser. Each entry is judged under P-188's locator
  law (registry.locator_state, judged live) and P-188's
  size bound (MAX_BROWSE_BYTES, imported: one bound
  law), then parsed through the owning layer's OWN
  verified parse road, dispatched exactly as P-191
  dispatches: lorebook_pack -> lorebooks.packs.
  parse_pack (payload member lorebook), prompt_pack ->
  presets.packs.parse_pack (payload member items),
  scenario_pack -> scenarios.packs.parse_pack (payload
  member scenario), preset_bundle -> presets.bundles.
  parse_share (the bundle it returns is the payload).
  Each parse road verifies format, manifest against
  payload, the content checksum and the payload itself
  before anything is measured: only a VERIFIED payload
  is measured.
- The measure is P-191's own string walk law: every
  STRING VALUE in the verified payload (dict values
  and list items, in document order) counts once toward
  string_value_count and its length toward
  string_char_count. Never counted, stated plainly:
  dict keys (structure, not content), any value under
  a content_sha256 key (the pack's identity, not its
  content - P-191's exclusion carried in), non-string
  values, the pack envelope (manifest and provenance
  live outside the payload member) and registry
  metadata (P-189's and P-190's surfaces, not repeated
  here).
- DISTINCTNESS, stated plainly (the P-192 scout's
  warning, judged in this slice's scout): a census over
  parse OUTCOMES alone would recount P-189 - inspect
  stands on parse in every pack layer, so parsed counts
  here will usually agree with P-189's inspected
  counts, and that agreement is expected, not the new
  fact. The new facts are the VOLUME axes P-189 has no
  field for: per-row and per-kind string-value and
  string-character totals over the verified payloads,
  and the estate's largest content holder.
- No silent omission (the P-191 law): every entry ends
  parsed, or named by its row's outcome - unavailable
  (the locator is not ready; no read attempted) or
  invalid (unreadable at read time, over the size
  bound, not valid JSON on the bundle road, or the
  owning layer's own parse road refused it, its refusal
  carried verbatim) - under the closed OUTCOMES law,
  and coverage_complete carries the truth as data: any
  non-parsed entry makes it false, and count always
  equals parsed plus unavailable plus invalid.
- NO content is retained or returned: this census
  carries counts, entry data and verified checksums
  only - never an excerpt and never a payload field,
  anywhere in the document (the P-183 law).
- The estate is classified under a closed census law
  (CONTENT_CENSUS_STATES), judged on the content axis:
  no_entries / no_content / some_content / all_content.

Honest boundaries, and the cost stated plainly: a
census parses every ready entry, so it READS pack
files - each through its own layer's verified parse
road, under the 16 MiB bound, so an oversize, corrupt
or wrong-kind pack is an invalid row, never a census
failure. The census writes nothing, imports nothing,
installs nothing, copies nothing and grants nothing;
an entry's registered checksum stays the caller's
claim and is never upgraded by being counted beside
the verified one. Signing and friend-instance exchange
stay declined - no key or transport machinery is
banked. There is no central store, no catalogue and no
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

CONTENT_CENSUS_SCHEMA = "runmal-p193-hub-content-census-v1"

MAX_BROWSE_BYTES = hub_browse.MAX_BROWSE_BYTES  # P-188's bound: one law

OUTCOME_PARSED = "parsed"
OUTCOME_UNAVAILABLE = "unavailable"
OUTCOME_INVALID = "invalid"
OUTCOMES = frozenset({
    OUTCOME_PARSED, OUTCOME_UNAVAILABLE, OUTCOME_INVALID,
})

CONTENT_CENSUS_STATE_NO_ENTRIES = "no_entries"
CONTENT_CENSUS_STATE_NO_CONTENT = "no_content"
CONTENT_CENSUS_STATE_SOME_CONTENT = "some_content"
CONTENT_CENSUS_STATE_ALL_CONTENT = "all_content"
CONTENT_CENSUS_STATES = frozenset({
    CONTENT_CENSUS_STATE_NO_ENTRIES,
    CONTENT_CENSUS_STATE_NO_CONTENT,
    CONTENT_CENSUS_STATE_SOME_CONTENT,
    CONTENT_CENSUS_STATE_ALL_CONTENT,
})

NOTES = (
    "Pure read, owner scoped: only the caller's own "
    "entries are censused; this census stores, "
    "registers, removes, imports, installs, copies "
    "and writes nothing.",
    "Distinctness: P-189's census counts browse "
    "verdicts and checksum claims and measures no "
    "content; this census measures the verified "
    "payloads' content volume - string values and "
    "string characters under P-191's string walk law. "
    "Parsed counts here will usually agree with "
    "P-189's inspected counts because each layer's "
    "inspect road stands on its parse road; that "
    "agreement is expected and stated, and the volume "
    "axes are the new facts.",
    "Cost law: a content census reads and verifies "
    "every ready pack in the estate, each through its "
    "own layer's verified parse road and each under "
    "the browse size bound (max_browse_bytes in this "
    "document) - the price of measuring contents the "
    "registry does not hold.",
    "The walk counts string values only: dict keys, "
    "non-string values, the pack envelope (manifest "
    "and provenance) and registry metadata are never "
    "counted, and any value under a content_sha256 "
    "key is the pack's identity, not its content, and "
    "its subtree is never counted. No content text "
    "appears anywhere in this document - counts, "
    "entry data and verified checksums only.",
    "No silent omission: every entry was parsed or "
    "is named by its row's outcome - unavailable (its "
    "locator is not ready) or invalid (its own layer's "
    "road refused it, it could not be read, or it "
    "exceeds the size bound). coverage_complete is "
    "false whenever any entry was not parsed, and "
    "count always equals parsed plus unavailable "
    "plus invalid.",
    "verified_content_sha256 on a row is the checksum "
    "the owning layer's own parse road verified "
    "(empty for a bare preset bundle, whose road "
    "verifies none, and for any entry that was not "
    "parsed). An entry's registered checksum stays "
    "the caller's claim and is never upgraded by "
    "being counted.",
    "Signing and friend-instance exchange stay "
    "declined: no key or transport machinery is "
    "banked, and this census invents none. There is "
    "no central store, no catalogue and no creator "
    "profile on this road (the VX-59 sovereign "
    "shape).",
)


def _parse_payload(entry: HubEntry, raw: bytes):
    """Dispatch to the owning layer's own verified parse
    road; returns (payload, verified_content_sha256).
    P-191's dispatch, carried verbatim."""
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
    document order (P-191's walk, carried verbatim). A
    value under a content_sha256 key is the pack's
    identity, not its content, and its subtree is never
    walked."""
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


def _string_stats(payload) -> tuple[int, int]:
    """(string value count, total string characters)
    for one verified payload, under the walk law."""
    count = 0
    chars = 0
    for value in _string_values(payload):
        count += 1
        chars += len(value)
    return count, chars


def content_census_document(entries: list[HubEntry]) -> dict:
    """The hub content census for one owner's entries.

    ``entries`` is the owner's own entry list (the
    router hands over HubStore.list_for_owner for the
    caller; a foreign owner's entries are never in
    it). The P-187 list document is composed verbatim
    and embedded whole; each entry is then parsed
    through its own layer's verified parse road and
    its verified payload measured under P-191's walk
    law. Always a document, never an error for a bad
    pack: a pack the owning road refuses is an invalid
    row.
    """
    list_doc = hub_registry.list_document(entries)
    rows = []
    by_outcome = {outcome: 0 for outcome in sorted(OUTCOMES)}
    by_kind_content = {
        kind: {"entries": 0, "parsed": 0,
               "string_values": 0, "string_chars": 0}
        for kind in sorted(hub_registry.HUB_KINDS)}
    total_string_values = 0
    total_string_chars = 0
    largest = None
    for entry in entries:
        row = entry.to_dict()
        state = hub_registry.locator_state(entry.locator)
        row["locator_state"] = state
        row["outcome"] = OUTCOME_UNAVAILABLE
        row["verified_content_sha256"] = ""
        row["string_value_count"] = 0
        row["string_char_count"] = 0
        row["error"] = ""
        kind_axis = by_kind_content.get(entry.kind)
        if kind_axis is not None:
            kind_axis["entries"] += 1
        if state == hub_registry.LOCATOR_READY:
            try:
                size = Path(entry.locator).stat().st_size
            except OSError as exc:
                row["outcome"] = OUTCOME_INVALID
                row["error"] = "locator could not be read: " + str(exc)
            else:
                if size > MAX_BROWSE_BYTES:
                    row["outcome"] = OUTCOME_INVALID
                    row["error"] = "pack file too large to census"
                else:
                    try:
                        raw = Path(entry.locator).read_bytes()
                    except OSError as exc:
                        row["outcome"] = OUTCOME_INVALID
                        row["error"] = (
                            "locator could not be read: " + str(exc))
                    else:
                        try:
                            payload, verified = _parse_payload(entry, raw)
                        except (ValueError, TypeError) as exc:
                            row["outcome"] = OUTCOME_INVALID
                            row["error"] = str(exc)
                        else:
                            values, chars = _string_stats(payload)
                            row["outcome"] = OUTCOME_PARSED
                            row["verified_content_sha256"] = verified
                            row["string_value_count"] = values
                            row["string_char_count"] = chars
        rows.append(row)
        by_outcome[row["outcome"]] += 1
        if row["outcome"] == OUTCOME_PARSED:
            total_string_values += row["string_value_count"]
            total_string_chars += row["string_char_count"]
            if kind_axis is not None:
                kind_axis["parsed"] += 1
                kind_axis["string_values"] += row["string_value_count"]
                kind_axis["string_chars"] += row["string_char_count"]
            if (largest is None
                    or row["string_char_count"] > largest["string_char_count"]):
                largest = {
                    "id": row["id"], "title": row["title"],
                    "kind": row["kind"],
                    "string_value_count": row["string_value_count"],
                    "string_char_count": row["string_char_count"],
                }
    total = len(rows)
    parsed = by_outcome[OUTCOME_PARSED]
    if total == 0:
        census_state = CONTENT_CENSUS_STATE_NO_ENTRIES
    elif parsed == 0:
        census_state = CONTENT_CENSUS_STATE_NO_CONTENT
    elif parsed == total:
        census_state = CONTENT_CENSUS_STATE_ALL_CONTENT
    else:
        census_state = CONTENT_CENSUS_STATE_SOME_CONTENT
    return {
        "schema": CONTENT_CENSUS_SCHEMA,
        "census_state": census_state,
        "count": total,
        "entries_considered": total,
        "parsed_count": parsed,
        "coverage_complete": parsed == total,
        "list": list_doc,
        "entries": rows,
        "by_outcome": by_outcome,
        "by_kind_content": by_kind_content,
        "total_string_values": total_string_values,
        "total_string_chars": total_string_chars,
        "largest_content_entry": largest,
        "max_browse_bytes": MAX_BROWSE_BYTES,
        "kind_formats": dict(hub_registry.KIND_FORMATS),
        "notes": list(NOTES),
    }
