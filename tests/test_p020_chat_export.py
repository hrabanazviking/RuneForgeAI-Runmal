"""P-020 acceptance: chat file export — ST-shaped chat JSONL out.

Shapes rest on P-002's census (official public documentation) and
P-005's authored corpus fixture (`chat_st.jsonl`, read-only here).
All other inputs are authored fresh in this file.

The stability contract pinned below:

1. field-clean round trip — parse(export(parse(x))) equals parse(x)
   on typed fields AND raw, recursively;
2. byte fixed point — export(parse(export(parse(x)))) equals
   export(parse(x)) byte-for-byte;
3. for the corpus fixture specifically, the first export's lines
   parsed as JSON equal the original lines parsed as JSON,
   object-for-object.

Plus the no-fabrication law: fields a line never carried (swipes,
send_date, is_system, extra, a header's create_date, ...) are never
invented on export.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from runmal.chats.fileexport import export_chat_jsonl
from runmal.chats.fileimport import parse_chat_jsonl
from runmal.chats.filemodels import ImportedChat, ImportedMessage

CORPUS_CHAT = Path(__file__).parent / "fixtures" / "interop" / "chat_st.jsonl"

ST_MS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} @\d{2}h \d{2}m \d{2}s \d{3}ms$")


def _jsonl(*objects: dict) -> bytes:
    return "".join(
        json.dumps(obj, ensure_ascii=False) + "\n" for obj in objects
    ).encode("utf-8")


def _objects(data: bytes) -> list[dict]:
    return [json.loads(line) for line in data.decode("utf-8").splitlines()]


def _parse(data: bytes):
    return parse_chat_jsonl(data).chat


def _assert_typed_equal(first: ImportedChat, second: ImportedChat) -> None:
    assert first.user_name == second.user_name
    assert first.character_name == second.character_name
    assert first.create_date_raw == second.create_date_raw
    assert first.create_date_parsed == second.create_date_parsed
    assert first.chat_metadata == second.chat_metadata
    assert len(first.messages) == len(second.messages)
    for a, b in zip(first.messages, second.messages, strict=True):
        assert a.role == b.role
        assert a.content == b.content
        assert a.speaker_name == b.speaker_name
        assert a.is_system == b.is_system
        assert a.send_date_raw == b.send_date_raw
        assert a.send_date_parsed == b.send_date_parsed
        assert a.swipes == b.swipes
        assert a.swipe_id == b.swipe_id
        assert a.has_explicit_swipes == b.has_explicit_swipes
        assert a.swipe_info == b.swipe_info
        assert a.has_swipe_info == b.has_swipe_info
        assert a.extra == b.extra


def _assert_chat_equal(first: ImportedChat, second: ImportedChat) -> None:
    """Typed fields AND raw, recursively (stability contract 1)."""
    _assert_typed_equal(first, second)
    assert first.source_shape == second.source_shape
    assert first.header_raw == second.header_raw
    for a, b in zip(first.messages, second.messages, strict=True):
        assert a.raw == b.raw


def _assert_stable(data: bytes) -> ImportedChat:
    """Contracts 1+2 for one authored input; returns the first parse."""
    chat = _parse(data)
    once = export_chat_jsonl(chat)
    reparsed = _parse(once)
    _assert_chat_equal(reparsed, chat)
    assert export_chat_jsonl(reparsed) == once
    return chat


RICH_HEADER = {
    "user_name": "Ferry Passenger",
    "character_name": "Old Bruni",
    "create_date": "2026-10-01 @20h 00m 00s 000ms",
    "chat_metadata": {
        "integrity": "authored",
        "x_meta_unknown": [1, {"deep": None}],
    },
    "x_header_unknown": {"nested": {"flag": True, "items": [1.5, "two", None]}},
}

RICH_MESSAGE = {
    "name": "Old Bruni",
    "is_user": False,
    "is_system": False,
    "send_date": "2026-10-01 @20h 00m 01s",
    "mes": "Mind the gap — it minds you, Sigríðr.",
    "extra": {
        "api": "authored",
        "model": "authored-model",
        "x_extra_unknown": {"levels": [{"deep": [True, None]}]},
    },
    "swipes": ["Mind the gap — it minds you, Sigríðr.", "Step careful."],
    "swipe_id": 0,
    "swipe_info": [
        {"send_date": "2026-10-01 @20h 00m 01s", "extra": {"model": "m-a"}},
        {"send_date": "2026-10-01 @20h 00m 02s", "extra": {"model": "m-b"}},
    ],
    "x_unknown_string": "must-survive",
    "x_unknown_int": 42,
    "x_unknown_float": 42.5,
    "x_unknown_bool_true": True,
    "x_unknown_bool_false": False,
    "x_unknown_null": None,
    "x_unknown_list": ["a", 1, None, {"k": "v"}, [True, False]],
    "x_unknown_object": {"a": {"b": {"c": [1, {"d": None}], "e": {}}}},
}


# --- unknown fields survive (INV-009) ------------------------------------


def test_unknown_fields_of_every_json_type_survive_round_trip() -> None:
    chat = _assert_stable(_jsonl(RICH_HEADER, RICH_MESSAGE))
    out = _objects(export_chat_jsonl(chat))[1]
    for key in (
        "x_unknown_string",
        "x_unknown_int",
        "x_unknown_float",
        "x_unknown_bool_true",
        "x_unknown_bool_false",
        "x_unknown_null",
        "x_unknown_list",
        "x_unknown_object",
    ):
        assert out[key] == RICH_MESSAGE[key], key
    assert out["x_unknown_bool_true"] is True
    assert out["x_unknown_bool_false"] is False
    assert out["x_unknown_null"] is None
    assert out["x_unknown_object"]["a"]["b"]["c"][1] == {"d": None}


def test_header_and_chat_metadata_unknowns_survive() -> None:
    chat = _assert_stable(_jsonl(RICH_HEADER, RICH_MESSAGE))
    header = _objects(export_chat_jsonl(chat))[0]
    assert header["x_header_unknown"] == RICH_HEADER["x_header_unknown"]
    assert header["chat_metadata"] == RICH_HEADER["chat_metadata"]
    assert header["chat_metadata"]["x_meta_unknown"] == [1, {"deep": None}]


def test_extra_unknowns_survive() -> None:
    chat = _assert_stable(_jsonl(RICH_HEADER, RICH_MESSAGE))
    out = _objects(export_chat_jsonl(chat))[1]
    assert out["extra"] == RICH_MESSAGE["extra"]
    assert out["extra"]["x_extra_unknown"] == {"levels": [{"deep": [True, None]}]}


def test_non_dict_extra_restored_verbatim_on_export() -> None:
    header = {"user_name": "U", "character_name": "C"}
    for weird_extra in ("legacy-string-extra", ["a", 1, None], 42, True):
        message = {"name": "C", "is_user": False, "mes": "Hi.", "extra": weird_extra}
        chat = _assert_stable(_jsonl(header, message))
        out = _objects(export_chat_jsonl(chat))[1]
        assert out["extra"] == weird_extra
        assert type(out["extra"]) is type(weird_extra)


# --- no fabrication -------------------------------------------------------


def test_bare_message_exports_without_uncarried_fields() -> None:
    header = {"user_name": "U", "character_name": "C"}
    message = {"name": "C", "is_user": False, "mes": "Bare."}
    chat = _parse(_jsonl(header, message))
    header_out, message_out = _objects(export_chat_jsonl(chat))
    for key in ("swipes", "swipe_id", "swipe_info", "send_date", "is_system", "extra"):
        assert key not in message_out, key
    assert message_out["is_user"] is False  # is_user is always written
    assert message_out["mes"] == "Bare." and message_out["name"] == "C"
    # the bare header gains nothing either
    assert "create_date" not in header_out and "chat_metadata" not in header_out


def test_headerless_input_round_trips_stably() -> None:
    data = _jsonl(
        {"name": "C", "is_user": False, "mes": "One."},
        {"name": "U", "is_user": True, "mes": "Two."},
    )
    _assert_stable(data)


# --- swipes ---------------------------------------------------------------


def test_multi_swipe_and_swipe_id_preserved() -> None:
    message = {
        "name": "C",
        "is_user": False,
        "mes": "Third take.",
        "swipes": ["First take.", "Second take.", "Third take."],
        "swipe_id": 2,
    }
    chat = _assert_stable(_jsonl(RICH_HEADER, message))
    out = _objects(export_chat_jsonl(chat))[1]
    assert out["swipes"] == ["First take.", "Second take.", "Third take."]
    assert out["swipe_id"] == 2 and out["mes"] == "Third take."


def test_swipe_info_preserved() -> None:
    chat = _assert_stable(_jsonl(RICH_HEADER, RICH_MESSAGE))
    out = _objects(export_chat_jsonl(chat))[1]
    assert out["swipe_info"] == RICH_MESSAGE["swipe_info"]
    assert out["swipes"] == RICH_MESSAGE["swipes"]
    assert out["swipe_id"] == RICH_MESSAGE["swipe_id"]


def test_repaired_swipes_overlay_raw() -> None:
    # Non-string members are dropped at import; the repaired typed
    # array — not raw's broken one — is what export writes, and the
    # second export is the fixed point.
    message = {
        "name": "C",
        "is_user": False,
        "mes": "Keep this.",
        "swipes": ["Keep this.", 42, None, "And this.", {"bad": 1}],
        "swipe_id": 0,
    }
    data = _jsonl(RICH_HEADER, message)
    chat = _parse(data)
    assert chat.messages[0].swipes == ["Keep this.", "And this."]
    once = export_chat_jsonl(chat)
    out = _objects(once)[1]
    assert out["swipes"] == ["Keep this.", "And this."]
    assert out["swipe_id"] == 0
    # Typed fields round-trip clean; raw round-trips clean except
    # for the one sanctioned difference — the repaired `swipes`
    # array replaces raw's broken one. From here the export is
    # the fixed point, in raw as well as in bytes.
    reparsed = _parse(once)
    _assert_typed_equal(reparsed, chat)
    raw_before = {k: v for k, v in chat.messages[0].raw.items() if k != "swipes"}
    raw_after = {k: v for k, v in reparsed.messages[0].raw.items() if k != "swipes"}
    assert raw_after == raw_before
    assert reparsed.messages[0].raw["swipes"] == ["Keep this.", "And this."]
    _assert_chat_equal(_parse(export_chat_jsonl(reparsed)), reparsed)
    assert export_chat_jsonl(reparsed) == once


# --- dates ----------------------------------------------------------------


def test_numeric_send_date_left_untouched() -> None:
    message = {
        "name": "C",
        "is_user": False,
        "mes": "Epoch-stamped.",
        "send_date": 1760000001,
    }
    chat = _assert_stable(_jsonl(RICH_HEADER, message))
    out = _objects(export_chat_jsonl(chat))[1]
    assert out["send_date"] == 1760000001
    assert isinstance(out["send_date"], int)


def test_numeric_create_date_reformatted_to_st_with_ms() -> None:
    # The one sanctioned reformatting: a numeric-epoch header date
    # is written as the parsed datetime in ST-with-ms form.
    header = {"user_name": "U", "character_name": "C", "create_date": 1759344000}
    message = {"name": "C", "is_user": False, "mes": "Dated."}
    chat = _parse(_jsonl(header, message))
    once = export_chat_jsonl(chat)
    header_out = _objects(once)[0]
    assert isinstance(header_out["create_date"], str)
    assert ST_MS_PATTERN.match(header_out["create_date"])
    reparsed = _parse(once)
    assert reparsed.create_date_parsed == chat.create_date_parsed
    assert export_chat_jsonl(reparsed) == once


def test_string_dates_ride_back_verbatim() -> None:
    chat = _assert_stable(_jsonl(RICH_HEADER, RICH_MESSAGE))
    header_out, message_out = _objects(export_chat_jsonl(chat))
    assert header_out["create_date"] == "2026-10-01 @20h 00m 00s 000ms"
    assert message_out["send_date"] == "2026-10-01 @20h 00m 01s"


# --- natively built chats (no raws) ---------------------------------------


def _native_chat() -> ImportedChat:
    return ImportedChat(
        user_name="Native User",
        character_name="Native Char",
        chat_metadata={"origin": "native"},
        messages=[
            ImportedMessage(
                role="user",
                content="Hello?",
                speaker_name="Native User",
                swipes=["Hello?"],
            ),
            ImportedMessage(
                role="assistant",
                content="Second answer.",
                speaker_name="Native Char",
                swipes=["First answer.", "Second answer."],
                swipe_id=1,
                has_explicit_swipes=True,
            ),
        ],
        source_shape="native",
    )


def test_native_chat_exports_valid_st_jsonl() -> None:
    native = _native_chat()
    data = export_chat_jsonl(native)
    header, user_line, assistant_line = _objects(data)
    # header synthesized only from carried fields — no create_date
    assert header == {
        "user_name": "Native User",
        "character_name": "Native Char",
        "chat_metadata": {"origin": "native"},
    }
    assert user_line == {
        "name": "Native User",
        "is_user": True,
        "mes": "Hello?",
    }
    assert assistant_line["swipes"] == ["First answer.", "Second answer."]
    assert assistant_line["swipe_id"] == 1
    assert "send_date" not in assistant_line and "extra" not in assistant_line
    # re-imports field-clean on typed fields, and export is a fixed point
    reparsed = _parse(data)
    _assert_typed_equal(reparsed, native)
    assert export_chat_jsonl(reparsed) == data


def test_native_chat_with_create_date_raw_carries_it() -> None:
    native = _native_chat()
    native.create_date_raw = "2026-10-02 @10h 00m 00s 000ms"
    header = _objects(export_chat_jsonl(native))[0]
    assert header["create_date"] == "2026-10-02 @10h 00m 00s 000ms"


def test_native_chat_carrying_nothing_has_no_header() -> None:
    native = ImportedChat(
        messages=[ImportedMessage(role="assistant", content="Alone.")],
        source_shape="native",
    )
    lines = _objects(export_chat_jsonl(native))
    assert lines == [{"is_user": False, "mes": "Alone."}]
    assert export_chat_jsonl(ImportedChat(source_shape="native")) == b""


def test_native_message_new_keys_append_in_fixed_order() -> None:
    message = ImportedMessage(
        role="assistant",
        content="Ordered.",
        speaker_name="Native Char",
        is_system=True,
        send_date_raw="2026-10-02 @10h 00m 01s",
        extra={"k": "v"},
        swipes=["Ordered.", "Alt."],
        swipe_id=0,
        has_explicit_swipes=True,
        swipe_info=[{"send_date": "2026-10-02 @10h 00m 01s"}],
        has_swipe_info=True,
    )
    native = ImportedChat(messages=[message], source_shape="native")
    (line,) = _objects(export_chat_jsonl(native))
    assert list(line) == [
        "name",
        "is_user",
        "is_system",
        "send_date",
        "mes",
        "extra",
        "swipes",
        "swipe_id",
        "swipe_info",
    ]


# --- export byte shape ------------------------------------------------------


def test_export_byte_shape() -> None:
    chat = _parse(_jsonl(RICH_HEADER, RICH_MESSAGE))
    data = export_chat_jsonl(chat)
    assert data.endswith(b"\n") and not data.endswith(b"\n\n")
    assert data.count(b"\n") == 2
    # ensure_ascii=False: non-ASCII rides as raw UTF-8, never escapes
    assert "Sigríðr".encode() in data
    assert b"\\u" not in data


# --- corpus fixture ---------------------------------------------------------


def test_corpus_first_export_object_for_object() -> None:
    original = _objects(CORPUS_CHAT.read_bytes())
    exported = _objects(export_chat_jsonl(_parse(CORPUS_CHAT.read_bytes())))
    assert exported == original


def test_corpus_round_trip_field_clean_and_byte_fixed_point() -> None:
    _assert_stable(CORPUS_CHAT.read_bytes())
