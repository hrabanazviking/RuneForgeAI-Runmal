"""0029 — lorebook scan windows (P-037).

Scan depth & context windows become stored data: a book's
scan settings grow ``lorebooks.scan_mode`` (TEXT, the window
vocabulary of ``runmal.lorebooks.windows`` -- ``depth`` scans
the last ``scan_depth`` messages, ``whole_chat`` scans them
all) and ``lorebooks.scan_external_context`` (INTEGER bool:
whether caller-supplied external context joins the scan
window). Both default to the pre-P-037 behaviour (depth mode,
external off), so every existing book scans exactly as it did
before this migration runs.

NUMBERING: P-037 banks FIRST in roadmap order (the keeper's
wave plan), so 0029 is expected to stand as numbered; P-038
builds concurrently on team-02, and if it claims a migration
number too, the keeper composes the chain at banking (the
0026 -> 0027 -> 0028 precedent).
"""
from __future__ import annotations
import sqlite3

REVISION = "0029"
DESCRIPTION = "lorebooks scan_mode + scan_external_context (scan depth & context windows P-037)"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute(
        "ALTER TABLE lorebooks ADD COLUMN scan_mode TEXT NOT NULL DEFAULT 'depth'"
    )
    conn.execute(
        "ALTER TABLE lorebooks ADD COLUMN scan_external_context INTEGER NOT NULL DEFAULT 0"
    )
