"""P-046 budget battery (@pytest.mark.manual ONLY, design Sec.4.3).

Builds the deterministic 10,000-entry book (the bench harness's
ONE generator, imported -- never duplicated), runs warmup + 7
timed full ticks, and asserts the MEDIAN total stays under the
5.0 s absolute laptop ceiling: a catastrophic-regression
tripwire ~10x the derated BUDGET-P046 gate, generous enough
that a loaded shared machine does not flake. The binding
budget check (single-core pinned median <= 500 ms laptop /
<= 2000 ms Pi-equivalent at x4.0 derating, keyword <= 300 ms /
1200 ms) is run via the harness command in the slice evidence
(hidden_files/P046_EVIDENCE.md), not as a CI assert -- wall-
clock truth lives in evidence, flakiness never in CI.

The test also asserts the tick RESULT on the 10k book equals
the frozen-oracle result (scale must not change semantics);
the oracle here is the same pre-P-046 regex loop, duplicated
in miniature from test_p046_equivalence.py.
"""

from __future__ import annotations

import gc
import importlib.util
import re
import statistics
from pathlib import Path

import pytest

from runmal.lorebooks.activation import ActivatableEntry
from runmal.lorebooks.logic import secondary_gate
from runmal.lorebooks.scan import ScanEntry, ScanHit
from runmal.lorebooks.vector_match import LocalEmbeddingBackend
from runmal.lorebooks.windows import ScanSettings


def _load_bench():
    path = Path(__file__).resolve().parents[1] / "scripts" / "bench_p046_scan.py"
    spec = importlib.util.spec_from_file_location("bench_p046_scan", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _oracle_hits(scan_view, texts):
    """Pre-P-046 scan over one window (frozen regex loop)."""
    hits = []
    for entry in scan_view:
        if not entry.enabled or entry.constant or entry.vectorised:
            continue
        primaries = [k for k in entry.keys if isinstance(k, str) and k.strip()]
        if not primaries:
            continue
        def match(keys, entry=entry):
            matched, indices = [], set()
            for key in keys:
                pattern = re.escape(key)
                if entry.whole_word:
                    pattern = r"\b" + pattern + r"\b"
                rx = re.compile(pattern, 0 if entry.case_sensitive else re.IGNORECASE)
                hit = False
                for i, text in enumerate(texts):
                    if rx.search(text):
                        hit = True
                        indices.add(i)
                if hit:
                    matched.append(key)
            return tuple(matched), indices
        matched_p, idx_p = match(primaries)
        if not matched_p:
            continue
        secondaries = [k for k in entry.secondary_keys if isinstance(k, str) and k.strip()]
        if secondaries:
            matched_s, idx_s = match(secondaries)
            if not secondary_gate(entry.selective_logic, secondary_count=len(secondaries), matched_count=len(matched_s)):
                continue
        else:
            matched_s, idx_s = (), set()
        hits.append(ScanHit(entry_id=entry.id, matched_primary=matched_p, matched_secondary=matched_s, message_indices=tuple(sorted(idx_p | idx_s)), selective_logic=entry.selective_logic))
    return hits


@pytest.mark.manual
def test_p046_budget_tripwire_and_scale_result():
    bench = _load_bench()
    entries = bench.build_book(bench.SEED, 10000)
    messages = bench.build_messages(entries)
    scan_view = [ScanEntry.from_orm(en) for en in entries]
    act_view = [ActivatableEntry.from_orm(en) for en in entries]
    settings = ScanSettings(scan_depth=10, scan_mode="depth", scan_external_context=False)
    backend = LocalEmbeddingBackend()
    # Scale must not change semantics: live windowed scan == oracle.
    from runmal.lorebooks.scan import scan_entries_windowed
    live_hits = scan_entries_windowed(scan_view, list(messages), settings, ())
    assert live_hits == _oracle_hits(scan_view, list(messages))
    assert len(live_hits) == 240
    for _ in range(2):
        bench.run_tick(entries, messages, scan_view, act_view, settings, backend)
    totals, keywords = [], []
    counts = {}
    for _ in range(7):
        gc.collect()
        timing, counts = bench.run_tick(entries, messages, scan_view, act_view, settings, backend)
        totals.append(timing["total"])
        keywords.append(timing["keyword"])
    median_total = statistics.median(totals)
    median_kw = statistics.median(keywords)
    print(f"P-046 budget (unpinned, shared laptop): median total {median_total:.1f} ms, "
          f"keyword {median_kw:.1f} ms; derated x4 Pi-equiv total {median_total * 4:.0f} ms")
    assert counts["keyword_hits"] == 240
    assert counts["vector_candidates"] == 1000
    assert median_total <= 5000.0, f"median tick {median_total:.0f} ms over the 5 s tripwire"
