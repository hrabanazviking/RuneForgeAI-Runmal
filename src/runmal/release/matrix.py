"""Self-hosted platform matrix (S805, owner's ruling 2026-10-13).

S805's original shape was a hosted CI matrix (GitHub Actions). Volmarr
ruled that out — *"don't rely on Microsoft's AIs. Test it yourself and
don't worry about them"* — so the matrix runs on the project's own
hardware instead: this module executes the core test suite in the
current environment and records a durable, structured evidence report
(machine, OS, Python, command, suite result). ``runmal release matrix``
is the entry point; docs/PLATFORM_MATRIX.md is the human record.

One leg is one machine/environment. A leg that never ran is recorded
as not run — never inferred from another leg's result.
"""

from __future__ import annotations

import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

MATRIX_SCHEMA = "runmal.platform-matrix/v1"

#: The core suite: the ordinary test suite, exactly as a developer
#: runs it locally (``pytest -q`` over ``tests/`` per pyproject).
CORE_SUITE_ARGS: tuple[str, ...] = ("-m", "pytest", "-q")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def platform_environment(*, hostname: str | None = None) -> dict:
    """The evidence identity of this leg: machine, OS, Python."""
    uname = platform.uname()
    return {
        "hostname": hostname if hostname is not None else uname.node,
        "os": uname.system,
        "os_release": uname.release,
        "os_version": uname.version,
        "platform": platform.platform(),
        "machine": uname.machine,
        "processor": uname.processor or platform.processor() or "unknown",
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_executable": sys.executable,
    }


def core_suite_command(python: str | None = None) -> list[str]:
    return [python or sys.executable, *CORE_SUITE_ARGS]


_SUMMARY_RE = re.compile(r"(\d+ passed|\d+ failed|\d+ errors?|\d+ skipped|\d+ deselected)")


def _suite_summary(output: str) -> str:
    """The pytest summary line (the last result-shaped line), or the
    last non-empty line when the run died before reporting one."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in reversed(lines):
        if _SUMMARY_RE.search(line) and ("passed" in line or "failed" in line or "error" in line):
            return line
    return lines[-1] if lines else ""


@dataclass
class MatrixLeg:
    """One executed platform leg and its suite outcome."""

    environment: dict
    command: list[str]
    status: str  # "passed" | "failed"
    exit_code: int
    duration_s: float
    summary: str

    def to_dict(self) -> dict:
        return {
            "environment": self.environment,
            "command": self.command,
            "suite": {
                "status": self.status,
                "exit_code": self.exit_code,
                "duration_s": round(self.duration_s, 3),
                "summary": self.summary,
            },
        }


@dataclass
class MatrixReport:
    """The durable S805 evidence record for the legs that ran."""

    legs: list[MatrixLeg] = field(default_factory=list)
    generated_at: str = ""

    @property
    def passed(self) -> bool:
        return bool(self.legs) and all(leg.status == "passed" for leg in self.legs)

    def to_dict(self) -> dict:
        return {
            "schema": MATRIX_SCHEMA,
            "generated_at": self.generated_at,
            "hosting": "self-hosted",
            "hosted_ci": (
                "not used — GitHub Actions deliberately not used (owner's ruling, 2026-10-13)"
            ),
            "legs": [leg.to_dict() for leg in self.legs],
        }

    def summary(self) -> str:
        lines = ["platform matrix: " + ("PASS" if self.passed else "FAIL")]
        for leg in self.legs:
            env = leg.environment
            lines.append(
                f"  [{leg.status}] {env['hostname']} — {env['os']} "
                f"{env['os_release']} / {env['machine']} / Python "
                f"{env['python']}: {leg.summary}"
            )
        return "\n".join(lines)


def run_platform_matrix(
    *,
    root: Path | None = None,
    runner=None,
    python: str | None = None,
    timeout: int = 3600,
) -> MatrixReport:
    """Execute the core suite once, in THIS environment, and record
    the leg. ``runner`` is injectable for tests (same protocol as
    :func:`runmal.voice.install.run_install`'s runner)."""
    run = runner or subprocess.run
    command = core_suite_command(python)
    started = time.perf_counter()
    proc = run(
        command,
        cwd=str(root or _repo_root()),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    duration = time.perf_counter() - started
    output = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    leg = MatrixLeg(
        environment=platform_environment(),
        command=command,
        status="passed" if proc.returncode == 0 else "failed",
        exit_code=int(proc.returncode),
        duration_s=duration,
        summary=_suite_summary(output),
    )
    return MatrixReport(
        legs=[leg],
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
