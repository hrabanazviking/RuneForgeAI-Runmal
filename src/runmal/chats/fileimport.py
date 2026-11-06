"""Chat file import: ST-shaped JSONL and Runmal native exports (P-020).

Clean-room basis: the ST JSONL chat shape (a header record followed
by one message record per line, with ``mes`` / ``is_user`` /
``swipes`` / ``swipe_id`` / ``swipe_info`` / ``extra`` fields) and
the date spellings are as recorded in P-002's census from public
documentation and as carried by P-005's authored corpus fixture.
The native shape is Runmal's own S111 export document. No mirror
source code was read.

Import is pure: it never touches the DB, never calls
``chats.service``, and never logs message content. Issue details
carry human reasons only; the one place raw text rides along is the
``excerpt`` of an INVALID_JSON issue, as the contract allows.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

from runmal.safety import SafetyError, safe_json_loads
from .filemodels import (
    EXTRA_NOT_OBJECT,
    HEADER_MISSING,
    INFERRED_ROLE,
    INVALID_JSON,
    ISSUE_SEVERITY,
    LINE_TOO_LARGE,
    MES_NOT_STRING,
    MES_SWIPE_MISMATCH,
    MISSING_MES,
    NOT_AN_OBJECT,
    SEND_DATE_UNPARSED,
    SWIPE_ID_OUT_OF_RANGE,
    SWIPE_INFO_MALFORMED,
    SWIPES_MALFORMED,
    ChatFileErrorKind,
    ChatFileParseError,
    ImportedChat,
    ImportedMessage,
    ImportReport,
    ImportResult,
    LineIssue,
)

MAX_CHAT_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 16 * 1024 * 1024
MAX_LINES = 1_000_000

_ST_FORMATS = (
    "%Y-%m-%d @%Hh %Mm %Ss %fms",
    "%Y-%m-%d @%Hh %Mm %Ss",
)
_NATIVE_ROLES = frozenset({"user", "assistant", "system"})
_NATIVE_FORMAT = "runmal-chat-export"
# Kinds that mean "the line was kept, with a repair applied". Counted
# as repairs even if ISSUE_SEVERITY spells one of them a warning.
_REPAIR_KINDS = frozenset(
    {SWIPES_MALFORMED, SWIPE_INFO_MALFORMED, SWIPE_ID_OUT_OF_RANGE}
)

__all__ = [
    "MAX_CHAT_BYTES",
    "MAX_LINE_BYTES",
    "MAX_LINES",
    "parse_chat_file",
    "parse_chat_jsonl",
]


def _decode(data: bytes | str) -> tuple[str, bool]:
    """Apply the fatal gates: size, UTF-8, BOM, emptiness."""
    if isinstance(data, bytes):
        if len(data) > MAX_CHAT_BYTES:
            raise ChatFileParseError(
                ChatFileErrorKind.INPUT_TOO_LARGE,
                f"chat file is {len(data)} bytes, exceeding the "
                f"{MAX_CHAT_BYTES}-byte cap",
            )
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ChatFileParseError(
                ChatFileErrorKind.NOT_UTF8,
                "chat file is not valid UTF-8 text",
            ) from exc
    elif isinstance(data, str):
        if len(data.encode("utf-8")) > MAX_CHAT_BYTES:
            raise ChatFileParseError(
                ChatFileErrorKind.INPUT_TOO_LARGE,
                f"chat file exceeds the {MAX_CHAT_BYTES}-byte cap",
            )
        text = data
    else:
        raise TypeError(
            f"chat data must be bytes or str, got {type(data).__name__}"
        )
    bom_stripped = False
    if text.startswith("\ufeff"):
        text = text[1:]
        bom_stripped = True
    if not text.strip():
        raise ChatFileParseError(
            ChatFileErrorKind.EMPTY_INPUT, "chat file is empty"
        )
    return text, bom_stripped


def _parse_date_string(value: str) -> datetime | None:
    """Parse one date string in the contracted order; naive result."""
    candidate = value.strip()
    if not candidate:
        return None
    for fmt in _ST_FORMATS:
        try:
            return datetime.strptime(candidate, fmt)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _date_fields(value: object) -> tuple[str | None, datetime | None, bool]:
    """Split a raw date value into (raw, parsed, unparsed_flag).

    Strings keep their verbatim raw form; numeric epochs parse only
    (raw stays None); absent/None is neither raw nor an error.
    """
    if value is None:
        return None, None, False
    if isinstance(value, bool):
        return None, None, True
    if isinstance(value, (int, float)):
        epoch = float(value)
        seconds = epoch / 1000.0 if abs(epoch) >= 1e12 else epoch
        try:
            parsed = datetime.fromtimestamp(seconds, tz=UTC).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None, None, True
        return None, parsed, False
    if isinstance(value, str):
        parsed = _parse_date_string(value)
        return value, parsed, parsed is None
    return None, None, True


def _coerce_swipe_id(value: object) -> int:
    """Coerce a swipe_id: real ints as-is, integral floats and
    numeric strings converted, everything else (incl. bools) -> 0."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else 0
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError:
            pass
        try:
            number = float(text)
        except ValueError:
            return 0
        return int(number) if number.is_integer() else 0
    return 0


