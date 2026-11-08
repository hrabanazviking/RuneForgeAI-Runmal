# P-107 - Voice Rendered Confidence Markings (Part VII, Voice the Voxta Way)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md) gives Part VII only its part line - "VII | Voice, the Voxta Way | P-101..P-116" - and no per-slice entries. This slice's scope is therefore DERIVED, not roadmap-verbatim, from in-tree sources only: the Voxta census row VX-11 (the UI shows speech-to-text confidence markings), the P-105 slice doc (docs/VOICE_MISHEARING_2026-11-07.md section 4: confidence markings are data on the HTTP surface, no UI renders them, and VX-11's remaining surface - rendered markings, mid-dialogue detection - stays open on top of the truth layer), and the P-106 design (hidden on team-03, in flight ahead of this slice: the projection mark is a receipt, not a rendering; no UI shows it in that slice). The keeper reviews this derived scope at banking.

The gap, exactly: P-105 persisted per-word STT confidence and built detection + replacement views; P-106 carries the facts into projected-message provenance. But a person reading the chat thread - the surface VX-11 names - sees a doubtful transcript identical to a certain one. The session store keeps the truth; the thread, its human shadow, hides it. P-107 is the rendering.

The other named open items were weighed and NOT taken:
- Mid-dialogue repeat request (P-105's other remaining surface): the character asking is dialogue, and the live responder is still P-102's honest-unavailable seam; P-105 records that fabricating a repeat request would cross it. Nothing banked since changes that judgement.
- VX-12 (affects/prosody): no affect seam exists in any TTS backend (VoiceInfo carries no affect field, no backend consumes one); it needs its own engine design.
- VX-13 (narrator voice): chats have no narration taxonomy consumer (VX-41 types are not chat citizens), so a narrator voice would have nothing lawful to read.
- L3 (P-091 citizen registration): deliberate host-explicit law, re-affirmed by P-101 through P-105. No new evidence overturns it; not reopened.
- The live responder seam: previously judged larger than one slice; no part taken - a partial responder would fabricate replies.
- Back-marking already-projected turns: P-106 declined it on the P-075 law (a landed message's provenance is its production receipt); this slice does not contradict a banking slice's recorded law.
- P-104's by-design items (in-process hosts call the service function; live start does not back-project): stated as design, not defects.

Base: fc4ea07 (P-105 banking record; P-106 banks before this slice in roadmap order and reconciles at banking). Migration: NONE - head stays 0041.

## 1. What landed

- src/runmal/voice/markings.py (new) - the pure marking view for one landed message: voice_origin reads the P-103 provenance link (recorded, via=voice_session, side=transcript, session id + turn number) off the message's provenance active_view; message_marking resolves session + turn in the P-101 store and returns P-105's own turn_mishearing view trimmed to rendering facts, plus the evidence_available flag; markings_for_messages attaches the view additively to qualifying message dicts.
- src/runmal/chats/router.py - the thread surfaces (GET /chats/{id} history payload; GET /chats/{id}/messages in both its bare-list and paged shapes) run their message dicts through the attach helper with a VoiceSessionStore + the P-105 ReplacementStore on the app data dir. Additive key only; the helper is tolerant by design - any voice-store failure leaves dicts unmarked rather than bricking the thread.
- src/runmal/web/static/renderer.js - renderMarkedTranscript(text, lowWords), a pure S302-discipline function: escape-first through renderMarkdownLite, low-confidence word cores wrapped in span.stt-low with punctuation outside the span (the P-105 token law, mirrored).
- src/runmal/web/static/app.js - the thread renders a message carrying voice_marking.has_confidence_evidence through renderMarkedTranscript and appends a badge (Heard with doubt - N unclear word(s), with the P-105 suggested hearing as text when the lexicon applied; Heard clearly; or the honest no-evidence / evidence-unavailable lines).
- src/runmal/web/static/style.css - .stt-low (dotted underline carries the signal, tint assists - never colour alone) and .voice-marking.
- Battery: tests/test_p107_voice_markings.py (12 tests).

## 2. The truth law

- One truth source: P-105 turn_mishearing. The threshold and bands are imported from runmal.voice.mishearing, never redeclared; probabilities are the backend's persisted estimates, never recomputed. This rendering and P-106's provenance receipt read the same persisted evidence and cannot disagree.
- No evidence is a fact, not a zero: a turn with no recorded words renders has_confidence_evidence False with NO low spans and the no-evidence badge line - never marked clear, never marked doubtful. A voice transcript whose session or turn can no longer be resolved gets the gap marking (evidence_available False) - a gap recorded, never a silent clean bill.
- Content law UNCHANGED: the stored message text is the verbatim transcript; the suggested hearing appears only inside the badge as text, never as message content and never rendered as markup.
- Response side untouched: the marking concerns what the ear heard of the USER; response messages carry no marking.

## 3. HTTP surface

No new road. GET /api/v1/chats/{id} and GET /api/v1/chats/{id}/messages (bare and paged) gain one additive key, voice_marking, ONLY on landed voice-transcript messages: {voice_session_id, voice_turn_no, evidence_available, has_confidence_evidence, needs_repeat, threshold, word_count, low_confidence_words, low_confidence_count, min_probability, mean_probability, words: [{text, probability, band}], suggested_text, replacements_applied}. Every founding field is unchanged; chats without voice messages are byte-identical in shape.

## 4. Honest limitations

- The badge and spans render in the founding web thread (app.js renderThread). Other consumers of the messages API receive the same voice_marking data and may render it or not; no other client is wired in this slice.
- Word alignment is token-based: a word core is marked when its punctuation-stripped lower-case form is in the low set, and a repeated word is marked at every occurrence (the evidence is per-word; the render is per-token-type - stated plainly, not hidden). A word fused into markup-like text ("<b>lift</b>") is one token whose core is not the word, so it stays unmarked - and escaped.
- Mid-dialogue repeat requests stay open (the responder seam, above). VX-12 and VX-13 stay open (above).
- Streaming (in-flight) messages are not marked; markings attach to landed history, where the evidence lives. Already-projected turns DO receive markings at read time, because the marking is a read-time view over the session store, not a rewrite of the landed message or its provenance receipt (P-106's no-back-marking law is about the receipt, and it stands untouched).

## 5. Battery

tests/test_p107_voice_markings.py - 12 tests: the pure views (non-voice / unrecorded / malformed None, response side None, resolved marking equal to P-105's own facts, lexicon suggestion, the gap marking on missing session and missing turn, the no-evidence turn), the attach helper (only qualifying dicts gain the key), the HTTP flow (project a worded session through the P-103 road; GET chat + both GET messages shapes carry the marking on the transcript message only, stored content verbatim, suggestion from the live lexicon road; a voiceless chat carries none), the renderer under node (low word wrapped, punctuation outside the span, script input escaped first, no low words renders plain), the CSS token pin (below), and the 0041 migration pin. One defect was found and fixed in-slice: the first .stt-low rule carried a raw rgba tint, breaking the S301 design-token law (test_no_raw_colors_outside_token_blocks failed on the first full-suite run); the tint is now the --stt-low-tint token defined in every theme token block, the rule references the token, and a battery test pins it. Neighbour and full-suite counts are recorded from the run logs in hidden_files/P107_EVIDENCE.md, never estimated here.
