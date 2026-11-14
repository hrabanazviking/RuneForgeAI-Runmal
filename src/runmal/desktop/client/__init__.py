"""Desktop client layer (R-04): the ONLY road from widgets to the engine.

Architecture law (plan §2.2): widgets never import engine services and
never touch SQL. Every engine interaction goes through this package
over the same HTTP contract the engine tests prove. This package is
Qt-free by construction — it is importable and unit-testable on hosts
with no PySide6 installed; Qt worker adapters live in
``runmal.desktop.workers``.

Auth road (chosen here, documented in
``docs/DESKTOP_SHELL_R04_2026-11-14.md``): the desktop shell runs
in-process, in the same OS user account as the engine, so it reads
the owner-only local credential (``runmal.auth``) in-process and
sends it as a bearer token. The launcher bootstrap-nonce ->
session-cookie road exists for *browsers*, which cannot read that
file; it is also implemented here (``DesktopSession.from_bootstrap``)
for completeness and tested, but it is not the desktop default: it
costs a nonce exchange and cookie-origin checks buy nothing inside
one trusted local process. The credential value is held only in
memory, is never logged, and never appears in reprs or errors
(INV-023).
"""

from runmal.desktop.client.core import RunmalClient, fetch_snapshot
from runmal.desktop.client.errors import (
    ApiError,
    AuthError,
    ClientError,
    NotFoundError,
    TransportError,
)
from runmal.desktop.client.models import (
    AuthorsNoteView,
    BackendProfile,
    CharacterSummary,
    ChatSummary,
    CheckpointView,
    EngineSnapshot,
    FirstRunState,
    GeneratedReply,
    HealthStatus,
    ImportOutcome,
    MessageView,
    PersonaView,
    PresetSummary,
    SearchHitView,
    StreamEvent,
    UndoEntryView,
    detect_first_run,
)
from runmal.desktop.client.session import DesktopSession

__all__ = [
    "ApiError",
    "AuthError",
    "AuthorsNoteView",
    "BackendProfile",
    "CharacterSummary",
    "ChatSummary",
    "CheckpointView",
    "ClientError",
    "DesktopSession",
    "EngineSnapshot",
    "FirstRunState",
    "GeneratedReply",
    "HealthStatus",
    "ImportOutcome",
    "MessageView",
    "NotFoundError",
    "PersonaView",
    "PresetSummary",
    "RunmalClient",
    "SearchHitView",
    "StreamEvent",
    "TransportError",
    "UndoEntryView",
    "detect_first_run",
    "fetch_snapshot",
]
