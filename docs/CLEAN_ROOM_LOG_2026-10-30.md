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
