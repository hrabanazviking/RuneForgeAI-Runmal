"""Qt worker-thread adapters for the client layer (R-04).

Architecture law: no network call runs on the GUI thread. Widgets
hand a plain callable (usually a ``RunmalClient`` method bundle) to
:func:`run_async`; it executes in the global ``QThreadPool`` and the
result comes back through Qt signals, which Qt delivers on the GUI
thread. This module is the only client-adjacent module that imports
Qt — the client core itself stays Qt-free.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class _WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class CallableWorker(QRunnable):
    """Run ``fn()`` off-thread; emit its result or error as signals."""

    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:  # surfaced as words, never a freeze
            self.signals.failed.emit(f"{exc.__class__.__name__}: {exc}")
            return
        self.signals.finished.emit(result)


def run_async(
    fn: Callable[[], Any],
    on_result: Callable[[Any], None],
    on_error: Callable[[str], None] | None = None,
) -> CallableWorker:
    """Schedule ``fn`` on the global thread pool with signal callbacks.

    Returns the worker so callers can keep a reference (Qt requires
    the Python object to outlive its pool run).
    """
    worker = CallableWorker(fn)
    worker.signals.finished.connect(on_result)
    if on_error is not None:
        worker.signals.failed.connect(on_error)
    QThreadPool.globalInstance().start(worker)
    return worker
