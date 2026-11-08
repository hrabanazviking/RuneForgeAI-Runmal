# P-012 — The Clean-Room Log (opened 2026-10-30)

*Sources consulted per feature area, recorded as the road
proceeds — the founding `docs/RESEARCH.md` pattern, continued
for the Two Mirrors campaign. This log is the project's legal
hygiene made visible: it proves, feature area by feature area,
that Rúnmál's parity work rests on public documentation, public
specifications, published release notes, and this repo's own
tree — and on nothing else. A parity claim that cannot point
to an entry in this log (or in the founding ledger it
continues) has no provenance and must not be banked.*

## §0 The rule this log enforces

1. **Behaviour is studied; code is never read.** No
   SillyTavern source code was read for any slice in this
   campaign, and no Voxta source code was read — none exists
   in public and none was sought. No source-derived analysis
   (code-wiki summaries of a mirror's repository, third-party
   provider lists derived from a mirror's code, or the like)
   is census evidence in this campaign.
2. **Allowed source classes, in preference order** (the
   founding RESEARCH.md order, kept): normative public
   specification; official project/product documentation;
   official site; published release notes; the project's own
   tree and its own versioned documents (for Rúnmál itself
   and for Volmarr's own Aesir); a research paper or official
   model/licence papers for a licence judgement.
3. **Secondary and unofficial sources never carry a row
   alone.** Where one was used at all, it is flagged in the
   slice document and in this log, named, and limited to the
   exact row or corroboration it supports.
4. **Interop formats are specifications, not code.**
   Character-card, lorebook, preset, chat and persona shapes
   are implemented from their public spec documents and
   public documentation so a user's own content can move;
   the user's content is the user's property.
5. **Every future slice adds its entry before banking.**
   The entry names: the slice, the date read, the feature
   area, each source (title/publisher and version or date),
   its class from (2), the behaviour taken from it, and —
   where relevant — what was deliberately *not* taken.
   A slice that consulted no external source says so
   explicitly (own-tree slices do, below). The log grows by
   appending; entries are never rewritten — a correction is
   a new entry that names the entry it corrects.

## §1 The founding ledger (before this campaign)

`docs/RESEARCH.md` (started 2026-10-12) is this log's
predecessor and remains in force; this log does not repeat
its full text. Its consulted sources, per area, were:

- **Character cards:** the public Character Card v2 spec
  (`github.com/malfoyslastname/character-card-spec-v2`) and
  the public Character Card v3 spec
  (`github.com/kwaroran/character-card-spec-v3`, `SPEC_V3.md`
  normative over the older `concepts.md`) — specifications,
  class (2) normative spec.
- **Lorebooks / prompt / groups / extensions:**
  SillyTavern's official public documentation at
  `docs.sillytavern.app` (world-info, group-chats and
  writing-extensions pages) — behaviour concepts only.
- **Backends:** Ollama's official API documentation
  (`docs.ollama.com`: chat, embed, OpenAI-compatibility) and
  OpenRouter's official API documentation
  (`openrouter.ai/docs`) — official documentation.
- **Storage / retrieval:** SQLite's official documentation
  (`sqlite.org`, including backup, WAL, foreign keys, FTS5)
  and the sqlite-vec project's public repository — official
  documentation / public project record.
- **Voice research:** the Silero VAD and faster-whisper
  public repositories, the Kokoro model/repository pages,
  the Misaki and eSpeak-NG public records (the licence trap
  the founding survey exists to catch) — public project and
  licence papers.
- **Stack / testing:** FastAPI's and htmx's official
  documentation, and pytest's official exit-code reference
  (exit code 5 for an empty suite — the fact that corrected
  S101's acceptance contract).

## §2 Campaign entries — Part I (P-001–P-011)

### Cards, lorebooks, presets and interop shapes

- **P-001 (2026-10-30, own tree only):** no external source.
  Rúnmál's own `docs/ROADMAP.md` slice definitions and the
  test files in this repo's `tests/` only.
- **P-005 (2026-10-30, interop corpus):** shapes from the
  public file-format specifications and public
  documentation already logged in §1 and in the P-002/P-003
  censuses. No public user corpus was gathered: no corpus
  exists whose licence clearly permits redistribution in
  this repo, so all 12 fixtures were authored fresh for
  Rúnmál. That provenance decision is recorded in
  `docs/INTEROP_CORPUS_2026-10-30.md` and in the corpus
  manifest itself. No stranger's content was downloaded.

### The SillyTavern mirror (P-002)

- **Official documentation** at `docs.sillytavern.app`,
  read in full on 2026-10-30 — pages: What is SillyTavern,
  Characters, Personas, Group Chats, World Info, Prompt
  Manager, Context Template, Advanced Formatting, Chatting,
  Chat Completions, User Settings, Regex, Summarize,
  Writing Extensions. Class: official documentation.
  Behaviour taken: the ST-01–ST-74 census rows.
- **Published release notes:** the 1.13.0 notes read in
  full (rows marked `[RN-1.13]`); the **1.19 release line**
  (1.19.0, 2026-09-14) taken as the current baseline.
  Class: published release notes.
- **Flagged secondary corroboration (limited):** the 1.19
  baseline itself is corroborated by independent
  October-2026 guides citing the official release notes
  and by the project's official container image tag.
  Reported 1.19 behaviours (a side-by-side swipe picker,
  improved World Info sorting, provider-error surfacing)
  rest on those guides and are recorded in P-002's version
  note only — they are **not** inventory rows.
- **Explicitly not used:** SillyTavern source code, and
  source-derived analysis of it. P-002 names this boundary
  in its Method section; this entry is that census's entry
  in this log, exactly as P-002 handed it onward.

### The Voxta mirror (P-003)

- **Official site** at `voxta.ai`, read in full on
  2026-10-30. Class: official site.
- **Official documentation** at `doc.voxta.ai`, pages read
  in full on 2026-10-30: Scenarios, Events, Actions &
  tools, Buttons & controls, Contexts, Memory books,
  Scripting, Templates, Messages, Packages, HUD & stage
  effects. Class: official documentation. Honest limit
  carried from P-003: the live docs are not
  version-pinned, so a doc-only row may post-date v1.11.0.
- **Published release notes:** v1.11.0 (2026-10-06, the
  baseline, read in full), v1.9.0 and v1.9.3 (read in
  full); rows resting on them are marked `[RN-1.11]`,
  `[RN-1.9.0]`, `[RN-1.9.3]`. Class: published release
  notes.
- **Weakest evidence, flagged in P-003:** rows resting on
  the Two Mirrors roadmap's own §1 survey are marked
  `[roadmap §1]` in the census (MP4/AVIF video avatars and
  the vision folder-watcher among them) and are depth
  notes until read directly.
- **Flagged unofficial corroboration (one row only):**
  the community Services overview at `voxta.axailotl.ai`,
  an unofficial docs mirror, cited on exactly one row
  (VX-15) and flagged there; no other row depends on it.
- **Surveyed-but-not-yet-read (not rows):** the Assistant
  view and the full Inspector surface are named in the
  roadmap §1 survey and P-003's version note, but the doc
  pages read do not spell them out; they are recorded as
  open reading for a later slice, never as census rows.
- **Explicitly not used:** Voxta source code — none
  exists in public and none was sought; no source-derived
  analysis was used as census evidence.

### Derived and own-tree slices (no new mirror reading)

- **P-004 (delta table):** no new external source. Its
  inputs are P-001 (own tree), P-002 and P-003 only.
- **P-006 (continuation audit):** internal sources only —
  this repo's `docs/STATUS.md`, `docs/fellowship/`
  FORGE-LOG, ADRs 0001–0007, `docs/PLATFORM_MATRIX.md`,
  and the goal-workspace Evaluation Sitting files. No
  mirror source of any kind.
- **P-007 (fresh baseline):** no external source — the
  suite in this tree, run and counted on this host.
- **P-008 (backend parity ledger):** mirror side taken
  solely from P-002 rows ST-41–ST-45 and P-003 rows
  VX-15–VX-19 (already logged above); Rúnmál side from
  this tree. No new mirror reading was done or invented.
- **P-011 (mobile reality check):** Rúnmál side from this
  tree and its ADRs; mirror side solely from P-002/P-003
  rows VX-62/VX-63/VX-50/VX-58. Platform facts relied on
  are the web platform's public, stable rules (secure
  contexts for service workers, `getUserMedia` and
  installable web apps; `localhost` is a secure context,
  a plain-HTTP LAN address is not) — stated as platform
  facts, not as measurements. No device was tested.

### Aesir — Volmarr's own engine, a different class (P-009)

- P-009 is **not** a mirror census. Aesir is Volmarr's own
  engine, and the check binds Rúnmál's adapter assumptions
  to Aesir's own versioned statements in its own repo
  (checkout HEAD `1eed9706`, read 2026-10-30):
  `docs/API_SUPPORT_MATRIX_V1.md`, `CAPABILITY_LEDGER.md`,
  `docs/NATIVE_SERVICE.md`, and `docs/CURRENT_STATUS.md`.
  Class: the project's own published-in-repo API matrix
  and capability ledger. No Aesir source code was copied
  into Rúnmál and no feature was redesigned from it — a
  surface-compatibility check only, with its evidence
  boundary (the v1 matrix is Aesir's latest own statement)
  recorded in the slice document itself.

### Voice providers and the licence gate (P-010)

- **SillyTavern TTS surface:** SillyTavern's official
  public TTS documentation page
  (`docs.sillytavern.app/extensions/tts/`), read in full
  on 2026-10-30 — 16 listed providers plus the
  OpenAI-compatible provider named in the same page.
  Class: official documentation. Third-party
  source-derived provider lists exist, name more, and
  were **not** used.
- **Voxta voice surface:** solely the names P-003 already
  attested from Voxta's official site, documentation and
  release notes (including its official Cloud Credits FAQ
  naming ElevenLabs). No new Voxta reading was invented.
- **The gate's papers:** the founding survey
  (`docs/TTS_ENGINE_SURVEY.md`) and
  `docs/VOICE_LICENSE_MATRIX.md`, re-read for this census
  — code licence and weights licence judged separately,
  per provider, from their own papers.
- **Flagged secondary evidence (one entrant):** Voxtral
  TTS's CC-BY-NC-4.0 weights verdict rests on secondary
  reporting of the model's Hugging Face card, read
  2026-10-30 and flagged as such in P-010; the verdict
  must be re-read against the card itself before any
  slice acts on it.
- **Surveyed-but-not-enumerated (2):** SillyTavern's STT
  provider list and Voxta's full TTS provider catalogue
  are not enumerated in the official public documentation
  read for P-002/P-003/P-010. Both are recorded as open
  reading, not filled from unofficial or source-derived
  lists.
- No provider was installed, called, or subscribed to by
  the census; CONNECT verdicts judge a future user-key
  adapter, SHIP verdicts rest on papers.

### Priority order (P-013)

- **P-013 (2026-10-30, derived / own documents only):** no
  new external source and no mirror reading. Its inputs are
  this campaign's own banked records (the filed roadmap,
  P-004, P-006, P-008, P-009, P-010, P-011 and this log),
  read in full on 2026-10-30. The ratification rests on
  provenance already logged above; it creates none.

### Part I gate (P-014)

- **P-014 (2026-10-30, derived / own documents and own-tree
  measurement only):** no new external source and no mirror
  reading. Its inputs are this campaign's own banked
  records (the filed roadmap, P-001–P-013 and this log),
  read in full on 2026-10-30, plus one own-tree measurement:
  the project's own S806 release tooling
  (`runmal release gate` / `runmal release licenses`) run
  over this tree's installed set. The gate rests on
  provenance already logged above; it creates none.

## §3 Open reading carried forward

These gaps are part of the log, not omissions from it.
A later slice that needs one closes it from an allowed
source in §0(2) and appends its entry here:

1. SillyTavern's STT provider enumeration (P-010 flag).
2. Voxta's full TTS provider catalogue (P-010 flag).
3. Voxta's Assistant view and full Inspector surface
   (P-003 surveyed-but-not-yet-read; Part XIII territory).
4. SillyTavern 1.19's own full release notes, read
   directly (P-002's 1.19 behaviours currently rest on
   the flagged secondary corroboration in §2).
5. Voxtral TTS's model card, read directly, before any
   slice acts on its FAIL-SHIP verdict (P-010 flag).
6. Silero TTS's and WhisperLive's own papers (P-010's
   REVERIFY rows — no gate pass is claimed for either).

## §4 What this log does not prove

- Inclusion here proves **provenance, not correctness**:
  a behaviour row can still be wrong about the mirror;
  that is judged by the census and delta slices, not by
  this log.
- No entry in this log licenses copying: a public spec
  may be implemented, public documentation may be
  summarised as behaviour — a mirror's text, code, and
  assets are never reproduced in this repo.
- The founding TTS licence discipline binds independently
  of this log: no GPL-tainted engine ships, whatever a
  mirror plugs (P-010's FAIL-SHIP rows are the current
  worked example).

## §5 Handover

- To **P-013 / P-014**: the priority order and the Part I
  gate must treat §3's open reading as named, priced
  unknowns — especially the Part XIII rows that rest on
  surveyed-but-not-yet-read Voxta surface.
- To **every later part**: append the §0(5) entry for
  your slice to this file in the same commit that banks
  the slice. The Part XIV parity matrix (P-219–P-232,
  title only in the filed roadmap) is this log's eventual
  publisher: the matrix's provenance column is this log,
  published.

### Part I follow-ons (F-01–F-04)

- **F-01 (2026-10-30, own tree only):** no new external source
  and no mirror reading. The generic OpenAI-compatible adapter
  generalises the wire shape this tree already speaks (S303
  OpenRouter and S701 Aesir adapters) under the sampler profile
  the tree already declares (S208 `openai` in
  `generation/compat.py`); its inputs are P-008's ledger, the
  P-014 gate's homing, and P-009's wire lessons, all already
  logged above. No live endpoint was called.
- **F-02 (2026-10-30, own tree + Volmarr's own engine ledger
  only):** no new external source and no mirror reading. The
  Aesir binding repair implements exactly the repair P-009
  named, against Aesir's own v1 API matrix as already logged
  in §2 (P-009's entry — Aesir is Volmarr's own engine, a
  different class from the mirrors, and no Aesir source code
  was read or copied for this slice either). Its other
  inputs are the P-014 gate's homing and F-01's wire
  discipline, both already logged above. No live server was
  run; NOT PROVEN LIVE stands until the owed smoke runs.
- **F-03 (2026-10-30, own tree only):** no new external source
  and no mirror reading. The generic OpenAI-compatible speech
  adapter implements the common speech surface exactly as
  P-010's census already recorded it from the mirrors'
  official documentation (logged in §2 above), behind
  Rúnmál's own TTS/STT seams and in F-01's adapter pattern;
  its other inputs are the P-014 gate's homing and P-010 §3's
  sizing, both already logged. No live endpoint was called.
- **F-04 (2026-10-31, own tree only):** no new external source
  and no mirror reading. The clean-up tool implements ST-73
  exactly as P-002's census already recorded it from
  SillyTavern's official public documentation (logged in §2
  above) and the P-014 gate homed it, over Rúnmál's own
  S804 doctor diagnostics and its own data-dir layout; no
  live endpoint was called and no installation was cleaned —
  all evidence is fixture installs under pytest temporary
  directories.

### Part II (P-015–)

- **P-015 (2026-10-31, public spec + own tree):** the v2
  envelope shape and field set rest on the normative public
  Character Card v2 spec already logged in §1 (founding
  ledger), whose `data`-envelope structure the founding
  importer had not implemented for v2. Read this tick as
  corroboration only, flagged secondary per §0(3): public
  v2 spec summaries and spec examples (charactercardconverter
  guides, read via search results 2026-10-31) showing the
  `{spec, spec_version, data}` envelope and the v2 field set
  including `character_version`, and public card-reader
  documentation of the data-first / top-level-fallback field
  resolution for v2. No SillyTavern or Voxta source code was
  read — neither project is the source of the card spec —
  and no card file was downloaded; the slice's test cards
  are authored fresh in the test module (P-005 discipline).
- **P-016 (2026-10-31, public spec + own tree):** the v3
  additions' field names and shapes (`assets` descriptors,
  `nickname`, `creator_notes_multilingual`, `source`,
  `group_only_greetings`, `creation_date`,
  `modification_date`) rest on the normative public
  Character Card v3 specification already logged in §1
  (founding ledger) and on P-005's authored corpus fixture,
  which already carried the shapes. No new external reading
  was needed and none was done; no SillyTavern or Voxta
  source code was read — neither project is the source of
  the card spec — and no card file was downloaded; the
  slice's test cards are authored fresh in the test module
  (P-005 discipline).
