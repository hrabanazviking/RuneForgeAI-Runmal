"""P-046 equivalence battery (ALWAYS RUN, STRICT).

Roadmap line: *Performance: a 10,000-entry book scans within a
stated budget on Pi-class hardware.*

This file is the licence for the P-046 optimisations (design
Sec.4.1): a frozen reference oracle -- the pre-P-046 scan/match
logic copied verbatim from base c0cec73 (P-044 banking record)
BEFORE any optimisation landed -- runs against the live
functions on seeded books, and every result must be EXACTLY
equal: ScanHit lists (ids, matched keys, message/external
indices, order), near-miss lists, recursive results, and
vector scores to full float equality (the local backend is
deterministic). Any diff here blocks banking, no exceptions.

The oracle's matching core (compile / match / scan / near-miss
/ recursive BFS) is the frozen copy; window construction and
the secondary gate are imported live because P-046 does not
touch windows.py or logic.py.
"""

from __future__ import annotations

import importlib.util
import random
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from runmal.lorebooks.logic import secondary_gate
from runmal.lorebooks.scan import (
    MAX_RECURSIVE_SCAN_DEPTH,
    NearMiss,
    ScanEntry,
    ScanHit,
    scan_entries,
    scan_entries_recursive,
    scan_entries_windowed,
    scan_near_misses,
)
from runmal.lorebooks.vector_match import (
    LocalEmbeddingBackend,
    cosine_similarity,
    match_vectorised_sync,
    match_with_vectors,
    vector_candidates,
)
from runmal.lorebooks.windows import ScanSettings, build_scan_window
from runmal.tokens import estimate_tokens

# ------------------------------------------------------------------ oracle
# Frozen pre-P-046 logic (base c0cec73), copied before optimisation.


def _oracle_compile(key, whole_word, case_sensitive):
    pattern = re.escape(key)
    if whole_word:
        pattern = r"\b" + pattern + r"\b"
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(pattern, flags)


def _oracle_match_keys(keys, window, offset, whole_word, case_sensitive):
    matched = []
    indices = set()
    for key in keys:
        rx = _oracle_compile(key, whole_word, case_sensitive)
        hit_here = False
        for i, text in enumerate(window):
            if rx.search(text):
                hit_here = True
                indices.add(offset + i)
        if hit_here:
            matched.append(key)
    return tuple(matched), tuple(sorted(indices))


def _oracle_usable(keys):
    return [k for k in keys if isinstance(k, str) and k.strip()]