def _convert_message(
    obj: dict,
    line_no: int,
    header_user_name: str,
    issues: list[LineIssue],
) -> ImportedMessage | None:
    """Map one message record; None means the line was refused."""
    if "mes" not in obj:
        issues.append(
            LineIssue(
                line_no=line_no,
                kind=MISSING_MES,
                detail="message record has no 'mes' field",
            )
        )
        return None
    mes = obj["mes"]
    if not isinstance(mes, str):
        issues.append(
            LineIssue(
                line_no=line_no,
                kind=MES_NOT_STRING,
                detail=f"'mes' must be a string, got {type(mes).__name__}",
            )
        )
        return None
    content = mes
    name_value = obj.get("name")
    speaker_name = name_value if isinstance(name_value, str) else ""
    is_system = bool(obj.get("is_system")) if "is_system" in obj else False
    if "is_user" in obj:
        if obj["is_user"]:
            role = "user"
        elif is_system:
            role = "system"
        else:
            role = "assistant"
    else:
        if speaker_name and speaker_name == header_user_name:
            role = "user"
        else:
            role = "assistant"
        issues.append(
            LineIssue(
                line_no=line_no,
                kind=INFERRED_ROLE,
                detail="'is_user' absent; role inferred from speaker name",
            )
        )
    send_date_raw: str | None = None
    send_date_parsed: datetime | None = None
    if "send_date" in obj:
        send_date_raw, send_date_parsed, unparsed = _date_fields(obj["send_date"])
        if unparsed:
            issues.append(
                LineIssue(
                    line_no=line_no,
                    kind=SEND_DATE_UNPARSED,
                    detail="'send_date' could not be parsed as a date",
                )
            )
    has_explicit_swipes = "swipes" in obj
    swipes: list[str] = [content]
    if has_explicit_swipes:
        raw_swipes = obj["swipes"]
        if isinstance(raw_swipes, list):
            kept = [item for item in raw_swipes if isinstance(item, str)]
            swipes = kept if kept else [content]
        else:
            issues.append(
                LineIssue(
                    line_no=line_no,
                    kind=SWIPES_MALFORMED,
                    detail="'swipes' is not a list; replaced with the "
                    "message text",
                )
            )
            swipes = [content]
    swipe_id = _coerce_swipe_id(obj["swipe_id"]) if "swipe_id" in obj else 0
    if swipe_id < 0 or swipe_id >= len(swipes):
        clamped = min(max(swipe_id, 0), len(swipes) - 1)
        issues.append(
            LineIssue(
                line_no=line_no,
                kind=SWIPE_ID_OUT_OF_RANGE,
                detail=f"'swipe_id' {swipe_id} is out of range for "
                f"{len(swipes)} swipe(s); clamped to {clamped}",
            )
        )
        swipe_id = clamped
    if has_explicit_swipes and swipes[swipe_id] != content:
        issues.append(
            LineIssue(
                line_no=line_no,
                kind=MES_SWIPE_MISMATCH,
                detail="'mes' differs from 'swipes[swipe_id]'; both kept "
                "as written",
            )
        )
    has_swipe_info = "swipe_info" in obj
    swipe_info: list = []
    if has_swipe_info:
        raw_info = obj["swipe_info"]
        if isinstance(raw_info, list):
            swipe_info = copy.deepcopy(raw_info)
        else:
            issues.append(
                LineIssue(
                    line_no=line_no,
                    kind=SWIPE_INFO_MALFORMED,
                    detail="'swipe_info' is not a list; treated as empty",
                )
            )
            swipe_info = []
    extra: dict = {}
    if "extra" in obj:
        raw_extra = obj["extra"]
        if isinstance(raw_extra, dict):
            extra = copy.deepcopy(raw_extra)
        else:
            issues.append(
                LineIssue(
                    line_no=line_no,
                    kind=EXTRA_NOT_OBJECT,
                    detail="'extra' is not an object; treated as empty",
                )
            )
            extra = {}
    return ImportedMessage(
        role=role,
        content=content,
        speaker_name=speaker_name,
        is_system=is_system,
        send_date_raw=send_date_raw,
        send_date_parsed=send_date_parsed,
        swipes=swipes,
        swipe_id=swipe_id,
        has_explicit_swipes=has_explicit_swipes,
        swipe_info=swipe_info,
        has_swipe_info=has_swipe_info,
        extra=extra,
        raw=copy.deepcopy(obj),
    )


