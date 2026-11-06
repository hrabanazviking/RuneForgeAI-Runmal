"""P-020 acceptance: chat file import (ST JSONL + native export).

Inputs are authored inline here; the one corpus fixture used
(``chat_st.jsonl``) is read-only. Expectations follow the frozen
P-020 contract for ``runmal.chats.fileimport`` / ``filemodels``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from runmal.chats import fileimport
from runmal.chats.fileimport import parse_chat_file, parse_chat_jsonl
from runmal.chats.filemodels import (
    EXTRA_NOT_OBJECT,
    HEADER_MISSING,
    INFERRED_ROLE,
    INVALID_JSON,
    LINE_TOO_LARGE,
    MES_NOT_STRING,
    MES_SWIPE_MISMATCH,
    MISSING_MES,
    NOT_AN_OBJECT,
    SEND_DATE_UNPARSED,
    SWIPE_ID_OUT_OF_RANGE,
    SWIPES_MALFORMED,
    ChatFileErrorKind,
    ChatFileParseError,
)

CORPUS = Path(__file__).parent / "fixtures" / "interop" / "chat_st.jsonl"


def jl(*records: object) -> str:
    return "\n".join(json.dumps(r) for r in records)


def kinds(result, kind: str) -> list[int]:
    return [i.line_no for i in result.report.issues if i.kind == kind]


HEADER = {
    "character_name": "Old Bruni",
    "user_name": "Ferry Passenger",
    "create_date": "2026-10-01 @20h 00m 00s 000ms",
    "chat_metadata": {"integrity": "test"},
}


# --- corpus fixture -----------------------------------------------------


def test_corpus_fixture_imports() -> None:
    result = parse_chat_jsonl(CORPUS.read_bytes())
    assert result.report.ok and result.report.header_present
    assert result.chat.source_shape == "st-jsonl-header"
    assert result.chat.character_name == "Old Bruni"
    assert result.chat.user_name == "Ferry Passenger"
    assert result.chat.create_date_raw == "2026-10-01 @20h 00m 00s 000ms"
    assert result.chat.create_date_parsed == datetime(2026, 10, 1, 20, 0, 0)
    assert result.chat.chat_metadata == {"integrity": "corpus-placeholder"}
    assert result.report.chat_metadata_keys == ["integrity"]
    assert len(result.chat.messages) == 3
    first = result.chat.messages[0]
    assert first.role == "assistant" and first.speaker_name == "Old Bruni"
    assert first.swipes == [
        "Mind the gap. It minds you.",
        "Step careful. The planks remember rain.",
    ]
    assert first.extra == {"api": "corpus", "model": "corpus-model"}
    assert result.chat.messages[1].role == "user"


# --- header handling ------------------------------------------------------


def test_headerless_import_reports_missing_header() -> None:
    data = jl(
        {"name": "Solo", "is_user": False, "mes": "First line."},
        {"name": "Solo", "is_user": False, "mes": "Second line."},
    )
    result = parse_chat_jsonl(data)
    assert result.chat.source_shape == "st-jsonl-headerless"
    assert result.report.header_present is False
    assert result.report.header_line_no is None
    assert kinds(result, HEADER_MISSING) == [1]
    assert [m.content for m in result.chat.messages] == [
        "First line.",
        "Second line.",
    ]
    assert result.report.ok


def test_header_only_file_succeeds_with_zero_messages() -> None:
    result = parse_chat_jsonl(jl(HEADER))
    assert result.report.header_present and result.chat.messages == []
    assert result.report.ok and result.report.imported_messages == 0


def test_first_line_with_mes_is_a_message_not_a_header() -> None:
    data = jl({"name": "N", "is_user": True, "mes": "opening"})
    result = parse_chat_jsonl(data)
    assert result.report.header_present is False
    assert result.chat.messages[0].content == "opening"
    assert result.chat.messages[0].role == "user"


def test_mid_file_header_like_object_is_refused() -> None:
    data = jl(
        HEADER,
        {"name": "Old Bruni", "is_user": False, "mes": "Real message."},
        {"character_name": "Late", "user_name": "Headerish"},
    )
    result = parse_chat_jsonl(data)
    assert [m.content for m in result.chat.messages] == ["Real message."]
    assert kinds(result, MISSING_MES) == [3]
    assert result.report.refused_lines == 1 and not result.report.ok


# --- speakers, groups, roles ----------------------------------------------


def test_group_file_distinct_assistant_speakers_survive() -> None:
    data = jl(
        HEADER,
        {"name": "Old Bruni", "is_user": False, "mes": "Bruni speaks."},
        {"name": "Ferry Passenger", "is_user": True, "mes": "A question."},
        {"name": "Second Voice", "is_user": False, "mes": "Another voice."},
    )
    result = parse_chat_jsonl(data)
    speakers = [(m.speaker_name, m.role) for m in result.chat.messages]
    assert speakers == [
        ("Old Bruni", "assistant"),
        ("Ferry Passenger", "user"),
        ("Second Voice", "assistant"),
    ]
    assistants = {m.speaker_name for m in result.chat.messages if m.role == "assistant"}
    assert assistants == {"Old Bruni", "Second Voice"}


def test_inferred_role_and_system_role() -> None:
    data = jl(
        HEADER,
        {"name": "Ferry Passenger", "mes": "No is_user, but the user name."},
        {"name": "Old Bruni", "mes": "No is_user, character name."},
        {
            "name": "Narrator",
            "is_user": False,
            "is_system": True,
            "mes": "System note.",
        },
    )
    result = parse_chat_jsonl(data)
    assert [m.role for m in result.chat.messages] == ["user", "assistant", "system"]
    assert result.chat.messages[2].is_system is True
    assert kinds(result, INFERRED_ROLE) == [2, 3]


# --- swipes ---------------------------------------------------------------


def test_multi_swipe_message_points_at_active_swipe() -> None:
    data = jl(
        HEADER,
        {
            "name": "Old Bruni",
            "is_user": False,
            "mes": "Second take.",
            "swipes": ["First take.", "Second take."],
            "swipe_id": 1,
        },
    )
    msg = parse_chat_jsonl(data).chat.messages[0]
    assert msg.content == "Second take."
    assert msg.swipes == ["First take.", "Second take."]
    assert msg.swipes[msg.swipe_id] == msg.content == "Second take."
    assert msg.swipe_id == 1 and msg.has_explicit_swipes is True


def test_user_message_swipes_survive() -> None:
    data = jl(
        HEADER,
        {
            "name": "Ferry Passenger",
            "is_user": True,
            "mes": "Draft one.",
            "swipes": ["Draft one.", "Draft two."],
            "swipe_id": 0,
        },
    )
    msg = parse_chat_jsonl(data).chat.messages[0]
    assert msg.role == "user"
    assert msg.swipes == ["Draft one.", "Draft two."]
    assert msg.has_explicit_swipes is True


def test_swipe_info_verbatim_including_nested_unknowns() -> None:
    info = [
        {
            "send_date": "2026-10-01 @20h 00m 01s",
            "nested": {"unknown": [1, None, {"deep": True}]},
        },
        {"other": "shape"},
    ]
    data = jl(
        HEADER,
        {
            "name": "Old Bruni",
            "is_user": False,
            "mes": "With info.",
            "swipes": ["With info.", "Alt."],
            "swipe_id": 0,
            "swipe_info": info,
        },
    )
    msg = parse_chat_jsonl(data).chat.messages[0]
    assert msg.has_swipe_info is True
    assert msg.swipe_info == info


def test_swipe_id_out_of_range_is_clamped_and_repaired() -> None:
    data = jl(
        HEADER,
        {
            "name": "Old Bruni",
            "is_user": False,
            "mes": "Only take.",
            "swipes": ["Only take."],
            "swipe_id": 5,
        },
    )
    result = parse_chat_jsonl(data)
    msg = result.chat.messages[0]
    assert msg.swipe_id == 0
    assert kinds(result, SWIPE_ID_OUT_OF_RANGE) == [2]
    assert result.report.repaired_lines == 1
    assert result.report.refused_lines == 0 and result.report.ok


def test_mes_swipe_mismatch_warns_and_changes_nothing() -> None:
    data = jl(
        HEADER,
        {
            "name": "Old Bruni",
            "is_user": False,
            "mes": "Written text.",
            "swipes": ["Other text.", "More text."],
            "swipe_id": 0,
        },
    )
    result = parse_chat_jsonl(data)
    msg = result.chat.messages[0]
    assert msg.content == "Written text."
    assert msg.swipes == ["Other text.", "More text."] and msg.swipe_id == 0
    assert kinds(result, MES_SWIPE_MISMATCH) == [2]
    assert result.report.repaired_lines == 0 and result.report.refused_lines == 0


def test_swipes_as_bare_string_is_repaired() -> None:
    data = jl(
        HEADER,
        {
            "name": "Old Bruni",
            "is_user": False,
            "mes": "Solo text.",
            "swipes": "Solo text.",
        },
    )
    result = parse_chat_jsonl(data)
    msg = result.chat.messages[0]
    assert msg.swipes == ["Solo text."] and msg.has_explicit_swipes is True
    assert kinds(result, SWIPES_MALFORMED) == [2]
    assert result.report.repaired_lines == 1


def test_non_string_swipe_members_dropped_never_stringified() -> None:
    data = jl(
        HEADER,
        {
            "name": "Old Bruni",
            "is_user": False,
            "mes": "Keep me.",
            "swipes": ["Keep me.", None, 42, "Also keep.", True],
            "swipe_id": 0,
        },
    )
    msg = parse_chat_jsonl(data).chat.messages[0]
    assert msg.swipes == ["Keep me.", "Also keep."]
    assert "None" not in msg.swipes


def test_extra_non_object_warns_but_raw_keeps_original() -> None:
    data = jl(
        HEADER,
        {
            "name": "Old Bruni",
            "is_user": False,
            "mes": "Text.",
            "extra": "not-an-object",
        },
    )
    result = parse_chat_jsonl(data)
    msg = result.chat.messages[0]
    assert msg.extra == {} and msg.raw["extra"] == "not-an-object"
    assert kinds(result, EXTRA_NOT_OBJECT) == [2]


# --- branch linkage ---------------------------------------------------------


def test_branch_metadata_round_trip_and_branch_link() -> None:
    metadata = {
        "parent_chat": "harbour-main",
        "parent_chat_id": "chat-123",
        "branch_of": "harbour-main",
        "branch_point": 4,
        "unrelated_key": "kept",
    }
    header = dict(HEADER, chat_metadata=metadata)
    result = parse_chat_jsonl(
        jl(header, {"name": "Old Bruni", "is_user": False, "mes": "Branched."})
    )
    assert result.chat.chat_metadata == metadata
    assert result.chat.branch_link == {
        "parent_chat": "harbour-main",
        "parent_chat_id": "chat-123",
        "branch_of": "harbour-main",
        "branch_point": 4,
    }
    assert result.report.chat_metadata_keys == sorted(metadata.keys())


# --- malformed input, partial import, strict --------------------------------


def _mixed_file() -> str:
    return "\n".join(
        [
            json.dumps(HEADER),
            json.dumps({"name": "A", "is_user": False, "mes": "Valid one."}),
            "{not json",
            "[1, 2, 3]",
            json.dumps({"name": "NoMes", "is_user": False}),
            json.dumps({"name": "Num", "is_user": False, "mes": 42}),
            json.dumps({"name": "B", "is_user": True, "mes": "Valid two."}),
        ]
    )


def test_mixed_malformed_file_partial_import_exact_issues() -> None:
    result = parse_chat_jsonl(_mixed_file())
    assert [m.content for m in result.chat.messages] == ["Valid one.", "Valid two."]
    errors = [
        (i.line_no, i.kind)
        for i in result.report.issues
        if i.kind in (INVALID_JSON, NOT_AN_OBJECT, MISSING_MES, MES_NOT_STRING)
    ]
    assert errors == [
        (3, INVALID_JSON),
        (4, NOT_AN_OBJECT),
        (5, MISSING_MES),
        (6, MES_NOT_STRING),
    ]
    assert result.report.refused_lines == 4
    assert result.report.imported_messages == 2 and not result.report.ok
    bad = next(i for i in result.report.issues if i.kind == INVALID_JSON)
    assert bad.excerpt == "{not json" and len(bad.excerpt) <= 80
    assert "Valid" not in bad.detail


def test_strict_raises_on_first_error_but_not_on_warnings() -> None:
    with pytest.raises(ChatFileParseError) as excinfo:
        parse_chat_jsonl(_mixed_file(), strict=True)
    assert excinfo.value.report is not None
    assert excinfo.value.report.refused_lines == 4
    warn_only = jl(
        HEADER,
        {"name": "Old Bruni", "mes": "Inferred role only."},
    )
    result = parse_chat_jsonl(warn_only, strict=True)
    assert len(result.chat.messages) == 1
    assert kinds(result, INFERRED_ROLE) == [2]


def test_all_malformed_headerless_raises_no_valid_records() -> None:
    data = "\n".join(
        [
            "{broken",
            json.dumps({"name": "X", "is_user": False}),
            json.dumps({"name": "Y", "is_user": True, "mes": 7}),
        ]
    )
    with pytest.raises(ChatFileParseError) as excinfo:
        parse_chat_jsonl(data)
    assert excinfo.value.kind == ChatFileErrorKind.NO_VALID_RECORDS
    assert excinfo.value.report is not None


def test_empty_and_non_utf8_are_fatal() -> None:
    for empty in (b"", "", "  \n \r\n "):
        with pytest.raises(ChatFileParseError) as excinfo:
            parse_chat_jsonl(empty)
        assert excinfo.value.kind == ChatFileErrorKind.EMPTY_INPUT
    with pytest.raises(ChatFileParseError) as excinfo:
        parse_chat_jsonl(b"\xff\xfe not utf-8")
    assert excinfo.value.kind == ChatFileErrorKind.NOT_UTF8


def test_oversized_line_refused_while_neighbours_import(monkeypatch) -> None:
    monkeypatch.setattr(fileimport, "MAX_LINE_BYTES", 50)
    data = "\n".join(
        [
            json.dumps({"mes": "a", "is_user": True}),
            json.dumps({"mes": "x" * 100, "is_user": True}),
            json.dumps({"mes": "c", "is_user": True}),
        ]
    )
    result = parse_chat_jsonl(data)
    assert [m.content for m in result.chat.messages] == ["a", "c"]
    assert kinds(result, LINE_TOO_LARGE) == [2]
    assert result.report.refused_lines == 1


def test_oversized_input_is_fatal(monkeypatch) -> None:
    monkeypatch.setattr(fileimport, "MAX_CHAT_BYTES", 10)
    with pytest.raises(ChatFileParseError) as excinfo:
        parse_chat_jsonl(jl(HEADER))
    assert excinfo.value.kind == ChatFileErrorKind.INPUT_TOO_LARGE


def test_bom_and_crlf_import_cleanly() -> None:
    payload = (
        "\ufeff" + json.dumps(HEADER) + "\r\n"
        + json.dumps({"name": "Old Bruni", "is_user": False, "mes": "Clean."})
        + "\r\n"
    )
    result = parse_chat_jsonl(payload.encode("utf-8"))
    assert result.report.bom_stripped is True
    assert result.report.total_lines == 2 and result.report.blank_lines == 0
    assert result.report.ok and len(result.chat.messages) == 1


# --- send_date variants -------------------------------------------------------


def test_send_date_variants() -> None:
    epoch_ms = 1760000000000
    expected_epoch = datetime.fromtimestamp(epoch_ms / 1000, tz=UTC).replace(
        tzinfo=None
    )
    records = [
        {"mes": "ms", "is_user": False, "send_date": "2026-10-01 @20h 00m 00s 123ms"},
        {"mes": "plain", "is_user": False, "send_date": "2026-10-01 @20h 01m 00s"},
        {"mes": "iso", "is_user": False, "send_date": "2026-10-01T20:02:03"},
        {"mes": "epoch", "is_user": False, "send_date": epoch_ms},
        {"mes": "junk", "is_user": False, "send_date": "not a date"},
    ]
    result = parse_chat_jsonl(jl(HEADER, *records))
    msgs = result.chat.messages
    assert msgs[0].send_date_parsed == datetime(2026, 10, 1, 20, 0, 0, 123000)
    assert msgs[0].send_date_raw == "2026-10-01 @20h 00m 00s 123ms"
    assert msgs[1].send_date_parsed == datetime(2026, 10, 1, 20, 1, 0)
    assert msgs[2].send_date_parsed == datetime(2026, 10, 1, 20, 2, 3)
    assert msgs[2].send_date_raw == "2026-10-01T20:02:03"
    assert msgs[3].send_date_parsed == expected_epoch
    assert msgs[3].send_date_raw is None
    assert msgs[4].send_date_parsed is None
    assert msgs[4].send_date_raw == "not a date"
    assert kinds(result, SEND_DATE_UNPARSED) == [6]


# --- native export + dispatch ---------------------------------------------------


def _native_doc() -> dict:
    return {
        "format": "runmal-chat-export",
        "version": 1,
        "exported_at": "2026-10-02T10:00:00+00:00",
        "chat": {
            "id": "chat-1",
            "title": "Export me",
            "character_id": "char-1",
            "created_at": "2026-10-01T20:00:00",
        },
        "messages": [
            {
                "id": "m1",
                "chat_id": "chat-1",
                "role": "user",
                "content": "hi",
                "speaker_id": None,
                "speaker_name": "Ferry Passenger",
                "created_at": "2026-10-01T20:00:01",
                "updated_at": None,
            },
            {
                "id": "m2",
                "chat_id": "chat-1",
                "role": "assistant",
                "content": "hello",
                "speaker_id": None,
                "speaker_name": "Old Bruni",
                "created_at": "2026-10-01T20:00:02",
                "updated_at": None,
            },
        ],
    }


def test_native_s111_doc_imports_via_parse_chat_file() -> None:
    doc = _native_doc()
    result = parse_chat_file(json.dumps(doc))
    assert result.chat.source_shape == "runmal-native"
    assert [m.content for m in result.chat.messages] == ["hi", "hello"]
    assert [m.role for m in result.chat.messages] == ["user", "assistant"]
    assert result.chat.messages[0].speaker_name == "Ferry Passenger"
    assert result.chat.messages[0].swipes == ["hi"]
    assert result.chat.messages[0].has_explicit_swipes is False
    assert result.chat.messages[0].send_date_raw == "2026-10-01T20:00:01"
    assert result.chat.messages[0].send_date_parsed == datetime(2026, 10, 1, 20, 0, 1)
    assert result.chat.messages[0].raw == doc["messages"][0]
    assert result.chat.create_date_parsed == datetime(2026, 10, 1, 20, 0, 0)
    assert result.report.ok and result.report.imported_messages == 2


def test_parse_chat_file_dispatches_jsonl_and_rejects_array() -> None:
    result = parse_chat_file(CORPUS.read_bytes())
    assert result.chat.source_shape == "st-jsonl-header"
    with pytest.raises(ChatFileParseError) as excinfo:
        parse_chat_file("[1, 2, 3]")
    assert excinfo.value.kind == ChatFileErrorKind.NOT_JSONL
