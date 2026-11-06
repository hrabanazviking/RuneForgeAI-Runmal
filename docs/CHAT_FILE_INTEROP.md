# P-020 — Chat File Interop (2026-10-31)

*Part II (Cards & Content Interop): ST-shaped chat JSONL in/out
plus a bridge to Runmal's live chat document shape, with full
swipe, metadata and unknown-field fidelity. Acceptance in
`tests/test_p020_chat_import.py`, `tests/test_p020_chat_export.py`
and `tests/test_p020_chat_bridge.py`.*

## The measured gap this slice closes

On entry there was **no chat file importer or exporter at all**:
P-005's corpus pinned `chat_st.jsonl` as well-formed JSONL and
named P-020 as its home, and the corpus manifest stated outright
that no chat importer existed yet. A chat exported from the
mirror could not be brought into Runmal, and a Runmal chat could
not be written out in the exchanged shape, without hand work.

## What was built

`src/runmal/chats/filemodels.py` — the typed contract: 
`ChatFileErrorKind` / `ChatFileParseError`, per-line `LineIssue`
and `ImportReport` (issue-kind constants + `ISSUE_SEVERITY`),
`ImportedMessage`, `ImportedChat` (with the `branch_link`
property over `BRANCH_LINK_KEYS`), and `ImportResult`. No I/O.

`src/runmal/chats/fileimport.py` — `parse_chat_jsonl` /
`parse_chat_file`: defensive JSONL import (header line plus one
message per line) and Runmal native (S111) document import.
Whole-input refusals are typed errors; per-line problems are
reported, repaired deterministically where the contract allows,
or refused line by line — never a bare exception.

`src/runmal/chats/fileexport.py` — `export_chat_jsonl`: export
starts from each line's `raw` mapping and overlays the normalized
fields, so unknown-but-valid fields survive verbatim (INV-009).
Re-export is a fixed point, pinned byte-for-byte in the tests.

`src/runmal/chats/filebridge.py` — glue to the live service,
importing only `.filemodels` and using plain dicts in/out:
`to_service_document` (the S111 shape, caller-supplied
`exported_at`, never a clock), `project_messages`,
`loss_report`, `field_diff`, and `resolve_character`
(exact-name lookup only, never a guess). The package surface is
re-exported from `runmal.chats`.

## Field mapping

| File field | Typed field | Live projection | Notes |
|---|---|---|---|
| header `user_name` | `ImportedChat.user_name` | `chat.user_name` | verbatim |
| header `character_name` | `ImportedChat.character_name` | `chat.character_name` | resolved by exact name only |
| header `create_date` | `create_date_raw` / `create_date_parsed` | — | ST spellings parsed; raw kept |
| header `chat_metadata` | `ImportedChat.chat_metadata` | — (loss-reported) | verbatim; branch keys via `branch_link` |
| header unknowns | `ImportedChat.header_raw` | — | survive export verbatim |
| `mes` | `ImportedMessage.content` | `content` | authoritative; wins on MES_SWIPE_MISMATCH |
| `name` | `speaker_name` | `speaker_name` | verbatim |
| `is_user` / `is_system` | `role` / `is_system` | `role` | role in `chats.service.VALID_ROLES` |
| `send_date` | `send_date_raw` / `send_date_parsed` | — (loss-reported) | no full-fidelity live column |
| `swipes` / `swipe_id` | `swipes` / `swipe_id` | active text only | alternates loss-reported by count |
| `swipe_info` | `swipe_info` | — | carried verbatim in the file model |
| `extra` | `extra` | — (loss-reported) | provenance, carried in the file model |
| message unknowns | `ImportedMessage.raw` | — | survive export verbatim |

`field_diff(a, b)` compares the typed fields and the
`header_raw` / `raw` mappings recursively and returns dotted
paths (for example `messages[2].swipes[1]`,
`header.chat_metadata.x`); an empty list is field-clean, which
is how the corpus round trip `parse(export(parse(fixture)))`
is pinned.

## Not in this slice

No live-service persistence wiring (no router or service
changes, no database schema): the bridge produces the service
document shape and names every loss in `loss_report`, and the
import into a live chat stays a later slice's work. Character
creation from a chat file, branch/checkpoint materialization
beyond carrying the linkage keys, and swipe editing in the live
UI are likewise not in this slice.

## Clean-room basis

Shapes from P-002's census of public documentation, P-005's
authored corpus fixture (`tests/fixtures/interop/chat_st.jsonl`),
and public JSONL format documentation. No mirror source code
was read; no chat file was downloaded.
