"""Keyword scanning for lorebook entries (S202).

Pure-domain module: no DB, no I/O, no network. Given a book's scan depth,
an ordered list of entries, and recent message texts, it determines which
entries trigger by keyword.

Semantics (normative for the lorebook pipeline):
- Disabled entries never trigger.
- ``constant`` entries are NOT handled here; they belong to S203
  (activation semantics). The scanner skips them so S203 can layer
  constant/selective/sticky/cooldown/delay/recursion on top of these hits.
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

Hits are returned in the input entry order (callers pass entries in
priority order; see S204 for budget/priority resolution). Matching is fully
deterministic: same inputs always produce the same hits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ScanEntry:
    """Minimal scannable view of a lorebook entry."""

    id: str
    enabled: bool = True
    constant: bool = False
    keys: tuple[str, ...] = ()
    secondary_keys: tuple[str, ...] = ()
    whole_word: bool = True
    case_sensitive: bool = False

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
            keys=_decode(entry.keys_json),
            secondary_keys=_decode(entry.secondary_keys_json),
            whole_word=bool(entry.whole_word),
            case_sensitive=bool(entry.case_sensitive),
        )


@dataclass(frozen=True)
class ScanHit:
    """One triggered entry: which keys matched, and where."""

    entry_id: str
    matched_primary: tuple[str, ...] = ()
    matched_secondary: tuple[str, ...] = ()
    # 0-based indices into the FULL message list passed to scan_entries.
    message_indices: tuple[int, ...] = ()


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


def scan_entries(
    entries: list[ScanEntry],
    messages: list[str],
    scan_depth: int,
) -> list[ScanHit]:
    """Scan the last ``scan_depth`` messages; return hits in entry order."""
    if scan_depth < 1:
        raise ValueError("scan_depth must be >= 1")
    if not messages or not entries:
        return []
    window = messages[-scan_depth:]
    offset = len(messages) - len(window)

    hits: list[ScanHit] = []
    for entry in entries:
        if not entry.enabled or entry.constant:
            continue
        primaries = _usable(entry.keys)
        if not primaries:
            continue
        matched_p, idx_p = _match_keys(
            primaries, window, offset, entry.whole_word, entry.case_sensitive
        )
        if not matched_p:
            continue
        secondaries = _usable(entry.secondary_keys)
        if secondaries:
            matched_s, idx_s = _match_keys(
                secondaries, window, offset, entry.whole_word, entry.case_sensitive
            )
            if not matched_s:
                continue  # primary hit, but no secondary: no trigger
        else:
            matched_s, idx_s = (), ()
        hits.append(
            ScanHit(
                entry_id=entry.id,
                matched_primary=matched_p,
                matched_secondary=matched_s,
                message_indices=tuple(sorted(set(idx_p) | set(idx_s))),
            )
        )
    return hits
