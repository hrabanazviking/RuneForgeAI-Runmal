"""Backups logic for the desktop shell (R-14) — Qt-free.

The words over the engine's backup surface (S114 + S802):
database backups and full bundles, created online while the
engine serves, and restore-STAGED — never applied. (The
engine's listing names database backups only; a full bundle
is known by the name its create road returned.) Staging verifies the copy and
leaves the live installation untouched; swapping a staged
restore into place is a separate, deliberate act outside this
surface, and the words here say so.
"""

from __future__ import annotations

from typing import Any

from runmal.desktop.client import BackupView, RunmalClient


def _size_words(size_bytes: int) -> str:
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.1f} MB"
    if size_bytes >= 1_000:
        return f"{size_bytes / 1_000:.1f} KB"
    return f"{size_bytes} bytes"


def backup_line(view: BackupView) -> str:
    """One backup, one line: kind, name, size, and the stamps
    the row's shape carries (verified info rows know their
    schema revision; listing rows know their modified time)."""
    bits = [
        "full backup" if view.kind == "full" else "database backup",
        view.name or "(unnamed)",
    ]
    if view.size_bytes:
        bits.append(_size_words(view.size_bytes))
    if view.schema_revision:
        bits.append(f"schema {view.schema_revision}")
    if view.asset_files is not None:
        bits.append(f"{view.asset_files} asset file(s)")
    stamp = view.created_at or view.modified_at
    if stamp:
        bits.append(stamp)
    if view.secrets_included:
        bits.append("WARNING: claims secrets included")
    return " · ".join(bits)


def backups_words(views: list[BackupView]) -> str:
    """The backups pane: the count, then one line per backup —
    or the honest empty state."""
    if not views:
        return (
            "No backups yet. A backup copies the live database "
            "safely while Rúnmál runs; a full backup bundles the "
            "database and the asset tree into one sealed file."
        )
    lines = [f"{len(views)} backup(s) on disk:"]
    lines.extend(f"- {backup_line(v)}" for v in views)
    return "\n".join(lines)


def stage_words(result: dict[str, Any]) -> str:
    """The staging verdict in words, for either staging road.

    A database stage answers the staged copy's verified info
    document; a full stage answers the restore report (checks,
    counts, warnings). Both end with the discipline stated
    plainly: staging never touches the live installation."""
    if not result:
        return "Staging returned nothing."
    lines: list[str] = []
    if "bundle" in result or "staged_db" in result:
        ok = bool(result.get("ok"))
        lines.append(
            "Full backup staged and verified."
            if ok
            else "Full backup staging did not pass."
        )
        staged_db = result.get("staged_db")
        if staged_db:
            lines.append(f"Staged database: {staged_db}")
        staged_assets = result.get("staged_assets_dir")
        if staged_assets:
            lines.append(f"Staged assets: {staged_assets}")
        revision = result.get("schema_revision")
        if revision:
            lines.append(f"Schema revision: {revision}")
        counts = result.get("counts")
        if isinstance(counts, dict) and counts:
            counted = ", ".join(
                f"{k}: {counts[k]}" for k in sorted(counts)
            )
            lines.append(f"Contents: {counted}")
        checks = result.get("checks")
        if isinstance(checks, list):
            for check in checks:
                if not isinstance(check, dict):
                    continue
                mark = "ok" if check.get("ok") else "FAILED"
                lines.append(
                    f"- check {check.get('name', '')}: {mark}"
                    f" — {check.get('detail', '')}"
                )
        warnings = result.get("warnings")
        if isinstance(warnings, list):
            lines.extend(
                f"Warning: {w}" for w in warnings if isinstance(w, str)
            )
    else:
        lines.append("Backup staged and verified.")
        name = result.get("name")
        if name:
            lines.append(f"Staged copy: {name}")
        path = result.get("path")
        if path:
            lines.append(f"At: {path}")
        revision = result.get("schema_revision")
        if revision:
            lines.append(f"Schema revision: {revision}")
    lines.append(
        "The live installation was not touched — staging only "
        "proves the backup can be restored."
    )
    return "\n".join(lines)


class BackupFlow:
    """The Backups dialog's verbs over the typed client."""

    def __init__(self, client: RunmalClient) -> None:
        self._client = client

    def list_backups(self) -> list[BackupView]:
        return self._client.list_backups()

    def create_backup(self) -> BackupView:
        return self._client.create_backup()

    def create_full_backup(self) -> BackupView:
        return self._client.create_full_backup()

    def stage_backup(self, filename: str) -> dict[str, Any]:
        return self._client.stage_backup(filename)

    def stage_full_backup(self, filename: str) -> dict[str, Any]:
        return self._client.stage_full_backup(filename)

    def import_archive(self, path: str) -> dict[str, Any]:
        return self._client.import_archive(path)
