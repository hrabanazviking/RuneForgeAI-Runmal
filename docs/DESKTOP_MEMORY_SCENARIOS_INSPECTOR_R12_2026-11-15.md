# R-12 — Memory, Scenarios, Inspector & Tools (desktop definition)

Date: 2026-11-15. Slice R-12 of the Interface Redo plan (Part 3):
"Memory, Scenarios, Inspector & Tools. Memories browser +
embedding controls; scenario library + bindings; prompt
inspector bound to the open chat (trace + ledger);
compose/macros explorer. *Verification:* launch proof —
inspector explains, for a real sent message, why each slot was
included or discarded."

## Ground truth (engine, read from source 2026-11-15)

- **Memory** (S410): `GET /memories` (q / state / kind filters;
  rows carry content, kind, state, scope, salience, stability,
  confidence, pinned, witnesses, character/chat links, recall
  counts, validity window, supersession) and
  `GET /memories/{id}` (+ sources with extractor provenance +
  the provenance graph). **There are no memory write, embedding
  or re-embedding routes in the API** — embedding is a property
  of the backend profile (R-09's Connections editor owns it).
  The Memory screen is therefore an honest browser: search,
  filter, and read with provenance; it names where embedding
  lives instead of offering decoy controls.
- **Scenarios** (P-131…P-148): library `GET /scenarios`
  (q/tags/favourites/sort/paging over enriched summaries),
  `GET/PUT/DELETE /scenarios/{id}`, `POST /scenarios` (the body
  is a scenario file), duplicate, organisation
  (`PUT …/favourite`, `PUT …/tags`, `GET /scenarios/library/tags`),
  bindings (`POST /scenarios/{id}/bind {chat_id}` — binds to an
  owned EMPTY chat and seeds its bootstrap lines; `GET
  /scenarios/bindings`, `GET /scenarios/bindings/{chat_id}`,
  `DELETE /scenarios/bindings/{chat_id}`), import/export
  (`POST /scenarios/import`, `POST /scenarios/export`
  ?format=native|voxta). A definition's authored text fields
  ride with structured sections (roles, bootstrap messages,
  contexts, initial flags/variables) that the editor carries
  verbatim, R-09/R-10 style.
- **Inspector** (P-203/P-204/P-210): `GET
  /inspector/chats/{id}` (overview), `…/events` (event census),
  `…/reasoning` (reasoning census) — plus the prompt trace
  itself: `POST /debug/prompt-inspect` with a chat id returns
  the trace — a `ledger` (context limit, reserved response,
  overhead, input budget, totals) and `slots[]`, each with
  kind, role, status, tokens, reason, trigger, provenance —
  exactly "why each slot was included or discarded", with
  `include_activation_inspection` for the lore account.
- **Tools** (S307/P-055): `GET /tools/macros` (the registry:
  name, kind, description, syntax, example), `POST
  /tools/macros/expand` (expand a text against char/user
  names), `POST /tools/compose` (compose preview from system /
  persona / history / author's note under a context budget).

## The slice

- Client: memory list/get; scenario list/get/create/update/
  delete/duplicate/favourite/tags/library-tags/bind/unbind/
  bindings/import/export; inspector overview/events/reasoning;
  prompt-inspect; macros list/expand; compose preview. Models
  `MemoryView`, `ScenarioView` (definition carried raw). No
  new engine routes.
- Qt-free logic: `memory_logic.py` (browser words, provenance
  words), `scenario_logic.py` (authored-field compose over the
  stored definition, carried-section words, binding words),
  `inspector_logic.py` (slot/ledger words, generic document
  words for the overview/events/reasoning documents),
  `compose_logic.py` (macro + compose words).
- Window: `MemoryDialog` (World ▸ Memory…), `ScenariosDialog`
  (World ▸ Scenarios…), `InspectorDialog` (Chat ▸ Prompt
  Inspector, bound to the open chat), `ComposeDialog`
  (Tools ▸ Compose & Macros…) — the last three placeholders
  graduate; Compose is a new real action.
- Tests: logic (fake transport, all four flows), live (real
  engine: memory seeded through the engine's own service and
  read back through the flow; scenario create → bind to an
  empty chat → bootstrap seeded; a real send then the trace
  explains its slots, lore slot included), window (real Qt,
  offscreen).
- Proof: `scripts/desktop_r12_proof.py` — send a real message
  in a chat with a keyworded lorebook, open the Inspector and
  read the slot explanations; create + bind a scenario from
  the window; browse memory; expand a macro; restart
  persistence for the scenario + binding.

## What was built

Four surfaces, all over existing engine routes (census
unchanged at 365 paths / 455 operations):

- **Memory** (World ▸ Memory…): the S410 browser as a
  read-only dialog — search + state/kind filters, the result
  list in words, and a detail pane carrying every stored
  field, the provenance sources (with extractor), and the
  provenance graph's size. The engine has no memory write or
  re-embedding route: the dialog says so, and names Connections
  (R-09) as the place where a profile's embedding model and
  recall switches live.
- **Scenarios** (World ▸ Scenarios…): the P-131…P-148
  library — search, the twelve authored text fields as a
  generated form composed over the stored definition (roles,
  bootstrap messages, contexts, memory-book refs, flags and
  variables carried verbatim and named on screen), tags and
  favourite, duplicate/delete, JSON import/export, binding
  to the window's open chat (the engine binds only to an
  owned EMPTY chat and seeds its bootstrap lines), unbind,
  and the full bindings list with stale bindings named, never
  hidden.
- **Inspector** (Chat ▸ Prompt Inspector…): bound to the
  open chat — the prompt trace for the chat's latest exchange
  with the budget ledger in words, one line per slot (status,
  tokens, reason, the trigger key that fired it, its
  provenance), the token-counted lore account, and the
  P-203/P-204/P-210 overview/events/reasoning documents
  rendered by a generic depth-capped words renderer. With no
  chat open it refuses honestly in the status bar.
- **Compose & Macros** (Tools ▸ Compose & Macros…): the
  P-055 macro registry in a list, an expansion playground
  (text + character/user names), and the compose preview —
  system/persona/history in, the composed messages and their
  account out in words.

Qt-free flows: `desktop/memory_logic.py`,
`desktop/scenario_logic.py`, `desktop/inspector_logic.py`,
`desktop/compose_logic.py`.

**Bug found and fixed in-slice** (by the launch proof, first
run): the inspector's slot lines dropped the lore trigger —
the engine names the matched key as a plain string
(`"trigger": "ember"`), where the renderer expected a dict —
and the lore account rendered nothing, because the engine's
account counts tokens (`tokens_used` / `by_provenance`)
where the renderer expected included/discarded totals. Both
renderers now speak the engine's real shapes, pinned by the
logic fake and the live test.

**Gates (purplelongship seat):** slice logic 6/6, live 4/4,
window 5/5; neighbours 511 passed / 1 skipped with only the
known pre-existing P-232 H1 tree-law failure; window
neighbours 30 passed; full-suite collection 6,675 (was
6,665); ruff clean. Launch proof
`scripts/desktop_r12_proof.py`: 33/33 PASS on purplelongship
and 33/33 PASS on Mimir (ARM, offscreen; Mimir's evidence
JSON was verified on-device — its transfer to the VM was
blocked by the safety layer, so the purplelongship evidence
file stands in `hidden_files/r12-evidence/`).

**Deferred venues:** purpleraider (paused by Volmarr's
order) and F15 Windows (machine unreachable — off or asleep
since 2026-11-15 ~01:30 EST; the R-09…R-12 Windows proofs
are owed when it wakes, in any case at R-17).