def _oracle_scan_texts(entries, texts):
    hits = []
    for entry in entries:
        if not entry.enabled or entry.constant or entry.vectorised:
            continue
        primaries = _oracle_usable(entry.keys)
        if not primaries:
            continue
        matched_p, idx_p = _oracle_match_keys(
            primaries, texts, 0, entry.whole_word, entry.case_sensitive
        )
        if not matched_p:
            continue
        secondaries = _oracle_usable(entry.secondary_keys)
        if secondaries:
            matched_s, idx_s = _oracle_match_keys(
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


def oracle_scan_entries(entries, messages, scan_depth):
    if scan_depth < 1:
        raise ValueError("scan_depth must be >= 1")
    if not messages or not entries:
        return []
    window = messages[-scan_depth:]
    offset = len(messages) - len(window)
    return [
        replace(hit, message_indices=tuple(i + offset for i in hit.message_indices))
        for hit in _oracle_scan_texts(entries, list(window))
    ]


def _translate(window, positions):
    chat_idx, ext_idx = set(), set()
    for pos in positions:
        msg_i = window.message_indices[pos]
        if msg_i is not None:
            chat_idx.add(msg_i)
        else:
            ext_idx.add(window.external_indices[pos])
    return tuple(sorted(chat_idx)), tuple(sorted(ext_idx))


def oracle_scan_windowed(entries, messages, settings, external_context=()):
    if not entries:
        return []
    window = build_scan_window(settings, list(messages), external_context)
    if not window.texts:
        return []
    out = []
    for hit in _oracle_scan_texts(entries, list(window.texts)):
        chat_idx, ext_idx = _translate(window, hit.message_indices)
        out.append(replace(hit, message_indices=chat_idx, external_indices=ext_idx))
    return out


def _oracle_near_misses_texts(entries, texts):
    out = []
    for entry in entries:
        if not entry.enabled or entry.constant or entry.vectorised:
            continue
        primaries = _oracle_usable(entry.keys)
        if not primaries:
            continue
        matched_p, idx_p = _oracle_match_keys(
            primaries, texts, 0, entry.whole_word, entry.case_sensitive
        )
        if not matched_p:
            continue
        secondaries = _oracle_usable(entry.secondary_keys)
        if not secondaries:
            continue
        matched_s, idx_s = _oracle_match_keys(
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


def oracle_near_misses(entries, messages, settings, external_context=()):
    if not entries:
        return []
    window = build_scan_window(settings, list(messages), external_context)
    if not window.texts:
        return []
    out = []
    for miss in _oracle_near_misses_texts(entries, list(window.texts)):
        chat_idx, ext_idx = _translate(window, miss.message_indices)
        out.append(replace(miss, message_indices=chat_idx, external_indices=ext_idx))
    return out


def oracle_recursive(entries, messages, scan_depth, *, max_recursion_depth=MAX_RECURSIVE_SCAN_DEPTH, token_budget=None, settings=None, external_context=None):
    """Frozen BFS replication: oracle scans + the live algorithm's
    admission/budget rules (scan_entries_recursive itself is not
    modified by P-046 except through the shared scan core)."""
    entries = list(entries)
    if max_recursion_depth > MAX_RECURSIVE_SCAN_DEPTH:
        max_recursion_depth = MAX_RECURSIVE_SCAN_DEPTH
    entry_by_id = {}
    for ent in entries:
        entry_by_id.setdefault(ent.id, ent)
    admitted, seen, tokens_used, budget_exhausted = [], set(), 0, False
    if settings is not None:
        round0 = oracle_scan_windowed(entries, messages, settings, external_context or ())
    else:
        round0 = oracle_scan_entries(entries, messages, scan_depth)
    frontier = []
    for hit in round0:
        if hit.entry_id in seen:
            continue
        target = entry_by_id.get(hit.entry_id)
        content = target.content if target is not None else ""
        admitted.append(ScanHit(entry_id=hit.entry_id, matched_primary=hit.matched_primary, matched_secondary=hit.matched_secondary, message_indices=hit.message_indices, depth=0, triggered_by=None, selective_logic=hit.selective_logic, external_indices=hit.external_indices))
        seen.add(hit.entry_id)
        tokens_used += estimate_tokens(content)
        if target is not None:
            frontier.append(target)
    if token_budget is not None and tokens_used >= token_budget:
        budget_exhausted = True
    if max_recursion_depth == 0 or not admitted:
        return tuple(admitted), tokens_used, budget_exhausted, 0
    for depth in range(1, max_recursion_depth + 1):
        if token_budget is not None and tokens_used >= token_budget:
            budget_exhausted = True
            break
        next_frontier = []
        for parent in frontier:
            if not parent.content:
                continue
            for hit in oracle_scan_entries(entries, [parent.content], 1):
                if hit.entry_id in seen:
                    continue
                seen.add(hit.entry_id)
                target = entry_by_id.get(hit.entry_id)
                target_content = target.content if target is not None else ""
                cost = estimate_tokens(target_content)
                if token_budget is not None and cost > token_budget - tokens_used:
                    budget_exhausted = True
                    continue
                admitted.append(ScanHit(entry_id=hit.entry_id, matched_primary=hit.matched_primary, matched_secondary=hit.matched_secondary, message_indices=(), depth=depth, triggered_by=parent.id, selective_logic=hit.selective_logic))
                tokens_used += cost
                if target is not None:
                    next_frontier.append(target)
        if not next_frontier:
            break
        frontier = next_frontier
    depth_reached = max((h.depth for h in admitted), default=0)
    return tuple(admitted), tokens_used, budget_exhausted, depth_reached


# ---------------------------------------------------------------- fixtures

KEY_POOL = [
    "dragon", "Cat", "cat", "c++", "(test)", "red fox", "ice-cream",
    "sword", "song", "\u017fong", "SONG", "CaseKey", "lorekey", "a",
    "fire breath", "x", "under_score", "1234", "caf\u00e9", "don't",
]
TEXT_POOL = [
    "the dragon woke at dawn", "a Cat sat, then a cat ran",
    "concatenate this string", "i love c++ and (test) driven code",
    "the red fox jumps; an ice-cream melts", "SONG of the \u017fong singer",
    "CaseKey and casekey differ", "sword sword SWORD", "caf\u00e9 lorekey a",
    "don't stop the fire breath", "under_score and 1234 tokens here",
    "\u017fong alone", "nothing relevant in this one", "x marks x",
]
LOGICS = ["and_any", "and_all", "not_any", "not_all"]


def make_book(seed, n):
    rng = random.Random(seed)
    entries = []
    for i in range(n):
        keys = tuple(rng.choice(KEY_POOL) for _ in range(rng.randint(0, 3)))
        secs = tuple(rng.choice(KEY_POOL) for _ in range(rng.randint(0, 2)))
        entries.append(ScanEntry(
            id=f"e{i:04d}",
            enabled=rng.random() > 0.1,
            constant=rng.random() < 0.05,
            vectorised=rng.random() < 0.05,
            keys=keys, secondary_keys=secs,
            whole_word=rng.random() > 0.3,
            case_sensitive=rng.random() < 0.3,
            content=rng.choice(TEXT_POOL),
            selective_logic=rng.choice(LOGICS),
        ))
    return entries


def make_messages(seed, n=6):
    rng = random.Random(seed)
    return [rng.choice(TEXT_POOL) for _ in range(n)]


def special_book():
    def e(eid, **kw):
        base = dict(enabled=True, constant=False, vectorised=False, keys=(),
                    secondary_keys=(), whole_word=True, case_sensitive=False,
                    content="", selective_logic="and_any")
        base.update(kw)
        return ScanEntry(id=eid, **base)
    return [
        e("plus", keys=("c++",)),
        e("paren", keys=("(test)",)),
        e("multi", keys=("red fox",)),
        e("hyphen", keys=("ice-cream",)),
        e("long-s", keys=("\u017fong",)),
        e("ascii-song", keys=("SONG",)),
        e("sub", keys=("cat",), whole_word=False),
        e("cs", keys=("CaseKey",), case_sensitive=True),
        e("dup", keys=("dragon",)),
        e("dup", keys=("sword",)),  # duplicate id, other keys
        e("gate-any", keys=("dragon",), secondary_keys=("fire breath",), selective_logic="and_any"),
        e("gate-all", keys=("dragon",), secondary_keys=("sword", "x"), selective_logic="and_all"),
        e("gate-notany", keys=("dragon",), secondary_keys=("sword",), selective_logic="not_any"),
        e("gate-notall", keys=("dragon",), secondary_keys=("sword", "zzz"), selective_logic="not_all"),
        e("off", keys=("dragon",), enabled=False),
        e("const", keys=("dragon",), constant=True),
        e("vec", keys=("dragon",), vectorised=True),
    ]


# ------------------------------------------------------------------- tests


def test_scan_entries_equivalence_seeded_sizes():
    for n in (0, 1, 100, 1000):
        book = make_book(4600 + n, n)
        msgs = make_messages(9700 + n)
        for depth in (1, 3, 6):
            assert scan_entries(book, msgs, depth) == oracle_scan_entries(book, msgs, depth)


def test_scan_entries_equivalence_special_cases():
    msgs = TEXT_POOL
    for depth in (2, len(msgs)):
        assert scan_entries(special_book(), msgs, depth) == oracle_scan_entries(special_book(), msgs, depth)


def test_windowed_equivalence_with_external_context():
    book = make_book(4242, 200) + special_book()
    msgs = make_messages(3131, 8)
    external = ["an external dragon with a sword", "\u017fong in external", "plain filler"]
    for mode in ("depth", "whole_chat"):
        settings = ScanSettings(scan_depth=3, scan_mode=mode, scan_external_context=True)
        live = scan_entries_windowed(book, msgs, settings, external)
        want = oracle_scan_windowed(book, msgs, settings, external)
        assert live == want
        settings_off = ScanSettings(scan_depth=3, scan_mode=mode, scan_external_context=False)
        assert scan_entries_windowed(book, msgs, settings_off) == oracle_scan_windowed(book, msgs, settings_off)


def test_near_misses_equivalence():
    book = make_book(5150, 300) + special_book()
    msgs = make_messages(6161, 8)
    external = ["external sword x"]
    settings = ScanSettings(scan_depth=4, scan_mode="depth", scan_external_context=True)
    assert scan_near_misses(book, msgs, settings, external) == oracle_near_misses(book, msgs, settings, external)


def test_recursive_equivalence():
    def e(eid, keys, content):
        return ScanEntry(id=eid, keys=tuple(keys), content=content)
    book = [
        e("a", ["alpha"], "this mentions beta loudly"),
        e("b", ["beta"], "and gamma follows"),
        e("c", ["gamma"], "alpha again (cycle)"),
        e("d", ["delta"], "unrelated"),
        e("e2", ["alpha"], "second alpha holder"),
    ]
    msgs = ["alpha rises"]
    for budget in (None, 3, 100):
        live = scan_entries_recursive(book, msgs, 1, token_budget=budget)
        want = oracle_recursive(book, msgs, 1, token_budget=budget)
        assert (live.hits, live.tokens_used, live.budget_exhausted, live.depth_reached) == want
    seeded = make_book(777, 120)
    live = scan_entries_recursive(seeded, make_messages(778), 2)
    want = oracle_recursive(seeded, make_messages(778), 2)
    assert (live.hits, live.tokens_used, live.budget_exhausted, live.depth_reached) == want


def _orm(eid, name, content, keys=(), **kw):
    base = dict(id=eid, name=name, content=content, enabled=True, constant=False,
                vectorised=True, keys=tuple(keys), whole_word=True,
                case_sensitive=False, selective_logic="and_any")
    base.update(kw)
    return SimpleNamespace(**base)


def test_vector_scores_match_cosine_oracle():
    entries = [
        _orm("d", "Dragon Peaks", "Dragons fly over high mountain peaks", ("dragon",)),
        _orm("b", "Market Bread", "Fresh bread is baked at dawn", ("bread",)),
        _orm("bell", "Gale Bell", "The bell rings when storms approach", ("gale bell",)),
        _orm("off", "Off", "dragon dragon", ("dragon",), enabled=False),
    ]
    backend = LocalEmbeddingBackend()
    candidates = vector_candidates(entries)
    query = backend.embed_sync(["a dragon over the mountains"]).vectors[0]
    vectors = {c.id: v for c, v in zip(candidates, backend.embed_sync([c.embed_text for c in candidates]).vectors, strict=True)}
    out = match_with_vectors(entries, ["a dragon over the mountains"], query, vectors)
    expected_scores = {cid: cosine_similarity(query, vec) for cid, vec in vectors.items()}
    assert out.scores == expected_scores  # full float equality
    order = {c.id: i for i, c in enumerate(candidates)}
    expected_ranked = tuple(sorted(expected_scores.items(), key=lambda kv: (-kv[1], order[kv[0]], kv[0])))
    assert out.ranked == expected_ranked
    sync_out = match_vectorised_sync(entries, ["a dragon over the mountains"], backend.embed_sync)
    assert sync_out.scores == expected_scores
    assert sync_out.ranked == expected_ranked
    assert sync_out.hit_ids == out.hit_ids


def _load_bench():
    path = Path(__file__).resolve().parents[1] / "scripts" / "bench_p046_scan.py"
    spec = importlib.util.spec_from_file_location("bench_p046_scan", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ten_k_book_scale_equivalence():
    bench = _load_bench()
    entries = bench.build_book(bench.SEED, 10000)
    messages = bench.build_messages(entries)
    scan_view = [ScanEntry.from_orm(en) for en in entries]
    settings = ScanSettings(scan_depth=10, scan_mode="depth", scan_external_context=False)
    live = scan_entries_windowed(scan_view, messages, settings)
    want = oracle_scan_windowed(scan_view, messages, settings)
    assert live == want
    assert len(live) == 240  # bench-pinned hit count (seed 46046)
    backend = LocalEmbeddingBackend()
    out = match_vectorised_sync(entries, messages, backend.embed_sync, settings=settings)
    candidates = vector_candidates(entries)
    result = backend.embed_sync([c.embed_text for c in candidates])
    # strict float check: recompute every score from raw vectors
    from runmal.lorebooks.vector_match import _window_query_text
    qtext = _window_query_text(messages, settings, ())
    qvec = backend.embed_sync([qtext]).vectors[0]
    for cand, vec in zip(candidates, result.vectors, strict=True):
        assert out.scores[cand.id] == cosine_similarity(qvec, vec)