def _apply_header(
    obj: dict,
    line_no: int,
    chat: ImportedChat,
    report: ImportReport,
) -> None:
    """Populate chat + report from the header record."""
    report.header_present = True
    report.header_line_no = line_no
    chat.source_shape = "st-jsonl-header"
    chat.header_raw = copy.deepcopy(obj)
    user_value = obj.get("user_name")
    chat.user_name = user_value if isinstance(user_value, str) else ""
    char_value = obj.get("character_name")
    chat.character_name = char_value if isinstance(char_value, str) else ""
    if "create_date" in obj:
        raw, parsed, _unparsed = _date_fields(obj["create_date"])
        chat.create_date_raw = raw
        chat.create_date_parsed = parsed
    if "chat_metadata" in obj:
        metadata = obj["chat_metadata"]
        if isinstance(metadata, dict):
            chat.chat_metadata = copy.deepcopy(metadata)
            report.chat_metadata_keys = sorted(metadata.keys())
        else:
            report.issues.append(
                LineIssue(
                    line_no=line_no,
                    kind=EXTRA_NOT_OBJECT,
                    detail="'chat_metadata' is not an object; treated "
                    "as empty",
                )
            )
            chat.chat_metadata = {}
            report.chat_metadata_keys = []


def _parse_jsonl_text(text: str, bom_stripped: bool, *, strict: bool) -> ImportResult:
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        raise ChatFileParseError(
            ChatFileErrorKind.INPUT_TOO_LARGE,
            f"chat file has {len(lines)} lines, exceeding the "
            f"{MAX_LINES}-line cap",
        )
    report = ImportReport(
        total_lines=len(lines),
        blank_lines=0,
        header_present=False,
        header_line_no=None,
        imported_messages=0,
        refused_lines=0,
        repaired_lines=0,
        bom_stripped=bom_stripped,
        chat_metadata_keys=[],
        issues=[],
    )
    chat = ImportedChat(source_shape="st-jsonl-headerless")
    first_dict_seen = False
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            report.blank_lines += 1
            continue
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            report.issues.append(
                LineIssue(
                    line_no=line_no,
                    kind=LINE_TOO_LARGE,
                    detail=f"line exceeds the {MAX_LINE_BYTES}-byte cap",
                )
            )
            continue
        try:
            obj = safe_json_loads(line, limit=MAX_LINE_BYTES)
        except SafetyError as exc:
            report.issues.append(
                LineIssue(
                    line_no=line_no,
                    kind=INVALID_JSON,
                    detail=str(exc),
                    excerpt=line[:80],
                )
            )
            continue
        if not isinstance(obj, dict):
            report.issues.append(
                LineIssue(
                    line_no=line_no,
                    kind=NOT_AN_OBJECT,
                    detail=f"expected a JSON object, got "
                    f"{type(obj).__name__}",
                )
            )
            continue
        if not first_dict_seen:
            first_dict_seen = True
            if "mes" not in obj and "is_user" not in obj:
                _apply_header(obj, line_no, chat, report)
                continue
            report.issues.append(
                LineIssue(
                    line_no=line_no,
                    kind=HEADER_MISSING,
                    detail="no header record; first record treated as "
                    "a message",
                )
            )
        message = _convert_message(obj, line_no, chat.user_name, report.issues)
        if message is not None:
            chat.messages.append(message)
    report.imported_messages = len(chat.messages)
    error_lines = {
        issue.line_no
        for issue in report.issues
        if ISSUE_SEVERITY.get(issue.kind) == "error"
    }
    report.refused_lines = len(error_lines)
    repaired = {
        issue.line_no
        for issue in report.issues
        if ISSUE_SEVERITY.get(issue.kind) == "repair"
        or issue.kind in _REPAIR_KINDS
    }
    report.repaired_lines = len(repaired)
    if not report.header_present and not chat.messages and error_lines:
        raise ChatFileParseError(
            ChatFileErrorKind.NO_VALID_RECORDS,
            "chat file has no header and no valid message records",
            report=report,
        )
    if strict:
        first_error = next(
            (
                issue
                for issue in report.issues
                if ISSUE_SEVERITY.get(issue.kind) == "error"
            ),
            None,
        )
        if first_error is not None:
            raise ChatFileParseError(
                first_error.kind,
                f"strict mode: line {first_error.line_no} refused: "
                f"{first_error.detail}",
                report=report,
            )
    return ImportResult(chat=chat, report=report)


