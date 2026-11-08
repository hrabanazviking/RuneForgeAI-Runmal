"""Chat service + API (S107) + chat file interop (P-020)
+ branches (P-066)
+ continue & impersonate (P-069).
+ chat search (P-072)
+ data bank (P-074).

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
from runmal.chats.continue_impersonate import (
    GenerationFailedError,
    accept_impersonate,
    build_continue_messages,
    build_impersonate_messages,
    continue_chat,
    discard_impersonate,
    impersonate_draft,
    resolve_continue_mode,
)
from runmal.chats.databank import (
    DataBankError,
    accounting_to_dict,
    attach_document,
    detach_document,
    document_to_dict,
    get_budget,
    get_document,
    list_documents,
    load_prompt_selection,
    remove_chat_databank,
    render_document,
    select_documents,
    set_budget,
    slots_for_selection,
    update_document,
)
from runmal.chats import provenance as message_provenance
from runmal.chats.search import (
    SearchError,
    make_snippet,
    rank_hits,
    score_fulltext,
    search_chats,
    tokenise,
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
from runmal.chats.liveimport import (
    EVENT_CHAT_IMPORTED,
    LiveImportReport,
    import_chat_file,
    materialise_import,
    plan_import,
)
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
    "update_document",
    "slots_for_selection",
    "set_budget",
    "select_documents",
    "render_document",
    "remove_chat_databank",
    "load_prompt_selection",
    "list_documents",
    "get_document",
    "get_budget",
    "document_to_dict",
    "detach_document",
    "attach_document",
    "accounting_to_dict",
    "DataBankError",
    "GenerationFailedError",
    "accept_impersonate",
    "build_continue_messages",
    "build_impersonate_messages",
    "continue_chat",
    "discard_impersonate",
    "impersonate_draft",
    "resolve_continue_mode",
    "message_provenance",
    "SearchError",
    "make_snippet",
    "rank_hits",
    "score_fulltext",
    "search_chats",
    "tokenise",
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
    "EVENT_CHAT_IMPORTED",
    "LiveImportReport",
    "import_chat_file",
    "materialise_import",
    "parse_chat_file",
    "plan_import",
    "parse_chat_jsonl",
    "project_messages",
    "resolve_character",
    "to_service_document",
]
