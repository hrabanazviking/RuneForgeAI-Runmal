"""P-020 acceptance: chat file bridge (projection, loss, diff, resolve)."""

from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path

from runmal.chats import service
from runmal.chats.filebridge import (
    field_diff,
    loss_report,
    project_messages,
    resolve_character,
    to_service_document,
)
from runmal.chats.fileexport import export_chat_jsonl
from runmal.chats.fileimport import parse_chat_jsonl
from runmal.chats.filemodels import ImportedChat, ImportedMessage

CORPUS = Path(__file__).parent / "fixtures" / "interop" / "chat_st.jsonl"


def _corpus_chat() -> ImportedChat:
    return parse_chat_jsonl(CORPUS.read_bytes()).chat


def test_corpus_fixture_imports_pinned() -> None:
    result = parse_chat_jsonl(CORPUS.read_bytes())
    assert result.report.ok
    assert result.report.header_present
    assert result.report.refused_lines == 0
    chat = result.chat
    assert chat.user_name == "Ferry Passenger"
    assert chat.character_name == "Old Bruni"
    assert chat.chat_metadata == {"integrity": "corpus-placeholder"}
    assert chat.create_date_parsed == datetime(2026, 10, 1, 20, 0)
    assert len(chat.messages) == 3
    assert [m.role for m in chat.messages] == ["assistant", "user", "assistant"]


def test_corpus_round_trip_field_clean() -> None:
    chat = _corpus_chat()
    again = parse_chat_jsonl(export_chat_jsonl(chat)).chat
    assert field_diff(chat, again) == []


def test_roles_within_service_valid_roles() -> None:
    for message in _corpus_chat().messages:
        assert message.role in service.VALID_ROLES
    for projected in project_messages(_corpus_chat()):
        assert projected["role"] in service.VALID_ROLES


def test_project_messages_correctness() -> None:
    projected = project_messages(_corpus_chat())
    assert projected == [
        {
            "role": "assistant",
            "content": "Mind the gap. It minds you.",
            "speaker_name": "Old Bruni",
        },
        {
            "role": "user",
            "content": "Is the letter heavy, Bruni?",
            "speaker_name": "Ferry Passenger",
        },
        {
            "role": "assistant",
            "content": "Letters are never heavy. News is.",
            "speaker_name": "Old Bruni",
        },
    ]


def test_to_service_document_shape() -> None:
    doc = to_service_document(_corpus_chat(), exported_at="2026-11-06T00:00:00Z")
    assert doc["format"] == "runmal-chat-export"
    assert doc["version"] == 1
    assert doc["exported_at"] == "2026-11-06T00:00:00Z"
    assert doc["chat"] == {
        "title": "",
        "character_id": None,
        "character_name": "Old Bruni",
        "user_name": "Ferry Passenger",
    }
    assert len(doc["messages"]) == 3
    for message in doc["messages"]:
        assert set(message) == {"role", "content", "speaker_name"}


def test_loss_report_names_losses() -> None:
    chat = ImportedChat(
        user_name="U",
        character_name="C",
        chat_metadata={"integrity": "x", "branch_of": "parent-1"},
        messages=[
            ImportedMessage(
                role="assistant",
                content="active",
                speaker_name="C",
                send_date_raw="2026-10-01 @20h 00m 01s",
                swipes=["active", "alt one", "alt two"],
                has_explicit_swipes=True,
                extra={"api": "corpus"},
                raw={"mes": "active", "send_date": "2026-10-01 @20h 00m 01s"},
            )
        ],
    )
    report = loss_report(chat)
    text = "\n".join(report)
    assert "2 alternate swipe" in text
    assert "extra" in text
    assert "integrity" in text
    assert "branch" in text and "branch_of" in text
    assert "send_date" in text


def test_loss_report_empty_for_lossless() -> None:
    chat = ImportedChat(
        user_name="U",
        character_name="C",
        messages=[
            ImportedMessage(
                role="user",
                content="hello",
                speaker_name="U",
                swipes=["hello"],
                has_explicit_swipes=True,
            )
        ],
    )
    assert loss_report(chat) == []


def test_loss_report_corpus_nonempty() -> None:
    assert loss_report(_corpus_chat()) != []


def test_resolve_character_exact_and_none() -> None:
    chat = _corpus_chat()
    assert resolve_character(chat, {"Old Bruni": "char-1"}) == "char-1"
    assert resolve_character(chat, {"old bruni": "char-1"}) is None
    assert resolve_character(chat, {}) is None


def test_field_diff_identical_is_clean() -> None:
    chat = _corpus_chat()
    assert field_diff(chat, copy.deepcopy(chat)) == []


def test_field_diff_detects_planted_change() -> None:
    chat = _corpus_chat()
    changed = copy.deepcopy(chat)
    changed.messages[0].swipes[1] = "tampered"
    diffs = field_diff(chat, changed)
    assert "messages[0].swipes[1]" in diffs
    changed2 = copy.deepcopy(chat)
    changed2.chat_metadata["integrity"] = "tampered"
    assert "chat_metadata.integrity" in field_diff(chat, changed2)
    changed3 = copy.deepcopy(chat)
    changed3.header_raw["chat_metadata"]["integrity"] = "tampered"
    assert "header.chat_metadata.integrity" in field_diff(chat, changed3)