def parse_chat_jsonl(data: bytes | str, *, strict: bool = False) -> ImportResult:
    """Parse an ST-shaped JSONL chat file (header + message lines)."""
    text, bom_stripped = _decode(data)
    return _parse_jsonl_text(text, bom_stripped, strict=strict)


def _parse_native(doc: dict, text: str, bom_stripped: bool) -> ImportResult:
    """Parse a Runmal native export document (S111 shape)."""
    chat_obj = doc.get("chat")
    if not isinstance(chat_obj, dict):
        chat_obj = {}
    chat = ImportedChat(
        source_shape="runmal-native",
        header_raw=copy.deepcopy(doc),
        chat_metadata={},
    )
    if "created_at" in chat_obj:
        raw, parsed, _unparsed = _date_fields(chat_obj["created_at"])
        chat.create_date_raw = raw
        chat.create_date_parsed = parsed
    raw_messages = doc.get("messages")
    if not isinstance(raw_messages, list):
        raw_messages = []
    for entry in raw_messages:
        if not isinstance(entry, dict):
            continue
        role_value = entry.get("role")
        role = role_value if role_value in _NATIVE_ROLES else "assistant"
        content_value = entry.get("content")
        content = content_value if isinstance(content_value, str) else ""
        speaker_value = entry.get("speaker_name")
        speaker_name = speaker_value if isinstance(speaker_value, str) else ""
        send_date_raw: str | None = None
        send_date_parsed: datetime | None = None
        if "created_at" in entry:
            send_date_raw, send_date_parsed, _u = _date_fields(entry["created_at"])
        chat.messages.append(
            ImportedMessage(
                role=role,
                content=content,
                speaker_name=speaker_name,
                is_system=(role == "system"),
                send_date_raw=send_date_raw,
                send_date_parsed=send_date_parsed,
                swipes=[content],
                swipe_id=0,
                has_explicit_swipes=False,
                swipe_info=[],
                has_swipe_info=False,
                extra={},
                raw=copy.deepcopy(entry),
            )
        )
    total = len(text.splitlines()) or 1
    report = ImportReport(
        total_lines=total,
        blank_lines=0,
        header_present=True,
        header_line_no=1,
        imported_messages=len(chat.messages),
        refused_lines=0,
        repaired_lines=0,
        bom_stripped=bom_stripped,
        chat_metadata_keys=[],
        issues=[],
    )
    return ImportResult(chat=chat, report=report)


def parse_chat_file(data: bytes | str, *, strict: bool = False) -> ImportResult:
    """Parse a chat file: native Runmal export if the whole text is
    one such JSON document, otherwise ST-shaped JSONL."""
    text, bom_stripped = _decode(data)
    whole: object = None
    whole_parsed = True
    try:
        whole = safe_json_loads(text, limit=MAX_CHAT_BYTES)
    except SafetyError:
        whole_parsed = False
    if whole_parsed and isinstance(whole, dict):
        if whole.get("format") == _NATIVE_FORMAT:
            return _parse_native(whole, text, bom_stripped)
    elif whole_parsed:
        raise ChatFileParseError(
            ChatFileErrorKind.NOT_JSONL,
            "file is a single JSON value, not a chat file: expected "
            "JSONL (one JSON object per line, header first) or a "
            "Runmal native chat export",
        )
    return _parse_jsonl_text(text, bom_stripped, strict=strict)
