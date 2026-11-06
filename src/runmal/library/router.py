"""Bulk library import REST API (P-022).

One route: ``POST /library/imports`` (mounted at ``/api/v1`` by the
app factory, behind the local bearer credential like every other
router). The request is ``multipart/form-data`` with one repeated
``files`` part per file — a browser folder picker puts the file's
path relative to the picked folder in the part's filename, and that
relative path is part of the import's identity, so it is kept.

Safety: this router never accepts a server-side folder path (import
from a folder path is a CLI-only act — ``runmal library import``),
and an upload filename is never used as a filesystem path here. A
filename that tries to escape the picked folder (``..`` segments,
an absolute path, a drive prefix, a NUL byte) is refused as a
*skipped* entry in the report instead of being handed to the import
service: refusals and skips are data in the report, not HTTP errors.
The only HTTP error this route raises for a bad request is 400,
when the request carries no files at all. Partial success is
success: HTTP 200 with the bulk report as JSON.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session

try:  # The library package re-exports the service contract (P-022).
    from runmal.library import import_library_uploads
except ImportError:  # pragma: no cover - fallback if re-export lags
    from runmal.library.service import import_library_uploads

router = APIRouter(tags=["library"])

_TRUE_WORDS = {"1", "true", "yes", "on"}
_FALSE_WORDS = {"0", "false", "no", "off", ""}
_ENTRY_LIST_KEYS = ("entries", "outcomes", "results", "items", "files")


def _parse_dry_run(value: object) -> bool:
    if isinstance(value, bool):
        return value
    word = str(value).strip().lower()
    if word in _TRUE_WORDS:
        return True
    if word in _FALSE_WORDS:
        return False
    raise HTTPException(
        status_code=400, detail=f"unrecognised dry_run value: {value!r}"
    )


def _sanitise_upload_name(raw: str | None) -> tuple[str | None, str | None]:
    """Return ``(safe_relative_name, None)`` or ``(None, skip_reason)``.

    Keeps a relative path (``sub/card.json`` stays ``sub/card.json``);
    rejects anything that would escape the picked folder.
    """
    name = (raw or "").replace("\\", "/")
    if not name.strip():
        return None, "empty filename"
    if "\x00" in name:
        return None, "path traversal rejected: filename contains a NUL byte"
    if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        return None, f"path traversal rejected: absolute path {raw!r}"
    parts = [part for part in name.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return None, f"path traversal rejected: {raw!r} escapes the import folder"
    if not parts:
        return None, "empty filename"
    return "/".join(parts), None


def _skipped_entry(raw: str | None, reason: str) -> dict:
    """A report entry in the bulk report's own shape (models.BulkEntry
    via to_dict), plus the router's alias keys."""
    relpath = raw or ""
    filename = relpath.rsplit("/", 1)[-1]
    return {
        "relpath": relpath,
        "path": relpath,
        "source": relpath,
        "filename": filename,
        "size_bytes": 0,
        "sha256": "",
        "detected_kind": "unknown",
        "detected_format": None,
        "outcome": "skipped",
        "status": "skipped",
        "reason_code": "path_traversal",
        "reason": reason,
        "detail": reason,
        "repairs": [],
        "notes": [],
        "created_id": None,
        "created_name": None,
        "duplicate_of": None,
    }


def _bump(container: dict, key: str, amount: int) -> None:
    if isinstance(container.get(key), int):
        container[key] += amount


def _merge_skipped(payload: dict, skipped: list[dict]) -> dict:
    """Fold router-side skipped entries into a service report dict,
    keeping the report's totals honest: the entries land both in the
    entry list (outcome ``skipped``) and in the report's separate
    ``skipped`` list, and every totals spelling is bumped."""
    if not skipped:
        return payload
    list_key = next(
        (key for key in _ENTRY_LIST_KEYS if isinstance(payload.get(key), list)),
        "entries",
    )
    payload[list_key] = [*payload.get(list_key, []), *skipped]
    if isinstance(payload.get("skipped"), list):
        payload["skipped"] = [
            *payload["skipped"],
            *({"relpath": s["relpath"], "reason": s["reason"]} for s in skipped),
        ]
    for container in (payload, payload.get("totals")):
        if isinstance(container, dict):
            _bump(container, "total_seen", len(skipped))
            _bump(container, "seen", len(skipped))
            _bump(container, "total_skipped", len(skipped))
            _bump(container, "skipped", len(skipped))
    return payload


def _empty_report_payload(*, dry_run: bool) -> dict:
    """Report-shaped body for when every part was rejected by name
    sanitising, in the bulk report's own to_dict shape."""
    return {
        "batch_id": "",
        "source_label": "uploads",
        "dry_run": dry_run,
        "started_at": None,
        "finished_at": None,
        "totals": {
            "total_seen": 0,
            "accepted": 0,
            "repaired": 0,
            "refused": 0,
            "skipped": 0,
        },
        "entries": [],
        "skipped": [],
    }


@router.post("/library/imports")
async def import_library(
    files: list[UploadFile] | None = File(default=None),
    dry_run: str = Form("false"),
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Import a batch of card + lorebook files as one act (P-022).

    Returns the bulk report (accepted / repaired / refused / skipped,
    with reasons) as JSON with HTTP 200 — refusals are data. 400 only
    when the request itself is malformed: no files at all.
    """
    if not files:
        raise HTTPException(status_code=400, detail="no files supplied")
    is_dry_run = _parse_dry_run(dry_run)
    uploads: list[tuple[str, bytes]] = []
    skipped: list[dict] = []
    for upload in files:
        safe_name, reason = _sanitise_upload_name(upload.filename)
        if safe_name is None:
            skipped.append(_skipped_entry(upload.filename, reason or "unsafe filename"))
            continue
        uploads.append((safe_name, await upload.read()))
    if uploads:
        report = await import_library_uploads(session, user_id, uploads, dry_run=is_dry_run)
        payload = report.to_dict()
    else:
        payload = _empty_report_payload(dry_run=is_dry_run)
    return _merge_skipped(payload, skipped)
