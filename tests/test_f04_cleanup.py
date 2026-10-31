"""F-04 acceptance: the clean-up tool over ``runmal doctor``.

Part I follow-on F-04 (homed by the P-014 gate from ST-73):
scan for orphaned files, unreferenced images, chats of deleted
characters, and stale backups — with per-category risk warnings —
and remove them only under discipline: dry-run by default,
explicit apply, re-validation at delete time, containment inside
the data dir, high-risk gating, and never-removable unknowns.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from runmal.__main__ import main as runmal_main
from runmal.db.migrate import migrate_to_head
from runmal.diagnostics.cleanup import (
    CHATS_OF_DELETED_CHARACTERS,
    ORPHAN_CHARACTER_ASSETS,
    STALE_BACKUPS,
    STALE_STAGING,
    UNRECOGNIZED_BACKUP_FILES,
    UNREFERENCED_CHARACTER_FILES,
    clean_cleanup,
    scan_cleanup,
)
from runmal.diagnostics.doctor import run_doctor

TS = "2026-01-01T00:00:00+00:00"
NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def make_install(tmp_path: Path) -> Path:
    db = tmp_path / "runmal.db"
    migrate_to_head(db)
    return db


def seed(db: Path, statements: list[tuple[str, tuple]]) -> None:
    conn = sqlite3.connect(db)
    try:
        for sql, params in statements:
            conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def seed_user(db: Path) -> None:
    seed(db, [("INSERT INTO users (id, name, created_at) VALUES ('u1', 'v', ?)", (TS,))])


def seed_character(db: Path, cid: str, *, avatar: str | None = None, deleted: bool = False) -> None:
    seed(
        db,
        [
            (
                "INSERT INTO characters (id, user_id, name, card_json, "
                "avatar_asset, created_at, deleted_at) VALUES (?, 'u1', 'C', "
                "'{}', ?, ?, ?)",
                (cid, avatar, TS, TS if deleted else None),
            )
        ],
    )


def insert_chat(db: Path, chat_id: str, character_id: str) -> None:
    seed(
        db,
        [
            (
                "INSERT INTO chats (id, user_id, character_id, title, "
                "created_at) VALUES (?, 'u1', ?, 't', ?)",
                (chat_id, character_id, TS),
            )
        ],
    )


def insert_message(db: Path, message_id: str, chat_id: str) -> None:
    seed(
        db,
        [
            (
                "INSERT INTO messages (id, chat_id, role, content, "
                "created_at) VALUES (?, ?, 'user', 'hi', ?)",
                (message_id, chat_id, TS),
            )
        ],
    )


def set_age(path: Path, days: float) -> None:
    ts = (NOW - timedelta(days=days)).timestamp()
    os.utime(path, (ts, ts))


def asset_file(base: Path, cid: str, name: str, data: bytes = b"x") -> Path:
    p = base / "assets" / "characters" / cid / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def test_scan_finds_orphans_and_unreferenced_but_keeps_referenced(tmp_path):
    db = make_install(tmp_path)
    seed_user(db)
    seed_character(db, "c1", avatar="avatar.png")
    seed_character(db, "c2")  # live, no avatar
    asset_file(tmp_path, "c1", "avatar.png", b"live")
    asset_file(tmp_path, "c1", "old.png", b"stale-extra")
    asset_file(tmp_path, "c2", "note.png", b"unreferenced")
    asset_file(tmp_path, "ghost", "art.png", b"orphan-art")

    report = scan_cleanup(db_path=db, base_dir=tmp_path, now=NOW)
    orphans = report.by_category(ORPHAN_CHARACTER_ASSETS)
    assert [i.item_id for i in orphans] == ["ghost"]
    assert orphans[0].size_bytes == len(b"orphan-art")
    unref = {
        Path(i.path).name for i in report.by_category(UNREFERENCED_CHARACTER_FILES)
    }
    assert unref == {"old.png", "note.png"}
    # The referenced avatar appears nowhere in the report.
    assert all(
        not (i.path and i.path.endswith("c1/avatar.png")) for i in report.items
    )


def test_every_item_carries_a_risk_warning(tmp_path):
    db = make_install(tmp_path)
    seed_user(db)
    asset_file(tmp_path, "ghost", "art.png")
    report = scan_cleanup(db_path=db, base_dir=tmp_path, now=NOW)
    assert report.items
    for item in report.items:
        assert item.risk in ("low", "medium", "high")
        assert item.warning  # ST-73: per-category risk warnings


def test_doctor_no_longer_calls_live_characters_directory_orphaned(tmp_path):
    # The F-04 scan exposed the doctor's coarse orphan test: a
    # directory belonged to a character with no avatar was warned
    # as orphaned. Only a directory with NO character row is.
    db = make_install(tmp_path)
    seed_user(db)
    seed_character(db, "c2")  # live, no avatar
    asset_file(tmp_path, "c2", "note.png")
    asset_file(tmp_path, "ghost", "x.png")
    report = run_doctor(db_path=db, base_dir=tmp_path, audio_probe=lambda: (1, "x"))
    orphaned = [f for f in report.findings if f.check == "assets_orphaned"]
    assert len(orphaned) == 1
    assert "1 asset directorie(s)" in orphaned[0].detail
    assert "ghost" in orphaned[0].detail


def test_scan_finds_chats_of_deleted_and_missing_characters(tmp_path):
    db = make_install(tmp_path)
    seed_user(db)
    seed_character(db, "gone-soft", deleted=True)
    seed_character(db, "alive")
    insert_chat(db, "chat-soft", "gone-soft")
    insert_chat(db, "chat-dangling", "never-existed")
    insert_chat(db, "chat-live", "alive")
    insert_message(db, "m1", "chat-soft")
    insert_message(db, "m2", "chat-soft")
    report = scan_cleanup(db_path=db, base_dir=tmp_path, now=NOW)
    chats = report.by_category(CHATS_OF_DELETED_CHARACTERS)
    assert {i.item_id for i in chats} == {"chat-soft", "chat-dangling"}
    assert all(i.risk == "high" for i in chats)
    soft = next(i for i in chats if i.item_id == "chat-soft")
    assert "2 message(s)" in soft.detail
    assert "soft-deleted" in soft.detail


def test_stale_backups_keep_newest_of_each_kind_and_flag_unknowns(tmp_path):
    db = make_install(tmp_path)
    backups = tmp_path / "backups"
    backups.mkdir()
    old_db = backups / "runmal-backup-20260101T000000.db"
    new_db = backups / "runmal-backup-20260201T000000.db"
    old_full = backups / "runmal-full-backup-20260101T000000.zip"
    new_full = backups / "runmal-full-backup-20260201T000000.zip"
    mystery = backups / "someones-own-file.bin"
    for p in (old_db, new_db, old_full, new_full, mystery):
        p.write_bytes(b"data")
    set_age(old_db, 90)
    set_age(new_db, 60)  # also past threshold, but it is the newest db backup
    set_age(old_full, 90)
    set_age(new_full, 60)
    set_age(mystery, 90)

    report = scan_cleanup(db_path=db, base_dir=tmp_path, now=NOW)
    stale = {Path(i.path).name for i in report.by_category(STALE_BACKUPS)}
    assert stale == {old_db.name, old_full.name}
    unknown = report.by_category(UNRECOGNIZED_BACKUP_FILES)
    assert [Path(i.path).name for i in unknown] == [mystery.name]


def test_stale_staging_by_age(tmp_path):
    db = make_install(tmp_path)
    staging = tmp_path / "staging"
    (staging / "restore-old").mkdir(parents=True)
    (staging / "restore-old" / "runmal.db").write_bytes(b"staged")
    (staging / "restore-fresh").mkdir()
    (staging / "restore-fresh" / "runmal.db").write_bytes(b"staged")
    set_age(staging / "restore-old" / "runmal.db", 30)
    set_age(staging / "restore-old", 30)
    set_age(staging / "restore-fresh" / "runmal.db", 1)
    set_age(staging / "restore-fresh", 1)

    report = scan_cleanup(db_path=db, base_dir=tmp_path, now=NOW)
    stale = report.by_category(STALE_STAGING)
    assert len(stale) == 1
    assert stale[0].path.endswith("restore-old")
    assert stale[0].risk == "low"


def test_dry_run_removes_nothing(tmp_path):
    db = make_install(tmp_path)
    seed_user(db)
    orphan = asset_file(tmp_path, "ghost", "art.png")
    report = scan_cleanup(db_path=db, base_dir=tmp_path, now=NOW)
    result = clean_cleanup(report, now=NOW)
    assert result.dry_run
    assert len(result.planned) == 1
    assert result.removed == []
    assert orphan.exists()


def test_apply_removes_planned_files_and_keeps_the_rest(tmp_path):
    db = make_install(tmp_path)
    seed_user(db)
    seed_character(db, "c1", avatar="avatar.png")
    keep = asset_file(tmp_path, "c1", "avatar.png", b"live")
    extra = asset_file(tmp_path, "c1", "old.png")
    orphan_dir = tmp_path / "assets" / "characters" / "ghost"
    asset_file(tmp_path, "ghost", "art.png")
    staging_old = tmp_path / "staging" / "restore-old"
    staging_old.mkdir(parents=True)
    (staging_old / "x.db").write_bytes(b"s")
    set_age(staging_old / "x.db", 30)
    set_age(staging_old, 30)
    backups = tmp_path / "backups"
    backups.mkdir()
    old_b = backups / "runmal-backup-20260101T000000.db"
    new_b = backups / "runmal-backup-20260201T000000.db"
    old_b.write_bytes(b"o")
    new_b.write_bytes(b"n")
    set_age(old_b, 90)
    set_age(new_b, 60)

    report = scan_cleanup(db_path=db, base_dir=tmp_path, now=NOW)
    result = clean_cleanup(report, apply=True, now=NOW)
    assert not result.dry_run
    assert result.bytes_reclaimed > 0
    assert keep.exists()
    assert new_b.exists()
    assert not extra.exists()
    assert not orphan_dir.exists()
    assert not staging_old.exists()
    assert not old_b.exists()


def test_high_risk_chats_need_explicit_allowance(tmp_path):
    db = make_install(tmp_path)
    seed_user(db)
    seed_character(db, "gone-soft", deleted=True)
    insert_chat(db, "chat-soft", "gone-soft")
    insert_message(db, "m1", "chat-soft")
    seed(
        db,
        [
            (
                "INSERT INTO chat_summaries (id, user_id, chat_id, "
                "summary, created_at) VALUES ('s1', 'u1', 'chat-soft', "
                "'sum', ?)",
                (TS,),
            )
        ],
    )
    report = scan_cleanup(db_path=db, base_dir=tmp_path, now=NOW)

    refused = clean_cleanup(report, apply=True, now=NOW)
    assert refused.removed == []
    assert any("high-risk" in s["reason"] for s in refused.skipped)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0] == 1
    conn.close()

    allowed = clean_cleanup(report, apply=True, allow_high_risk=True, now=NOW)
    assert len(allowed.removed) == 1
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM chat_summaries").fetchone()[0] == 0
    conn.close()


def test_unrecognized_backup_files_are_never_removed(tmp_path):
    db = make_install(tmp_path)
    backups = tmp_path / "backups"
    backups.mkdir()
    mystery = backups / "precious.bin"
    mystery.write_bytes(b"keep me")
    set_age(mystery, 365)
    report = scan_cleanup(db_path=db, base_dir=tmp_path, now=NOW)
    result = clean_cleanup(report, apply=True, allow_high_risk=True, now=NOW)
    assert mystery.exists()
    assert any("never removable" in s["reason"] for s in result.skipped)


def test_revalidation_saves_a_character_who_came_back(tmp_path):
    db = make_install(tmp_path)
    seed_user(db)
    orphan_dir = tmp_path / "assets" / "characters" / "ghost"
    asset_file(tmp_path, "ghost", "art.png")
    report = scan_cleanup(db_path=db, base_dir=tmp_path, now=NOW)
    assert report.by_category(ORPHAN_CHARACTER_ASSETS)
    # The character is re-created between scan and apply.
    seed_character(db, "ghost")
    result = clean_cleanup(report, apply=True, now=NOW)
    assert result.removed == []
    assert orphan_dir.exists()
    assert any("no longer orphaned" in s["reason"] for s in result.skipped)


def test_missing_database_judges_no_orphans_but_still_scans_files(tmp_path):
    orphan_dir = tmp_path / "assets" / "characters" / "ghost"
    asset_file(tmp_path, "ghost", "art.png")
    staging_old = tmp_path / "staging" / "restore-old"
    staging_old.mkdir(parents=True)
    set_age(staging_old, 30)
    report = scan_cleanup(db_path=tmp_path / "runmal.db", base_dir=tmp_path, now=NOW)
    assert report.by_category(ORPHAN_CHARACTER_ASSETS) == []
    assert report.by_category(STALE_STAGING)
    reasons = " ".join(s["reason"] for s in report.skipped)
    assert "nothing is called orphan without the database" in reasons
    assert orphan_dir.exists()


def test_symlinked_asset_directory_is_never_touched(tmp_path):
    db = make_install(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep")
    link = tmp_path / "assets" / "characters" / "linky"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside, target_is_directory=True)
    report = scan_cleanup(db_path=db, base_dir=tmp_path, now=NOW)
    assert report.by_category(ORPHAN_CHARACTER_ASSETS) == []
    assert any("symlinked" in s["reason"] for s in report.skipped)
    result = clean_cleanup(report, apply=True, allow_high_risk=True, now=NOW)
    assert result.removed == []
    assert (outside / "precious.txt").exists()


def test_cleanup_cli_dry_run_apply_and_bad_category(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db = make_install(tmp_path)
    seed_user(db)
    orphan = asset_file(tmp_path, "ghost", "art.png")

    rc = runmal_main(["cleanup", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["result"]["dry_run"] is True
    cats = {i["category"] for i in out["scan"]["items"]}
    assert ORPHAN_CHARACTER_ASSETS in cats
    assert orphan.exists()

    rc = runmal_main(["cleanup", "--apply", "--category", ORPHAN_CHARACTER_ASSETS])
    assert rc == 0
    capsys.readouterr()
    assert not orphan.exists()
    assert not (tmp_path / "assets" / "characters" / "ghost").exists()

    rc = runmal_main(["cleanup", "--category", "nonsense"])
    assert rc == 2
    capsys.readouterr()
