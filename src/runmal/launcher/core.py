"""Cross-platform Rúnmál desktop-launcher lifecycle (D001/D003)."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runmal.auth import create_bootstrap_nonce, data_dir

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8098
STATE_FILENAME = "launcher_state.json"
LOG_FILENAME = "launcher-server.log"
START_TIMEOUT_SECONDS = 30.0


class LauncherError(RuntimeError):
    """Human-readable launcher failure."""


@dataclass(frozen=True)
class LaunchStatus:
    running: bool
    managed: bool
    port: int
    pid: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "managed": self.managed,
            "port": self.port,
            "pid": self.pid,
        }


def state_path() -> Path:
    return data_dir() / STATE_FILENAME


def log_path() -> Path:
    return data_dir() / LOG_FILENAME


def _write_state(pid: int, port: int) -> None:
    path = state_path()
    payload = {
        "pid": int(pid),
        "port": int(port),
        "started_at": int(time.time()),
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        # Windows ACLs are the real boundary there; chmod is best-effort.
        pass
    tmp.replace(path)


def _read_state() -> dict[str, Any] | None:
    path = state_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            "pid": int(payload["pid"]),
            "port": int(payload["port"]),
            "started_at": int(payload.get("started_at", 0)),
        }
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return None


def _clear_state() -> None:
    state_path().unlink(missing_ok=True)


def _health(port: int, *, timeout: float = 0.75) -> bool:
    url = f"http://{DEFAULT_HOST}:{port}/healthz"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("status") == "ok"
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return False


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((DEFAULT_HOST, port)) == 0


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        # Windows may reject signal 0 in some Python/runtime combinations.
        if os.name == "nt":
            return True
        return False
    return True


def _server_command(port: int) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "_serve", "--port", str(port)]
    return [
        sys.executable,
        "-m",
        "runmal.launcher",
        "_serve",
        "--port",
        str(port),
    ]


def _child_process_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    else:
        kwargs["start_new_session"] = True
    return kwargs


def status(port: int = DEFAULT_PORT) -> LaunchStatus:
    """Return local server/launcher ownership state."""
    running = _health(port)
    state = _read_state()
    if state and not _pid_exists(state["pid"]):
        _clear_state()
        state = None
    managed = bool(state and state["port"] == port and _pid_exists(state["pid"]))
    return LaunchStatus(
        running=running,
        managed=managed,
        port=port,
        pid=state["pid"] if managed and state else None,
    )


def start_server(
    port: int = DEFAULT_PORT,
    *,
    timeout: float = START_TIMEOUT_SECONDS,
) -> LaunchStatus:
    """Start the managed local server only when it is not already healthy."""
    current = status(port)
    if current.running:
        return current
    if _port_open(port):
        raise LauncherError(
            f"Port {port} is already in use by another application. "
            "Rúnmál was not started."
        )

    log = log_path().open("a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            _server_command(port),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            cwd=str(data_dir()),
            close_fds=os.name != "nt",
            **_child_process_kwargs(),
        )
    finally:
        log.close()

    _write_state(proc.pid, port)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            _clear_state()
            raise LauncherError(
                "Rúnmál stopped during startup. "
                f"See the launcher log at {log_path()}."
            )
        if _health(port):
            return LaunchStatus(running=True, managed=True, port=port, pid=proc.pid)
        time.sleep(0.15)

    _terminate_managed_pid(proc.pid)
    _clear_state()
    raise LauncherError(
        "Rúnmál did not become ready before the startup timeout. "
        f"See the launcher log at {log_path()}."
    )


def _terminate_managed_pid(pid: int) -> None:
    if not _pid_exists(pid):
        return
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            check=False,
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def stop_server(port: int = DEFAULT_PORT, *, timeout: float = 8.0) -> bool:
    """Stop only a server process previously recorded by this launcher."""
    state = _read_state()
    if not state or state["port"] != port:
        return False
    pid = state["pid"]
    if not _pid_exists(pid):
        _clear_state()
        return False

    _terminate_managed_pid(pid)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_exists(pid) or not _health(port):
            _clear_state()
            return True
        time.sleep(0.1)

    if os.name != "nt" and hasattr(signal, "SIGKILL"):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    _clear_state()
    return True


def restart_server(port: int = DEFAULT_PORT) -> LaunchStatus:
    stop_server(port)
    return start_server(port)


def bootstrap_url(port: int = DEFAULT_PORT) -> str:
    """Create a one-use browser bootstrap URL containing no permanent secret."""
    nonce = create_bootstrap_nonce()
    query = urllib.parse.urlencode({"nonce": nonce})
    return f"http://{DEFAULT_HOST}:{port}/launcher/bootstrap?{query}"


def open_runmal(port: int = DEFAULT_PORT, *, browser: bool = True) -> str:
    """Ensure Rúnmál is running and open an authenticated local browser session."""
    start_server(port)
    url = bootstrap_url(port)
    if browser:
        opened = webbrowser.open(url, new=2)
        if not opened:
            raise LauncherError(
                "Rúnmál started, but the default browser could not be opened. "
                f"Open this local address manually: {url}"
            )
    return url


def diagnostics_text(port: int = DEFAULT_PORT) -> str:
    """Return a copyable human-readable diagnostic report."""
    lines = [
        "Rúnmál Launcher Diagnostics",
        f"Platform: {sys.platform}",
        f"Python: {sys.version.split()[0]}",
        f"Executable: {sys.executable}",
        f"Data directory: {data_dir()}",
        f"Launcher log: {log_path()}",
    ]
    current = status(port)
    lines.append(f"Server: {'running' if current.running else 'stopped'}")
    lines.append(f"Launcher-managed: {'yes' if current.managed else 'no'}")
    if current.pid is not None:
        lines.append(f"PID: {current.pid}")

    try:
        from runmal.diagnostics.doctor import run_doctor

        report = run_doctor(port=port)
        lines.append("")
        lines.append("runmal doctor:")
        for finding in report.findings:
            lines.append(f"[{finding.status}] {finding.check}: {finding.detail}")
            if finding.action and finding.status != "ok":
                lines.append(f"  Action: {finding.action}")
    except Exception as exc:  # diagnostics must still be copyable on partial failure
        lines.append("")
        lines.append(f"Doctor could not complete: {type(exc).__name__}: {exc}")

    return "\n".join(lines)
