"""Chat service + API (S107) + chat file interop (P-020)
+ branches (P-066).

The file-interop surface parses ST-shaped chat JSONL and
Runmal native export documents into the typed contract in
`filemodels`, exports imported chats back to ST-shaped JSONL,
and bridges imported chats to the live service document shape.
Clean-room basis: P-002 census of public documentation, P-005
authored corpus fixture, public JSONL format documentation.
"""

from runmal.chats.branches import (
    branch_info,
    fork_chat,
    list_branch_family,
    merge_back,
    rename_branch,
)
from runmal.chats.filebridge import (
    field_diff,
    loss_report,
    project_messages,
    resolve_character,
    to_service_document,
)
from runmal.chats.fileexport import export_chat_jsonl
from runmal.chats.fileimport import parse_chat_file, parse_chat_jsonl
from runmal.chats.filemodels import (
    ChatFileErrorKind,
    ChatFileParseError,
    ImportedChat,
    ImportedMessage,
    ImportReport,
    ImportResult,
    LineIssue,
)

__all__ = [
    "branch_info",
    "fork_chat",
    "list_branch_family",
    "merge_back",
    "rename_branch",
    "ChatFileErrorKind",
    "ChatFileParseError",
    "ImportReport",
    "ImportResult",
    "ImportedChat",
    "ImportedMessage",
    "LineIssue",
    "export_chat_jsonl",
    "field_diff",
    "loss_report",
    "parse_chat_file",
    "parse_chat_jsonl",
    "project_messages",
    "resolve_character",
    "to_service_document",
]
