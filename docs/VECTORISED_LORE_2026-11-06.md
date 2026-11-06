# Vectorised lore (P-041) — 2026-11-06

Roadmap line: *Vectorised lore: embedding-matched entries for
large books, on the founding RAG stack, with keyword fallback.*

## What was built

- src/runmal/lorebooks/vector_match.py — the embedding matcher
  P-035 left dormant, on the founding RAG stack: the S304
  embedding seam (backends/embeddings.py EmbeddingBackend +
  embed_or_fallback), the S311 provenance discipline (every
  compared vector comes from ONE batched embed call, one space;
  spaces never mix, INV-019), and the S401 cosine contract.
  - Candidates: enabled vectorised-kind entries only (P-035
    derivation; constant dominates and fires anyway, selective
    entries belong to the keyword scanner alone).
  - Query text: the P-037 scan window the keyword scanner
    would see (book settings over the messages plus, when the
    book admits it, the external segment), joined in window
    order — vector matching and keyword scanning look at the
    same context.
  - Entry embed text: name + keys + content — the three things
    an author declares the entry to be about. Query and all
    candidates embed in ONE batched call (one round trip
    however large the book; the S204 token-budget pass still
    bounds what actually injects).
  - A hit needs cosine >= threshold (DEFAULT_VECTOR_THRESHOLD
    0.30, per-call overridable; strict check_vector_threshold
    in [-1, 1], tolerant normaliser). Ranked hits (score desc,
    ties by input order then id) may be capped by max_entries
    — the per-extension max-entries cap P-035 assigned to this
    slice; the cap drops the lowest-ranked hits and the drop
    count is reported on the outcome, never silent.
  - The outcome is an honest record: mode (vector /
    keyword_fallback / none), degraded flag, fallback_reason,
    every candidate's score (below-threshold scores are
    inspectable, not hidden), the full ranked list, the
    provenance dict, the cap count, and the fallback ScanHits
    when the fallback ran.
- LocalEmbeddingBackend (in vector_match.py): the deterministic
  local provider on the repo's own EmbeddingBackend interface
  — hashed bag of stemmed tokens (weight 1.0, function words
  excluded) plus character trigrams (weight 0.4), signed-hash
  projected into 256 buckets, L2-normalised. Provider "local",
  model "hash-ngram-1". It passes the S304
  check_embedding_contract. Calibration (battery-pinned):
  stem-sharing paraphrases score 0.54–0.57 against a matching
  entry, unrelated texts <= 0.08 — the 0.30 threshold sits in
  the empty band. It is a lexical-semantic surrogate, honestly
  labelled: it matches paraphrases that share stems/roots, not
  true neural semantics.
- Backend resolution (resolve_lore_embedding_backend): the
  owner's ACTIVE embedding profile (S311 activation table)
  wins when set — its backend is built by the profile
  machinery, and if that backend is the unavailable one the
  matcher degrades to keyword fallback (an explicit owner
  configuration is honoured, never silently replaced). With
  no active profile, the local backend is the built-in
  default, so vectorised lore works out of the box with no
  provider configured. No new dependency of any kind; no
  migration (head stays 0031).
- Keyword fallback — the deliberate design closing P-035's
  kind exclusivity for the degraded cases only. It runs ONLY
  when embeddings are unavailable (no backend, a backend error
  of any kind, the S304 FTS-fallback result, a vector-count
  mismatch, or no comparable vectors) OR when no candidate
  reaches the threshold. It reuses the S202 scan core
  (scan_entries_windowed) over the vectorised entries flipped
  to scannable — their own keys, secondary keys, selective
  logic, whole-word and case flags, over the same window.
  When at least one vector hit lands the fallback does NOT
  run: a keyed entry with a low vector score stays unfired
  that tick, or the threshold would be meaningless. Below
  threshold is not degradation (degraded=False; the reason
  says below_threshold); unavailability is (degraded=True
  with its reason: no_backend / embeddings_unavailable /
  backend_error:<type> / the BackendError code /
  vector_count_mismatch / no_comparable_vectors).
- Activation (activation.py, additive): activate() gains
  vector_fallback_ids; _tick_entry fires a vectorised entry
  on a fallback hit via "vector_fallback" — honestly labelled,
  never "vector". A real vector hit on the same entry wins
  the "vector" label; timing knobs (cooldown suppresses,
  delay arms, sticky carries) and inclusion groups apply to
  fallback hits exactly as to vector hits, the one-engine
  rule. A fallback id never fires a selective entry, and a
  plain keyword hit still never fires a vectorised entry.
  With the new argument absent, behaviour is exactly
  pre-P-041 (the P-035 battery passes unchanged).
