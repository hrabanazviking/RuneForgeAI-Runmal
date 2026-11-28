"""W-10: account hardening + the agent door.

ACCOUNT HARDENING (webface-native; the desktop has no account
concept):
- Password change: current password required; on success the
  stored hash is replaced and EVERY session for the account is
  closed, including the caller's own - the words say so before
  and after. A wrong current password changes nothing.
- Recovery codes: a set of one-time codes per account, stored
  only as SHA-256 digests (the store's session pattern). The
  plaintext set is shown exactly once, at generation;
  regenerating deletes the previous set outright. The logged-out
  recovery road (username + one code + new password) consumes
  the code, sets the password and closes all sessions. Failed
  recovery attempts are throttled: 5 failures inside 15 minutes
  locks the road for that username until the window passes
  (a successful recovery clears the slate).
- Sessions list + sign-out-everywhere ride the store's real
  session rows (created/expires only; digests never display).

THE AGENT DOOR: the engine's bridge surface (S601/S602) IS an
HTTP door, but it is scoped per-chat-id, offers no discovery
(no characters list, no chats list/create), and its generation
road resolved pinned-else-fake with no guard (FIX-STUB). It is
therefore not, by itself, the door an agent can walk through to
meet the characters. The door built here is webface-native:
agent API tokens issued from the Account tab (named, plaintext
shown exactly once, digest-stored, revocable - revocation is
immediate), authenticating /agent/v1 roads (whoami, characters,
chats list/create, history, send->reply as one JSON exchange)
that ride the SAME guarded machinery as the human chat tab -
stub_guard decides the mind, so an unpinned chat answers with
the no-mind payload, never a stub. Scope law: an agent token
talks to characters ONLY. It is not a session: it cannot change
the password, manage tokens, or touch account roads at all.
The engine bridge road itself is hardened separately (the
FIX-STUB counterpart fix in runmal.bridge.conversation): an
unpinned bridge chat now refuses with a no_mind error instead
of streaming the fake default.
"""
from __future__ import annotations

import secrets

from . import stub_guard
from .engine import EngineError
from .security import digest, hash_password, verify_password

RECOVERY_CODE_COUNT = 10
RECOVERY_WINDOW_SECONDS = 15 * 60
RECOVERY_MAX_FAILURES = 5
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

CHANGE_WORDS = (
    "Changing your password closes every session for this "
    "account, including this one - you will log in fresh with "
    "the new password.")
RECOVERY_ONCE_WORDS = (
    "These codes are shown exactly once, now. Save them "
    "somewhere safe: each one can set a new password once, "
    "from the recovery page, and generating a new set makes "
    "every code in this set useless.")
TOKEN_ONCE_WORDS = (
    "This token is shown exactly once, now. Give it to the "
    "agent it is named for. It can talk to your characters; "
    "it cannot change your password or manage tokens, and "
    "revoking it stops it at once.")
AGENT_SCOPE_WORDS = (
    "An agent token talks to characters: whoami, the character "
    "list, chats (list, create, read, send). It does not "
    "administer this account.")


# ------------------------------------------------------------ passwords


def change_password(store, user: dict, current: str, new: str):
    """(ok, words). On success: hash replaced, ALL sessions
    closed (the caller logs in fresh). On any refusal nothing
    changes."""
    if not verify_password(current or "", user["pass_hash"]):
        return False, "The current password did not match; nothing changed."
    if len(new or "") < 8:
        return False, "The new password needs at least 8 characters; nothing changed."
    if new == current:
        return False, "The new password is the same as the current one; nothing changed."
    store.set_password_hash(user["id"], hash_password(new))
    store.close_all_sessions(user["id"])
    return True, ("Password changed. Every session for this account "
                  "was closed, including this one - log in with the "
                  "new password.")


# ------------------------------------------------------------ recovery codes


def _new_code() -> str:
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(12))
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"


