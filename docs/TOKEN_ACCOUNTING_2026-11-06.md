# Token accounting (P-044) — 2026-11-06

Roadmap line: *Token accounting: lore's exact prompt cost per turn, visible before sending.*

## What was built

- `src/runmal/lorebooks/accounting.py` — NEW pure module (no DB, no I/O, no migration; head stays 0032). Counts come only from runmal.tokens: count_lore_tokens is (counter or estimate_tokens) — the same function the budget pass (lorebooks/budget.py) and the composer (prompt/composer.py via prompt/slots.py slot_tokens) spend with; no second estimator. account_from_rows(rows, token_budget, counter, contents) -> LoreTokenAccount: tokens_used (included only), budget_remaining (None when unlimited; unclamped arithmetic; a zero scope budget is a real 0, never conflated with None), discarded_tokens, untriggered_tokens (None when the caller supplies no contents — honest uncounted; otherwise would-be costs counted from stored content), by_status and by_book breakdowns, count_quality EXACT iff a counter was supplied else ESTIMATED (mirrors PromptManifest.count_quality). An included row with no count and no contents raises — the account never silently under-reports spend. account_from_trace(trace) sums the trace's lore-kind slots (lore_before/lore_after) so the inspector's account reconciles with the composer's own manifest by construction; it also reports share_of_input and share_of_budget and by_provenance subtotals. Account dicts carry ids/counts/labels only, never entry content (S214 trace safety).
- `src/runmal/lorebooks/preview.py` — preview_activation gains an always-present "token_account" and an optional counter kwarg. Invariant: token_account.tokens_used == preview tokens_used == budget.tokens_used. With a counter, the account recounts every entry with that counter (the same counter compose(counter=...) would spend with) and is labeled exact; the budget pass itself still resolves with the canonical estimator, so row tokens keep the budget-pass numbers and only the account reflects the counter. Visible before sending: the preview never sends.
- `src/runmal/lorebooks/scopes.py` — layered_preview carries a token_account per layer plus a top-level aggregate (token_budget None at the top: layers hold separate budgets, never summed into a fake one); _apply_layer_budget rebuilds a present account after trimming, so scope_over_budget trims are reflected; a muted (zero-budget) layer accounts token_budget 0, tokens_used 0, budget_remaining 0.
- `src/runmal/prompt/inspect.py` — inspect_prompt's trace dict gains "lore_account" (account_from_trace over the trace it just built): lore's exact share of the composed prompt, per provenance, reconciled with the ledger by construction.

## Deliberate boundaries

- No migration (0033 not needed); no change to budget.py, composer.py, slots.py, trace.py, tokens.py.
- Would-be costs for entries that did not fire are counted from STORED content; activation may expand references ({{lore:...}}) for fired entries, so a non-fired entry's would-be is the stored-text cost, not a promise about its expanded cost. Fired entries' costs are always the budget-pass/composer numbers themselves.
- Two budgets exist (the lore budget and the composer's input budget): a preview-included entry can still be discarded by the composer (over_input_budget) — that is exactly why the inspector's lore_account is built from the composed trace, and its discarded_tokens include composer discards; the trace entries list carries status so the stages can be told apart by reason in the slots list.
- The character-book binding path (lorebooks/binding.py) calls preview_activation and tags row scope AFTER the preview returns, so its token_account entries carry scope None; the account totals are unaffected.
- PROVIDER quality never appears: provider usage exists only after a send, and this surface is before sending.

## Proof

- tests/test_p044_token_accounting.py (21 tests): pure accounting arithmetic + honesty rules, preview invariants, counter exactness vs row estimate, layered trim rebuild + muted layer, inspector reconciliation (lore_account.tokens_used == sum of trace lore included tokens, via the live prompt-inspect API), and a compose-level tight-budget discard case. 21 passed.
- Neighbour batteries (14 files: s204, s214 x2, s215 x2, p031, p034, p036, p037, p038, p039, p040, p041, p042): 496 passed. Logs: hidden_files/p044_battery.log, hidden_files/p044_neighbours.log. (The lead adds the full-suite line to hidden_files/P044_EVIDENCE.md; do not claim a full-suite count in this doc.)
