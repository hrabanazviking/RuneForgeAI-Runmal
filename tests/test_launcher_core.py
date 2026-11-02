"""D001/D003 acceptance: launcher lifecycle behavior."""

import sys

import pytest

from runmal.launcher import core


def test_bootstrap_url_contains_only_disposable_nonce(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(core, "create_bootstrap_nonce", lambda: "disposable-nonce")
    url = core.bootstrap_url(18098)
    assert url == (
        "http://127.0.0.1:18098/launcher/bootstrap?nonce=disposable-nonce"
    )
    assert "local_credential" not in url


def test_open_reuses_running_server_and_opens_browser(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    calls = {"started": 0, "opened": []}

    def fake_start(port: int):
        calls["started"] += 1
        return core.LaunchStatus(running=True, managed=False, port=port)

    monkeypatch.setattr(core, "start_server", fake_start)
    monkeypatch.setattr(core, "create_bootstrap_nonce", lambda: "one-use")
    monkeypatch.setattr(
        core.webbrowser,
        "open",
        lambda url, new=0: calls["opened"].append((url, new)) or True,
    )

    url = core.open_runmal(18098)
    assert calls["started"] == 1
    assert calls["opened"] == [(url, 2)]
    assert "one-use" in url


def test_start_does_not_spawn_duplicate_when_healthy(monkeypatch) -> None:
    healthy = core.LaunchStatus(running=True, managed=False, port=8098)
    monkeypatch.setattr(core, "status", lambda port=8098: healthy)

    def fail_popen(*args, **kwargs):
        raise AssertionError("Popen must not be called for an existing server")

    monkeypatch.setattr(core.subprocess, "Popen", fail_popen)
    assert core.start_server().running is True


def test_start_refuses_foreign_process_on_port(monkeypatch) -> None:
    stopped = core.LaunchStatus(running=False, managed=False, port=8098)
    monkeypatch.setattr(core, "status", lambda port=8098: stopped)
    monkeypatch.setattr(core, "_port_open", lambda port: True)
    with pytest.raises(core.LauncherError, match="already in use"):
        core.start_server()


def test_stop_never_kills_without_launcher_state(monkeypatch) -> None:
    monkeypatch.setattr(core, "_read_state", lambda: None)

    def fail_kill(pid: int):
        raise AssertionError("must not kill a process without managed state")

    monkeypatch.setattr(core, "_terminate_managed_pid", fail_kill)
    assert core.stop_server() is False


def test_server_command_source_mode(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    command = core._server_command(19000)
    assert command[:3] == [sys.executable, "-m", "runmal.launcher"]
    assert command[-2:] == ["--port", "19000"]


def test_server_command_frozen_mode(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    command = core._server_command(19000)
    assert command == [sys.executable, "_serve", "--port", "19000"]


def test_status_clears_dead_managed_process(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    core._write_state(424242, 8098)
    monkeypatch.setattr(core, "_health", lambda port: False)
    monkeypatch.setattr(core, "_pid_exists", lambda pid: False)
    result = core.status()
    assert result.running is False
    assert result.managed is False
    assert not core.state_path().exists()