def normalize_code(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def generate_recovery_codes(store, user_id: int) -> list:
    """Returns the PLAINTEXT set (shown exactly once). Only
    digests are stored; the previous set is invalidated."""
    codes = [_new_code() for _ in range(RECOVERY_CODE_COUNT)]
    store.replace_recovery_codes(
        user_id, [digest(normalize_code(c)) for c in codes])
    return codes


def recovery_locked(store, username: str) -> bool:
    return store.recovery_failures(
        username, RECOVERY_WINDOW_SECONDS) >= RECOVERY_MAX_FAILURES


def recover_account(store, username: str, code: str, new_password: str):
    """(ok, words). The code is consumed exactly once; reuse is
    refused. Success sets the password and closes all sessions."""
    username = (username or "").strip()
    if recovery_locked(store, username):
        return False, ("Too many failed recovery attempts for that "
                       "username; the recovery road is paused for a "
                       "while. Nothing changed.")
    user = store.get_user_by_name(username) if username else None
    row = None
    if user is not None:
        row = store.recovery_code_row(
            user["id"], digest(normalize_code(code)))
    if user is None or row is None or row["used_at"] is not None:
        store.record_recovery_failure(username)
        return False, ("That username and recovery code did not "
                       "work; nothing changed. A code works once, "
                       "and a newer set replaces the old one.")
    if len(new_password or "") < 8:
        return False, ("The new password needs at least 8 "
                       "characters; the code was not used.")
    if not store.mark_recovery_code_used(
            user["id"], digest(normalize_code(code))):
        store.record_recovery_failure(username)
        return False, ("That recovery code was already used; "
                       "nothing changed.")
    store.set_password_hash(user["id"], hash_password(new_password))
    store.close_all_sessions(user["id"])
    store.clear_recovery_failures(username)
    return True, ("Password set. Every session for the account was "
                  "closed - log in with the new password.")


# ------------------------------------------------------------ agent tokens


def create_agent_token(store, user_id: int, name: str):
    """(view, plaintext-once) or (None, words) on a refusal."""
    name = (name or "").strip()
    if not name:
        return None, "Give the token a name first - it is how you will know whose it is."
    if len(name) > 80:
        return None, "Token names are at most 80 characters."
    view, token = store.create_agent_token(user_id, name)
    return view, token


def token_view(row: dict) -> dict:
    return {
        "id": row["id"], "name": row["name"],
        "created_at": row["created_at"],
        "revoked_at": row["revoked_at"],
        "last_used_at": row["last_used_at"],
        "state": "revoked" if row["revoked_at"] else "active",
    }


def account_data(store, user: dict) -> dict:
    """Everything the Account page renders: sessions + tokens,
    name/date/state only - no digests, no plaintext."""
    return {
        "sessions": store.list_sessions(user["id"]),
        "tokens": [token_view(r) for r in store.list_agent_tokens(user["id"])],
    }


# ------------------------------------------------------------ agent conversation


def agent_send(engine, chat_id: str, content: str) -> dict:
    """One JSON send->reply exchange over the guarded machinery.
    Unpinned chat -> the no-mind payload, nothing appended. A
    real mind: user message lands, the composed stream runs,
    the reply lands only on a clean done (the chat tab's law)."""
    content = (content or "").strip()
    if not content:
        raise EngineError("write a message first", status=422)
    mind = stub_guard.chat_mind(engine, chat_id)
    if mind["state"] == "none":
        return stub_guard.no_mind_payload(mind)
    import uuid
    request_id = uuid.uuid4().hex
    engine.append_message(chat_id, "user", content)
    parts: list = []
    done_clean = False
    saw_error = False
    stubbed = False
    for kind, event in engine.stream_generate(chat_id, request_id):
        if kind == "started":
            if (event.get("backend_key") == stub_guard.FAKE_BACKEND_KIND
                    and mind["state"] != "demo"):
                stubbed = True
                try:
                    engine.cancel_generate(request_id)
                except EngineError:
                    pass
                break
            continue
        if kind == "token":
            text = event.get("text")
            if isinstance(text, str):
                parts.append(text)
        elif kind == "done":
            done_clean = True
        elif kind == "error":
            saw_error = True
    reply = "".join(parts)
    if stubbed:
        return stub_guard.no_mind_payload(mind)
    if done_clean and not saw_error and reply:
        saved = engine.append_message(chat_id, "assistant", reply)
        return {"type": "reply", "chat_id": chat_id, "reply": reply,
                "message": saved, "mind": mind["words"]}
    return {"type": "error", "chat_id": chat_id,
            "message": ("the stream ended without a clean done; your "
                        "message was saved but no reply was")}
