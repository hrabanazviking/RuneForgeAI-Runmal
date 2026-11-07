"""Keyword scanning for lorebook entries (S202).

Pure-domain module: no DB, no I/O, no network. Given a book's scan depth,
an ordered list of entries, and recent message texts, it determines which
entries trigger by keyword.

Semantics (normative for the lorebook pipeline):
- Disabled entries never trigger.
- ``constant`` entries are NOT handled here; they belong to S203
  (activation semantics). The scanner skips them so S203 can layer
  constant/selective/sticky/cooldown/delay/recursion on top of these hits.
- ``vectorised`` entries (P-035) are NOT keyword-scanned either;
  the scanner skips them too. Their hits arrive from vector
  matching (the embedding matcher is P-041), never from keys.
- An entry with no usable primary keys never triggers via scanning.
  A "usable" key is a non-empty, non-whitespace string.
- Primary keys: the entry is a candidate when ANY primary key matches.
- Secondary keys refine the candidate: when an entry defines secondary
  keys, the entry triggers ONLY when at least one primary key AND at least
  one secondary key both match. (With no secondary keys defined, a primary
  match alone suffices.)
- ``whole_word``: keys match on ``\\b`` word boundaries; otherwise they
  match as substrings. Keys are always ``re.escape``-d first, so
  regex-special characters (``c++``, ``(test)``) match literally.
- ``case_sensitive``: entry flag; matching is case-insensitive otherwise.
- ``scan_depth``: only the last ``scan_depth`` message texts are scanned.
  A key appearing only in older messages does not trigger.
- Scan windows (P-037): ``scan_entries_windowed`` scans the window a
  book's stored ``ScanSettings`` (runmal.lorebooks.windows) resolves:
  ``depth`` mode is exactly the window above; ``whole_chat`` scans
  every message; and when the book's ``scan_external_context`` is on,
  caller-supplied external context texts form a second segment,
  appended after the chat segment and not counted against the
  depth. A hit records chat matches in ``message_indices`` (indices
  into the FULL message list, as above) and external matches in
  ``external_indices`` (indices into the external list), so where a
  key fired is never ambiguous. Primary and secondary keys may be
  satisfied across segments -- the window is one context.
- ``selective_logic``: secondary keys gate the primary hit by the
  entry's mode -- ``and_any`` (the default: at least one secondary
  matches), ``and_all`` (every secondary matches), ``not_any`` (no
  secondary matches), or ``not_all`` (at least one secondary does not
  match). With no usable secondary keys, the mode is not applied and
  a primary match alone suffices, in every mode.

Hits are returned in the input entry order (callers pass entries in
priority order; see S204 for budget/priority resolution). Matching is fully
deterministic: same inputs always produce the same hits.

Near misses (P-043): :func:`scan_near_misses` reports the one
scan-level near miss the plain scan otherwise drops silently --
an entry whose primary key matched but whose secondary gate
(P-032 selective logic) refused the hit. It returns the matched
keys and counts so an inspector can explain the refusal without
re-running matching. Entries with no primary match are not near
misses, and gate-passing entries are hits, not near misses.

Recursive scanning (``scan_entries_recursive``) extends the plain scan
breadth-first: round 0 is exactly ``scan_entries`` over the chat
messages, and each later round scans the *content* of the entries
admitted in the previous round as if it were a fresh message, so an
entry whose content mentions another entry's key pulls that entry in
too. A single global seen set spans every round, so an entry fires at
most once per call no matter how many parents (or cycles) reference
it -- that seen set is the cycle-safety proof: even mutually recursive
entries (A mentions B, B mentions A) terminate, because the second
encounter of any entry is always skipped. Recursion is bounded by ``MAX_RECURSIVE_SCAN_DEPTH`` and, optionally,
by a token budget. Round-0 (direct) hits are always admitted and
their content cost is counted in ``tokens_used`` -- in the pipeline
the budget/priority pass (S204) makes the final inclusion call on
direct hits. The budget bounds *expansion*: a recursive candidate
that does not fit the remaining budget is skipped (and never scanned
later) while smaller later candidates may still be admitted, and once
admitted content meets or exceeds the budget no further rounds run.
Within a round, candidates are considered in input (priority) order,
not in order of mention. One deliberate narrowing vs. round 0: in a
recursive round an entry's primary AND secondary keys must co-occur
in the single parent content that triggers it (round 0 may satisfy
them from different messages inside the scan window) -- that is what
keeps ``triggered_by`` attribution to one parent honest.
``budget_exhausted`` reports that the budget stopped, or would stop,
expansion. Disabled, constant and vectorised entries are skipped in
every round, exactly as in the plain scan (recursive rounds inherit
the skip because they call ``scan_entries``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from runmal.lorebooks.logic import normalise_selective_logic, secondary_gate
from runmal.lorebooks.states import normalise_vectorised
from runmal.lorebooks.windows import ScanSettings, build_scan_window
from runmal.tokens import estimate_tokens

#: Hard cap on recursive-scan rounds (mirrors activation.MAX_RECURSION_DEPTH).
MAX_RECURSIVE_SCAN_DEPTH = 5


@dataclass(frozen=True)
class ScanEntry:
    """Minimal scannable view of a lorebook entry."""

    id: str
    enabled: bool = True
    constant: bool = False
    vectorised: bool = False
    keys: tuple[str, ...] = ()
    secondary_keys: tuple[str, ...] = ()
    whole_word: bool = True
    case_sensitive: bool = False
    content: str = ""
    selective_logic: str = "and_any"

    @classmethod
    def from_orm(cls, entry) -> "ScanEntry":
        """Adapt a SQLAlchemy LoreEntry (or anything with the same shape)."""
        import json as _json

        def _decode(raw: str) -> tuple[str, ...]:
            try:
                decoded = _json.loads(raw)
            except _json.JSONDecodeError:
                return ()
            if not isinstance(decoded, list):
                return ()
            return tuple(str(k) for k in decoded)

        return cls(
            id=str(entry.id),
            enabled=bool(entry.enabled),
            constant=bool(entry.constant),
            vectorised=normalise_vectorised(getattr(entry, "vectorised", False)),
            keys=_decode(entry.keys_json),
            secondary_keys=_decode(entry.secondary_keys_json),
            whole_word=bool(entry.whole_word),
            case_sensitive=bool(entry.case_sensitive),
            content=str(getattr(entry, "content", "") or ""),
            selective_logic=normalise_selective_logic(
                getattr(entry, "selective_logic", None)
            ),
        )


@dataclass(frozen=True)
class ScanHit:
    """One triggered entry: which keys matched, and where."""

    entry_id: str
    matched_primary: tuple[str, ...] = ()
    matched_secondary: tuple[str, ...] = ()
    # 0-based indices into the FULL message list passed to scan_entries.
    message_indices: tuple[int, ...] = ()
    depth: int = 0
    triggered_by: str | None = None
    selective_logic: str = "and_any"
    # P-037: indices into the caller's external-context list for
    # matches in the window's external segment (() when none).
    external_indices: tuple[int, ...] = ()


def _usable(keys: tuple[str, ...]) -> list[str]:
    return [k for k in keys if isinstance(k, str) and k.strip()]


def _compile(key: str, whole_word: bool, case_sensitive: bool) -> "re.Pattern[str]":
    pattern = re.escape(key)
    if whole_word:
        pattern = r"\b" + pattern + r"\b"
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(pattern, flags)


def _match_keys(
    keys: list[str],
    window: list[str],
    offset: int,
    whole_word: bool,
    case_sensitive: bool,
) -> tuple[tuple[str, ...], tuple[int, ...]]:
    matched: list[str] = []
    indices: set[int] = set()
    for key in keys:
        rx = _compile(key, whole_word, case_sensitive)
        hit_here = False
        for i, text in enumerate(window):
            if rx.search(text):
                hit_here = True
                indices.add(offset + i)
        if hit_here:
            matched.append(key)
    return tuple(matched), tuple(sorted(indices))


def _scan_texts(
    entries: list[ScanEntry],
    texts: list[str],
) -> list[ScanHit]:
    """Scan ``texts`` as one window; hit indices are window positions.

    The single matching core: scan_entries (depth window) and
    scan_entries_windowed (P-037 settings window) both run it and
    then translate positions into their own index spaces, so the
    two paths can never drift in matching semantics.
    """
    hits: list[ScanHit] = []
    for entry in entries:
        if not entry.enabled or entry.constant or entry.vectorised:
            continue
        primaries = _usable(entry.keys)
        if not primaries:
            continue
        matched_p, idx_p = _match_keys(
            primaries, texts, 0, entry.whole_word, entry.case_sensitive
        )
        if not matched_p:
            continue
        secondaries = _usable(entry.secondary_keys)
        if secondaries:
            matched_s, idx_s = _match_keys(
                secondaries, texts, 0, entry.whole_word, entry.case_sensitive
            )
            if not secondary_gate(
                entry.selective_logic,
                secondary_count=len(secondaries),
                matched_count=len(matched_s),
            ):
                continue
        else:
            matched_s, idx_s = (), ()
        hits.append(
            ScanHit(
                entry_id=entry.id,
                matched_primary=matched_p,
                matched_secondary=matched_s,
                message_indices=tuple(sorted(set(idx_p) | set(idx_s))),
                selective_logic=entry.selective_logic,
            )
        )
    return hits


def scan_entries(
    entries: list[ScanEntry],
    messages: list[str],
    scan_depth: int,
) -> list[ScanHit]:
    """Scan the last ``scan_depth`` messages; return hits in entry order.

    Constant and vectorised entries are skipped: vectorised entries
    are not keyword-scanned (P-035); their hits arrive from vector
    matching (P-041).
    """
    if scan_depth < 1:
        raise ValueError("scan_depth must be >= 1")
    if not messages or not entries:
        return []
    window = messages[-scan_depth:]
    offset = len(messages) - len(window)
    return [
        replace(hit, message_indices=tuple(i + offset for i in hit.message_indices))
        for hit in _scan_texts(entries, list(window))
    ]


def scan_entries_windowed(
    entries: list[ScanEntry],
    messages: list[str],
    settings: ScanSettings,
    external_context=(),
) -> list[ScanHit]:
    """Scan the window ``settings`` resolves (P-037).

    Same matching semantics as :func:`scan_entries` (the shared
    ``_scan_texts`` core), over the window built by
    runmal.lorebooks.windows: the chat segment per the book's
    scan mode plus, when enabled, the external segment. Chat
    matches report indices into the FULL ``messages`` list;
    external matches report ``external_indices`` into
    ``external_context``. With depth settings and no external
    segment this returns exactly what ``scan_entries`` returns
    for the same depth.
    """
    if not entries:
        return []
    window = build_scan_window(settings, list(messages), external_context)
    if not window.texts:
        return []
    hits: list[ScanHit] = []
    for hit in _scan_texts(entries, list(window.texts)):
        chat_idx: set[int] = set()
        ext_idx: set[int] = set()
        for pos in hit.message_indices:
            msg_i = window.message_indices[pos]
            if msg_i is not None:
                chat_idx.add(msg_i)
            else:
                ext_i = window.external_indices[pos]
                assert ext_i is not None
                ext_idx.add(ext_i)
        hits.append(
            replace(
                hit,
                message_indices=tuple(sorted(chat_idx)),
                external_indices=tuple(sorted(ext_idx)),
            )
        )
    return hits


@dataclass(frozen=True)
class NearMiss:
    """One secondary-gate near miss (P-043): primary matched, gate refused."""

    entry_id: str
    matched_primary: tuple[str, ...] = ()
    matched_secondary: tuple[str, ...] = ()
    secondary_count: int = 0
    selective_logic: str = "and_any"
    # 0-based indices into the FULL message list (chat matches).
    message_indices: tuple[int, ...] = ()
    # P-037: indices into the external-context list.
    external_indices: tuple[int, ...] = ()


def _near_misses_texts(
    entries: list[ScanEntry],
    texts: list[str],
) -> list[NearMiss]:
    """Near misses over one window; indices are window positions."""
    out: list[NearMiss] = []
    for entry in entries:
        if not entry.enabled or entry.constant or entry.vectorised:
            continue
        primaries = _usable(entry.keys)
        if not primaries:
            continue
        matched_p, idx_p = _match_keys(
            primaries, texts, 0, entry.whole_word, entry.case_sensitive
        )
        if not matched_p:
            continue
        secondaries = _usable(entry.secondary_keys)
        if not secondaries:
            continue
        matched_s, idx_s = _match_keys(
            secondaries, texts, 0, entry.whole_word, entry.case_sensitive
        )
        if secondary_gate(
            entry.selective_logic,
            secondary_count=len(secondaries),
            matched_count=len(matched_s),
        ):
            continue
        out.append(
            NearMiss(
                entry_id=entry.id,
                matched_primary=matched_p,
                matched_secondary=matched_s,
                secondary_count=len(secondaries),
                selective_logic=entry.selective_logic,
                message_indices=tuple(sorted(set(idx_p) | set(idx_s))),
            )
        )
    return out


def scan_near_misses(
    entries: list[ScanEntry],
    messages: list[str],
    settings: ScanSettings,
    external_context=(),
) -> list[NearMiss]:
    """Secondary-gate near misses over the window ``settings`` resolves.

    Same matching semantics as :func:`scan_entries_windowed` (the
    shared ``_match_keys`` core plus P-032's ``secondary_gate``);
    an entry appears here exactly when it has at least one usable
    primary key matched in the window, defines usable secondary
    keys, and the gate refuses. Chat matches report indices into
    the FULL ``messages`` list; external matches report
    ``external_indices``. Deterministic, input order.
    """
    if not entries:
        return []
    window = build_scan_window(settings, list(messages), external_context)
    if not window.texts:
        return []
    out: list[NearMiss] = []
    for miss in _near_misses_texts(entries, list(window.texts)):
        chat_idx: set[int] = set()
        ext_idx: set[int] = set()
        for pos in miss.message_indices:
            msg_i = window.message_indices[pos]
            if msg_i is not None:
                chat_idx.add(msg_i)
            else:
                ext_i = window.external_indices[pos]
                assert ext_i is not None
                ext_idx.add(ext_i)
        out.append(
            replace(
                miss,
                message_indices=tuple(sorted(chat_idx)),
                external_indices=tuple(sorted(ext_idx)),
            )
        )
    return out


@dataclass(frozen=True)
class RecursiveScanResult:
    """Outcome of :func:`scan_entries_recursive`."""

    hits: tuple[ScanHit, ...]
    tokens_used: int
    budget_exhausted: bool
    depth_reached: int


def scan_entries_recursive(
    entries,
    messages,
    scan_depth,
    *,
    max_recursion_depth=MAX_RECURSIVE_SCAN_DEPTH,
    token_budget=None,
    settings: ScanSettings | None = None,
    external_context=None,
) -> RecursiveScanResult:
    """Recursively scan entries, following keyword links in entry content.

    Round 0 is :func:`scan_entries` over ``messages`` -- or, when
    ``settings`` is given (P-037), :func:`scan_entries_windowed`
    over the book's resolved window (``scan_depth`` is then the
    fallback for callers that pass no settings, and the settings'
    own depth governs); later rounds scan
    each admitted entry's ``content`` for further entries' keys (BFS,
    deterministic admission order). An entry fires at most once per call
    (global seen set), which makes reference cycles terminate. See the
    module docstring for the full semantics.
    """
    if (
        isinstance(max_recursion_depth, bool)
        or not isinstance(max_recursion_depth, int)
        or max_recursion_depth < 0
    ):
        raise ValueError("max_recursion_depth must be an int >= 0")
    if token_budget is not None and (
        isinstance(token_budget, bool)
        or not isinstance(token_budget, int)
        or token_budget < 1
    ):
        raise ValueError("token_budget must be None or an int >= 1")

    entries = list(entries)
    if max_recursion_depth > MAX_RECURSIVE_SCAN_DEPTH:
        max_recursion_depth = MAX_RECURSIVE_SCAN_DEPTH

    entry_by_id: dict[str, ScanEntry] = {}
    for _entry in entries:
        entry_by_id.setdefault(_entry.id, _entry)

    admitted: list[ScanHit] = []
    seen: set[str] = set()
    tokens_used = 0
    budget_exhausted = False

    if settings is not None:
        round0_hits = scan_entries_windowed(
            entries, messages, settings, external_context or ()
        )
    else:
        round0_hits = scan_entries(entries, messages, scan_depth)
    frontier: list[ScanEntry] = []
    for hit in round0_hits:
        if hit.entry_id in seen:
            continue  # duplicate id rows: an entry fires at most once
        target = entry_by_id.get(hit.entry_id)
        content = target.content if target is not None else ""
        admitted.append(
            ScanHit(
                entry_id=hit.entry_id,
                matched_primary=hit.matched_primary,
                matched_secondary=hit.matched_secondary,
                message_indices=hit.message_indices,
                depth=0,
                triggered_by=None,
                selective_logic=hit.selective_logic,
                external_indices=hit.external_indices,
            )
        )
        seen.add(hit.entry_id)
        tokens_used += estimate_tokens(content)
        if target is not None:
            frontier.append(target)

    if token_budget is not None and tokens_used >= token_budget:
        budget_exhausted = True

    if max_recursion_depth == 0 or not admitted:
        return RecursiveScanResult(
            hits=tuple(admitted),
            tokens_used=tokens_used,
            budget_exhausted=budget_exhausted,
            depth_reached=0,
        )

    for depth in range(1, max_recursion_depth + 1):
        if token_budget is not None and tokens_used >= token_budget:
            budget_exhausted = True
            break
        next_frontier: list[ScanEntry] = []
        for parent in frontier:
            if not parent.content:
                continue
            for hit in scan_entries(entries, [parent.content], 1):
                if hit.entry_id in seen:
                    continue
                seen.add(hit.entry_id)
                target = entry_by_id.get(hit.entry_id)
                target_content = target.content if target is not None else ""
                cost = estimate_tokens(target_content)
                if token_budget is not None and cost > token_budget - tokens_used:
                    budget_exhausted = True
                    continue
                admitted.append(
                    ScanHit(
                        entry_id=hit.entry_id,
                        matched_primary=hit.matched_primary,
                        matched_secondary=hit.matched_secondary,
                        message_indices=(),
                        depth=depth,
                        triggered_by=parent.id,
                        selective_logic=hit.selective_logic,
                    )
                )
                tokens_used += cost
                if target is not None:
                    next_frontier.append(target)
        if not next_frontier:
            break
        frontier = next_frontier

    depth_reached = max((h.depth for h in admitted), default=0)
    return RecursiveScanResult(
        hits=tuple(admitted),
        tokens_used=tokens_used,
        budget_exhausted=budget_exhausted,
        depth_reached=depth_reached,
    )
