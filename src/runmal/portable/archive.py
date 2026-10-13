"""Portable ``.runmal`` archive: export + validation (S801).

The archive is the provider/machine-independent user-data bundle of
BACKUP_AND_RECOVERY §3: a ZIP whose members are canonical JSON rows
(original IDs preserved) plus asset bytes, sealed by a manifest with a
SHA-256 per member. Restore/import is S802's surface; this module owns
the format, the export, and the validator.

Contents (owner-scoped): characters, chats (+messages), lorebooks
(+entries), memories (+sources +chunks: text and provenance, never the
derived vectors), sampling presets, backend profiles, connection
profiles, groups (+members), per-character voice profiles, character
asset files, and the public voice settings.

Exclusions, by policy (manifest records them):

- the ``secrets`` table — secret VALUES never enter an archive;
- backend-profile secret REFERENCES are blanked (installation-local;
  ``has_*_secret`` flags survive so the user knows to re-add them);
- bridge credentials and bridge operational state (outbox events,
  checkpoints, idempotency keys) — installation-local security state;
  bridges re-pair after a move;
- derived state: chat summaries, re-embedding jobs, embedding
  activations, FTS indexes and vector stores — rebuilt on restore.

As defense in depth, the exporter scans the finished members for any
of the owner's stored secret values appearing inside user content and
records only the COUNT in the manifest (``secret_scan_matches``); the
secrets themselves are never written anywhere.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal import __version__
from runmal.auth import data_dir
from runmal.db.migrations import MIGRATIONS
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
    SecretEntry,
)

FORMAT_NAME = "runmal-archive"
FORMAT_VERSION = 1
ARCHIVE_SUFFIX = ".runmal"
MANIFEST_NAME = "manifest.json"
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

#: Fields blanked on export (installation-local references, not values).
_BLANKED_FIELDS = {
    "backend_profiles": ("chat_secret_ref", "embedding_secret_ref"),
}


class ArchiveError(Exception):
    """An archive is malformed, unsafe, or of an unsupported version."""


@dataclass
class ArchiveInfo:
    path: str
    manifest: dict
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "manifest": self.manifest,
            "warnings": list(self.warnings),
        }


def _encode(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"__b64__": base64.b64encode(value).decode("ascii")}
    return value


def row_to_dict(obj) -> dict:
    """Serialize one ORM row by its table columns (canonical JSON)."""
    out = {}
    for col in obj.__table__.columns:
        out[col.name] = _encode(getattr(obj, col.name))
    table = obj.__table__.name
    for name in _BLANKED_FIELDS.get(table, ()):
        if out.get(name):
            out[f"has_{name}"] = True
            out[name] = ""
    return out


def _json_bytes(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


async def _collect_members(
    session: AsyncSession, user_id: str, base: Path
) -> tuple[dict[str, bytes], dict[str, int], list[str]]:
    members: dict[str, bytes] = {}
    counts: dict[str, int] = {}
    warnings: list[str] = []

    def put(name: str, payload) -> None:
        members[name] = _json_bytes(payload)

    characters = list(
        await session.scalars(
            select(Character).where(Character.user_id == user_id).order_by(Character.id)
        )
    )
    counts["characters"] = len(characters)
    for character in characters:
        put(f"characters/{character.id}.json", row_to_dict(character))
        if character.avatar_asset:
            asset_path = base / "assets" / "characters" / character.id / character.avatar_asset
            arcname = f"assets/characters/{character.id}/{character.avatar_asset}"
            if asset_path.is_file():
                members[arcname] = asset_path.read_bytes()
                counts["assets"] = counts.get("assets", 0) + 1
            else:
                warnings.append(
                    f"asset missing on disk, skipped: character {character.id} "
                    f"avatar {character.avatar_asset!r}"
                )

    voice_profiles = list(
        await session.scalars(
            select(CharacterVoiceProfile)
            .where(CharacterVoiceProfile.user_id == user_id)
            .order_by(CharacterVoiceProfile.character_id)
        )
    )
    counts["voice_profiles"] = len(voice_profiles)
    for vp in voice_profiles:
        put(f"voice_profiles/{vp.character_id}.json", row_to_dict(vp))

    chats = list(
        await session.scalars(select(Chat).where(Chat.user_id == user_id).order_by(Chat.id))
    )
    counts["chats"] = len(chats)
    counts["messages"] = 0
    for chat in chats:
        messages = list(
            await session.scalars(
                select(Message)
                .where(Message.chat_id == chat.id)
                .order_by(Message.created_at, Message.id)
            )
        )
        counts["messages"] += len(messages)
        put(
            f"chats/{chat.id}.json",
            {"chat": row_to_dict(chat), "messages": [row_to_dict(m) for m in messages]},
        )

    books = list(
        await session.scalars(
            select(Lorebook).where(Lorebook.user_id == user_id).order_by(Lorebook.id)
        )
    )
    counts["lorebooks"] = len(books)
    counts["lore_entries"] = 0
    for book in books:
        entries = list(
            await session.scalars(
                select(LoreEntry).where(LoreEntry.lorebook_id == book.id).order_by(LoreEntry.id)
            )
        )
        counts["lore_entries"] += len(entries)
        put(
            f"lorebooks/{book.id}.json",
            {"lorebook": row_to_dict(book), "entries": [row_to_dict(e) for e in entries]},
        )

    memories = list(
        await session.scalars(select(Memory).where(Memory.user_id == user_id).order_by(Memory.id))
    )
    counts["memories"] = len(memories)
    counts["memory_chunks"] = 0
    for memory in memories:
        sources = list(
            await session.scalars(select(MemorySource).where(MemorySource.memory_id == memory.id))
        )
        chunks = list(
            await session.scalars(
                select(MemoryChunk)
                .where(MemoryChunk.memory_id == memory.id)
                .order_by(MemoryChunk.chunk_index)
            )
        )
        counts["memory_chunks"] += len(chunks)
        put(
            f"memories/{memory.id}.json",
            {
                "memory": row_to_dict(memory),
                "sources": [row_to_dict(s) for s in sources],
                "chunks": [row_to_dict(c) for c in chunks],
            },
        )

    for kind, model, dirname in (
        ("presets", SamplingPreset, "presets"),
        ("backend_profiles", BackendProfile, "profiles"),
        ("connection_profiles", ConnectionProfile, "connections"),
    ):
        rows = list(
            await session.scalars(select(model).where(model.user_id == user_id).order_by(model.id))
        )
        counts[kind] = len(rows)
        for row in rows:
            put(f"{dirname}/{row.id}.json", row_to_dict(row))

    groups = list(
        await session.scalars(select(Group).where(Group.user_id == user_id).order_by(Group.id))
    )
    counts["groups"] = len(groups)
    for group in groups:
        group_members = list(
            await session.scalars(select(GroupMember).where(GroupMember.group_id == group.id))
        )
        put(
            f"groups/{group.id}.json",
            {
                "group": row_to_dict(group),
                "members": [row_to_dict(m) for m in group_members],
            },
        )

    settings_path = base / "voice_settings.json"
    public_settings: dict = {}
    if settings_path.is_file():
        try:
            public_settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            warnings.append("voice_settings.json unreadable; exported empty settings")
            public_settings = {}
    put("configuration/public-settings.json", {"voice_settings": public_settings})
    return members, counts, warnings


async def export_archive(
    session: AsyncSession,
    user_id: str,
    dest: str | Path,
    *,
    base_dir: Path | None = None,
) -> ArchiveInfo:
    """Export the owner's canonical data to a ``.runmal`` archive."""
    base = base_dir or data_dir()
    members, counts, warnings = await _collect_members(session, user_id, base)

    # Defense in depth: count stored secret values appearing in content.
    secret_values = [
        v
        for v in await session.scalars(
            select(SecretEntry.value).where(SecretEntry.user_id == user_id)
        )
        if v and len(v) >= 8
    ]
    secret_scan_matches = 0
    for blob in members.values():
        for value in secret_values:
            if value.encode("utf-8") in blob:
                secret_scan_matches += 1
                break

    manifest = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "app_version": __version__,
        "schema_revision": MIGRATIONS[-1][0],
        "exported_at": datetime.now(UTC).isoformat(),
        "contents": counts,
        "policy": {
            "secrets_included": False,
            "secret_references": "blanked",
            "derived_state_included": False,
            "excluded": [
                "secrets table (values never exported)",
                "bridge credentials and bridge operational state",
                "chat summaries, re-embedding jobs, embedding activations",
                "vector stores and FTS indexes (rebuilt on restore)",
            ],
            "secret_scan_matches": secret_scan_matches,
        },
        "checksums": {
            name: hashlib.sha256(blob).hexdigest() for name, blob in sorted(members.items())
        },
    }
    members[MANIFEST_NAME] = _json_bytes(manifest)

    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, members[name])
    dest_path.write_bytes(buffer.getvalue())
    return ArchiveInfo(path=str(dest_path), manifest=manifest, warnings=warnings)


