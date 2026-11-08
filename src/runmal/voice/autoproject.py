"""Voice auto-projection host (P-104, Part VII - DERIVED scope).

P-103 landed projection as an EXPLICIT road and named this
slice in its honest limitations: "An async auto-projecting
host is a later slice's design." This module is that host.

The design constraint P-102/P-103 both state stands: the
live controller is synchronous and DB-free, so no projection
hook lives inside it. Auto-projection lives HERE, in the
async host layer, and the HTTP roads (live speak / live stop
/ the P-101 manual turns road) call it after a turn has been
recorded and persisted:

- opt-in per session: ``VoiceSession.auto_project`` (durable
  in the P-101 JSON store, default False). A session that
  never opted in behaves exactly as P-103 left it.
- the landing itself is P-103's one service
  (``projection.project_session_turns``) — same heard-text
  law, same provenance, same idempotency. This module adds
  no second landing road; it only decides WHEN the one road
  is walked and reports what happened.
- never raises: the turn is persisted BEFORE projection is
  attempted, and a projection failure (the chat is gone, a
  store write fails) is reported in the returned dict with
  its plain reason. The manual P-103 road can always retry,
  because projection is idempotent and resumable.

In-process hosts that drive ``LiveVoiceController`` directly
call :func:`autoproject_session` after turns complete — the
same function the HTTP host calls; there is no other magic.
"""

from __future__ import annotations

from runmal.voice import projection as proj_mod

__all__ = [
    "pending_turns",
    "autoproject_status",
    "autoproject_session",
]


def pending_turns(session) -> int:
    """Turns projection has not fully considered yet (pure)."""
    return sum(1 for t in session.turns if not t.projected)


def autoproject_status(session) -> dict:
    """The auto-projection view of one session, as data (pure)."""
    status = proj_mod.projection_status(session)
    return {
        "session_id": session.session_id,
        "chat_id": session.chat_id,
        "auto_project": bool(getattr(session, "auto_project", False)),
        "pending_turns": pending_turns(session),
        "turns_total": status["turns_total"],
        "turns_projected": status["turns_projected"],
        "messages_projected": status["messages_projected"],
    }


async def autoproject_session(db, *, session, store=None) -> dict:
    """Project one session's pending turns IF it opted in.

    ``db`` is an AsyncSession; ``session`` is a P-101
    VoiceSession; ``store`` is saved by the projection
    service after every turn, as in P-103. Returns a report:
    {enabled, attempted, ok, projected_turns,
    messages_created, no_content_turns} plus ``reason`` when
    nothing was attempted and ``error`` when an attempt
    failed. NEVER raises (see the module docstring).
    """
    report = {
        "enabled": bool(getattr(session, "auto_project", False)),
        "attempted": False,
        "ok": True,
        "projected_turns": 0,
        "messages_created": 0,
        "no_content_turns": 0,
    }
    if not report["enabled"]:
        report["reason"] = "auto-projection is not enabled for this session"
        return report
    if pending_turns(session) == 0:
        report["reason"] = "no unprojected turns"
        return report
    report["attempted"] = True
    try:
        landed = await proj_mod.project_session_turns(
            db, user_id=session.user_id, session=session, store=store)
    except Exception as exc:  # failure is reported, never hidden
        report["ok"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
        return report
    report["projected_turns"] = landed["projected_turns"]
    report["messages_created"] = landed["messages_created"]
    report["no_content_turns"] = landed["no_content_turns"]
    return report
