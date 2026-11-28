"""FIX-STUB guard: no webface user is ever answered by the engine's
fake/stub backend undisclosed.

The engine resolves generation for a chat from the chat's pinned
backend profile; with no pin it falls back to the deterministic
FakeChatBackend (backend kind "fake", scripted stub text) — an
honest offline default for tests and the desktop, whose own chat
surface labels it. The webface originally pinned nothing and said
nothing, so a real user could be answered by the stub under the
assistant's name. This module is the webface's one place that knows
the rule:

- a chat pinned to a REAL profile (chat_backend != "fake") answers
  for real;
- a chat pinned to a fake-kind profile is an explicit Demo choice
  and passes, labelled "Demo — not a real model";
- anything else (no pin, or a pin that no longer resolves) is
  NO MIND: generation must not run, nothing may be appended, and
  the hall says so in words and walks the user to connect a mind.

Backend-kind vocabulary (engine, runmal.backends.profiles):
CHAT_BACKENDS = ("fake", "ollama", "openrouter", "aesir",
"openai"); the resolved backend_key of the fake default is
"fake" (runmal.backends.fake.FakeChatBackend.backend_key).
Only "fake" is not a real mind.

Groups: a room has no profile of its own — its transcript lives in
the room's own chat row (groups.chat_id), and that chat's pin is
the room's mind, pinned through the ordinary per-chat pin road.
The engine's group deepening seam now honours that pin (FIX-STUB
counterpart fix); this guard refuses generation for a room whose
chat carries no real pin, exactly as for a one-to-one chat.

The bridge road shares the engine's resolution too; it is W-10
scope and not guarded here, but chat_mind()/no_mind_payload() are
the reusable pattern for it.
"""
from __future__ import annotations

from typing import Any

from .engine import EngineError

FAKE_BACKEND_KIND = "fake"
NO_MIND_WORDS = "No mind is connected to this chat yet"
DEMO_WORDS = "Demo — not a real model"
CONNECTIONS_PATH = "/connections"
FIRSTRUN_PATH = "/firstrun"


def is_demo_profile(profile: dict | None) -> bool:
    return bool(profile) and str(profile.get("chat_backend") or "") == FAKE_BACKEND_KIND


def is_real_profile(profile: dict | None) -> bool:
    if not profile:
        return False
    kind = str(profile.get("chat_backend") or "")
    return kind not in ("", FAKE_BACKEND_KIND)


def profile_view(profile: dict) -> dict:
    return {
        "id": str(profile.get("id") or ""),
        "name": str(profile.get("name") or ""),
        "chat_backend": str(profile.get("chat_backend") or ""),
        "chat_model": str(profile.get("chat_model") or ""),
        "is_demo": is_demo_profile(profile),
    }


def disclosure_words(mind: dict) -> str:
    """The persistent 'who answers this chat' line, per state."""
    state = mind.get("state")
    profile = mind.get("profile") or {}
    if state == "real":
        model = profile.get("chat_model") or profile.get("chat_backend") or ""
        return f"Answering: {profile.get('name') or profile.get('id')} · {model}"
    if state == "demo":
        return DEMO_WORDS
    return "No mind is connected to this chat yet."


def mind_for_chat(chat: dict, profiles: list, *, group_id: str = "") -> dict:
    """Pure resolution: chat row + profile rows -> the mind state."""
    by_id = {str(p.get("id") or ""): p for p in profiles if isinstance(p, dict)}
    pin = chat.get("backend_profile_id")
    pinned = by_id.get(str(pin)) if pin else None
    real = [profile_view(p) for p in profiles if is_real_profile(p)]
    if pinned is not None and is_real_profile(pinned):
        state, view = "real", profile_view(pinned)
    elif pinned is not None and is_demo_profile(pinned):
        state, view = "demo", profile_view(pinned)
    else:
        state, view = "none", None
    mind: dict[str, Any] = {
        "chat_id": str(chat.get("id") or ""),
        "state": state,
        "profile": view,
        "real_profiles": real,
        "has_real_profiles": bool(real),
    }
    if group_id:
        mind["group_id"] = group_id
    mind["words"] = disclosure_words(mind)
    mind["no_mind"] = no_mind_payload(mind) if state == "none" else None
    return mind


def no_mind_payload(mind: dict) -> dict:
    """The honest no-mind outcome every guarded road returns."""
    return {
        "type": "no_mind",
        "no_mind": True,
        "words": NO_MIND_WORDS,
        "message": NO_MIND_WORDS,
        "chat_id": mind.get("chat_id", ""),
        "group_id": mind.get("group_id", ""),
        "connect": [
            {"profile_id": p["id"], "name": p["name"],
             "chat_backend": p["chat_backend"], "chat_model": p["chat_model"]}
            for p in mind.get("real_profiles", [])
        ],
        "has_real_profiles": bool(mind.get("real_profiles")),
        "connections_url": CONNECTIONS_PATH,
        "firstrun_url": FIRSTRUN_PATH,
    }


# ------------------------------------------------------------ engine reads


def _get(engine, path: str) -> Any:
    return engine.request("GET", path)


def list_profiles(engine) -> list:
    rows = _get(engine, "/api/v1/backend-profiles")
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def get_chat(engine, chat_id: str) -> dict:
    chat = _get(engine, f"/api/v1/chats/{chat_id}")
    if not isinstance(chat, dict):
        raise EngineError("chat not found", status=404)
    return chat


def chat_mind(engine, chat_id: str) -> dict:
    return mind_for_chat(get_chat(engine, chat_id), list_profiles(engine))


def room_mind(engine, group_id: str) -> dict:
    group = _get(engine, f"/api/v1/groups/{group_id}")
    if not isinstance(group, dict):
        raise EngineError("group not found", status=404)
    chat_id = str(group.get("chat_id") or "")
    profiles = list_profiles(engine)
    if not chat_id:
        mind = mind_for_chat({}, profiles, group_id=group_id)
    else:
        mind = mind_for_chat(get_chat(engine, chat_id), profiles, group_id=group_id)
    mind["group_name"] = str(group.get("name") or "")
    return mind


def blocked_chat_payload(engine, chat_id: str) -> dict | None:
    """The no-mind payload when this chat must not generate, else None."""
    mind = chat_mind(engine, chat_id)
    return mind["no_mind"] if mind["state"] == "none" else None


def blocked_room_payload(engine, group_id: str) -> dict | None:
    mind = room_mind(engine, group_id)
    return mind["no_mind"] if mind["state"] == "none" else None
