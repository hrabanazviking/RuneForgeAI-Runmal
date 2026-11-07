# P-090 — Regex Scripts (Part VI, Extensions Row)

Roadmap line: *Regex scripts: ST-shaped find/replace rules
(importable format) applied at declared stages, with a safe
regex dialect and timeout discipline.*

Clean-room: built from the roadmap line and Rúnmál's own
contracts only — the P-081 Plugin API v1 citizen pattern
(banked by P-084/P-085/P-087/P-088), the P-082 sandbox
policy, and the P-089 durable per-user file-store idiom.
Base a986a13 (P-088 banking record), migration head 0041.
**No migration taken.** The keeper banks P-089 before this
slice and reconciles the delta.

## What landed

`src/runmal/plugins/regex_scripts.py` — a first-class
P-081 citizen plugin, id `runmal.regex-scripts`:

- capabilities `chat.events`, `prompt.hooks`, `ui.slots`;
  permissions `chat.read`, `prompt.inject`, `prompt.modify`,
  `ui.contribute` (`chat.write` NOT declared — reserved in
  v1, and this citizen never writes chat rows);
- events `chat.created` / `chat.deleted`, both a deliberate
  no-op: chat deletion never deletes user-owned scripts
  (the P-089 stance);
- one messages-stage prompt hook `regex-scripts-messages`
  (priority 90) applying the `prompt_assembly` stage;
- one UI contribution `regex-scripts-panel` in
  `settings.panel`.

`build_registry` / `create_app` are unchanged — P-081's
battery pins the empty boot registry. The citizen registers
only through its own `register_plugin` from trusted code.
No HTTP routes / UI ship in this slice (the P-088
precedent); the other declared stages apply through
explicit `apply_scripts` calls only, and no such caller
ships.

## The importable format — ST-shaped, strict

A script's canonical keys are exactly `id, name, pattern,
flags, replace_string, trim_strings, stages, enabled,
scope, chat_id, created_at, updated_at`. The importer
additionally accepts the ST-shaped aliases `scriptName`,
`findRegex` (including the `/body/flags` slash form, with
`\/` unescaped and `g`/`u` dropped — substitution is
global by construction), `replaceString`, `trimStrings`,
`placement`, `disabled` (inverted), and the
`markdownOnly` / `promptOnly` filters. Placement decodes
Rúnmál's stage names plus `prompt -> prompt_assembly` and
`markdown` / `md_display -> display`, and the integer
codes `1/2/3`; numeric strings are refused. Strictness is
the contract: unknown keys refuse, alias + canonical
values that disagree refuse (`conflicting_alias`),
`disabled` + `enabled` that disagree refuse
(`contradictory_field`), and nothing is type-coerced.
Flags are a subset of `ims`, stored sorted in `ims` order.
Scopes are `user` (always selected) and `chat` (selected
only for its own chat, UUID-bound).

## Safe dialect + timeout discipline

`validate_pattern` runs a single-pass token scan before
`re.compile`: backreferences (`\1`–`\9`, `(?P=name)`),
lookbehind, non-allowlisted `(?...)` constructs
(atomic groups, conditionals, comments, .NET-style named
groups, flags outside `ims`), nested quantifiers (a
quantifier on a group whose body contains a quantifier at
any depth, or on an already-quantified atom), duplicate
group names, and quantifier bounds over 1000 all refuse
with typed codes. Brace quantifiers are recognised in
every form Python treats as a repeat — `{m}`, `{m,}`,
`{m,n}`, `{,n}` and `{,}` (see "Defects" below).

The scan is a heuristic first defence, not a proof:
`(a|aa)+$` passes it and is caught only by the timeout.
Every rule's substitution runs in a forked child process
with a per-rule budget (default 0.25s, caller-capped at
1.0s); on expiry the child is terminated, everything it
produced is discarded, the row reports `timed_out`, and
later rules run unaffected. If a child cannot be started
at all, the rule falls back to an in-process substitution
with a cooperative per-match deadline check, which cannot
interrupt a single catastrophic match — stated plainly,
not hidden. `apply_scripts` is pure and returns one row
per script (`applied`, `no_match`, `skipped_disabled`,
`skipped_wrong_stage`, `refused_unsafe`, `timed_out`,
`refused_output_growth`, `failed`); a result over
262,144 chars is discarded whole, and one rule's failure
never stops the next.

Replacements are hand-parsed and expanded through a
function passed to `Pattern.sub` (never Python template
strings): `$$`, `$0` / `$&`, `$<name>`, `${name}`,
`${digits}`, and `$digits` as one maximal digit run are
validated against the compiled pattern at import; unknown
groups and malformed substitutions refuse. Trim strings
are removed from each match's substituted text, in order.

## Store

The P-089 idiom: one JSON document per user at
`data_dir()/regex_scripts/<user_id>.json` (user id
UUID-validated and normalised before any path is built),
atomic save (tmp sibling, chmod 0o600 best-effort,
`os.replace`), corrupt stores raise
`RegexScriptStoreCorruptError` and are never silently
reset. CRUD plus `import_scripts` (per-row independent,
one atomic save iff at least one row is accepted, the
whole call refused past 500 rows) and `export_scripts`
(canonical dicts — the round-trip road). Caps: 200
scripts per user, 512-char patterns, 4,096-char
replacements, 32 trim strings.

## Sandbox stance (P-082)

Only v1 surface permissions are declared, so the derived
resource grant set is empty (`sandbox_grants()` returns
it; the battery pins it). The module opens no socket and
touches no network; the only process it spawns is the
per-rule timeout child, which is host machinery, not a
plugin resource grant.

## Defects found / fixed in-slice

Two safe-dialect holes in the built implementation,
found by the finisher's review and pinned by the battery:

- **Brace-quantifier bypass.** The scanner's brace regex
  required a leading digit, but Python treats `{,n}` as
  `{0,n}` and `{,}` as `{0,}` — so `a{,2000}` escaped the
  1000-bound check and `(x{,3})+` escaped the
  nested-quantifier check. The scanner now recognises
  every brace form Python treats as a repeat; `{}` with
  neither digits nor a comma stays a literal, as in
  Python.
- **Duplicate group names** were caught only by the
  `re.compile` fallback (`invalid_pattern`); the design
  requires names unique at the scanner, so a duplicate
  now refuses in the scan as
  `unsupported_group_construct`.

## Limitations

- Process spawn per rule is the cost of the timeout
  guarantee; the budget is per rule, not per call.
- No cache: the hook re-reads the store on each assembly.
- ST-shaped, not ST-compatible: unknown ST fields are
  refused, placement codes are Rúnmál's own, and trim
  semantics are as defined here.
- Single-process file store; last-writer-wins across
  processes (the P-089 standing limitation).

## Verification

Battery `tests/test_p090_regex_scripts.py` plus plugin
neighbours and the full suite — counts in
`hidden_files/P090_EVIDENCE.md`.
