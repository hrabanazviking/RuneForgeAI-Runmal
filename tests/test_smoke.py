"""S101 smoke tests: the scaffold is real and runnable."""

import subprocess
import sys

import runmal


def test_package_imports_and_version() -> None:
    assert runmal.__version__ == "0.1.0"


def test_cli_help_exits_zero() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "runmal", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0
    assert "Rúnmál" in proc.stdout


def test_cli_version_reports_version() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "runmal", "--version"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0
    assert runmal.__version__ in proc.stdout