def _check_member_name(name: str) -> None:
    if (
        name.startswith("/")
        or name.startswith("\\")
        or "\\" in name
        or any(part in ("..", "") for part in name.split("/"))
    ):
        raise ArchiveError(f"unsafe archive member name: {name!r}")


#: Required top-level keys per member directory (schema shape).
_MEMBER_SHAPES = {
    "characters": ("id",),
    "voice_profiles": ("character_id",),
    "presets": ("id",),
    "profiles": ("id",),
    "connections": ("id",),
    "chats": ("chat", "messages"),
    "lorebooks": ("lorebook", "entries"),
    "memories": ("memory", "sources", "chunks"),
    "groups": ("group", "members"),
    "configuration": (),
    "assets": (),
}


def validate_archive(path: str | Path) -> dict:
    """Validate a ``.runmal`` archive; returns its manifest.

    Raises ArchiveError with a precise reason for: unreadable zip,
    unsafe/duplicate member names, missing or malformed manifest,
    unsupported format version, checksum mismatches, unmanifested
    members, and member JSON that does not match the export schema.
    """
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArchiveError(f"not a readable archive: {exc}") from exc
    with zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            raise ArchiveError("duplicate member names in archive")
        for name in names:
            _check_member_name(name)
        if MANIFEST_NAME not in names:
            raise ArchiveError("manifest.json missing")
        try:
            manifest = json.loads(zf.read(MANIFEST_NAME))
        except (KeyError, json.JSONDecodeError) as exc:
            raise ArchiveError(f"manifest unreadable: {exc}") from exc
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT_NAME:
            raise ArchiveError("manifest format is not runmal-archive")
        version = manifest.get("format_version")
        if not isinstance(version, int) or version < 1:
            raise ArchiveError(f"invalid format_version: {version!r}")
        if version > FORMAT_VERSION:
            raise ArchiveError(
                f"unsupported archive format version {version} "
                f"(this build supports <= {FORMAT_VERSION}); upgrade Rúnmál "
                "or re-export with a supported version"
            )
        checksums = manifest.get("checksums")
        if not isinstance(checksums, dict) or not checksums:
            raise ArchiveError("manifest checksums missing")
        for name, expected in checksums.items():
            _check_member_name(name)
            if name not in names:
                raise ArchiveError(f"checksummed member missing: {name}")
            actual = hashlib.sha256(zf.read(name)).hexdigest()
            if actual != expected:
                raise ArchiveError(f"checksum mismatch: {name}")
        extra = set(names) - set(checksums) - {MANIFEST_NAME}
        if extra:
            raise ArchiveError(f"unmanifested members present: {sorted(extra)}")
        for name in checksums:
            top = name.split("/", 1)[0]
            required = _MEMBER_SHAPES.get(top)
            if required is None:
                raise ArchiveError(f"unknown member kind: {name}")
            if top == "assets":
                continue
            try:
                payload = json.loads(zf.read(name))
            except json.JSONDecodeError as exc:
                raise ArchiveError(f"member is not valid JSON: {name}") from exc
            if not isinstance(payload, dict) or any(key not in payload for key in required):
                raise ArchiveError(f"member does not match export schema: {name}")
    return manifest
