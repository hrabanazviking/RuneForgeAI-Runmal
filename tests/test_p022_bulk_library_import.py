"""P-022 acceptance: bulk library import — a whole folder of cards +
lorebooks imported as one act, with a report (accepted / repaired /
refused with reasons).

Shapes rest on the P-005 interop corpus fixtures and the card /
lorebook parsers' public behaviour; fixtures below are authored fresh
here except where an existing corpus fixture is reused by path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.characters.service import list_characters
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.library import service as bulk_service
from runmal.library import import_library_folder, import_library_uploads
from runmal.lorebooks import service as lore_service

FIXTURES = Path(__file__).parent / "fixtures"
CARDS = FIXTURES / "cards"
INTEROP = FIXTURES / "interop"


# ---------------------------------------------------------------- helpers

def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory) -> str:
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        return user.id


def card_bytes(name: str = "Bulk Card", **over) -> bytes:
    card = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": name,
        "description": "A card authored for the bulk-import battery.",
        "personality": "Steady.",
        "scenario": "A test hall.",
        "first_mes": "Hail!",
        "mes_example": "<START>Yo<END>",
        "creator_notes": "",
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": [],
        "tags": ["bulk"],
        "creator": "forge",
        "extensions": {},
    }
    card.update(over)
    return json.dumps(card).encode()


def lorebook_bytes(name: str = "Bulk Lore", entries=None) -> bytes:
    book = {
        "format": "runmal-lorebook",
        "version": 1,
        "name": name,
        "description": "A lorebook authored for the bulk-import battery.",
        "scan_depth": 4,
        "token_budget": None,
        "entries": entries
        if entries is not None
        else [
            {
                "name": "The Ferry",
                "content": "The ferry crosses at dawn.",
                "keys": ["ferry"],
                "secondary_keys": [],
                "priority": 100,
                "position": "before_char",
                "enabled": True,
                "constant": False,
                "case_sensitive": False,
                "whole_word": True,
                "sticky_prompts": 0,
                "cooldown_prompts": 0,
                "delay_prompts": 0,
            }
        ],
    }
    return json.dumps(book).encode()


def write(folder: Path, relpath: str, data: bytes) -> Path:
    path = folder / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def by_relpath(report) -> dict:
    return {e.relpath: e for e in report.entries}


def assert_invariant(report) -> None:
    totals = report.totals or report.compute_totals()
    assert totals["total_seen"] == len(report.entries)
    assert totals["total_seen"] == (
        totals["accepted"] + totals["repaired"] + totals["refused"] + totals["skipped"]
    )


async def counts(factory, user_id):
    async with factory() as session:
        chars = await list_characters(session, user_id)
        books = await lore_service.list_lorebooks(session, user_id)
        return len(chars), len(books)


# ---------------------------------------------------------------- the act

async def test_folder_import_mixed_library_all_accepted(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "card.json", card_bytes("Folder Card"))
    write(folder, "lore.json", lorebook_bytes("Folder Lore"))
    write(folder, "world.json", (INTEROP / "lorebook_worldinfo_full.json").read_bytes())
    write(folder, "card.png", (CARDS / "card.png").read_bytes())
    write(folder, "card.charx", (CARDS / "card.charx").read_bytes())
    write(folder, "sub/nested.json", card_bytes("Nested Card"))

    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)

    assert_invariant(report)
    assert report.totals["refused"] == 0, report.to_dict()
    assert report.totals["accepted"] + report.totals["repaired"] == 6
    entries = by_relpath(report)
    assert entries["card.json"].detected_kind == "card"
    assert entries["lore.json"].detected_kind == "lorebook"
    assert entries["world.json"].detected_kind == "lorebook"
    assert entries["card.png"].detected_format == "png"
    assert entries["card.charx"].detected_format == "charx"
    assert entries["sub/nested.json"].created_name == "Nested Card"
    assert all(e.created_id for e in report.entries)
    n_chars, n_books = await counts(factory, user_id)
    assert n_chars == 4  # json card + png + charx + nested
    assert n_books == 2


async def test_report_never_carries_file_contents(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "card.json", card_bytes("Secret Card"))
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    blob = json.dumps(report.to_dict())
    assert "A card authored for the bulk-import battery" not in blob
    entry = report.entries[0]
    assert entry.sha256 == hashlib.sha256(card_bytes("Secret Card")).hexdigest()
    assert entry.size_bytes == len(card_bytes("Secret Card"))


async def test_nonrecursive_import_only_sees_top_level(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "top.json", card_bytes("Top Card"))
    write(folder, "sub/nested.json", card_bytes("Nested Card"))
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder, recursive=False)
    assert [e.relpath for e in report.entries] == ["top.json"]


# ---------------------------------------------------------------- repairs

async def test_bom_and_whitespace_name_are_repaired(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "bom.json", b"\xef\xbb\xbf" + card_bytes("Bom Card"))
    write(folder, "padded.json", card_bytes("  Padded Card  "))
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    entries = by_relpath(report)
    assert entries["bom.json"].outcome == "repaired"
    assert [r.code for r in entries["bom.json"].repairs] == ["bom_stripped"]
    assert entries["padded.json"].outcome == "repaired"
    assert entries["padded.json"].created_name == "Padded Card"
    assert "name_whitespace_trimmed" in [str(r.code) for r in entries["padded.json"].repairs]
    n_chars, _ = await counts(factory, user_id)
    assert n_chars == 2


async def test_content_wins_over_extension(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "actually-json.png", card_bytes("Sniffed Card"))
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    entry = report.entries[0]
    assert entry.outcome == "repaired"
    assert entry.detected_format == "json"
    assert "content_sniffed" in [str(r.code) for r in entry.repairs]


async def test_nameless_native_lorebook_takes_filename(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    book = json.loads(lorebook_bytes())
    del book["name"]
    write(folder, "sea-lore.json", json.dumps(book).encode())
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    entry = report.entries[0]
    assert entry.outcome == "repaired"
    assert entry.created_name == "sea-lore"
    assert "lorebook_name_from_filename" in [str(r.code) for r in entry.repairs]


# ---------------------------------------------------------------- refusals

async def test_refusals_carry_reasons_and_never_stop_the_act(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "good.json", card_bytes("Good Card"))
    write(folder, "broken.json", b"{not json")
    write(folder, "unknown.json", json.dumps({"hello": "world"}).encode())
    write(folder, "empty.json", b"")
    ambiguous = json.loads(card_bytes("Amb Card"))
    ambiguous["entries"] = {}
    write(folder, "ambiguous.json", json.dumps(ambiguous).encode())
    nameless = {"description": "x", "personality": "y", "scenario": "z"}
    write(folder, "nameless.json", json.dumps(nameless).encode())

    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)

    assert_invariant(report)
    entries = by_relpath(report)
    assert entries["good.json"].outcome == "accepted"
    assert entries["broken.json"].outcome == "refused"
    assert str(entries["broken.json"].reason_code) == "invalid_json"
    assert entries["unknown.json"].outcome == "refused"
    assert str(entries["unknown.json"].reason_code) == "unrecognized_content"
    assert entries["empty.json"].outcome == "refused"
    assert entries["ambiguous.json"].outcome == "refused"
    assert str(entries["ambiguous.json"].reason_code) == "ambiguous_kind"
    assert entries["nameless.json"].outcome == "refused"
    assert str(entries["nameless.json"].reason_code) == "missing_name"
    assert all(e.reason for e in report.entries if e.outcome == "refused")
    n_chars, _ = await counts(factory, user_id)
    assert n_chars == 1


async def test_recognised_foreign_shapes_point_at_their_home_slice(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "preset.json", (INTEROP / "preset_st_chatcompletion.json").read_bytes())
    write(folder, "persona.json", (INTEROP / "persona_st.json").read_bytes())
    write(folder, "chat.jsonl", (INTEROP / "chat_st.jsonl").read_bytes())
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    entries = by_relpath(report)
    for relpath, home in (
        ("preset.json", "P-021"),
        ("persona.json", "P-018"),
        ("chat.jsonl", "P-020"),
    ):
        entry = entries[relpath]
        assert entry.outcome == "refused", relpath
        assert str(entry.reason_code) == "unsupported_kind"
        assert home in entry.reason
    n_chars, n_books = await counts(factory, user_id)
    assert (n_chars, n_books) == (0, 0)


# ---------------------------------------------------------------- duplicates

async def test_exact_duplicates_in_batch_and_against_library(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "a.json", card_bytes("Twin Card"))
    write(folder, "b.json", card_bytes("Twin Card"))
    write(folder, "lore-a.json", lorebook_bytes("Twin Lore"))
    write(folder, "lore-b.json", lorebook_bytes("Twin Lore"))

    async with factory() as session:
        first = await import_library_folder(session, user_id, folder)
    entries = by_relpath(first)
    assert entries["a.json"].outcome == "accepted"
    assert entries["b.json"].outcome == "refused"
    assert str(entries["b.json"].reason_code) == "duplicate_in_batch"
    assert entries["lore-b.json"].outcome == "refused"
    assert str(entries["lore-b.json"].reason_code) == "duplicate_in_batch"

    async with factory() as session:
        second = await import_library_folder(session, user_id, folder)
    assert second.totals["accepted"] == 0
    assert {str(e.reason_code) for e in second.entries} == {"duplicate_exact"}
    n_chars, n_books = await counts(factory, user_id)
    assert (n_chars, n_books) == (1, 1)


async def test_same_name_different_content_is_not_a_duplicate(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "one.json", card_bytes("Shared Name", description="First telling."))
    write(folder, "two.json", card_bytes("Shared Name", description="Second telling."))
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    assert report.totals["accepted"] == 2
    two = by_relpath(report)["two.json"]
    assert any(n.startswith("name_collision:") for n in two.notes)
    n_chars, _ = await counts(factory, user_id)
    assert n_chars == 2


# ---------------------------------------------------------------- dry run

async def test_dry_run_verdicts_match_real_run_and_store_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "card.json", card_bytes("Dry Card"))
    write(folder, "lore.json", lorebook_bytes("Dry Lore"))
    write(folder, "bad.json", b"{nope")
    async with factory() as session:
        dry = await import_library_folder(session, user_id, folder, dry_run=True)
    assert dry.dry_run is True
    assert (await counts(factory, user_id)) == (0, 0)
    async with factory() as session:
        real = await import_library_folder(session, user_id, folder)
    dry_verdicts = {e.relpath: str(e.outcome) for e in dry.entries}
    real_verdicts = {e.relpath: str(e.outcome) for e in real.entries}
    assert dry_verdicts == real_verdicts
    assert (await counts(factory, user_id)) == (1, 1)


# ---------------------------------------------------------------- atomicity

async def test_bad_entry_leaves_no_partial_lorebook(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    good_entry = json.loads(lorebook_bytes())["entries"][0]
    bad_entry = dict(good_entry, name="Bad", position="sideways")
    write(folder, "mixed.json", lorebook_bytes("Mixed Lore", [good_entry, bad_entry]))
    write(folder, "card.json", card_bytes("Survivor Card"))
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    entries = by_relpath(report)
    assert entries["mixed.json"].outcome == "refused"
    assert str(entries["mixed.json"].reason_code) == "invalid_lorebook"
    assert entries["card.json"].outcome == "accepted"
    n_chars, n_books = await counts(factory, user_id)
    assert (n_chars, n_books) == (1, 0)


# ---------------------------------------------------------------- skips & limits

async def test_unsupported_extensions_are_skipped_not_refused(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "card.json", card_bytes("Kept Card"))
    write(folder, "notes.md", b"# hello")
    write(folder, "tool.exe", b"MZ")
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    assert_invariant(report)
    entries = by_relpath(report)
    assert entries["notes.md"].outcome == "skipped"
    assert entries["tool.exe"].outcome == "skipped"
    assert {s.relpath for s in report.skipped} == {"notes.md", "tool.exe"}
    assert report.totals["skipped"] == 2


async def test_symlinks_are_never_followed(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    outside = write(tmp_path, "outside.json", card_bytes("Outside Card"))
    folder = tmp_path / "library"
    folder.mkdir()
    (folder / "link.json").symlink_to(outside)
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    assert report.entries[0].outcome == "skipped"
    assert report.entries[0].reason == "symlink_not_followed"
    assert (await counts(factory, user_id)) == (0, 0)


async def test_batch_file_limit_refuses_overflow(tmp_path, monkeypatch):
    monkeypatch.setattr(bulk_service, "MAX_FILES", 2)
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    for i in range(3):
        write(folder, f"card{i}.json", card_bytes(f"Card {i}"))
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    assert report.totals["accepted"] == 2
    overflow = [e for e in report.entries if str(e.reason_code) == "batch_limit"]
    assert len(overflow) == 1


async def test_missing_folder_is_an_act_error(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        with pytest.raises(FileNotFoundError):
            await import_library_folder(session, user_id, tmp_path / "nope")


# ---------------------------------------------------------------- uploads service

async def test_uploads_import_matches_folder_semantics(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    files = [
        ("sub/card.json", card_bytes("Upload Card")),
        ("lore.json", lorebook_bytes("Upload Lore")),
        ("junk.json", b"not json at all"),
    ]
    async with factory() as session:
        report = await import_library_uploads(session, user_id, files)
    assert_invariant(report)
    entries = by_relpath(report)
    assert entries["sub/card.json"].outcome == "accepted"
    assert entries["lore.json"].outcome == "accepted"
    assert entries["junk.json"].outcome == "refused"
    assert (await counts(factory, user_id)) == (1, 1)


# ---------------------------------------------------------------- HTTP API

@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_http_import_reports_per_file_verdicts(app_client):
    resp = app_client.post(
        "/api/v1/library/imports",
        files=[
            ("files", ("card.json", card_bytes("HTTP Card"), "application/json")),
            ("files", ("lore.json", lorebook_bytes("HTTP Lore"), "application/json")),
            ("files", ("bad.json", b"{broken", "application/json")),
        ],
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["totals"]["total_seen"] == 3
    assert payload["totals"]["accepted"] == 2
    assert payload["totals"]["refused"] == 1
    listed = app_client.get("/api/v1/characters").json()
    assert [c["name"] for c in listed] == ["HTTP Card"]


def test_http_import_dry_run_stores_nothing(app_client):
    resp = app_client.post(
        "/api/v1/library/imports",
        data={"dry_run": "true"},
        files=[("files", ("card.json", card_bytes("HTTP Dry"), "application/json"))],
    )
    assert resp.status_code == 200
    assert resp.json()["dry_run"] is True
    assert app_client.get("/api/v1/characters").json() == []


def test_http_import_traversal_filename_is_skipped(app_client):
    resp = app_client.post(
        "/api/v1/library/imports",
        files=[
            ("files", ("../evil.json", card_bytes("Evil"), "application/json")),
            ("files", ("good.json", card_bytes("Good HTTP"), "application/json")),
        ],
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["totals"]["skipped"] == 1
    assert payload["totals"]["accepted"] == 1
    names = [c["name"] for c in app_client.get("/api/v1/characters").json()]
    assert names == ["Good HTTP"]


def test_http_import_unrecognised_dry_run_value_is_400(app_client):
    # A typo'd dry_run must fail closed, never silently run a real import.
    resp = app_client.post(
        "/api/v1/library/imports",
        data={"dry_run": "ture"},
        files=[("files", ("card.json", card_bytes("Typo Dry"), "application/json"))],
    )
    assert resp.status_code == 400
    assert app_client.get("/api/v1/characters").json() == []


async def test_double_bom_is_stripped_once_noted(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "bom2.json", b"\xef\xbb\xbf\xef\xbb\xbf" + card_bytes("Double Bom"))
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    entry = report.entries[0]
    assert entry.outcome == "repaired"
    assert "bom_stripped" in [str(r.code) for r in entry.repairs]


async def test_oversize_file_refused_from_size_not_parsed(tmp_path, monkeypatch):
    monkeypatch.setattr(bulk_service, "MAX_INPUT_BYTES", 8)
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "library"
    write(folder, "big.json", card_bytes("Too Big"))
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    entry = report.entries[0]
    assert entry.outcome == "refused"
    assert str(entry.reason_code) == "input_too_large"
    assert (await counts(factory, user_id)) == (0, 0)


def test_http_import_no_files_is_400_and_auth_required(app_client, tmp_path, monkeypatch):
    resp = app_client.post("/api/v1/library/imports", files=[])
    assert resp.status_code == 400
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "auth.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    anon = TestClient(create_app(create_session_factory(engine)))
    resp = anon.post(
        "/api/v1/library/imports",
        files=[("files", ("c.json", card_bytes("Anon"), "application/json"))],
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------- CLI

def test_cli_import_exit_codes_and_json(tmp_path, monkeypatch, capsys):
    from runmal.__main__ import main

    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    # Seed the CLI's OWN default database: _run_library resolves its
    # session factory from the data dir, not from a test-local file.
    from runmal.app import default_session_factory

    factory = default_session_factory()

    async def seed_user():
        async with factory() as session:
            user = User(name="cli")
            session.add(user)
            await session.commit()
            return user.id

    import asyncio

    user_id = asyncio.run(seed_user())
    folder = tmp_path / "library"
    write(folder, "card.json", card_bytes("CLI Card"))

    assert main(["library", "import", str(folder), "--user-id", user_id]) == 0
    out = capsys.readouterr().out
    assert "CLI Card" in out
    assert "1 accepted" in out

    # Second run: the same card is now an exact duplicate -> exit 1.
    assert main(["library", "import", str(folder), "--user-id", user_id]) == 1

    # Missing folder -> exit 2, no report.
    assert main(["library", "import", str(tmp_path / "nope"), "--user-id", user_id]) == 2
