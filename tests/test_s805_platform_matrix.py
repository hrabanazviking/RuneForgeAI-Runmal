"""S805 (roadmap, as redefined by Volmarr's 2026-10-13 ruling):
self-hosted platform matrix.

The matrix is a local harness, not hosted CI: ``runmal release
matrix`` runs the core suite in the current environment and records
a structured evidence leg (machine, OS, Python, command, result).
These tests drive the harness with a fake runner — the real leg is
executed on project hardware and recorded in docs/PLATFORM_MATRIX.md;
a unit test must never recurse into the full suite.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from runmal.__main__ import main as runmal_main
from runmal.release.matrix import (
    MATRIX_SCHEMA,
    core_suite_command,
    platform_environment,
    run_platform_matrix,
)


def _fake_runner(result):
    calls = []

    def runner(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return result

    runner.calls = calls
    return runner


def test_core_suite_command_is_the_ordinary_suite():
    command = core_suite_command()
    assert command[0] == sys.executable
    assert command[1:] == ["-m", "pytest", "-q"]


def test_environment_records_machine_os_and_python():
    env = platform_environment(hostname="forge-host")
    assert env["hostname"] == "forge-host"
    assert env["os"] and env["machine"]
    assert env["python"].count(".") >= 1
    assert env["python_executable"] == sys.executable


def test_passing_leg_records_full_evidence(tmp_path):
    runner = _fake_runner(
        SimpleNamespace(
            returncode=0,
            stdout="681 passed, 3 skipped in 40.22s\n",
            stderr="",
        )
    )
    report = run_platform_matrix(root=tmp_path, runner=runner)
    assert report.passed
    payload = report.to_dict()
    assert payload["schema"] == MATRIX_SCHEMA
    assert payload["hosting"] == "self-hosted"
    assert "GitHub Actions" in payload["hosted_ci"]
    leg = payload["legs"][0]
    assert leg["suite"]["status"] == "passed"
    assert leg["suite"]["exit_code"] == 0
    assert "681 passed, 3 skipped" in leg["suite"]["summary"]
    assert leg["command"][1:] == ["-m", "pytest", "-q"]
    assert runner.calls[0][1]["cwd"] == str(tmp_path)


def test_failing_leg_is_recorded_not_hidden(tmp_path):
    runner = _fake_runner(
        SimpleNamespace(
            returncode=1,
            stdout="2 failed, 679 passed in 12.00s\n",
            stderr="",
        )
    )
    report = run_platform_matrix(root=tmp_path, runner=runner)
    assert not report.passed
    leg = report.to_dict()["legs"][0]
    assert leg["suite"]["status"] == "failed"
    assert leg["suite"]["exit_code"] == 1
    assert "2 failed" in leg["suite"]["summary"]


def test_matrix_cli_writes_evidence_and_reports(monkeypatch, tmp_path, capsys):
    import runmal.release.matrix as matrix_module

    runner = _fake_runner(SimpleNamespace(returncode=0, stdout="5 passed in 0.10s\n", stderr=""))
    real_run = matrix_module.run_platform_matrix
    monkeypatch.setattr(
        matrix_module,
        "run_platform_matrix",
        lambda **kwargs: real_run(runner=runner, **kwargs),
    )
    out = tmp_path / "evidence.json"
    assert runmal_main(["release", "matrix", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "platform matrix: PASS" in text
    import json

    payload = json.loads(out.read_text())
    assert payload["schema"] == MATRIX_SCHEMA
    assert payload["legs"][0]["suite"]["status"] == "passed"
