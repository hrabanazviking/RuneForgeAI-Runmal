#!/usr/bin/env python3
"""P-046 bench: 10,000-entry lorebook full scan tick.

One tick (design Sec.0) = scan_entries_windowed (P-037 depth
window, scan_depth=10 over 10 messages) + match_vectorised_sync
with LocalEmbeddingBackend (local/hash-ngram-1, 256 dims) +
activate() over combined hits, fresh state. No DB, no network.

Run:  taskset -c 2 python scripts/bench_p046_scan.py --json
      python scripts/bench_p046_scan.py --verify
Budget BUDGET-P046 (stated pre-measurement, design Sec.1):
Pi-equivalent (laptop single-core median x4.0) full tick
<=2000 ms and keyword component <=1200 ms; operative laptop
gates: full <=500 ms, keyword <=300 ms, single-core pinned.
Stdlib only in this script; runmal imports are lazy.
"""
from __future__ import annotations
import argparse, gc, json, os, platform, random, statistics, subprocess, sys, time
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
SEED = 46046
VOCAB = [f"word{i:04d}" for i in range(1200)]
GATE_TOTAL_MS = 500.0
GATE_KEYWORD_MS = 300.0
DERATING = 4.0

def _entry(idx, cat, keys, sec, content, rng, **kw):
    e = SimpleNamespace(
        id=f"e{idx:05d}", name=f"Entry {idx:05d}", content=content,
        enabled=True, constant=False, vectorised=False,
        keys=tuple(keys), keys_json=json.dumps(list(keys)),
        secondary_keys=tuple(sec),
        secondary_keys_json=json.dumps(list(sec)),
        whole_word=True, case_sensitive=False,
        selective_logic="and_any", sticky_prompts=0,
        cooldown_prompts=0, delay_prompts=0, inclusion_group="",
        group_weight=100, priority=100, planted=False, category=cat)
    for k, v in kw.items():
        setattr(e, k, v)
    return e

def _content(rng):
    return " ".join(rng.choices(VOCAB, k=rng.randint(40, 120)))

def build_book(seed=SEED, total=10000):
    """Deterministic synthetic book (design Sec.2 mix).

    Returns ORM-shaped rows usable by ScanEntry.from_orm,
    ActivatableEntry.from_orm and vector_candidates alike.
    ~3% of keyword entries are flagged ``planted``; the
    message builder plants their primary (+secondary) keys
    so the measured hit rate lands in the 2-5% band.
    """
    rng = random.Random(seed)
    n_plain = int(total * 0.70); n_var = int(total * 0.10)
    n_vec = int(total * 0.10); n_const = int(total * 0.05)
    n_dis = total - n_plain - n_var - n_vec - n_const
    entries = []; idx = 0; keyword = []
    for _ in range(n_plain):
        keys = [f"lorekey{idx:05d}"]
        for j in range(rng.randint(0, 2)):
            keys.append(f"lorekey{idx:05d}x{j}")
        sec = []
        if rng.random() < 0.30:
            sec = [f"seckey{idx:05d}"]
            if rng.random() < 0.5:
                sec.append(f"seckey{idx:05d}y")
        e = _entry(idx, "plain", keys, sec, _content(rng), rng)
        entries.append(e); keyword.append(e); idx += 1
    for _ in range(n_var):
        if idx % 2 == 0:  # substring variant
            e = _entry(idx, "variant", [f"subkey{idx:05d}"], [],
                       _content(rng), rng, whole_word=False)
        else:  # case-sensitive variant
            e = _entry(idx, "variant", [f"CaseKey{idx:05d}"], [],
                       _content(rng), rng, case_sensitive=True)
        entries.append(e); keyword.append(e); idx += 1
    for _ in range(n_vec):
        e = _entry(idx, "vectorised", [f"veckey{idx:05d}"], [],
                   _content(rng), rng, vectorised=True)
        entries.append(e); idx += 1
    for _ in range(n_const):
        e = _entry(idx, "constant", [f"constkey{idx:05d}"], [],
                   _content(rng), rng, constant=True)
        entries.append(e); idx += 1
    for _ in range(n_dis):
        e = _entry(idx, "disabled", [f"offkey{idx:05d}"], [],
                   _content(rng), rng, enabled=False)
        entries.append(e); idx += 1
    n_plant = round(len(keyword) * 0.03)
    for e in rng.sample(keyword, n_plant):
        e.planted = True
    rng.shuffle(entries)
    return entries