- **P-017 (2026-10-31, own tree only):** no new external
  source and no mirror reading. The export round-trip matrix
  runs entirely on P-005's authored corpus and Rúnmál's own
  exporter/importer; the dual-published PNG shape it restores
  for v3 cards (`chara` + `ccv3` chunks in one file) is the
  shape P-005's own corpus fixture already carries, from the
  public card specs logged in §1. No card file was
  downloaded; no live endpoint was called.
- **P-018 (2026-10-31, own tree only):** no new external
  source and no mirror reading. The persona interop shape
  and the description-position set implement ST-08/ST-09
  exactly as P-002's census already recorded them from
  SillyTavern's official public documentation (logged in
  §2 above), in the shape P-005's authored corpus fixture
  already carries; placement is made real against Rúnmál's
  own prompt-composer slots (S205/S206). No persona file
  was downloaded; the slice's test personas are authored
  fresh in the test module (P-005 discipline).
- **P-020 (2026-10-31, own tree only):** no new external
  source and no mirror reading. The chat-file shape (ST-shaped
  JSONL: metadata header line, then one message object per line
  with `mes` / `swipes` / `swipe_id` / `swipe_info` / `extra` /
  `send_date`, plus branch-linkage keys in `chat_metadata`)
  implements the shape exactly as P-002's census already
  recorded it from SillyTavern's official public documentation,
  in the form P-005's authored corpus fixture
  (`chat_st.jsonl`) already carries, plus public JSONL format
  documentation. The native document shape is Runmal's own
  S111 export. No SillyTavern or Voxta source code was read
  and no chat file was downloaded; the slice's test chats are
  authored fresh in the test modules (P-005 discipline).
- **P-021 (2026-10-31, own tree only):** no new external
  source and no mirror reading. The preset interop shapes
  implement ST-34 exactly as P-002's census already recorded
  it from SillyTavern's official public documentation (logged
  in §2 above), in the shapes P-005's authored corpus
  fixtures already carry; the stored carriage rides Rúnmál's
  own S207 preset system and migration chain. No preset file
  was downloaded; the slice's extra test presets are authored
  inline in the test module (P-005 discipline).
