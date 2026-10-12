# Rúnmál Prompt Composer

The Prompt Composer is the only domain that turns persona, lore, memory, examples, history and instructions into model-facing messages. Other subsystems provide structured candidates; they do not secretly append text to the final prompt.

## 1. Slot model

Each candidate slot should carry:

- stable ID/type;
- role (`system`, `user`, `assistant`, provider-supported equivalent);
- content or structured message payload;
- insertion position/order/depth rule;
- priority;
- hard/soft token budget;
- source/provenance references;
- optional character/group scope;
- debug metadata safe for Prompt Trace.

## 2. Baseline order

Default conceptual order:

```text
main/system instruction
persona/card fields
memory nucleus
lorebook-before
retrieved memories
example dialogue
conversation summary + history
lorebook-after
Author's Note/depth injection
post-history instruction
```

A prompt preset may intentionally alter ordering, but changes remain explicit data rather than hidden code branches.

## 3. Response reservation

Before admitting optional prompt material:

1. determine model context limit or conservative configured limit;
2. reserve requested/allowed response tokens;
3. reserve provider/system overhead when known;
4. allocate remaining input budget among slots.

Never fill the entire context with prompt/history and then discover there is no safe response allowance.

## 4. Overflow policy

Overflow behavior is deterministic and versioned.

General policy:

- required system/safety/application contract slots stay unless request is impossible;
- preserve current persona identity/core memory according to configured priorities;
- optional lore/memory follows explicit rank/priority;
- old raw history may be replaced by existing summary before deletion;
- oldest low-priority history is trimmed before recent turns;
- discarded material and reason are visible in Prompt Trace.

Do not silently summarize during the synchronous generation path unless a summary already exists or the policy explicitly allows a pre-generation summarization step with its own failure behavior.

## 5. Lorebook candidates

Lore Service returns structured activated entries including trigger metadata, resolved insertion position, priority and content. Prompt Composer does not reimplement keyword scanning.

Recursive activation must already have terminated safely before slots arrive.

## 6. Memory candidates

Memory Service returns only witness-eligible candidates with temporal/status metadata and retrieval scores. Prompt Composer may apply budget/priority but does not bypass witness filtering or revive superseded memories by searching the vector store directly.

## 7. Character-card macros

Supported compatibility macros such as `{{char}}`, `{{user}}` and `{{original}}` are resolved by a defined rendering stage with fixture tests.

Metadata fields such as creator notes do not enter prompt slots merely because they exist in source JSON.

## 8. Token counting

Token count metadata declares quality:

- `exact` — tokenizer/provider exact for selected model;
- `provider` — provider endpoint/service result;
- `estimated` — conservative approximation.

Prompt Trace exposes the quality so a developer does not mistake an estimate for precision.

## 9. Prompt Trace

A trace is an explainability artifact, not the raw secret-bearing provider request.

Example:

```text
Generation G1832
model context: 16384
reserved response: 2048
count quality: exact

INCLUDED
system/main                 438
persona                     912
memory nucleus              327
lore/Folkvangr              611  trigger="Fólkvangr"
memory/M42                  244  rank=2 witness=eligible
history                    4120
Author's Note                82

DISCARDED
lore/Vanir Politics              over lore budget, priority 40
memory/M99                      superseded before composer
history/msg-17                  oldest low-priority trim
```

Trace should include stable IDs so the UI can link to memory/lore source details.

## 10. Trace privacy

Prompt Trace must redact/exclude:

- provider credentials/tokens;
- secret headers;
- internal filesystem secrets;
- bridge bearer tokens;
- hidden values unrelated to actual prompt explanation.

Whether full prompt content is persisted should be a deliberate privacy setting. Metadata-only trace may be safer by default.

## 11. Golden tests

Golden fixtures cover:

- basic persona chat;
- v2/v3 macro behavior;
- lore before/after/depth injection;
- memory witness eligibility;
- output-budget reservation;
- equal-priority deterministic tie-breaking;
- context overflow/history summarization behavior;
- unsupported/estimated token counter;
- group speaker persona selection;
- trace secret-redaction canary.

## 12. Invariant

No extension/backend/lore/memory module gets a side door to mutate the final prompt after the Composer's trace/budget decision. Extensions participate by registering typed slots/hooks that remain visible to the same budgeting and trace system.