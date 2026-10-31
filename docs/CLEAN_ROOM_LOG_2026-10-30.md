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