def build_messages(entries, seed=SEED):
    """10 messages, 70-80 words; planted keys replace filler."""
    rng = random.Random(seed + 1)
    planted = [e for e in entries if getattr(e, "planted", False)]
    tokens = []
    for e in planted:
        tokens.append(e.keys[0])
        tokens.extend(e.secondary_keys[:1])
    msgs = []
    per = (len(tokens) + 9) // 10
    for m in range(10):
        words = rng.choices(VOCAB, k=rng.randint(70, 80))
        chunk = tokens[m * per:(m + 1) * per]
        for j, tok in enumerate(chunk):
            if j < len(words):
                words[j] = tok
        msgs.append(" ".join(words))
    return msgs

def run_tick(entries, messages, scan_view, act_view, settings, backend, cache=None):
    """One full tick; returns (timings_ms dict, counts dict)."""
    from runmal.lorebooks.activation import activate
    from runmal.lorebooks.scan import scan_entries_windowed
    from runmal.lorebooks.vector_match import match_vectorised_sync
    t0 = time.perf_counter()
    hits = scan_entries_windowed(scan_view, list(messages), settings, ())
    t1 = time.perf_counter()
    outcome = match_vectorised_sync(entries, list(messages),
        backend.embed_sync, settings=settings, cache=cache)
    t2 = time.perf_counter()
    result = activate(act_view, {h.entry_id for h in hits}, {},
        vector_hit_ids=set(outcome.hit_ids),
        vector_fallback_ids=set(outcome.fallback_ids))
    t3 = time.perf_counter()
    ms = lambda a, b: (b - a) * 1000.0
    return ({"keyword": ms(t0, t1), "vector": ms(t1, t2),
             "activate": ms(t2, t3), "total": ms(t0, t3)},
            {"keyword_hits": len(hits),
             "vector_hits": len(outcome.hit_ids),
             "fallback_hits": len(outcome.fallback_ids),
             "activations": len(result.activations),
             "vector_mode": outcome.mode,
             "vector_candidates": outcome.candidates})

def _stats(vals):
    s = sorted(vals)
    p90 = s[min(len(s) - 1, int(0.90 * len(s)))] if s else 0.0
    return {"median": round(statistics.median(vals), 3),
            "min": round(min(vals), 3), "p90": round(p90, 3),
            "max": round(max(vals), 3)}