- **P-023 (2026-11-06, own tree only):** no new external
  source and no mirror reading. Card thumbnails & assets
  implement the v3 `assets` descriptor shapes exactly as
  P-002's census and the public Character Card v3 spec
  already logged them (§1/§2 above, via P-016's entry), over
  Rúnmál's own S106 character storage and S113 CHARX asset
  handling; image inspection is stdlib header parsing of the
  public PNG/JPEG/GIF/WebP formats and the thumbnailer is an
  own-tree PNG codec. No SillyTavern or Voxta source code was
  read and no asset file was downloaded; the slice's test
  images are authored fresh in the test module (P-005
  discipline).
- **P-024 (2026-11-06, own tree only):** no new external source and no mirror reading. Tag/favourite/library-organisation behaviour (per-card tags, a favourite flag, filter/search/sort over a card library) implements only the public, commonly documented library behaviour already recorded in P-002's census spirit; storage rides Rúnmál's own migration chain (0021 after banking renumber) and the card parser/exporter. No SillyTavern or Voxta source code was read and no files were downloaded; the slice's test cards are authored fresh in the test module (P-005 discipline).
- **P-027 (2026-11-06, own tree only):** no new external source and no mirror reading. Content safety rails (imported content is data, never code; importers parse defensively) rest on the repo's own founding security model, docs/SECURITY_MODEL.md sections 9 and 13, and the roadmap P-027 line, implemented over Rúnmál's own card, lorebook, persona, preset, chat-file and portable-archive importers. No SillyTavern or Voxta source code was read and no files were downloaded; the slice's test files are authored fresh in the test module (P-005 discipline).
- **P-028 (2026-11-06, own tree only):** no new external source and no mirror reading. The `.runmal` archive growth (cards/lorebooks/presets carried with the existing per-member SHA-256 checksum discipline, plus the P-024 library organisation that was missing) is built entirely from Rúnmál's own roadmap line, its own S801/S802 portable archive and restore code, and the in-repo P-019/P-021/P-024 slice documents. No SillyTavern or Voxta source code was read and no files were downloaded; the slice's test library is authored fresh in the test module (P-005 discipline).
- **P-029 (2026-11-06, own tree only):** no new external source and no mirror reading. Provenance on import (a per-character record of where a card came from and when, so creator credit survives in Runmal) rests on Runmal's own P-022 bulk-import report facts and P-025 stored-form identity, plus the public Character Card v2/v3 creator-field shapes already logged in §1/§2 above (via the P-015/P-016 entries), implemented over Runmal's own character funnel, library import and migration chain. No SillyTavern or Voxta source code was read and no card file was downloaded; the slice's test cards are authored fresh in the test module (P-005 discipline).
- **P-031 (2026-11-06, own tree only):** no new external source and no mirror reading. Recursive lorebook scanning (entries triggering entries, with depth limits and cycle safety, token budget enforced) is built entirely from Runmal's own roadmap line and its own S202 keyword scan, S203 activation and S204 budget pipeline, plus the public world-info behaviour already recorded in P-002's census. No SillyTavern or Voxta source code was read and no files were downloaded; the slice's test entries are authored fresh in the test module (P-005 discipline).
- **P-032 (2026-11-06, own tree only):** no new external
  source and no mirror reading. Selective logic (the four
  public modes AND ANY / AND ALL / NOT ANY / NOT ALL combined
  with an entry's primary keys, with the world-info
  `selectiveLogic` integer codes 0/1/2/3 in that documented
  order) implements ST-16 exactly as P-002's census already
  recorded it from SillyTavern's official public documentation
  (logged in §2 above), in the shape P-005's authored corpus
  fixture already carries (`selectiveLogic` 0 and 1); the
  truth table, the empty-secondary rule, and the code mapping
  are built over Rúnmál's own S202 scanner and S201 store.
  No SillyTavern or Voxta source code was read and no file
  was downloaded; the slice's test entries are authored fresh
  in the test module (P-005 discipline).
- **P-033 (2026-11-06, own tree only):** no new external
  source and no mirror reading. Timed effects persistence
  (sticky/cooldown/delay counters surviving across a chat's
  life) is built from Rúnmál's own S203 activation semantics,
  the separate-modelling note in `docs/DATA_MODEL.md` (runtime
  activation state modelled separately from the canonical
  entry definition), and the public world-info behaviour
  already recorded in P-002's census. No SillyTavern or Voxta
  source code was read and no file was downloaded; the
  slice's test entries are authored fresh in the test module
  (P-005 discipline).
- **P-034 (2026-11-06, own tree only):** no new external
  source and no mirror reading. Inclusion groups (mutually
  exclusive entries resolved by weight/priority,
  deterministically) are built entirely from Rúnmál's own
  roadmap line and its own S202/S203/S204 lorebook pipeline,
  over the public world-info field names (`group`,
  `groupWeight`, `groupOverride`, `useGroupScoring`) exactly
  as P-005's authored corpus fixture already carries them
  (the Gale-Bell entry: `weather` / 75); the deterministic
  resolution semantics (weight, then priority, then entry
  id; no random draw) are Rúnmál's own design for the
  roadmap line, not a reproduction of any mirror behaviour.
  No SillyTavern or Voxta source code was read and no file
  was downloaded; the slice's test entries are authored fresh
  in the test module (P-005 discipline).
- **P-035 (2026-11-06, own tree only):** no new external
  source and no mirror reading. Entry states (the three
  activation kinds -- constant, selective, vectorised --
  served by one activation engine) are built entirely from
  Runmal's own roadmap line and its own S202/S203/S204
  lorebook pipeline, over the public entry-strategy behaviour
  already recorded in P-002's census (ST-17: constant =
  always inserted, keyword-triggered, or vectorised =
  inserted by embedding similarity subject to all other
  checks) and the public world-info field name
  ('vectorized') exactly as P-005's authored corpus fixture
  already carries it (the Harbour Law entry: constant and
  vectorized both true; the Gale-Bell entry: vectorized
  false). The kind derivation and precedence (constant >
  vectorised > selective), the via='vector' dispatch, and
  the caller-supplied vector-hit seam (the embedding matcher
  itself is P-041's road) are Runmal's own design for the
  roadmap line. No SillyTavern or Voxta source code was read
  and no file was downloaded; the slice's test entries are
  authored fresh in the test module (P-005 discipline).
- **P-036 (2026-11-06, own tree only):** no new external
  source and no mirror reading. Probability & RNG honesty
  (probabilistic entries use a seeded, inspectable roll)
  is built entirely from Rúnmál's own roadmap line and its
  own S204 budget pipeline, over the public world-info
  field names (`probability`, `useProbability`) exactly as
  P-005's authored corpus fixture already carries them
  (the Gale-Bell entry: 80 / true); the roll derivation
  (SHA-256 over seed/context/entry-id, algorithm-versioned,
  recorded per entry) is Rúnmál's own design for the
  roadmap line, not a reproduction of any mirror behaviour.
  No SillyTavern or Voxta source code was read and no file
  was downloaded; the slice's test entries are authored
  fresh in the test module (P-005 discipline).
- **P-037 (2026-11-06, own tree only):** no new external
  source and no mirror reading. Scan depth & context windows
  (per-book scan settings -- messages-deep, whole-chat,
  external context -- as data) are built entirely from
  Rúnmál's own roadmap line and its own S201/S202 lorebook
  pipeline: `scan_depth` is Rúnmál's own stored book field
  since S201 (migration 0004), and the world-info shapes the
  slice touches are exactly those already recorded in-tree
  (book settings riding in `originalData` and the per-entry
  `scanDepth` field, both as P-005's authored corpus fixture
  already carries them -- the Gale-Bell entry's explicit-null
  `scanDepth` stays preserved-as-data, no per-entry semantics
  claimed). The mode vocabulary (`depth` / `whole_chat`),
  the external-segment rule (appended, uncounted against the
  depth, governed by its own per-book flag), and the honest
  hit provenance (`external_indices` beside `message_indices`)
  are Rúnmál's own design for the roadmap line, not a
  reproduction of any mirror behaviour. No SillyTavern or
  Voxta source code was read and no file was downloaded;
  the slice's test entries are authored fresh in the test
  module (P-005 discipline).
- **P-039 (2026-11-06, own tree only):** no new external
  source and no mirror reading. Character-book binding
  (a card's own lorebook travels with it and merges with
  the world's by declared precedence) is built from the
  card `character_book` field exactly as Rúnmál's own
  P-015/P-016 public-spec import work and P-005's authored
  corpus already record it, and from the world-info entry
  field set P-019 recorded from public documentation.
  The binding store, the three declared precedence modes
  and the deterministic name-collision merge with shadowed
  provenance are Rúnmál's own design for the roadmap line,
  not a reproduction of any mirror behaviour. No
  SillyTavern or Voxta source code was read and no file
  was downloaded; the slice's test entries are authored
  fresh in the test module (P-005 discipline).
- **P-040 (2026-11-06, own tree only):** no new external
  source and no mirror reading. Global + persona + chat
  lore scopes are built from the layering behaviour the
  P-002 census recorded from the mirrors' official public
  documentation (a world layer applying everywhere, a
  character layer, a per-chat layer, per-layer budgets).
  The assignment store (one book, several scope rows), the
  four-layer order world -> character -> persona -> chat
  (the persona layer is Runmal's own placement: a chat's
  persona IS a character here), the scope-budget semantics
  (None unlimited, 0 mutes the layer, strictest assignment
  wins), the most-specific-layer dedupe with shadowed
  reporting, and the per-scope inspect summary are Runmal's
  own design for the roadmap line, not a reproduction of
  any mirror behaviour. No SillyTavern or Voxta source
  code was read and no file was downloaded; the slice's
  test entries are authored fresh in the test module
  (P-005 discipline).
- **P-043 (2026-11-06, own tree only):** no new external
  source and no mirror reading. The activation inspector
  (why did this entry fire -- matched keys and the recorded
  roll shown per message) is built entirely from the roadmap
  line and from facts the engine already records in-tree:
  the S209/P-037 preview rows, the P-032 selective gate, the
  P-036 recorded probability roll, the P-034 group outcome,
  the P-033 timed counters, the P-041 matcher scores and the
  S204 budget verdict. The explanation schema (one dict per
  entry, per-message breakdown, tick totals, near misses as
  first-class rows, and the explicit facts_not_recorded
  list) is Runmal own design for the roadmap line, not a
  reproduction of any mirror behaviour. No SillyTavern or
  Voxta source code was read and no file was downloaded;
  the slice test entries are authored fresh in the test
  module (P-005 discipline).
- **P-046 (2026-11-06, own tree only):** no new external
  source and no mirror reading. The 10,000-entry scan
  performance pass (a budget stated in-tree before measuring,
  a deterministic synthetic book generated from an embedded
  word list, a per-window token index over Runmal's own S202
  scan core, and an in-process stored-vector cache closing
  the in-process half of P-041's recorded debt) is built
  entirely from the roadmap line and the P-046 scout/design
  documents written in-tree for this slice. The budget,
  derating method, cache key shape and equivalence-oracle
  method are Runmal's own design for the roadmap line, not a
  reproduction of any mirror behaviour. No SillyTavern or
  Voxta source code was read and no file was downloaded; the
  slice's test entries are authored fresh in the test modules
  (P-005 discipline).
- **Commissioned binding depth/role slice (2026-11-06,
  own tree only):** no new external source and no mirror
  reading. Closing gate finding F2 (character-book entries
  carry P-038 placement into materialisation) is built
  entirely from Runmal's own in-tree facts: the P-038
  placement module's tolerant normalisers, the P-039
  binding legs they were missing from, and the finding as
  P-047's evidence and P-048's gate record state it. The
  asymmetric degradation (bad depth to undeclared, bad
  role to system) and the role/position code tables are
  P-038's own, reused unchanged. No SillyTavern or Voxta
  source code was read and no file was downloaded; the
  slice's test entries are authored fresh in the test
  module (P-005 discipline).
- **P-049 (2026-11-06, own tree only):** no new external
  source and no mirror reading. The prompt manager (ordered,
  toggleable prompt blocks as a first-class editable
  structure) is built entirely from the roadmap line and
  Runmal's own prompt stack: the S205 slot kinds and baseline
  order supply the blocks (position-faithful, so lore and
  memory each appear at both of their baseline positions),
  the S206 depth contract supplies the splice guard, and the
  S214 trace supplies the disabled-block discard record. The
  layout shape ({blocks: [{block, enabled}]}, fill-missing
  normalisation, block-position order arithmetic) is Runmal's
  own design for the roadmap line, not a reproduction of any
  mirror behaviour. No SillyTavern or Voxta source code was
  read and no file was downloaded; the slice's test entries
  are authored fresh in the test module (P-005 discipline).
- **P-050 (2026-11-06, public format specifications only):**
  the instruct templates (ChatML, Llama-3, Alpaca, Vicuna) are
  built from the formats' public specifications as generally
  published (turn markers, header framing, section headings,
  and each format's customary system preamble text), plus
  Runmal's own in-tree facts: the S205 composer's structured
  messages supply what gets rendered, the S214 trace contract
  bounds what the inspector may echo, P-049 supplies the
  data/validation/resolution pattern, and the presets'
  template_ref supplies the registry's reason to exist. The
  per-model default table, the plain (no-framing) honest
  default, and the template data shape are Runmal's own design
  for the roadmap line. No SillyTavern or Voxta source code
  was read and no file was downloaded; the slice's test
  conversations are authored fresh in the test module
  (P-005 discipline).
- **P-051 (2026-11-06, public behaviour census + own tree
  only):** no new external source and no mirror reading. The
  context templates (story-string assembly formats as
  editable data, imported from P-021's preset carriage) are
  built from the roadmap line, the in-tree census ST-32
  description of the public behaviour (named anchors,
  example/chat-start separators, separators as stop strings),
  the P-005/P-021 fixture spellings for prompt identifiers,
  and Runmal's own in-tree facts: the S205 slot kinds and
  baseline order supply the anchors (position-faithful, as
  P-049), the S206 depth contract supplies the splice guard,
  P-049/P-050 supply the data/validation/resolution pattern,
  and the S214 trace bounds what the inspector may echo. The
  segment data shape, the story-string fill-disabled rule,
  the preset identifier-to-anchor mapping, and the plain
  honest default are Runmal's own design for the roadmap
  line, not a reproduction of any mirror behaviour. No
  SillyTavern or Voxta source code was read and no file was
  downloaded; the slice's test entries are authored fresh in
  the test module (P-005 discipline).
- **P-052 (2026-11-06, public sampler semantics only):** the
  complete sampler surface is built from the public sampler
  literature and public backend documentation: DRY and XTC
  from their public sampling descriptions, Mirostat / typical
  / tail-free / epsilon / eta / dynamic-temperature from the
  public sampler-research descriptions and the public
  llama.cpp sampling documentation, and Ollama's forwarded
  options from Ollama's public options documentation. The
  catalogue shape, the surface/merge/resolution design, and
  the per-backend honesty accounting are Runmal's own design
  for the roadmap line, extending the tree's S207/S208/S301/
  S310 contracts. No SillyTavern or Voxta source code was
  read and no file was downloaded; the slice's tests are
  authored fresh in the test module (P-005 discipline).
- **P-055 (2026-11-07, public behaviour + own tree
  only):** the text-macro engine (the {{name}} and
  {{name::arg1::arg2}} forms and the identity / clock /
  random / variable / transform set) is built from the
  mirrors' publicly documented macro behaviour as
  generally published, plus Runmal's own in-tree facts:
  S110 substitute_macros and S307 resolve_variables
  supply the legacy surfaces whose behaviour is preserved
  untouched, the P-036 seeded-RNG discipline supplies
  the recorded-roll honesty pattern, and the tools
  router's existing registry / preview endpoints supply
  the API shape. The single-pass rule, the unknown /
  malformed honesty contract (preserved verbatim and
  reported, or refused in strict mode), the variable
  working-copy rule, and the engine data shapes are
  Runmal's own design for the roadmap line. No
  SillyTavern or Voxta source code was read and no file
  was downloaded; the slice's tests are authored fresh
  in the test module (P-005 discipline).
- **P-077 (2026-11-07, public behaviour + own tree
  only):** long-chat performance is built entirely from
  Runmal's own facts: the founding UI campaign's
  THREAD_WINDOW = 100 standard in web/static/app.js and
  renderer.js, the P-046 budget discipline (budget stated
  before measuring, seeded corpus shared by bench and
  battery, single-core medians, frozen-oracle equivalence),
  the P-068 position semantics, and the P-072 search
  contract as already recorded in this tree. The paged
  history shape, the density-aggregate append proof, the
  composer prefix-sum trim, and the search word-prefix
  pre-filter are Runmal's own design for the roadmap line.
  No SillyTavern or Voxta source code was read and no file
  was downloaded; the slice's tests are authored fresh in
  the test module (P-005 discipline).
- **P-078 (2026-11-07, public behaviour + own tree
  only):** chat import surgery — P-020's parsed imports
  become fully live chats — is built entirely from
  Runmal's own in-tree contracts: the P-020 file contract
  (filemodels/fileimport/filebridge), the P-065 swipe-deck
  invariant, the P-066 lineage columns, the P-075
  provenance document shape, and the P-068 materialised-
  position rule. The deck-resolution rules (mes
  authoritative, empty alternates dropped and reported,
  branch-link header keys preserved as data and never
  mapped to lineage) extend the tree's own filebridge law;
  no external behaviour was consulted beyond what earlier
  slices already recorded. No SillyTavern or Voxta source
  code was read and no file was downloaded; the slice's
  tests are authored fresh in the test module (P-005
  discipline).
- **P-079 (2026-11-07, public behaviour + own tree only):**
  quiet/greeting controls are built from the mirrors'
  publicly known behaviour -- a new chat opens on the
  character's greeting and alternate greetings are swiped
  through on that first message -- plus Runmal's own facts:
  the card model's `first_mes` / `alternate_greetings`
  fields and the S212 editor that already maintained them,
  the P-065 swipe-deck contract (deck invariant, strict
  `select_index`, non-empty alternates), the P-075
  per-swipe provenance document, the P-036 seeded-RNG
  honesty discipline, and the P-076 journal pattern. The
  deck/choice contract (labelled entries with card-side
  source indexes, the four modes first/index/random/quiet,
  strict choice decode), the seed-into-empty road, and the
  deck-view shape are Runmal's own design for the roadmap
  line. No SillyTavern or Voxta source code was read and
  no file was downloaded; the slice's tests are authored
  fresh in the test module (P-005 discipline).
- **P-080 (2026-11-07, public behaviour + own tree
  only):** the Part V gate -- a surgery drill script
  (branch, checkpoint, swipe-storm, group scene) runs
  green; no operation loses data -- is built entirely
  from Runmal's own in-tree contracts: the P-030 / P-048 /
  P-064 gate discipline (battery + gate record + pinned
  limitations + numbered findings), the P-065 deck
  invariant, the P-066 lineage and merge law, the P-067
  checksum-sealed restore-as-new snapshots, the P-068
  variant-history rule, the P-070 room road, the P-076
  sealed journal, the P-077 paged history road, the P-078
  full-deck copy contract, and the P-079 greeting deck.
  The account discipline (a multiset over every deck
  string plus variant-history contents, read through
  message_to_dict) and the Surgeryhall world are Runmal's
  own design for the roadmap line. No SillyTavern or
  Voxta source code was read and no file was downloaded;
  the slice's tests are authored fresh in the test
  module (P-005 discipline).
- **P-081 (2026-11-07, public behaviour + own tree
  only):** the Plugin API v1 — Part VI's opener — is
  built entirely from Runmal's own bridge row
  (S601–S611): the versioned bridge protocol becomes
  PLUGIN_API_VERSION, the bridge scopes' exact-match
  grammar (INV-029) becomes the manifest's closed
  capability/permission vocabularies, the bridge
  /capabilities document becomes the plugin
  introspection document, and the bridge event outbox
  becomes fire-and-observe chat events — the Samtal
  adapter pattern turned inward, exactly as the
  roadmap line names it. The lifecycle states, the
  failure rule (three consecutive failures, then
  errored), the per-receiver chat.read payload
  redaction, the prompt-hook stages riding the P-057
  composition choke point, the forced-provenance rule
  (S214), and the UI slot registry are Runmal's own
  design for the roadmap line. No SillyTavern or
  Voxta source code was read and no file was
  downloaded; the slice's tests are authored fresh
  in the test module (P-005 discipline).
- **P-082 (2026-11-07, public behaviour + own tree
  only):** the plugin sandbox -- plugins are data+declared
  capabilities; no plugin touches the network/files/secrets
  uninvited -- is built entirely from Runmal's own in-tree
  contracts: the P-081 design as landed in team-01's tree
  (closed manifest vocabularies, the failure rule, the
  metadata-only failure record), the P-027 typed-refusal and
  error-hygiene discipline, and the SECURITY_MODEL section 8
  honesty rule (no implied sandboxing without a real
  boundary). The grant policy (surface permissions grant no
  resource access; resource permissions live outside the v1
  vocabulary, so a v1 plugin's resource grant set is empty),
  the guarded-context facade (grant check + realpath
  confinement + host-wired transport/provider + audit), and
  the ADR-0008 decision record are Runmal's own design for
  the roadmap line. No SillyTavern or Voxta source code was
  read and no file was downloaded; the slice's tests are
  authored fresh in the test module (P-005 discipline).
- **P-083 (2026-11-07, public behaviour + own tree
  only):** the plugin manager — Part VI's install road — is
  built entirely from Runmal's own precedents: the P-045
  lorebook-pack envelope discipline (single JSON envelope,
  content_sha256 over the canonical NORMALISED payload,
  provenance carried verbatim and never interpreted) becomes
  the local plugin pack; the P-025 collision discipline
  (exact duplicate = no-op report, never a silent overwrite)
  becomes the manager's duplicate/conflict rule; the P-081
  design's own bequests (its section 7 durable-state question
  and section 10 permission-card + manager-verbs sketch)
  become the file ledger in the data dir, the permission
  card rendering declared capabilities/permissions/events/
  hooks/slots plainly, and a manager driving exactly the
  P-081 registry verbs. The exact-grant rule (a grant must
  name precisely the declared permission set) and the
  data-only rule (packs declaring prompt hooks refuse —
  hooks are code, and code is not in packs) are Runmal's own
  design for the roadmap line. No SillyTavern or Voxta
  source code was read and no file was downloaded; the
  slice's tests are authored fresh in the test module
  (P-005 discipline).
- **P-084 (2026-11-07, public behaviour + own tree
  only):** the Memory Summarise plugin — rolling chat
  summary into memory — is built entirely from Runmal's
  own in-tree contracts: the P-081 Plugin API v1 (whose
  slice doc's canonical example is this very citizen,
  id runmal.summarise, made registerable by declaring
  the full surface the example omitted), the P-082
  sandbox grant policy (surface permissions only, an
  empty resource grant set), the founding S404 roll
  (versioned ChatSummary rows plus kind='summary'
  memories with full message sources) driven by
  fire-and-observe chat events, the S404 summarizer
  seam filled with a deterministic extractive
  summarizer in the P-073 honesty pattern (no model
  called or claimed), and the prompt composer's
  slots stage as the read-back path with forced
  plugin provenance (PLG-07). No SillyTavern or
  Voxta source code was read and no file was
  downloaded; the slice's tests are authored fresh
  in the test module (P-005 discipline).
- **P-085 (2026-11-07, public behaviour + own tree only):** the Vector Storage plugin — per-chat/character vector memory on the founding sqlite-vec store — is built entirely from Runmal's own contracts: the P-081 Plugin API v1 citizen pattern (as proven by the P-084 Memory Summarise citizen, read as a pattern and not imported), the P-082 empty-grant sandbox stance, the founding S401 vector-store contract with its provenance spaces, the S407 scope model (chat scope stays inside its chat, character scope stays private to its character), and the P-041 embedding-honesty law (the local hash-ngram provider is lexical-semantic and labelled `lexical_vector`; a configured profile gives `vector`; a degraded keyword scan is labelled `keyword_fallback`, never a vector hit). Scoped doc ids, the over-fetch-then-scope-filter search, and the inspectable status shape are Runmal's own design for the roadmap line. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-086 (2026-11-07, public behaviour + own tree only):**
  the Translate plugin — messages in/out via local models by
  default; provider-pluggable — is built entirely from
  Runmal's own in-tree contracts: the P-081 Plugin API v1
  citizen pattern as banked by P-084 (register via
  register_plugin; build_registry/create_app untouched), the
  P-082 sandbox rule (only v1 surface permissions, so the
  resource grant set is empty; model access is host wiring,
  never an uninvited network call), the chat.write reservation
  (IN is a messages-stage prompt transform in flight; OUT is
  an in-memory derived, inspectable view — originals never
  change), and the continue/impersonate generation precedent
  (plugin_events=False; an error, a non-clean finish or empty
  output raises, and partial text is never stored). The
  deterministic default road (a tiny authored lexicon plus a
  [deterministic:<target>] marker, provider deterministic-1,
  never presented as real translation), the per-chat
  configuration with an always-configured, never-detected
  source language, and the no-migration in-memory storage
  stance (config and derived store lost on restart, stated
  plainly) are Runmal's own design for the roadmap line. No
  SillyTavern or Voxta source code was read and no file was
  downloaded; the slice's tests are authored fresh in the test
  module (P-005 discipline).
- **P-087 (2026-11-07, public behaviour + own tree only):** the Image Generation plugin — prompt-from-scene + manual, local diffusion endpoints first — is built entirely from Runmal's own contracts: the P-081 Plugin API v1 citizen pattern (as proven by the P-084/P-085 citizens, read as a pattern), the P-082 empty-grant sandbox stance, the P-073 extractive honesty pattern (the scene prompt is assembled deterministically from the chat's own messages and names, inspectable before use, nothing invented), and the P-023 character-asset machinery as the landing road (with its character-scoping stated plainly where a chat has no bound character). The provider seam, the loopback-only refusal for local diffusion endpoints, the deterministic hash-canvas test provider with its labelled `deterministic_local` road, per-chat opt-in enablement, and the process-local generation ledger are Runmal's own design for the roadmap line. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-088 (2026-11-07, public behaviour + own tree only):** the Web Search plugin — opt-in, per-chat, with results cited into context (off by default; sovereignty is the default state) — is built entirely from Runmal's own in-tree contracts: the P-081 Plugin API v1 citizen pattern as banked by P-084/P-085/P-086 (register via register_plugin; build_registry/create_app untouched), the P-082 sandbox rule (only v1 surface permissions, so the resource grant set is empty; network.access is not in the v1 manifest vocabulary, so the provider/transport is host wiring in the P-086 model-access trust class, exercised only through the citizen's own per-chat opt-in gate), and the P-086 per-chat configuration stance (in-memory on the instance, lost on restart, stated plainly). The sovereignty gate (the explicit search action refuses before any provider call for a chat that has not opted in; the prompt hook never searches and abstains the moment opt-in is off), the citation rule (results render only with title + URL, exposed as inspectable citation data, and uncitable rows refuse at the seam), the deterministic default provider (labelled deterministic-1, URLs on the reserved example.invalid domain, snippets declaring themselves placeholders), and the injected-transport HTTP provider shape (the module opens no socket; tests use fakes only) are Runmal's own design for the roadmap line. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-089 (2026-11-07, public behaviour + own tree only):** the Quick Replies citizen — user-defined one-tap macros incl. chained actions and input senders — is built entirely from Runmal's own contracts: the P-081 Plugin API v1 citizen pattern (as proven by the P-084/P-087 citizens, read as patterns), the P-082 empty-grant sandbox stance, the P-055 macro engine as the single expansion road (strict mode at execution, so unknown macros fail a step loudly instead of posting raw text), the chats append road with its P-075 provenance discipline (origin kind stays in the closed vocabulary; the quick-reply road is named in scalar origin facts, never a forged kind) and P-076 undo coverage, and the P-076/P-083 durable file-store idiom for per-user definitions (no migration). Chained steps in declared order with a persisted per-step execution record, the input-sender semantics (a user-role message whose receipt still names the road), and the no-hidden-generation stance are Runmal's own design for the roadmap line. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-090 (2026-11-07, public behaviour + own tree only):** the Regex Scripts plugin — ST-shaped find/replace rules applied at declared stages, with a safe regex dialect and timeout discipline — is built entirely from Runmal's own in-tree contracts: the P-081 Plugin API v1 citizen pattern as banked by P-084/P-085/P-087/P-088 (register via register_plugin; build_registry/create_app untouched), the P-082 sandbox rule (only v1 surface permissions, so the resource grant set is empty), and the P-089 durable per-user file-store idiom (one JSON document per UUID-validated user, atomic save, corrupt stores raise and are never silently reset). The ST-shaped importer (aliases, the /body/flags slash form, placement decoding), the safe-dialect token scan (backreference, lookbehind, nested-quantifier and quantifier-bound refusals — extended in-slice to the {,n} brace form Python treats as {0,n} after the finisher's review caught it escaping both checks), the hand-parsed replacement grammar expanded through a Pattern.sub function, and the per-rule forked-child timeout (with its in-process cooperative fallback stated plainly) are Runmal's own design for the roadmap line. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-091 (2026-11-07, public behaviour + own tree only):** the TTS/STT plugin citizens — the founding voice stack behind the P-081 API — are built entirely from Rúnmál's own in-tree contracts: the P-081 Plugin API v1 citizen pattern as banked by P-088/P-089 (register via `register_plugin`; `build_registry`/`create_app` untouched), the P-082 empty-grant sandbox stance (only v1 surface permissions; the voice engine is host wiring, never a grant and never manifest data), and the founding S503/S504 voice seams (`STTBackend`/`TTSBackend`) driven unchanged through their existing ABCs. The two-citizen split mirroring the two independent seams/registries, the settings-panel pair, the metadata-only `message.created` observation that never synthesizes, the no-prompt-hooks stance (voice is not prompt text), the byte-parity law against the direct backend call, and the in-memory latest-result stance are Rúnmál's own design for the roadmap line. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-092 (2026-11-07, public behaviour + own tree only):** the Expression/sprite plugin surface — declared expression sets per character, current-expression selection per chat with provenance, bound to P-023 sprite assets (Part X builds on it) — is built entirely from Runmal's own in-tree contracts: the P-081 Plugin API v1 citizen pattern as banked by P-084/P-087/P-089 (register via register_plugin; build_registry/create_app untouched), the P-082 sandbox rule (only v1 surface permissions, so the resource grant set is empty), the P-023 character-asset machinery as the one sprite store (card "emotion" refs already land as kind expression assets; this citizen binds them by id and never copies bytes), and the P-089 durable per-user file-store idiom (one JSON document per UUID-validated user, atomic save, corrupt stores raise and are never silently reset; no migration). The set/selection/provenance vocabulary (a closed selection-source set, a selection receipt naming source, actor, reason, message and the expression replaced), the honest per-entry binding report (bound, or no_asset / asset_missing / wrong_kind / not_stored), the returned-never-saved derivation draft from existing expression assets, and the no-renderer / no-detection boundaries (Part X owns rendering; nothing scans message text to guess an expression) are Runmal's own design for the roadmap line. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-093 (2026-11-07, public behaviour + own tree only):** the Variables & State plugin - per-chat variables/flags in one shared store that Part IX scenarios consume too - is built entirely from Runmal's own in-tree contracts: the P-081 Plugin API v1 citizen pattern as banked by P-084..P-091 (register via `register_plugin`; `build_registry`/`create_app` untouched), the P-082 empty-grant sandbox stance (only v1 surface permissions declared), and the P-089 durable per-user file-store idiom (one JSON document per UUID-validated owner, atomic 0600 save, corrupt stores raise and are never silently reset; no migration, head stays 0041). The namespacing law (a plugin's bare keys land in its own namespace, `shared` is the documented collaboration surface whose overwrites are recorded in provenance and a version counter, and another plugin's namespace refuses outright), the typed-scalar/bool-only-flag discipline with kinds that never blur, the seed-only-missing Part IX seeding contract, and the P-055 macro bridge (shared namespace rendered as macro strings one way, expansion reports persisted back with macro provenance the other, with the ephemeral-vs-durable difference stated plainly) are Runmal's own design for the roadmap line. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-094 (2026-11-07, public behaviour + own tree only):** the Plugin Data Custody surface — a plugin's data is exportable and deletable with the plugin, no hostage state — is built entirely from Rúnmál's own in-tree contracts: the P-081 Plugin API v1 citizen pattern as banked by P-084..P-092 (register via register_plugin; build_registry/create_app untouched), the P-082 empty-grant sandbox stance, the packs canonical-JSON + sha256 checksum idiom, the P-083 manager/ledger (custody delete finishes through manager.uninstall when a row exists, so removal leaves neither orphaned data nor an orphan row), the P-089 durable per-user file-store idiom (verbatim export, owner-scoped file deletion), each citizen's own inspect/clear roads, and the P-093 namespacing law as the owner-scoping model. The honest-section rule (exported / empty / unavailable-with-reason / error-carried-in-the-document, never a silently omitted store), the lazy P-093 variables adapter (module absent on this base: section unavailable, its file never touched, lighting up unchanged at reconciliation), the vector-index boundary (the index is the plugin's data; founding memories are host data), and the HTTP honesty line (instance sections named unavailable over HTTP rather than a partial export dressed as complete) are Rúnmál's own design for the roadmap line. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-095 (2026-11-07, public behaviour + own tree only):** The gallery plugin — a per-chat image gallery with generation history as a first-class citizen — is built entirely from Runmal's own in-tree contracts: the P-081 Plugin API v1 citizen pattern as banked by P-087/P-092/P-093 (register via `register_plugin`; `build_registry`/`create_app` untouched), the P-082 empty-grant sandbox stance (only v1 surface permissions declared), the P-023 character-asset machinery as the one durable image store (asset-backed entries reference asset ids and read facts/thumbnail state through the P-023 roads; bytes are never copied), the P-087 generation ledger as the provenance source (its records are ingested verbatim and idempotently into the gallery's durable store, the deterministic road staying labelled `deterministic_local`, unlanded generations stated plainly with their landing reason), and the P-089 durable per-user file-store idiom (one JSON document per UUID-validated owner, atomic 0600 save, corrupt stores raise and are never silently reset; no migration, head stays 0041). The three-kind provenance vocabulary (generated / asset / attached), the honestly labelled `attached_local` byte-store road for chats with no bound character (the one place P-023 cannot land by construction), pull-based explicit generation import (the gallery preserves what it is handed and never claims to observe generations it was not shown), and curation that can touch title/notes only, never provenance, are Runmal's own design for the roadmap line. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-096 (2026-11-07, public behaviour + own tree only):** the Dice & game-bridge plugin surface - Sagnaskemma rolls and bridge events exposed as a plugin citizen - is built entirely from Runmal's own in-tree contracts: the P-081 Plugin API v1 citizen pattern as banked by P-084..P-094 (register via register_plugin; build_registry/create_app untouched), the P-082 empty-grant sandbox stance (only v1 surface permissions declared), the P-036/P-055 seeded-roll discipline given its own algorithm version (runmal-p096-dice-v1: a roll is a pure function of seed, context, canonical notation, roll key and die index, recorded with every face and draw, reproducible forever; the unseeded path is labelled and unverifiable, never dressed as reproducible), the P-089 durable per-user file-store idiom (one JSON document per UUID-validated owner, atomic 0600 save, stored rolls re-validated against their own faces on read, corrupt stores raise and are never silently reset; no migration), and the S609 bridge-outbox discipline at plugin scale (per-chat sequence numbers, after-cursor poll, monotonic per-consumer ack cursors, bounded retention with the prune count kept on the inspect document). The notation grammar (NdM[+-K] plus keep-highest/lowest, everything else refused plainly, multi-term named unsupported rather than half-parsed), the dice.rolled honesty rule (that kind is minted only by an actual roll in the same save; the generic emit road refuses it, so the log can never claim a roll that did not happen), the recorded-only game.event stance (never appended to a chat - chat.write is reserved; the credentialed bridge API owns turning game events into turns), the metadata-only event handler (a plugin event carries no owner id, so no durable write is made from it), and the no-transport boundary (the citizen opens no socket and talks to no game client; runmal.bridge and the runmal.bridges VRChat OSC / Skyrim HTTP adapters already exist and own transport) are Runmal's own design for the roadmap line. In this repo's own docs Sagnaskemma names the dice discipline itself (the P-036 line: "the Sagnaskemma dice discipline's kin"); no external Sagnaskemma material was consulted. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-097 (2026-11-07, public behaviour + own tree only):** the Plugin conformance kit — a plugin must pass contract + sandbox tests to be listed — is built entirely from Runmal's own in-tree contracts: the P-081 Plugin API v1 strict parser, surface rules and registry (reused as oracles on a throwaway registry; the default registry is untouched and the submission is never mutated), the P-082 grant policy and guarded context (behavioural denial probes that refuse at the grant gate), and the P-084..P-095 citizen pattern as the corpus the kit verifies. The thirteen checks in fixed order across two submission roads (a data-shaped manifest road and an in-tree citizen road), the deterministic checksummed report with no timestamps, the listing gate as data (is_listable / listable_ids), the corpus auto-discovery under runmal.plugins (so the P-096 citizen joins unchanged on the merged tree at banking), and the kit citizen itself (runmal.plugin-conformance, ui.slots only, P-082 grants empty, no state) are Runmal's own design for the roadmap line. One defect was found and fixed in-slice: on the parse-failure road the not_run rows for handlers_binding and registration were emitted before settings_shape, reshuffling the fixed check order; they now land in their own slots, pinned by a battery test on both roads. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-098 (2026-11-07, public behaviour + own tree only):** the Plugin settings UI generated from declared schemas - one generic renderer interpreting the P-081 settings block {schema, defaults} that P-081 stores verbatim and expressly leaves to this slice - is built entirely from Runmal's own in-tree contracts: the shipped citizens' actual declarations (flat string/integer/number fields with minimum/maximum bounds; seven citizens with fields, seven with honestly empty schemas), the P-089 durable per-user file-store idiom (one JSON document per UUID-validated owner, atomic 0600 save, strict re-validation on read, corrupt stores raise and are never silently reset; no migration, head stays 0041), the P-094 custody rules (one checksummed export document per plugin, owner-scoped delete that removes exactly the plugin's own section), and the P-081 citizen pattern (register via register_plugin; build_registry/create_app untouched; only v1 surface permissions, so the resource grant set is empty). The deterministic widget mapping (enum to select, boolean to checkbox, numeric to number, string to text), the strict named-error validation that is the deliberate mirror image of the citizens' lenient config_from_manifest roads (no coercion, no clamping, no silent drops; declaration defects are a separate loud class), the patch-merge-then-validate-whole write road, and the honest no-settings surface for empty-schema and settings=None plugins are Runmal's own design for the roadmap line. Shipped citizens' runtime config roads are unchanged in this slice, stated plainly in the slice doc. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-099 (2026-11-07, public behaviour + own tree only):** Failure manners - a crashing plugin disables itself with a plain report and the chat never dies with it - is built entirely from Runmal's own in-tree contracts: the P-081 registry failure rule (record_failure strikes, ERRORED at 3 consecutive, no dispatch while not ENABLED, enable/acknowledge lifecycle), the P-082 sandbox (Sandbox.run isolation and quarantine, secrets-by-name, metadata-only audit), and the P-083/P-096 router lazy-import idiom for the two new read routes. The guarded-call road for direct host invocations, the 1:1 sandbox-to-registry bridge (real failures only, watermarked, idempotent; no forged strikes), the declared re-enable rule (deliberate enable only; strikes clear, history kept; nothing retries or auto-re-enables), and the report hygiene rule (plain report carries no message text at all; dict messages scrubbed of caller-named secret values) are Runmal's own design for the roadmap line. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-100 (2026-11-07, public behaviour + own tree only):** the Part VI gate - the row ships with P-084-P-090 + P-095 live and a third-party-shaped test plugin installs and runs - is judged entirely from Runmal's own banked contracts: the P-097 conformance kit as the row oracle (every shipped citizen passes as shipped; the sixteen-citizen corpus is deterministic), the P-081 API as the composition surface (all sixteen citizens in one registry: event dispatch, both prompt-hook stages, UI contributions, no interference), the P-083 local-pack and manager road, the P-098 settings UI generated from the declared schema, the P-094 custody export/delete road, and the P-099 failure manners in a real HTTP chat flow. The blind plugin (a word counter, battery world ZqxGate100) was authored only against the five documented plugin surfaces (PLUGIN_API_V1, PLUGIN_MANAGER, PLUGIN_SETTINGS_UI, PLUGIN_DATA_CUSTODY, PLUGIN_CONFORMANCE_KIT, all 2026-11-07) and lives only in the gate battery. The data-only pack honesty (no code travels in a pack in v1; executable handlers bind through the documented citizen registration road), the carried items (the P-094 fixed list omitting the P-096 and P-098 citizens - gate finding F1 with a commissioned follow-up; P-098 stored values not yet driving a running citizen; P-099 failure state process-local; the deliberate empty boot registry) are Runmal's own records, pinned by measurement at the gate and named in the gate doc rather than loosened. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test modules (P-005 discipline).
- **P-101 (2026-11-07, public behaviour + own tree only):** Voice Sessions — the Part VII opener, whose scope is DERIVED (the roadmap gives Part VII only its part line, "Voice, the Voxta Way", P-101 – P-116; no verbatim P-101 entry exists, and the slice doc says so plainly). The derivation rests on Rúnmál's own in-tree record only: the P-003 Voxta census read as behaviour (VX-04 voices are character equipment, VX-09 the real-time voice core loop, VX-15 separately configured TTS/STT service slots, VX-65 the per-chat inspector), VOICE_ARCHITECTURE sections 2/4/8, the founding S501–S513 voice seams and stores, the P-053 provider-truth discipline (truth as data, imported from the source of truth, never copied), S512's fallback law (an unknown/removed backend falls back whole, never errors, never resurrects), the S508 playback-truth ledger (INV-020: no playback evidence, no heard claim), P-065's carried limitation (orchestrator turns are ephemeral TurnRecords, never persisted; persisting them is a voice-campaign decision — this is that campaign), and P-091's stated limitations (citizen voice state in memory only, citizens unregistered in the running app, no citizen HTTP surface). The session citizen (settings resolved once at start as character voice + user defaults + registry truth; one active session per chat with supersede; turns persisted through the heard-text split in the voice JSON-store pattern, no migration) is Rúnmál's own design for the derived opener. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-102 (2026-11-07, public behaviour + own tree only):** the Live Voice Orchestrator — Part VII's second slice, whose scope is DERIVED (the roadmap gives Part VII only its part line, "Voice, the Voxta Way", P-101 – P-116; no verbatim P-102 entry exists, and the slice doc says so plainly) from P-101's own named limitations: it takes L1 (no live orchestrator wired into the app process) and leaves L2 (turns projected into chat messages) and L3 (P-091 citizen registration, P-091's deliberate host-explicit law) untouched, for the reasons recorded in the scout. The derivation rests on Runmal's own in-tree record only: the Voxta census read as behaviour (VX-09 the real-time voice core loop, VX-65 the per-chat inspector), VOICE_ARCHITECTURE sections 2/4/8/13, the founding S501–S514 seams (the orchestrator's hook contract, the S508 ledger's subscription shape, the registry factories that raise BackendUnavailable rather than fall back, the RoleMap truth that never substitutes a default device), the founding /voice/status route's app.state.voice_session slot (always read LISTENING/0 because nothing ever set it — the wiring point), and P-101's append_orchestrator_turn "live-host road" consumed duck-typed with the session store imported lazily, so the slice imports only founding modules and reconciles cleanly when P-101 banks ahead of it. The one additive orchestrator method (speak_text, the mic turn's tail without STT/responder), the builder that assembles a session's orchestrator from its resolved settings snapshot with the ledger subscribed before any turn runs, the controller that persists every completed live turn through the citizen's own append road with a never-double-record watermark, the labelled-unavailable default responder (an honest error turn through ERROR_RECOVERY, never a fabricated reply), the wiring record whose road labels follow the BUILT backend ("fake" only where a test wired a fake), and the HTTP live roads whose default playback factory surfaces the RoleMap truth instead of defaulting a device are Runmal's own design for the derived slice. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-103 (2026-11-07, public behaviour + own tree only):** Voice Turn Projection - Part VII's third slice, whose scope is DERIVED (the roadmap gives Part VII only its part line, "Voice, the Voxta Way", P-101 - P-116; no verbatim P-103 entry exists, and the slice doc says so plainly) from P-101's named limitations and P-102's derivation: it takes L2 (session turns not projected into chat messages), which P-102 left open with the reason "L2 has nothing to project until live turns exist" - live turns now exist - and leaves L3 (P-091 citizen registration) untouched as the deliberate host-explicit law P-091 states and P-102's scout judged it to be. The derivation rests on Runmal's own in-tree record only: the P-101 session citizen and its history_text road (the S508 heard split as the one text law: certain text plus the explicit uncertainty marker, unplayed never included - INV-020 carried into the transcript itself, so a response the user never heard lands no assistant message however complete its stored text), the chats append road with its explicit-provenance parameter, P-076 undo journal and message.created dispatch (projection lands through it unchanged, one journal entry per side), the P-075 provenance discipline under the P-089 closed-vocabulary doctrine (origin kind stays "manual"; the voice road is named in scalar origin facts - via, session id, turn number, side, and the side's backend facts - never a forged kind; the response's model section is the recorded gap "unknown" because the persisted turn holds no generation model), and the P-101 JSON-store pattern for the durable projection state on the turn record itself (projected flag + per-side message ids + projected_at; tolerant load of the pre-P-103 stored shape; no migration, head stays 0041). The explicit-not-automatic stance (the P-102 live controller is synchronous and DB-free by design, so no auto-projection hook is wired into its persist road; a host or the HTTP road projects after turns complete), the truth-record stance (the session store stays the truth; projected messages are its linked transcript shadow, and edits/deletes never write back), and the owner-scoping rule (a foreign session or chat answers 404, existence never leaks, the P-101 session-start rule) are Runmal's own design for the derived slice. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-104 (2026-11-07, public behaviour + own tree only):** Voice Auto-Projection — Part VII's fourth slice, whose scope is DERIVED (the roadmap gives Part VII only its part line, "Voice, the Voxta Way", P-101 – P-116; no verbatim P-104 entry exists, and the slice doc says so plainly) from P-103's own stated limitation: projection was explicit, not automatic, because the P-102 live controller is synchronous and DB-free by design, and "an async auto-projecting host is a later slice's design" — this is that host. The derivation rests on Rúnmál's own in-tree record only: the P-101 session citizen and its JSON-store pattern (the durable per-session opt-in flag rides there, default off, tolerant load of the pre-P-104 shape, no migration, head stays 0041), the P-103 projection service as the ONE landing road (auto-projection calls it unchanged — same S508 heard-text law, unplayed never lands, same P-075 provenance — and adds no second road, only a when), the P-102 controller's stated design (preserved: two additive read accessors only; the async wiring lives in the HTTP host roads — live speak, live stop as the feed_frames catch-up, and the P-101 manual turns road), and the failure law (persistence precedes projection; the host service never raises; a failure is reported in-band with its plain reason and the turn stays retryable through the manual road). The items weighed and not taken are named in the slice doc: L3 citizen registration (deliberate host-explicit law, re-affirmed, not reopened), process-death of live hosts (P-102's designed recovery already covers it; active-but-not-live is the citizen's normal resting state), and the unbuilt census surface VX-11/VX-12/VX-13 (each needs its own truth-model or engine design, not host wiring). No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-105 (2026-11-07, public behaviour + own tree only):** Voice Mishearing Truth — Part VII's fifth slice, whose scope is DERIVED (the roadmap gives Part VII only its part line, "Voice, the Voxta Way", P-101 – P-116; no verbatim P-105 entry exists, and the slice doc says so plainly) from the census row VX-11 read as behaviour (mishearing is handled, not hidden: detection of misheard words, automatic replacement of often-missed words after transcription, STT confidence markings), the delta table's VX-11 row (MISSING — no mishearing detection, replacement list, or confidence surface in the inventory), and the Part I gate (VX-11 queued to the Part VII definition queue). The derivation rests on Rúnmál's own in-tree record only: the founding S503 STT seam (TranscriptWord.probability, real from faster-whisper with word timestamps on), whose per-word confidence P-101's persisted turn record dropped at the persistence boundary (only the transcript text survived, so no honest confidence surface could ever be built after the fact — this slice repairs that boundary first), the P-101 JSON-store pattern (word evidence on the turn record and the replacement lexicon as a versioned JSON document; tolerant loads for both the pre-P-105 turn shape and a corrupt lexicon; no migration, head stays 0041), the P-103 owner rule for the session view (unknown and foreign sessions answer 404, existence never leaks), and the S508 truth discipline carried to a new kind of evidence (the backend's own probability estimate persists verbatim, never recomputed or upgraded; no evidence is reported as no evidence, never as all-confident). The predeclared marking threshold (0.5 — below even odds the model's own estimate says the word is more likely wrong than right), the suggestion-never-rewrite law (the lexicon's output is a view over the stored transcript, which is never mutated, and P-103 projection still lands the original text), the whole-word-only matching with capitalisation and punctuation preserved, the one-word lexicon key refused at the door rather than stored as a silent no-op, and the detection-is-data stance (needs_repeat names the turns a host should ask about; no character asks for a repeat, because the live responder is P-102's honest-unavailable seam and fabricating one would cross it) are Rúnmál's own design for the derived slice. The items weighed and not taken are named in the slice doc: L3 citizen registration (deliberate host-explicit law, re-affirmed by P-102/P-103/P-104, not reopened), VX-12 affects (no affect seam exists in any TTS backend; an engine design, not this build), and VX-13 narrator voice (chats have no narration taxonomy consumer for it to read). No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-106 (2026-11-07, public behaviour + own tree only):** Voice Projection Mishearing Mark — Part VII's sixth slice, whose scope is DERIVED (the roadmap gives Part VII only its part line, "Voice, the Voxta Way", P-101 – P-116; no verbatim P-106 entry exists, and the slice doc says so plainly) from P-105's own slice doc §4, which names this exact gap as a later slice's design question: P-103 projection landed the original transcript with neither a suggestion nor a mishearing mark. This slice takes the mark half and declines the suggestion half on the record (P-075 provenance records no message content, and landing a suggested rewrite would rewrite the user's words in their own chat history). It is built entirely from Runmal's own in-tree contracts: the P-103 projection module and its one service road (P-104 inherits through it unchanged — no second road), the P-075 provenance doctrine (scalar origin facts only, a gap recorded never silently absent, tolerant readers), and the P-105 truth law (threshold 0.5 predeclared in runmal.voice.mishearing and imported when present with the same value as the on-base fallback, evidence verbatim, no evidence is a fact not a zero, non-numeric or out-of-range probabilities are not evidence). The duck-typed evidence read (getattr transcript_words; objects, dicts, or any text/probability shape) so the slice stands on the P-104 base and reads P-105's real persisted evidence unchanged once P-105 banks, the always-present scalar mishearing facts on transcript provenance, and the additive per-turn marks plus session aggregates on the projection status/report views are Runmal's own design for the derived slice. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-107 (2026-11-08, public behaviour + own tree only):** Voice Rendered Confidence Markings - Part VII's seventh slice, whose scope is DERIVED (the roadmap gives Part VII only its part line, "Voice, the Voxta Way", P-101 - P-116; no verbatim P-107 entry exists, and the slice doc says so plainly) from the census row VX-11 read as behaviour (the UI shows speech-to-text confidence markings), P-105's own stated limitation (confidence markings are data on the HTTP surface; no UI renders them; the rendered-markings surface stays open on top of the truth layer), and P-106's design (the projection mark is a receipt, not a rendering). The derivation rests on Runmal's own in-tree record only: the P-103 provenance link on every landed transcript message (origin via=voice_session with session id, turn number and side riding as scalar facts), the P-101 session store as the evidence home, P-105's turn_mishearing as the ONE truth source (threshold, bands and suggested hearing imported, never redeclared, so the rendering and P-106's receipt read the same persisted evidence and cannot disagree), the no-evidence honesty law carried to the render (a wordless turn is badged no-evidence, never clear and never doubtful; an unresolvable session or turn is a recorded gap marking, never a silent clean bill), the content law (stored text stays the verbatim transcript; the suggested hearing appears only as badge text, never as content), and the S302 renderer discipline (escape-first, pure functions, node-tested; the P-105 token law mirrored so punctuation stays outside the marked span, the signal carried by a dotted underline and never colour alone). The items weighed and not taken are named in the slice doc: the mid-dialogue repeat request (the live responder is still P-102's honest-unavailable seam and fabricating the ask would cross it), VX-12 affects and VX-13 narrator (each needs its own engine or taxonomy design; no lawful consumer exists yet), L3 citizen registration (deliberate host-explicit law, re-affirmed P-101 through P-105, no new evidence), the live responder seam (larger than one slice), back-marking landed provenance (P-106's P-075 production-receipt law stands untouched - the marking is a read-time view, not a rewrite), and P-104's by-design items. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-108 (2026-11-08, public behaviour + own tree only):** Voice Repeat-Request Signal - Part VII's eighth slice, whose scope is DERIVED (the roadmap gives Part VII only its part line, "Voice, the Voxta Way", P-101 - P-116; no verbatim P-108 entry exists, and the slice doc says so plainly) from the census row VX-11 read as behaviour (mishearing is handled, not hidden: detection, replacement, confidence markings, and asking the user to repeat) and the recorded limits of the slices that built the row's other halves: P-105 (detection is data, not dialogue; needs_repeat names the turns a host should ask about, and fabricating the ask would cross the P-102 honest-unavailable responder seam), P-106 (the projection mark is a receipt, not a rendering; the dialogue half stays open) and P-107 (the rendering; mid-dialogue repeat requests stay open). The derivation rests on Rúnmál's own in-tree record only: the P-105 mishearing truth layer as the single source (a turn is a repeat request exactly when turn_mishearing says needs_repeat; the predeclared 0.5 threshold and bands are imported, never redeclared, so the signal cannot disagree with P-105's view, P-106's receipt or P-107's rendering), the P-101 session citizen and its store as the derivation's input, the P-105 voice JSON-store house pattern for the durable acknowledgement record (versioned document, tolerant load, housekeeping delete that reports absence instead of erroring), and the P-103/P-105 owner rule for the HTTP roads (unknown and foreign sessions answer 404, existence never leaks). The signal-is-data stance (no chat message is created, no responder is wired or called, no text is generated; a host acts on the signal through its own surface or not at all), the acknowledgement-is-handling-not-truth law (detection is recomputed from the evidence on every read; first acknowledgement wins so the receipt names when a host first acted; clearing returns the request to pending with the truth untouched), the no-evidence-is-not-a-request rule (a turn with no recorded words never appears), and the acknowledge-refusal (a turn with no request answers 422 rather than recording handling for a request that does not exist) are Rúnmál's own design for the derived slice. The items weighed and not taken are named in the slice doc: the character-asks half of VX-11 (still blocked by the P-102 responder seam, which this slice does not cross), VX-12 affects (verified: VoiceInfo carries no affect field and no TTS backend consumes one; an engine design across the registry, not one slice, and a scoping-only paper slice was declined), VX-13 narrator voice (verified: no narration surface or taxonomy consumer exists in chats or voice), L3 P-091 citizen registration (deliberate host-explicit law, re-affirmed P-102 through P-105, no new evidence), the live responder build (the injection seam already exists complete; the missing generation bridge is a cross-subsystem build larger than one slice), P-104's by-design items, and P-107's recorded limitations (API data already rides both thread surfaces; in-flight marking would claim evidence that does not exist yet). No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-109 (2026-11-08, public behaviour + own tree only):** Voice Affects as Carried Data - Part VII's ninth slice, whose scope is DERIVED (the roadmap gives Part VII only its part line, "Voice, the Voxta Way", P-101 - P-116; no verbatim P-109 entry exists, and the slice doc says so plainly) from census row VX-12 read as behaviour (voices carry emotion - anger, whispering, laughing - with proper prosody and affects) and the P-105/P-101/P-104 scouts, which declined VX-12 because no affect seam exists in any TTS backend (VoiceInfo carries no affect field, no backend consumes one - re-verified on this base). This slice builds the bounded DATA half those scouts named as the honest first step and declines the engine half: a closed vocabulary (neutral plus exactly the census row's three named affects) in one module, validated strictly at the character voice profile write door (the vocabulary's first real consumer), read tolerantly with the fallback NAMED in the S512 law, resolved once into the P-101 session settings snapshot, and exposed on the founding voice road - with the consumption truth carried as data on every surface (consumed: False, because no backend accepts an affect and synthesis is unchanged by one). Neutral's one representation (absence of the profile params key), the stored-snapshot tolerant resolution that never bricks a pre-P-109 session, and the no-migration stance (the profile params dict and the session JSON snapshot already carry free data; head stays 0041) are Runmal's own design for the derived slice. The items weighed and not taken are named in the slice doc: VX-13 narrator (no narration taxonomy exists for a narrator voice to read), the character-asks half of the repeat request (the P-102 responder seam, honest-unavailable), P-108's recorded limitations (the Plugin API v1 event vocabulary is closed by law; per-host acknowledgements would weaken the do-not-ask-twice protection), L3 citizen registration (deliberate host-explicit law, no new evidence), and the generation bridge behind live.py's injection seam (cross-subsystem, no bounded non-hollow part identified). No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-110 (2026-11-08, public behaviour + own tree only):** Voice Turn Latency Evidence - Part VII's tenth slice, whose scope is DERIVED (the roadmap gives Part VII only its part line, "Voice, the Voxta Way", P-101 - P-116; no verbatim P-110 entry exists, and the slice doc says so plainly) from Runmal's own in-tree record only: VOICE_ARCHITECTURE section 2 (transitions logged with monotonic timestamps for latency measurement) and section 10 (the metrics to record, reported as p50/p95), the S505 orchestrator's clock-stamped transition log, S510's percentile (imported, never reimplemented), and the P-101 session citizen whose persisted turns carried no latency evidence while the S510 MetricsCollector behind the founding /voice/status was never fed by anything in the tree. The derivation holds the evidence-or-nothing law throughout: a duration exists only when both of its stage endpoints were stamped for that turn by the orchestrator's own clock; response_seconds is named generation duration and never time-to-first-token (the first token is not stamped and is not claimed); stages the log cannot prove (VAD speech-on, endpoint hangover, interruption detection-to-stop) are named unclaimed; a manually recorded turn carries no evidence and the views say so. The items weighed and not taken are named in the slice doc: VX-12's engine half (P-109 took the carried-data step in flight; no backend affect seam exists), VX-13 narrator (scenarios are file-interop models only, no narration taxonomy consumer), the character-asks repeat half (P-102's honest-unavailable responder seam), P-108's recorded limitations (closed Plugin API v1 event vocabulary; per-host acks would weaken its do-not-ask-twice point), L3 citizen registration (deliberate host-explicit law, no new evidence), the generation bridge (no bounded non-hollow part), P-104/P-107 by-design items, and feeding the global metrics collector (a process-global second truth; the persisted per-session record is the citizen-shaped fix). No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-111 (2026-11-08, public behaviour + own tree only):** Voice Repeat-Acknowledgement Housekeeping - Part VII's eleventh slice, whose scope is DERIVED (the roadmap gives Part VII only its part line, "Voice, the Voxta Way", P-101 - P-116; no verbatim P-111 entry exists, and the slice doc says so plainly) from P-108's own recorded limitation: a deleted session's repeat-request acknowledgements become inert records - they name a session that no longer exists, drive nothing, and before this slice no road could ever remove them, because the only housekeeping road (clear) hangs off a session view that answers 404 for a deleted session. The derivation rests on Rúnmál's own in-tree record only: the P-108 acknowledgement store and its tolerant versioned-JSON house pattern, the P-101 session store as the single source of which sessions are live, and the chat-drop road (DELETE /voice/chats/{chat_id}/sessions) as the act that orphans the records. The inert definition (a record is inert exactly when its session id is absent from the session store - no age, count, or heuristic threshold invented), the pure-read housekeeping view that names the inert session ids before any prune is called, the no-op guarantee (a prune that removes nothing leaves the store document byte-identical and creates no file for an absent store), the deliberately global drop-act prune (one housekeeping act clears all inert records and reports the act total, not only the dropped chat's share), and the install-wide stance of the housekeeping roads (the bearer gate is the authorisation, exactly like the P-105 lexicon and the P-108 store itself, stated plainly) are Rúnmál's own design for the derived slice. Housekeeping removes handling records only: P-105 detection truth is never touched, a live session's acknowledged requests stay acknowledged through any prune, and no chat message is created by any road in the slice. The character-asks half of VX-11 stays open on the P-102 responder seam, untouched. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-112 (2026-11-08, public behaviour + own tree only):** Voice Live-Start Back-Projection - Part VII's twelfth slice, whose scope is DERIVED (the roadmap gives Part VII only its part line, "Voice, the Voxta Way", P-101 - P-116; no verbatim P-112 entry exists, and the slice doc says so plainly) from Runmal's own in-tree record only: P-104's slice doc section 4, which records the limitation verbatim ("Live start does not back-project pre-existing turns; the next speak/stop - or the manual P-103 road - catches up"), the P-104 async host service (autoproject_session: opt-in, whole-session, idempotent, never-raises) and the live router's own shared _maybe_autoproject helper that the speak road already walks. The start road now walks the same helper after a successful start, so an opted-in session's pre-existing turns land in their chat at the moment it goes live, through P-103's one landing service and its heard-text law; no content is created or invented - no-content turns are counted, never landed, and a default-off or nothing-pending session returns the exact P-102 start shape. The P-102/P-104 design law stands untouched: the LiveVoiceController stays synchronous and DB-free, back-projection lives only in the async HTTP host layer, and in-process controller starts are pinned as not back-projecting. The items weighed and not taken are named in the slice doc and scout: L3 citizen registration (deliberate host-explicit law, no new evidence), the character-asks repeat half (the P-102 responder seam; building it would invent what a character says, against the P-075 no-content law), the VX-12 engine half and affect-aware history views (the carried affect is already surfaced per-session; affect is a standing snapshot, never per-turn truth), and VX-13. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-113 (2026-11-08, public behaviour + own tree only):** Plugin Custody Coverage: the F1 Fix - Part VII's thirteenth slice, whose scope is DERIVED (the roadmap gives Part VII only its part line, "Voice, the Voxta Way", P-101 - P-116; no verbatim P-113 entry exists, and the slice doc says so plainly) from the P-100 Part VI gate's finding F1 (carried item K1), which commissioned extending P-094 CITIZEN_PLUGIN_IDS with runmal.game-bridge and runmal.plugin-settings-ui at the next custody touch - this slice is that touch. The derivation rests on Rúnmál's own in-tree record only: the P-094 custody surface and its section discipline (verbatim durable-file exports, owner-scoped deletes, a section never silently omitted, corrupt stores as loud section errors), the P-096 game-bridge citizen's durable per-owner store (store_path + STORE_SCHEMA, exactly the P-089 idiom custody's file table already serves, so its rolls and bridge events stop being hostage state), and the P-098 settings-ui module's own custody-shaped verbs (the shared plugin_settings store is served section-scoped: only the settings-ui citizen's own section is its custody data, the shared file is never exported or deleted whole, and a refused delete removes nothing). Bare-id exports for both citizens now stamp their real manifests, and custody_coverage classifies both honestly (game-bridge as durable_file; settings-ui under a new plugin_settings classification, because no whole-file verb is lawful for its shared store). The items weighed and not taken are named in the slice doc: L3 auto-registration of the P-091 voice citizens (deliberate host-explicit law - each citizen's register_plugin already is that road; this slice registers nothing and the boot registry stays empty), the VX-12 engine half (no backend affect seam exists), marking projected message content itself (declined by P-106 on the record under the P-075 law), and adding gallery or conformance to the list (F1 names exactly two ids). Two pre-existing tests that pinned the pre-F1 state are updated in-slice at equal or greater strength and labelled in the slice doc (the P-100 gate's Area C pin now holds the covered state, battery count unchanged; the P-094 coverage test's durable_file set gains game-bridge). No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-114 (2026-11-08, public behaviour + own tree only):** Voice Mishearing Session Report - Part VII's fourteenth slice, whose scope is DERIVED (the roadmap gives Part VII only its part line, "Voice, the Voxta Way", P-101 - P-116; no verbatim P-114 entry exists, and the slice doc says so plainly) from Rúnmál's own in-tree record only: P-105's mishearing truth layer, which carried per-turn views and session totals but no pooled aggregate, and P-110's latency aggregate as the house pattern for exactly this shape (per-turn evidence paired with a count/mean/percentile aggregate block over the house metrics.percentile function). The aggregate pools ONLY what turn_mishearing already states - the bands, the 0.5 threshold and the probabilities are never recomputed under a second law - and adds the often-missed-word table grouped by the lexicon's own key law (the punctuation-stripped, lower-cased core from the same affix split the replacement roads use, so a frequent-low-word key is exactly the key a lexicon entry must use), the lexicon-coverage view (covered vs uncovered at occurrence and distinct-word level), and the per-backend split from each turn record's stt_backend. The no-evidence law is held throughout: a session with no recorded words reports has_confidence_evidence False and None for every statistic, never a 0.0 mean and never all-confident. The light report view carries exactly the totals session_mishearing already states plus the aggregate and no per-turn detail; the session view gains the same aggregate additively. The candidates weighed and not taken are recorded in the scout: per-session affect history (no per-turn affect was ever recorded - P-109's snapshot already has its honest read surface, and a history built from it would fabricate the per-turn truth P-109 disclaims), the repeat-request digest/aging view (it summarises a signal derived from this same evidence and needs invented age buckets), and session lifecycle custody (verified already complete - deletion drops the whole session record and P-111 prunes its orphaned acknowledgements in the same act). Data only, under the P-075 no-content law: no dialogue, no responder call, no chat message, no transcript mutation, no new store, no migration. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-115 (2026-11-08, public behaviour + own tree only):** Voice Repeat-Request Digest & Aging - Part VII's fifteenth slice, whose scope is DERIVED (the roadmap gives Part VII only its part line, "Voice, the Voxta Way", P-101 - P-116; no verbatim P-115 entry exists, and the slice doc says so plainly) from Runmal's own in-tree record only: P-114's scout record, which weighed the repeat-request digest/aging candidate second and left it named-open (cross-session roll-up plus wall-clock aging over the stored acknowledged_at / recorded_at, derivable with an injected now), and P-108's own per-session signal as the single truth source the digest sums. The digest answers the one cost that scout named - invented age buckets - by reporting ages as plain arithmetic seconds (oldest / newest / mean plus an explicit without-age count for missing, unparseable or future stamps, never clamped and never zero-claimed, the P-110 negative-span law applied to wall clock), with no bucket, no threshold and no staleness verdict. Its road is owner-scoped like the P-108 per-session roads, not install-wide like P-111 housekeeping, because it names live sessions, chats and pending turns. The items weighed and not taken are named in the slice doc and scout: L3 auto-registration of the P-091 voice citizens (deliberate host-explicit law - this slice registers nothing), and the VX-12 engine half (verified again at this base: affects are consumed: False on every surface and no backend seam exists). No content is created or invented - the digest is data about handling state only, and the character half of VX-11's ask stays open on the P-102 responder seam under the P-075 law. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-116 (2026-11-08, public behaviour + own tree only):** Part VII Gate - the gate slice whose scope is the filed roadmap's part line itself ("VII | Voice, the Voxta Way | P-101 - P-116"); Part VII's per-slice definitions are DERIVED throughout, as every slice doc states, so the gate judges the part against the census its own banked slice docs declare, following the P-030/P-100 gate precedents (a gate builds no new behaviour; it judges banked slices end to end through their own public contracts, from measured evidence only). The battery walks one fresh-authored gate world (ZqxGate116, P-005 discipline, word-confidence fixtures only under the P-075 test-data allowance, no fabricated dialogue) through sessions, the live host, projection and auto-projection, mishearing truth/markings/report agreement on P-105's single threshold source, the repeat-request signal + acknowledgement + housekeeping loop, affects as carried data, latency evidence, live-start back-projection, and the P-113 custody coverage including the P-091 voice citizens. P-115 (repeat-request digest) banks before this gate on a footprint this gate's base does not contain; the gate covers it by auto-discovery in the P-100 pattern - exercised in full where present (counts proven to be the P-108 views' sums; aging arithmetic from an injected now), pinned as pending at equal strength where absent - and both shapes were measured for this gate. The carried items are named in the gate record (K1-K7): the character-asks half of VX-11 on the P-102 responder seam, VX-12's engine half without a backend seam, L3 deliberate host-explicit registration, the no-UI data surfaces, HTTP-only back-projection with a DB-free in-process controller, uncalibrated backend confidence, and the digest's no-staleness-verdict stance. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test modules (P-005 discipline).
- **P-117 (2026-11-08, public behaviour + own tree only):** the Vision foundation — vision descriptions as first-class chat-bound records behind a provider seam, the metadata provider whose description is only the sniffed truth about the bytes, the no-provider plain refusal, the durable JSON store with the last-description read surface, and the owner-scoped HTTP road — is built entirely from Rúnmál's own in-tree contracts: the roadmap's Part VIII part line, the Voxta census VX-50/VX-43 behaviour record (vision on request; the last vision description as a template variable), the P-101 opener pattern, the voice JSON-store house pattern, P-053 provider truth as data, P-075's no-content law, and the P-023 sniff machinery in assets/imaging. The commissioned openapi fix (gate finding F2) is likewise in-tree only: both bare HTML page registrations in app.py now declare the HTMLResponse class every other HTML route already used. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-118 (2026-11-08, public behaviour + own tree only):** The Last Vision Description Reaches the Prompt — Part VIII's second slice, whose scope is DERIVED (the roadmap gives Part VIII only its part line, "Vision Services", P-117 – P-130; no verbatim P-118 entry exists, and the slice doc says so plainly) from Runmal's own in-tree record only: P-117's slice doc, which names open that the last vision description is retrievable as data but the prompt composer does not yet consume it as the VX-43/VX-50 template variable, and that descriptions are never deleted by chat housekeeping (custody on chat deletion named open, as voice custody was before its own slice); the census rows VX-43 and VX-50 read as behaviour (the last vision description is a template variable); the S307 variable model and its tools preview road as the in-tree prompt-variable surface; and the house guarded lazy-import custody pattern in chats/service.py delete_chat (the voice drop_chat precedent). P-117's store format (vision_descriptions.json, version 1) is read as DATA only — this slice, built from the P-116 base where P-117 is not yet merged, never imports runmal.vision and never inspected any SillyTavern or Voxta source; the format is pinned in one new module (prompt/vision_link.py) as the single place to re-pin. The honest-empty resolver law (an absent description resolves to the empty string, never a fabricated caption, P-075) and the purge write shape byte-matching P-117's own store writer are Runmal's own design for the roadmap line. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-119 (2026-11-08, public behaviour + own tree only):** vision provider selection + capability truth — the provider catalogue as data (neither shipped provider labelled semantic), the deterministic labelled test provider (road `deterministic_test`, the P-086/P-087 house pattern), per-backend `Capabilities.vision` truth read live from the adapters' own declarations via the P-053 `default_model` road, plain refusals for unknown and semantic requests, and the inspectable `/vision/providers` surface — is built entirely from Rúnmál's own in-tree contracts: P-117's named-open items (1) and (2), the P-053 truth discipline, the P-075 no-content law, and the assets/imaging sniff truth. No real semantic caption provider was built: no vision model, endpoint, or image wire exists in-tree to call honestly, and the slice says so as data instead of inventing one. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-120 (2026-11-08, public behaviour + own tree only):** image attachments on chat messages — user-supplied images bound to a chat or one of its messages, with bytes and honest sniffed metadata persisted — is built entirely from Runmal's own in-tree contracts: the P-117 vision JSON-store pattern (versioned index, tolerant load, no migration) extended with per-attachment byte files named by id with the extension taken from the sniffed format, the assets/imaging sniff truth as the record's only content claim (the user filename kept as data, never a path, never a caption), the house 16 MiB image cap shared with the P-023 asset and avatar roads, the P-117 describe road gaining the attachment as a third named source, the P-107 tolerant additive view idiom for the message-history surface, and the P-118 lazy custody-purge idiom extended to message deletion. The declines are recorded with their evidence in the slice doc: no semantic caption provider (no backend declares the vision capability and no image-input wire or local vision model exists in-tree), no OCR (no recognition engine in-tree), no capture or camera surface, and the folder watcher deferred until attachments exist to be its destination. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-121 (2026-11-08, public behaviour + own tree only):** the folder watcher — watch-folder registrations bound to a designated chat and an explicit polling scan that ingests new image files as P-120 chat attachments — is built entirely from Runmal's own in-tree contracts: P-120's attachments destination and its evidence naming the watcher as the natural follow-on, the P-117 JSON-store pattern (no migration, head stays 0041), the P-118 custody purge idiom and its build-against-a-sibling's-shape-as-data precedent (the attacher is resolved lazily; P-120 is not in this base), the sha256 dedupe truth (an unchanged file never duplicates; a changed file ingests anew), and the P-075 no-content law (sniffed truth only, named skips store nothing, no caption and no safety scan is claimed). No watcher daemon was built or claimed: no such machinery exists in-tree, so the scan is a deliberate polling operation, stated plainly. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-122 (2026-11-08, public behaviour + own tree only):** vision description history, search & custody completion - whose scope is DERIVED (the roadmap gives Part VIII only its part line, "Vision Services", P-117 - P-130; no verbatim P-122 entry exists, and the slice doc says so plainly) from Runmal own in-tree record only: the P-117 vision store and road shape (append / list-per-chat / last only, no get, no search, no delete), the P-118 custody idiom and its format-pinned vision_link read side, the P-119 provider-road truth used to validate the history road provider filter, the P-120 attachment deletion roads whose derived descriptions survived their source until this slice, the P-113 custody-coverage precedent, and the literal full-text-first search precedent in chats/search. The store gains owner-scoped get / list / literal substring search (description text and question only, never semantic, never ranked), single-record remove, and purge_source source custody; the router gains the history road and single-record read/delete; attachment deletion and message deletion now purge derived descriptions in the house guarded idiom. Declined with evidence in the slice doc: describe-batch / gallery wiring (no census behaviour, no gallery surface in-tree), provider health surfacing (P-119 already surfaces the truth and neither local provider has a health signal), a semantic caption provider, OCR, and capture/camera (no honest in-tree basis for any of them); the folder watcher is P-121 on team-03 and is not duplicated. No SillyTavern or Voxta source code was read and no file was downloaded; the slice tests are authored fresh in the test module (P-005 discipline).
- **P-123 (2026-11-08, public behaviour + own tree only):** Attachment Thumbnails for Vision Surfaces - Part VIII's seventh slice, whose scope is DERIVED (the roadmap gives Part VIII only its part line, "Vision Services", P-117 - P-130; no verbatim P-123 entry exists, and the slice doc says so plainly) from Runmal's own in-tree record only: the P-023 thumbnail engine in assets/imaging (pure-stdlib PNG decode, box-downscale, re-encode), which character assets already ride while P-120's chat attachments - the images a vision surface actually lists - could only be fetched at full size, and P-075's no-content law, which fixes the slice's honesty bound: the engine is PNG-only, so non-PNG attachments refuse plainly by name and the full bytes are never served in a thumbnail's place, an undecodable PNG refuses by name, and thumbnail availability stays a request-time fact that the attachment record never pre-claims. The derivation stores nothing (no byte file, no index change), so P-120 custody remains the whole custody story and no migration is taken. The candidates weighed and not taken are recorded in the scout and slice doc: watcher scan-history persistence (a synchronous operation result with no in-tree consumer and no retention law), vision settings via the P-098 pattern (driven by a P-081 manifest vision does not declare; no behaviour waits on stored settings), describe-on-attach opt-in wiring (reverses P-120's stated no-description-on-attach invariant and deserves its own reconciliation), and the standing impossibles with unchanged evidence - no semantic caption provider (no backend declares Capabilities.vision, no image wire, no local model), no OCR (no engine), no capture or camera (no surface), no watcher daemon (no machinery). No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-124 (2026-11-08, public behaviour + own tree only):** Watcher Custody & Control Completion — Part VIII's seventh slice, whose scope is DERIVED (the roadmap gives Part VIII only its part line, "Vision Services", P-117 - P-130; no verbatim P-124 entry exists, and the slice doc says so plainly) from Runmal's own in-tree record only: the P-121 watcher store, whose ingested records are the scan's dedupe memory and were removed only when a watch or its chat died — so an attachment deleted over its own road, or through its message's deletion, left a record that skipped its source file as already-ingested forever (the same custody hole P-122 closed for derived descriptions, one store over); and the P-121 enabled flag, refused-by-scan since it landed yet changeable by no service verb and no HTTP road, with no single-watch read road beside it. The store gains forget_attachment (attachment death forgets its records across watches; an empty id forgets nothing; a no-match forget leaves the file byte-untouched) and set_enabled (the flag's first handle, preserving every other field and all records); attachment deletion reports the forgotten count additively, message deletion forgets inside its existing guarded custody block, and the watch roads gain the single read and the PATCH toggle, owner-scoped like every vision road. Forgetting claims nothing about the source file — the next scan re-judges its actual bytes — and the toggle starts no daemon, because none exists in-tree. The candidates weighed and not taken are named in the slice doc: a semantic caption provider, OCR, capture/camera, a daemon, and non-PNG thumbnail decoding (no honest in-tree basis for any of them), describe-batch and scan-history persistence and vision settings and describe-on-attach (each declined on the record at P-122 or P-123), portable-archive inclusion (a portable-subsystem contract, not a vision slice), fork-carry of vision rows (rows are bound to the chat that produced them, the P-120 copied-message precedent), and attachment owner-wide history/search, which is real and stands as the named P-125 candidate rather than a second store bundled into this slice. P-123 (attachment thumbnails) banks before this slice and is not duplicated. No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-125 (2026-11-08, public behaviour + own tree only):** attachment owner-wide history and literal search - Part VIII's ninth slice (after P-124, which banks ahead of it), whose scope is DERIVED (the roadmap gives Part VIII only its part line, "Vision Services", P-117 - P-130; no verbatim P-125 entry exists, and the slice doc says so plainly) from Runmal's own in-tree record only: the P-124 scout's standing candidate and the verified parity gap it named - P-122 gave vision descriptions an owner-wide history with literal search while P-120's attachments, the images themselves, could still be listed only per-chat (the store had no list_for_owner and no search, and the list road requires a chat_id). The P-122 discipline ports exactly onto the same versioned-JSON store pattern: owner scoping first so foreign rows are never matched, counted, or returned; literal case-insensitive substring matching over the filename and the image sha256 only - the two text identifiers the record honestly holds under the P-075 no-content law, never semantic, never ranked, reading no image bytes; exact chat / message / format filters with an unknown format refused plainly; paging with the full total; and one new road, GET /vision/attachments/history, declared before the {attachment_id} roads so the literal segment is not captured as an id. Nothing is stored or altered, so custody stays wholly with P-120/P-122 and no migration is taken. Declined with evidence in the scout and slice doc: a semantic caption provider, OCR, and capture/camera (no honest in-tree basis for any of them), a watcher daemon (the P-121 deliberate-scan stance), non-PNG thumbnail decoding (the P-123 PNG-only engine bound), watcher scan-history persistence and vision settings (no consumer, no manifest), describe-on-attach (reverses the P-120 no-description-on-attach invariant), search over descriptions-of-attachments from this surface (already P-122's road), and bulk export (no census behaviour). No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-126 (2026-11-08, public behaviour + own tree only):** Describe-on-Attach Opt-In - Part VIII's tenth slice, whose scope is DERIVED (the roadmap gives Part VIII only its part line, "Vision Services", P-117 - P-130; no verbatim P-126 entry exists, and the slice doc says so plainly) from Runmal's own in-tree record only: the P-120 attach road and its stated invariant that attaching generates no description, the P-119 provider selection layer with its plain refusals, the P-117 describe service persisting source_kind attachment records, and the P-123 slice's own deferral of this candidate as a real follow-on shape that deserves its own slice and doc reconciliation rather than a ride-along. The reconciliation amends only the HTTP road's form of the invariant: attach_image itself is unchanged and still describes nothing (the P-121 watcher scan, which calls it directly, keeps its no-description bound exactly), while the attach road gains an explicit per-request opt-in, default off with the P-120 response shape unchanged, that is atomic - provider selection runs before anything is stored so a selection refusal stores nothing, and a describe failure after the attach removes the just-created attachment before the refusal rides out. The opt-in description is an ordinary attachment-sourced record and inherits the whole P-122 custody story. The candidates weighed and not taken are recorded in the scout and slice doc: watcher scan-history persistence (declined on the merits by three prior scouts - a synchronous result with no in-tree consumer and no retention law), vision settings via the P-098 pattern (driven by a P-081 manifest vision does not declare; no behaviour waits on stored settings), describe-batch, portable-archive inclusion, fork-carry, and the standing impossibles with unchanged evidence - no semantic caption provider (no backend declares Capabilities.vision, no image wire, no local model), no OCR (no engine), no capture or camera (no surface), no watcher daemon (no machinery), no non-PNG thumbnails (the P-023 engine is PNG-only). No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-127 (2026-11-08, public behaviour + own tree only):** watcher owner-wide history and literal search - Part VIII's eleventh slice (banking after P-126, which it does not duplicate), whose scope is DERIVED (the roadmap gives Part VIII only its part line, "Vision Services", P-117 - P-130; no verbatim P-127 entry exists, and the slice doc says so plainly) from Runmal's own in-tree record only: the P-122 history/search discipline and the P-125 parity surface, and the verified gap they left - descriptions and attachments each gained an owner-wide history with literal search while the watcher store, the third vision store, could still be listed only per-chat (registrations) and per-watch (ingested records) and had no search verb at all. The P-122/P-125 discipline ports exactly onto the same versioned-JSON store: owner scoping first (for ingested records, resolved through watch ownership, since the records carry no owner field and none is invented) so foreign rows are never matched, counted, or returned; literal case-insensitive substring matching over the folder path only for registrations, and over source_path and sha256 only for ingested records - the text identifiers the records honestly hold under the P-075 no-content law, never semantic, never ranked, reading no image bytes; exact filters (chat / enabled / recursive; watch / chat) that are never search text; paging with the full total; and two new roads, GET /vision/watch-folders/history and GET /vision/watch-folders/ingested/history, declared before the {watch_id} roads so the literal segments are not captured as ids, with unknown-or-foreign filter targets refused 404. Nothing is stored or altered - no scan report is persisted - so custody stays wholly with P-121/P-124 and no migration is taken. Declined with evidence in the scout and slice doc: watcher scan-report persistence (a synchronous result with no consumer and no retention law, declined for the fourth time on unchanged evidence - distinct from the already-persisted ingested records this slice merely reads), vision settings via the P-098 pattern (no declared schema; no behaviour waits on stored settings), portable-archive inclusion of the vision stores (the archive is a SQL-row bundle with manifest-validated member shapes; the vision stores are data-dir JSON documents by P-120/P-121 design - a portable-subsystem slice, named open for that line), a semantic caption provider, OCR, and capture/camera (no honest in-tree basis for any of them), a watcher daemon (the P-121 deliberate-scan stance), describe-batch, and fork-carry of vision rows (bound to their chat, the P-120 precedent). No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
- **P-128 (2026-11-08, public behaviour + own tree only):** Describe-on-Scan Opt-In - Part VIII's eleventh slice (after P-126; P-127 banks ahead of it), whose scope is DERIVED (the roadmap gives Part VIII only its part line, "Vision Services", P-117 - P-130; no verbatim P-128 entry exists, and the slice doc says so plainly) from Runmal's own in-tree record only: P-126's slice doc naming a describe opt-in on the watcher scan road as the one remaining describe-shaped item open, P-121's scan bound and attacher seam, P-126's attach_and_describe atomic pair, P-119's selection with plain refusals before storage, and P-122's custody for attachment-sourced descriptions. The reconciliation amends only the scan road's form of P-121's bound: scan_watch itself is unchanged and still describes nothing (a plain scan's report dict stays byte-identical, the "described" key appearing only on an opt-in scan), while a new composition, scan_and_describe, runs the same scan with a describing attacher so each newly ingested file lands as attachment + description or as a named refused skip, already-ingested files are never re-described, and the HTTP scan road gains an optional opt-in body with provider selection before the scan so a selection refusal ingests nothing. The candidates weighed and not taken are recorded in the scout and slice doc: watcher scan-history persistence and vision settings (declined on the merits by prior scouts - no in-tree consumer, no retention law, no declared schema), describe-batch (a loop over the single describe with no census behaviour naming it; describe-on-scan is the ingestion road's own opt-in, not that loop), portable-archive inclusion (a portable-subsystem contract, not a vision slice), fork-carry of vision rows, and the standing impossibles with unchanged evidence - no semantic caption provider (no backend declares Capabilities.vision, no image wire, no local model), no OCR (no engine), no capture or camera (no surface), no watcher daemon (no machinery), no non-PNG thumbnails (the P-023 engine is PNG-only). No SillyTavern or Voxta source code was read and no file was downloaded; the slice's tests are authored fresh in the test module (P-005 discipline).
