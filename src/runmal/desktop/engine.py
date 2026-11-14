"""In-process engine lifecycle for the desktop shell (R-04).

This module is the shell's *host* seam, not a widget: it starts the
FastAPI engine in-process (uvicorn in a worker thread — the pattern
proven by ``scripts/desktop_spike.py`` in R-01), and reports status
from the REAL ``/healthz`` route, never from internal flags alone.
It replaces the Tk Control Center's start/stop/status job for the
desktop road (``runmal.launcher.core`` keeps serving the subprocess
launcher road).

Widgets never import this module's engine neighbours directly; they
hold an :class:`EngineHandle` and talk HTTP through
``runmal.desktop.client`` for everything else.
"""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass
from enum import StrEnum

import httpx


class EngineState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass(frozen=True)
class EngineStatus:
    state: EngineState
    base_url: str
    detail: str = ""

    @property
    def label(self) -> str:
        """Status-bar words: state is never carried by colour alone."""
        if self.state is EngineState.RUNNING:
            return "Engine: running (healthz ok)"
        if self.state is EngineState.STARTING:
            return "Engine: starting…"
        if self.state is EngineState.STOPPING:
            return "Engine: stopping…"
        if self.state is EngineState.FAILED:
            return f"Engine: failed — {self.detail}" if self.detail else "Engine: failed"
        return "Engine: stopped"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class EngineHandle:
    """Owns one in-process engine server (or none, when stopped)."""

    def __init__(self, *, port: int = 0, host: str = "127.0.0.1") -> None:
        self._host = host
        self._port = port or _free_port()
        self._server = None  # uvicorn.Server | None
        self._thread: threading.Thread | None = None
        self._failed_detail = ""

    @property
    def port(self) -> int:
        return self._port

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    # ------------------------------------------------------------- status

    def _healthz_ok(self, timeout: float = 1.5) -> bool:
        try:
            with httpx.Client(trust_env=False, timeout=timeout) as client:
                response = client.get(f"{self.base_url}/healthz")
            return response.status_code == 200 and (
                response.json().get("status") == "ok"
            )
        except Exception:
            return False

    def status(self) -> EngineStatus:
        """Live status: a running claim requires a real /healthz ok."""
        thread_alive = self._thread is not None and self._thread.is_alive()
        if thread_alive:
            if self._healthz_ok():
                return EngineStatus(EngineState.RUNNING, self.base_url)
            return EngineStatus(EngineState.STARTING, self.base_url)
        if self._server is not None and self._failed_detail:
            return EngineStatus(
                EngineState.FAILED, self.base_url, self._failed_detail
            )
        return EngineStatus(EngineState.STOPPED, self.base_url)

    @property
    def is_running(self) -> bool:
        return self.status().state is EngineState.RUNNING

    # ------------------------------------------------------------ lifecycle

    def start(self, *, timeout: float = 30.0) -> EngineStatus:
        """Start the engine in a worker thread; block until /healthz
        answers ok (or the timeout/failure makes the state FAILED)."""
        if self._thread is not None and self._thread.is_alive():
            return self.status()
        import uvicorn

        from runmal.app import create_app, default_session_factory

        self._failed_detail = ""
        config = uvicorn.Config(
            create_app(default_session_factory()),
            host=self._host,
            port=self._port,
            log_level="error",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, name="runmal-engine", daemon=True
        )
        self._thread.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._thread.is_alive():
                self._failed_detail = "engine thread exited during startup"
                return self.status()
            if self._healthz_ok(timeout=1.0):
                return self.status()
            time.sleep(0.1)
        self._failed_detail = "engine did not answer /healthz before timeout"
        return self.status()

    def stop(self, *, timeout: float = 10.0) -> EngineStatus:
        """Ask uvicorn to exit and join its thread. Idempotent."""
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None
        self._server = None
        self._failed_detail = ""
        return self.status()

    def restart(self, *, timeout: float = 30.0) -> EngineStatus:
        self.stop()
        return self.start(timeout=timeout)