- Live paths wired (the carried debt — vectorised entries
  were dormant in all of them):
  - preview.py: preview_activation gains vector_match (a
    precomputed outcome from async callers), vector_embedder
    (a sync callable — LocalEmbeddingBackend.embed_sync is the
    built-in), vector_threshold and vector_max_entries. A
    caller-supplied vector_hit_ids still wins over both and
    produces exactly the pre-P-041 result shape. Every row
    gains vector_score (the candidate's cosine or None);
    fallback rows report their real matched keys with via
    vector_fallback; the result gains a vector_match summary
    when the book holds vectorised candidates.
  - lorebooks/router.py: the preview endpoint runs the
    matcher live when no vector hits are supplied — resolving
    the owner's backend and matching over the same resolved
    scan window the preview uses. PreviewRequest gains
    vector_threshold (ge=-1, le=1) and vector_max_entries
    (ge=1), strict at the boundary.
  - prompt/inspect.py: inspect_prompt resolves the backend
    once per call and matches per book; a vector-matched entry
    now appears as an included lore slot with trigger
    "vector" (the trace's generic via mapping needed no
    change).
  - lorebooks/state.py: run_activation_tick gains
    vector_messages / embedding_backend / vector_threshold /
    vector_max_entries; given a backend and messages (and no
    caller-supplied vector hits) it matches and passes both
    hit kinds through — the persisted per-chat tick is a live
    path now.
  - lorebooks/binding.py: merged_preview matches over the
    merged winners with the resolved backend and passes the
    outcome into the preview; rows keep their scope tags.
- Bug found and fixed in-slice (never-leave-a-bug rule):
  P-039's character-book normaliser dropped the vectorised
  flag — a card carrying vectorized: true materialised as a
  SELECTIVE entry, so no merged-preview vector match could
  ever fire for a character book. normalise_book_entry now
  carries vectorised (native vectorised / world-info
  vectorized), materialise_character_book stores it, and
  serialise_bound_book writes vectorized back on the
  travelling shape. The P-039 battery passes unchanged
  (its entries are constant/selective; the new key is
  additive).

## Clean-room basis

Built from Runmal's own roadmap line, its own S202/S203/S204
lorebook pipeline, the founding RAG stack (S304/S311/S401),
the P-035 slice record (which assigned this slice the matcher,
the keyword fallback, and the max-entries cap), and the public
entry-strategy behaviour recorded by P-002's census (ST-17:
vectorised = inserted by embedding similarity via the vector
extension, subject to all other checks, with a per-extension
cap on matched entries). No SillyTavern or Voxta source was
inspected; the battery's fixtures are authored fresh in the
test module (P-005 discipline). The threshold, the fallback
trigger conditions, the whole-tick fallback rule, and the
local provider are Runmal's own semantics for the roadmap
line.

## Carried limitations (honest record)

- The local provider is lexical-semantic, not neural: it
  cannot match a paraphrase that shares no stems or character
  n-grams with the entry (true synonyms with disjoint roots
  miss). Owners who configure a real embedding profile
  (Ollama / OpenAI-compatible) get true semantic matching
  through the identical matcher; the local backend is the
  no-configuration default and the testable seam.
- Entry vectors are recomputed on every tick (one batched
  provider call per book per prompt). For a 10,000-entry book
  that is one large provider request; a stored-vector cache
  keyed by (entry, provenance) is the obvious next step and
  belongs with P-046's performance pass, which owns the
  10,000-entry budget. The battery proves 300-entry books
  behave sanely and 2,000-entry pure scoring is fast; it
  makes no Pi-class timing claim.
- The fallback is whole-tick, not per-entry: on a tick where
  any vector hit lands, a vectorised entry whose keys match
  but whose score is low does not fire. This is deliberate
  (see above) and battery-pinned.
- Aesir embeddings remain unserved by the real engine
  (P-009 D3): an Aesir embedding profile degrades to the
  keyword fallback, exactly the S304 contract.
- The generation pipeline proper (chats -> composer) does not
  yet call run_activation_tick at all (P-033's standing seam
  note) — P-041 wires every caller that exists today
  (preview endpoint, inspector, merged preview, the tick
  seam itself); composing live chat prompts from stored lore
  remains a future pipeline slice's work, unchanged by this
  one.
- No editor/UI surface for threshold or cap (P-042 owns the
  editor-depth pass); both are reachable through the preview
  API today.
- Migration: none taken. P-040 may take 0032 in parallel; this
  slice needed no schema change, so no provisional number is
  held.

## Evidence

- Battery: tests/test_p041_vectorised_lore.py — see
  hidden_files/P041_EVIDENCE.md for exact counts read back
  from the run logs (p041_battery.log).
- Neighbours: hidden_files/p041_neighbours.log.
- Full suite: hidden_files/p041_fullsuite.log.
