"""Typed contract for chat-file interop (P-020).

The ST-shaped chat file is JSONL: a metadata header line, then
one message object per line carrying `mes`, `swipes` and friends.
This module is the *contract* every other P-020 module builds
on — the typed import result, the per-line issue report, and
the typed parse error. It performs no I/O and imports nothing
from `chats.service`, so importers, exporters and the bridge
can all depend on it without a cycle.

Clean-room basis: the shape is as recorded in P-002's census
of SillyTavern's official public documentation and as carried
by P-005's authored corpus fixture (`chat_st.jsonl`), plus
public JSONL format documentation. No mirror source code
was read.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ChatFileErrorKind(StrEnum):
    """Why a whole chat-file import was refused."""

    INPUT_TOO_LARGE = "input_too_large"
    NOT_UTF8 = "not_utf8"
    EMPTY_INPUT = "empty_input"
    NOT_JSONL = "not_jsonl"
    NO_VALID_RECORDS = "no_valid_records"


class ChatFileParseError(ValueError):
    """A chat-file import failed for a typed, testable reason.

    `report` carries the partial `ImportReport` when the
    failure was reached after line-by-line parsing (notably
    `NO_VALID_RECORDS`); it is `None` for whole-input refusals
    detected before any line was read.
    """

    def __init__(
        self,
        kind: ChatFileErrorKind,
        message: str,
        report: ImportReport | None = None,
    ) -> None:
        self.kind = kind
        self.report = report
        super().__init__(message)


#: Per-line issue kinds (plain strings; the report is data,
#: not an exception hierarchy).
INVALID_JSON = "invalid_json"
NOT_AN_OBJECT = "not_an_object"
MISSING_MES = "missing_mes"
MES_NOT_STRING = "mes_not_string"
LINE_TOO_LARGE = "line_too_large"
SWIPES_MALFORMED = "swipes_malformed"
SWIPE_INFO_MALFORMED = "swipe_info_malformed"
SWIPE_ID_OUT_OF_RANGE = "swipe_id_out_of_range"
MES_SWIPE_MISMATCH = "mes_swipe_mismatch"
INFERRED_ROLE = "inferred_role"
SEND_DATE_UNPARSED = "send_date_unparsed"
HEADER_MISSING = "header_missing"
EXTRA_NOT_OBJECT = "extra_not_object"

#: Severity per issue kind: `error` refuses the line, `repair`
#: means the line was imported after a deterministic repair,
#: `warning` means the line was imported with a noted loss or
#: inference, `info` is purely informational.
ISSUE_SEVERITY: dict[str, str] = {
    INVALID_JSON: "error",
    NOT_AN_OBJECT: "error",
    MISSING_MES: "error",
    MES_NOT_STRING: "error",
    LINE_TOO_LARGE: "error",
    SWIPE_ID_OUT_OF_RANGE: "repair",
    SWIPES_MALFORMED: "warning",
    SWIPE_INFO_MALFORMED: "warning",
    MES_SWIPE_MISMATCH: "warning",
    INFERRED_ROLE: "warning",
    SEND_DATE_UNPARSED: "warning",
    EXTRA_NOT_OBJECT: "warning",
    HEADER_MISSING: "info",
}


@dataclass(frozen=True)
class LineIssue:
    """One observed problem (or repair) on one input line."""

    line_no: int
    kind: str
    detail: str
    excerpt: str = ""


@dataclass
class ImportReport:
    """Line-by-line account of an import: what landed, what
    was refused, what was repaired, and every issue seen."""

    total_lines: int = 0
    blank_lines: int = 0
    header_present: bool = False
    header_line_no: int | None = None
    imported_messages: int = 0
    refused_lines: int = 0
    repaired_lines: int = 0
    bom_stripped: bool = False
    chat_metadata_keys: list[str] = field(default_factory=list)
    issues: list[LineIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when no line was refused."""
        return self.refused_lines == 0


@dataclass
class ImportedMessage:
    """One message normalized from a chat-file line.

    `content` is the line's `mes` and is authoritative (see
    `filebridge.project_messages`). `swipes` carries the
    line's swipe array verbatim when one was present
    (`has_explicit_swipes`); on a MES_SWIPE_MISMATCH line the
    active swipe text differs from `content` and both are
    kept. `raw` always holds the complete original mapping
    so unknown-but-valid fields survive (INV-009).
    """

    role: str
    content: str
    speaker_name: str = ""
    is_system: bool = False
    send_date_raw: str | None = None
    send_date_parsed: datetime | None = None
    swipes: list[str] = field(default_factory=list)
    swipe_id: int = 0
    has_explicit_swipes: bool = False
    swipe_info: list = field(default_factory=list)
    has_swipe_info: bool = False
    extra: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


#: chat_metadata keys that link a chat to a parent chat (a
#: branch / checkpoint relationship in the mirror's shape).
BRANCH_LINK_KEYS = (
    "parent_chat",
    "parent_chat_id",
    "branch_of",
    "branch_point",
    "checkpoint_of",
    "main_chat",
)


@dataclass
class ImportedChat:
    """A whole chat normalized from a chat file.

    `chat_metadata` is the header's metadata mapping verbatim;
    `header_raw` is the complete header line mapping, so any
    header field this contract does not type still survives.
    """

    user_name: str = ""
    character_name: str = ""
    create_date_raw: str | None = None
    create_date_parsed: datetime | None = None
    chat_metadata: dict = field(default_factory=dict)
    header_raw: dict = field(default_factory=dict)
    messages: list[ImportedMessage] = field(default_factory=list)
    source_shape: str = "st-jsonl-header"

    @property
    def branch_link(self) -> dict:
        """The branch/checkpoint linkage this chat declares,
        deep-copied out of `chat_metadata` ({} when none)."""
        return {
            key: deepcopy(self.chat_metadata[key])
            for key in BRANCH_LINK_KEYS
            if key in self.chat_metadata
        }


@dataclass
class ImportResult:
    """A successful import: the chat plus its report."""

    chat: ImportedChat
    report: ImportReport
