"""Release consistency check (S807) — the dry-run release gate.

A release is four version facts that must agree, plus the notes that
explain it:

1. the application version (``pyproject.toml`` == ``runmal.__version__``),
2. the portable-archive format version (S801 ``FORMAT_VERSION``),
3. the database schema revision at migration HEAD,
4. a CHANGELOG entry for the application version being released.

This check is a DRY RUN: it verifies and reports, changes nothing.
``runmal release check`` exits non-zero when any fact disagrees, so a
desynced tree cannot be tagged by accident.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from runmal import __version__
from runmal.db.migrations import MIGRATIONS
from runmal.portable.archive import FORMAT_VERSION as ARCHIVE_FORMAT_VERSION


@dataclass
class ConsistencyFinding:
    fact: str
    ok: bool
    detail: str


@dataclass
class ReleaseCheck:
    findings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(f.ok for f in self.findings)

    def summary(self) -> str:
        lines = ["release check: " + ("OK" if self.ok else "DESYNCED")]
        for finding in self.findings:
            mark = "ok " if finding.ok else "BAD"
            lines.append(f"  [{mark}] {finding.fact}: {finding.detail}")
        return "\n".join(lines)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _pyproject_version(root: Path) -> str | None:
    try:
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        return data.get("project", {}).get("version")
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _changelog_has_entry(root: Path, version: str) -> bool:
    try:
        text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(re.search(rf"^## \[{re.escape(version)}\]", text, re.MULTILINE))


def check_release_consistency(
    *,
    root: Path | None = None,
    app_version: str | None = None,
    pyproject_version: str | None = None,
    archive_format_version: int | None = None,
    schema_revision: str | None = None,
    changelog_ok: bool | None = None,
) -> ReleaseCheck:
    """Verify the four release facts agree. Parameters override the
    live values so tests can inject a desync without touching files."""
    root = root or _repo_root()
    app = app_version if app_version is not None else __version__
    pyv = pyproject_version if pyproject_version is not None else _pyproject_version(root)
    archive_v = (
        archive_format_version if archive_format_version is not None else ARCHIVE_FORMAT_VERSION
    )
    schema = schema_revision if schema_revision is not None else MIGRATIONS[-1][0]
    has_entry = changelog_ok if changelog_ok is not None else _changelog_has_entry(root, app)
    check = ReleaseCheck()
    check.findings.append(
        ConsistencyFinding(
            "app_version",
            pyv == app and pyv is not None,
            f"pyproject={pyv!r} package={app!r}",
        )
    )
    check.findings.append(
        ConsistencyFinding(
            "archive_format_version",
            isinstance(archive_v, int) and archive_v >= 1,
            f"runmal-archive format v{archive_v} (S801)",
        )
    )
    check.findings.append(
        ConsistencyFinding(
            "schema_revision",
            bool(schema) and schema == MIGRATIONS[-1][0],
            f"migration HEAD {schema} of {len(MIGRATIONS)} revisions",
        )
    )
    check.findings.append(
        ConsistencyFinding(
            "changelog_entry",
            bool(has_entry),
            f"CHANGELOG.md {'has' if has_entry else 'LACKS'} a [{app}] entry",
        )
    )
    return check
