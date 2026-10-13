"""Archive import: restore a ``.runmal`` archive into a staging install (S802).

Implements the BACKUP_AND_RECOVERY §5 restore flow for portable
archives: validate (S801) → import canonical rows into a FRESH staging
database at migration HEAD with original IDs → verify referential
integrity (``PRAGMA foreign_key_check``) and manifest counts → stage
asset files and public settings beside it → produce an import report.

The staging database must not already exist: restore never merges
into or overwrites a working installation. On any failure the staging
directory is removed and the error propagates.
"""

from __future__ import annotations

import base64
import json
import shutil
import sqlite3
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime

from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import (
    BackendProfile,
    Character,
    CharacterVoiceProfile,
    Chat,
    ConnectionProfile,
    Group,
    GroupMember,
    Lorebook,
    LoreEntry,
    Memory,
    MemoryChunk,
    MemorySource,
    Message,
    SamplingPreset,
    User,
)
from runmal.portable.archive import ArchiveError, validate_archive

__all__ = ["ArchiveError", "ImportReport", "import_archive"]


@dataclass
class ImportReport:
    ok: bool
    archive: str
    staged_db: str
    staged_root: str
    schema_revision: str | None
    counts: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "archive": self.archive,
            "staged_db": self.staged_db,
            "staged_root": self.staged_root,
            "schema_revision": self.schema_revision,
            "counts": self.counts,
            "checks": [asdict(c) for c in self.checks],
            "warnings": list(self.warnings),
        }


@dataclass
class _Check:
    name: str
    ok: bool
    detail: str


def _decode(col, value):
    if isinstance(value, dict) and "__b64__" in value:
        return base64.b64decode(value["__b64__"])
    if isinstance(col.type, DateTime) and isinstance(value, str) and value:
        return datetime.fromisoformat(value)
    return value


def _row(model, payload: dict):
    kwargs = {}
    for col in model.__table__.columns:
        if col.name in payload:
            kwargs[col.name] = _decode(col, payload[col.name])
    return model(**kwargs)


#: (member dir, manifest count key, [(payload key, model), ...]) in FK order.
_STEPS = (
    ("users", "users", (("self", User),)),
    ("characters", "characters", (("self", Character),)),
    ("lorebooks", "lorebooks", (("lorebook", Lorebook), ("entries", LoreEntry))),
    ("presets", "presets", (("self", SamplingPreset),)),
    ("profiles", "backend_profiles", (("self", BackendProfile),)),
    ("connections", "connection_profiles", (("self", ConnectionProfile),)),
    ("groups", "groups", (("group", Group), ("members", GroupMember))),
    ("chats", "chats", (("chat", Chat), ("messages", Message))),
    (
        "memories",
        "memories",
        (("memory", Memory), ("sources", MemorySource), ("chunks", MemoryChunk)),
    ),
    ("voice_profiles", "voice_profiles", (("self", CharacterVoiceProfile),)),
)
_COUNT_KEYS = {
    "messages": "messages",
    "lore_entries": "lore_entries",
    "memory_chunks": "memory_chunks",
}


def _payload_rows(payload, key):
    if key == "self":
        return [payload]
    value = payload.get(key)
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


async def import_archive(archive_path: str | Path, staging_root: str | Path) -> ImportReport:
    """Import a validated archive into a fresh staging directory."""
    manifest = validate_archive(archive_path)  # raises ArchiveError
    root = Path(staging_root)
    if root.exists():
        raise ArchiveError(f"refusing to overwrite staging directory: {root}")
    root.mkdir(parents=True)
    staged_db = root / "runmal.db"
    checks: list[_Check] = [_Check("archive_validation", True, "S801 validator passed")]
    warnings: list[str] = []
    counts: dict[str, int] = {}
    try:
        migrate_to_head(staged_db)
        factory = create_session_factory(create_db_engine(staged_db))
        with zipfile.ZipFile(archive_path) as zf:
            names = zf.namelist()

            def read_json(name: str):
                return json.loads(zf.read(name))

            async with factory() as session:
                for dirname, _count_key, parts in _STEPS:
                    members = sorted(n for n in names if n.startswith(f"{dirname}/"))
                    for member in members:
                        payload = read_json(member)
                        for key, model in parts:
                            for row_payload in _payload_rows(payload, key):
                                session.add(_row(model, row_payload))
                                counts[model.__tablename__] = counts.get(model.__tablename__, 0) + 1
                            # Parts are listed parent-first; flush between
                            # them so FK parents exist before children,
                            # independent of unit-of-work insert sorting.
                            await session.flush()
                    await session.commit()
                # Public settings land beside the staged database.
                settings_member = "configuration/public-settings.json"
                if settings_member in names:
                    settings = read_json(settings_member)
                    voice = settings.get("voice_settings") or {}
                    if voice:
                        (root / "voice_settings.json").write_text(
                            json.dumps(voice), encoding="utf-8"
                        )
            asset_count = 0
            for name in names:
                if name.startswith("assets/"):
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(name))
                    asset_count += 1
            counts["assets"] = asset_count

        # Referential integrity on the staged file itself.
        conn = sqlite3.connect(f"file:{staged_db}?mode=ro", uri=True)
        try:
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            conn.close()
        if violations:
            raise ArchiveError(
                f"foreign key violations after import: {len(violations)} (first: {violations[0]})"
            )
        checks.append(_Check("foreign_keys", True, "foreign_key_check clean"))

        expected = manifest.get("contents") or {}
        mismatches = []
        table_for = {
            "users": "users",
            "characters": "characters",
            "chats": "chats",
            "messages": "messages",
            "lorebooks": "lorebooks",
            "lore_entries": "lore_entries",
            "memories": "memories",
            "memory_chunks": "memory_chunks",
            "presets": "sampling_presets",
            "backend_profiles": "backend_profiles",
            "groups": "groups",
            "voice_profiles": "character_voice_profiles",
            "assets": "assets",
        }
        for key, table in table_for.items():
            if key in expected and expected[key] != counts.get(table, 0):
                mismatches.append(
                    f"{key}: manifest {expected[key]} vs imported {counts.get(table, 0)}"
                )
        if mismatches:
            raise ArchiveError(f"import count mismatches: {mismatches}")
        checks.append(_Check("manifest_counts", True, "all counts match manifest"))
        if manifest.get("schema_revision") not in (None, _head_revision()):
            warnings.append(
                f"archive schema revision {manifest.get('schema_revision')!r} "
                f"predates HEAD {_head_revision()!r}; rows imported into the "
                "HEAD schema (columns are name-matched)"
            )
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return ImportReport(
        ok=True,
        archive=str(archive_path),
        staged_db=str(staged_db),
        staged_root=str(root),
        schema_revision=_head_revision(),
        counts=counts,
        checks=checks,
        warnings=warnings,
    )


def _head_revision() -> str:
    from runmal.db.migrations import MIGRATIONS

    return MIGRATIONS[-1][0]