def _header():
    cpu = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip(); break
    except OSError:
        pass
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        sha = ""
    return {"cpu": cpu, "python": platform.python_version(),
            "platform": platform.platform(), "git_sha": sha,
            "derating": DERATING, "seed": SEED,
            "affinity": sorted(os.sched_getaffinity(0))}

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entries", type=int, default=10000)
    ap.add_argument("--repeats", type=int, default=15,
                    help="timed ticks (design protocol: 15)")
    ap.add_argument("--warmups", type=int, default=3)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--pin-single-core", type=int, default=None,
                    metavar="CPU", help="sched_setaffinity to CPU")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--cache", action="store_true",
                    help="reuse one EntryVectorCache across all ticks (warm-cache run)")
    ap.add_argument("--verify", action="store_true",
                    help="assert keyword hit rate in 2-5% band")
    args = ap.parse_args(argv)
    if args.pin_single_core is not None:
        os.sched_setaffinity(0, {args.pin_single_core})
    from runmal.lorebooks.activation import ActivatableEntry
    from runmal.lorebooks.scan import ScanEntry
    from runmal.lorebooks.vector_match import LocalEmbeddingBackend
    from runmal.lorebooks.windows import ScanSettings
    t0 = time.perf_counter()
    entries = build_book(args.seed, args.entries)
    messages = build_messages(entries, args.seed)
    build_s = time.perf_counter() - t0
    scan_view = [ScanEntry.from_orm(e) for e in entries]
    act_view = [ActivatableEntry.from_orm(e) for e in entries]
    settings = ScanSettings(scan_depth=10, scan_mode="depth",
                            scan_external_context=False)
    backend = LocalEmbeddingBackend()
    cache = None
    if args.cache:
        from runmal.lorebooks.vector_match import EntryVectorCache
        cache = EntryVectorCache()
    kw_total = sum(1 for e in entries if e.category in
                   ("plain", "variant"))
    if args.verify:
        _, counts = run_tick(entries, messages, scan_view,
                             act_view, settings, backend)
        rate = counts["keyword_hits"] / kw_total if kw_total else 0.0
        print(f"verify: keyword_hits={counts['keyword_hits']} "
              f"keyword_entries={kw_total} rate={rate:.4f}")
        assert 0.02 <= rate <= 0.05, f"hit rate {rate:.4f} out of band"
        print("verify: PASS (2-5% band)")
        return 0
    for _ in range(args.warmups):
        run_tick(entries, messages, scan_view, act_view, settings, backend, cache)
    rows = []; counts = {}
    for _ in range(args.repeats):
        gc.collect()
        timing, counts = run_tick(entries, messages, scan_view,
                                  act_view, settings, backend, cache)
        rows.append(timing)
    comp = {k: _stats([r[k] for r in rows]) for k in
            ("keyword", "vector", "activate", "total")}
    med = comp["total"]["median"]; med_kw = comp["keyword"]["median"]
    rate = counts["keyword_hits"] / kw_total if kw_total else 0.0
    out = {"header": _header(), "entries": args.entries,
        "build_seconds": round(build_s, 3),
        "warmups": args.warmups, "repeats": args.repeats,
        "counts": counts, "keyword_entries": kw_total,
        "keyword_hit_rate": round(rate, 4), "components_ms": comp,
        "entries_per_sec": round(args.entries /
            (med / 1000.0), 1) if med else None,
        "pi_equiv_ms": {"total": round(med * DERATING, 1),
            "keyword": round(med_kw * DERATING, 1)},
        "gates_ms": {"total_single_core": GATE_TOTAL_MS,
            "keyword_single_core": GATE_KEYWORD_MS},
        "gate_pass": {"total": med <= GATE_TOTAL_MS,
            "keyword": med_kw <= GATE_KEYWORD_MS},
        "cache": ({"enabled": True, "size": len(cache),
                   "hits": cache.hits, "misses": cache.misses}
                  if cache is not None else {"enabled": False})}
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"P-046 bench: {args.entries} entries, seed {args.seed}")
        print(f"machine: {out['header']['cpu']} py {out['header']['python']}")
        print(f"git: {out['header']['git_sha']} build {build_s:.2f}s")
        for k in ("keyword", "vector", "activate", "total"):
            s = comp[k]
            print(f"{k:9s} median {s['median']:9.2f} ms  min {s['min']:9.2f}  p90 {s['p90']:9.2f}  max {s['max']:9.2f}")
        print(f"hits: keyword {counts['keyword_hits']} ({rate:.2%}) vector {counts['vector_hits']} fallback {counts['fallback_hits']} activations {counts['activations']}")
        print(f"Pi-equiv x{DERATING}: total {out['pi_equiv_ms']['total']} ms keyword {out['pi_equiv_ms']['keyword']} ms")
        print(f"gates (single-core laptop): total <= {GATE_TOTAL_MS} ms: {out['gate_pass']['total']}; keyword <= {GATE_KEYWORD_MS} ms: {out['gate_pass']['keyword']}")
        print(f"cache: {out['cache']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
