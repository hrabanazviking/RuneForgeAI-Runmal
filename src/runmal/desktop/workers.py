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


class _StreamSignals(QObject):
    event = Signal(object)
    finished = Signal(object)
    failed = Signal(str)


class StreamWorker(QRunnable):
    """Run a streaming callable off-thread, forwarding each event.

    ``fn`` receives one ``emit`` callable and returns the stream's
    final result; every ``emit(event)`` crosses to the GUI thread as
    the ``event`` signal, in order, so the window can render tokens
    as they arrive instead of only at the end (R-06)."""

    def __init__(self, fn: Callable[[Callable[[Any], None]], Any]) -> None:
        super().__init__()
        self._fn = fn
        self.signals = _StreamSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self._fn(self.signals.event.emit)
        except Exception as exc:  # surfaced as words, never a freeze
            self.signals.failed.emit(f"{exc.__class__.__name__}: {exc}")
            return
        self.signals.finished.emit(result)


def run_stream(
    fn: Callable[[Callable[[Any], None]], Any],
    on_event: Callable[[Any], None],
    on_result: Callable[[Any], None],
    on_error: Callable[[str], None] | None = None,
) -> StreamWorker:
    """Schedule a streaming callable on the global thread pool."""
    worker = StreamWorker(fn)
    worker.signals.event.connect(on_event)
    worker.signals.finished.connect(on_result)
    if on_error is not None:
        worker.signals.failed.connect(on_error)
    QThreadPool.globalInstance().start(worker)
    return worker


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
