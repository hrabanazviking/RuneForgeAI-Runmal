# P-064 - Part IV Gate (2026-11-07)

*The Part IV gate. The roadmap's own text for this slice is:
"P-064 Part IV gate: an ST preset pack drives Rúnmál chats with visibly identical prompt assembly (preview-diffed), sampler truth table published per backend"
Part IV's goal, in the roadmap's own words, is: "the prompt is the instrument. Players of the mirrors expect to tune it to the string — Rúnmál's composer grows the full workshop".
This record is that gate, judged only from Part IV's banked records, the battery module, and the tester's logs filed with this slice; no mirror source consulted (clean-room).*

## Gate verdict

**Part IV is COMPLETE and the gate PASSES with named pinned limitations and carried findings.** This record claims only what the battery proves.

Verdict per area: Pack PASS, Truth PASS, Composition PASS.

## S1 The gate checklist

| Gate requirement (roadmap text) | Evidence | State |
|---|---|---|
| An ST preset pack drives Runmal chats | tests/test_p064_part_iv_gate.py - A-PACK-1, A-PACK-2, A-PACK-3 | DONE HERE |
| Visibly identical prompt assembly (preview-diffed) | tests/test_p064_part_iv_gate.py - A-PACK-3 (all 11 preview keys, field by field) | DONE HERE |
| Sampler truth table published per backend | tests/test_p064_part_iv_gate.py - B-TRUTH-1..5 | DONE HERE |
| Part IV citizens compose in one prompt (the part's own slices, end to end) | tests/test_p064_part_iv_gate.py - C-COMP-1..4 | DONE HERE |
| Measured counts at the gate | S6 of this record, from the tester's logs | DONE HERE |

Part IV spans P-049..P-064, sixteen slices continuous: P-049 through P-064, no gaps. Per-slice coverage map: P-049->C-COMP-1, P-050->C-COMP-1/C-COMP-4, P-051->C-COMP-1, P-052->B-TRUTH-1..4, P-053->B-TRUTH-1..5, P-054->A-PACK-1..3, P-055->C-COMP-2, P-056->C-COMP-2, P-057->C-COMP-2, P-058->C-COMP-3, P-059->A-PACK-3/C-COMP-1..4, P-060->B-TRUTH-2/B-TRUTH-3, P-061->B-TRUTH-2/B-TRUTH-3/B-TRUTH-5, P-062->A-PACK-3/C-COMP-4, P-063->A-PACK-1..3, P-064->this gate. No roadmap text was edited.

## S2 "Passes" means, per verdict area

- **Pack PASS.** The P-021 chat fixture parses through preset interop and a P-054 bundle is built from that parsed preset with its bag, prompts and prompt_order carried verbatim; the P-063 pack carrying that bundle plus the P-021-shaped preset round-trips as a fixed point, and import stores bundle + preset value-identically. A P-062 profile built from the stored bundle drives the P-059 preview of a real character + chat identically to the directly-assembled equivalent: the two prompt_preview payloads are equal field by field across all 11 preview keys. A no-layout control preview differs exactly by the persona the pack layout disables, so the pack's effect on assembly is visible, not assumed.
- **Truth PASS.** Every Part IV control is accounted for per backend as available/greyed with reasons: the 29 canonical controls (P-052 surface + P-060 logit_bias) and the 4 structured modes (P-061) each appear exactly once per backend, 29x5 control rows + 4x5 mode rows, both audits clean. Available equals each backend's own declared set; nothing offered that no backend serves - an offered control is declared by its own backend and an available structured mode is wire-buildable while a greyed one refuses at the wire layer. Nothing is silently dropped: partition_bag over the full canonical bag splits offered+greyed == the canonical set per backend, disjoint, and a non-canonical key refuses. The table is published: the capabilities and structured-modes endpoints return the same available/greyed rows as the local matrix.
- **Composition PASS.** The Part IV citizens compose together in one prompt: layout (P-049) disables the persona block with the discard recorded as prompt_manager_disabled; instruct + context templates (P-050/P-051) are echoed as in play and the preview text is the chatml render of exactly the composed messages; macros (P-055) expand at the text layer before history so no raw macro survives; author's note (P-056) is present and active, spliced after all history at depth 0; post-history (P-057) is the chat's own text winning over the character card's, composed baseline-last; the governor (P-058) budget sections sum to the ledger total and a history cap trims with a recorded governor_section_cap action while required slots survive; a model profile switch (P-062) changes exactly what the profile owns - template framing and echo - while history, character, lorebooks, authors_note and post_history carry unchanged, and the composed message contents are identical across the switch.

## S3 The Gatehall world

The battery's shared world is Gatehall, fresh-authored in the battery module (P-005 discipline, no real user files): the character Sigrun, a chat carrying an author's note and post-history instructions, the character card carrying its own post-history text (which must lose), and the P-005 corpus chat preset as the pack's seed. The preview diff in A-PACK-3 is the gate's centre: pack-driven and direct previews are not merely similar, they are equal on every one of the 11 preview keys - messages, wire_messages, text, template_name, stop_strings, rendered_tokens, backend_key, model_id, form, available, note.

## S4 Pinned limitations - named and deliberate

The gate passes with these limitations pinned, not hidden. Each is exact in the battery module or the banked slices' own records; this section names them so no later part mistakes them for clean ground.

- **(a) The preview is the composition pipeline, not a live send.** Carried verbatim from P-059/P-062: live generation does not yet route through the composer/inspector in this tree, so the gate's identical-assembly claim is about what the composition pipeline hands a backend - the previewed prompt - never a capture of a live send. Wiring generation through the composer is a separate future slice.
- **(b) Macros are a text-layer engine, not an inspect stage.** P-055's expand_macros is exercised by the tools router and by callers on text; inspect_prompt does not expand macros itself. The gate composes macros at the layer they live - expansion on the message text before it enters the history slot - and claims nothing more.
- **(c) Pack template/layout items are validated, not stored.** On pack import, bundle and preset items are stored; instruct_template, context_template and prompt_layout items are validated_not_stored (the P-063 honesty rule, re-proven by A-PACK-1's inspect report for the stored kinds and by the P-063 battery for the rest). The gate's pack carries bundle + preset items only, and claims storage only for those.
- **(d) Available truth rows carry a reason code, not prose.** In both the P-053 control rows and the P-061 structured rows, an available row carries reason_code "supported" with an empty prose reason; greyed rows always carry prose. The gate's first battery draft asserted prose on every row and failed on exactly this; the banked design is the contract, so the gate pins code-on-every-row + prose-on-greyed. Recorded here so the shape is never mistaken for missing reasons.
- **(e) Grammar is greyed on every backend.** No backend in this tree serves grammar mode (the P-061 recorded finding, re-proven at the gate by B-TRUTH-3: grammar's state set across backends is exactly {greyed}, and the wire layer refuses it everywhere). JSON modes are the served structured surface: openai/openrouter via response_format, ollama via format.
- **(f) A profile/bundle sampler is partitioned, never silently honoured.** Sampler keys a profile's backend does not serve come back as greyed truth rows in the profile echo (P-062 partition); the gate's fake-backend profile carries the fixture bag's greyed keys (top_k and friends) as reported rows, not as honoured settings. Composition claims never include sampler enforcement - samplers ride generation, which (a) covers.

## S5 Carried limitations - findings for the keeper

- **F1 - Grammar served nowhere is CARRIED, not closed.** B-TRUTH-3 re-proves the P-061 finding: grammar is greyed on all five chat backends with reasons. Closing it needs a backend that serves a grammar wire field; no Part IV slice was scoped to add one, and this gate adds none.
- **F2 - Live generation still does not route through the composer.** Carried from P-059/P-062 (see S4 (a)). The preview-diff identity proven here binds the composition pipeline; a future generation-wiring slice inherits this gate's diff as its acceptance shape.
- **F3 - No new defect was found by this gate.** The battery's only failures during construction were the gate's own over-assertions (S4 (d)), corrected to the banked contract and recorded there. No engine fix was made in this slice; nothing was left unfixed.

## S6 Evidence at the gate

Measured counts, from the tester's logs filed with this slice (hidden_files/p064_battery.log, hidden_files/p064_neighbours.log and hidden_files/p064_fullsuite.log):

- Gate battery: 13 passed - the one P-064 behaviour module: tests/test_p064_part_iv_gate.py (13 tests). 3 + 5 + 4 + 1 = 13 behaviour tests (Area A 3, Area B 5, Area C 4, hygiene 1).
- Gate-record module: tests/test_p064_gate_record.py (10 tests) - R = 10.
- Part IV neighbours: 699 passed - the P-049..P-063 batteries plus P-021.
- Full suite: 2898 passed, 4 skipped, 0 failed.
- The P-063 baseline B was 2875 passed, 4 skipped - the forge confirmation count at the merged P-063 tree recorded in CAMPAIGN_STATE.md's P-063 banking record (= 2858 + 17, exact).
- Arithmetic: full suite == B + 13 + R - 2875 + 13 + 10 = 2898, exact. The gate adds exactly the battery plus the gate-record module, no more.

## S7 Migration note

Migration note: none. The migration head remains 0035; a gate slice needs no migration and no migration was added by this slice.

## S8 What this gate does not do

- No new engine features: this gate builds no prompt behaviour; it judges Part IV's banked slices with the Gatehall pack.
- No fixes: no defect was found in Part IV scope (S5 F3); the one battery correction was to the gate's own assertion, recorded at S4 (d).
- No live-send claim: the gate never calls a backend; its identity claim is over the composition pipeline's preview (S4 (a)).
- It edits no roadmap text and renumbers nothing; every P-number keeps its filed meaning. No roadmap edits.
- It touches no README.md, and it pushes nothing. No README touched; nothing pushed.
- Banking: this record and its pinning tests are committed on yrsa/runmal-team-02 for the keeper to bank in roadmap order.
