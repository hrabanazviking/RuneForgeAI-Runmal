"""W-11: the entry-box sweep - auto-save drafts (webface-local).

Volmarr's four parts for every data entry box in the web face
(2026-11-27 ~19:58 EST): auto-expanding size, Copy/Paste
buttons with no confirmation, a Clear button that asks first,
and auto-saved drafts. Parts 1-3 + the draft wiring live in the
ONE shared control, static/entrybox.js (the pwtoggle.js
precedent); this module is the server half of part 4.

DRAFTS follow the account (the W-09 appearance precedent):
they are stored server-side in the webface store, keyed by
(user, draft key), so a draft typed on one device is waiting on
the next. Draft roads are session-authenticated ONLY: an agent
token is not a session and cannot read or write drafts - the
agent door talks to characters, never to a human's unsent
writing.

Draft key shape: "<page>:<context>:<field>" - the context is
what makes the same field on two entities two drafts (the chat
composer is per chat; a character editor field is per
character; a group say box is per room). Keys are built by the
page scripts that own the context; boxes with no stable
identity carry no draft key and get parts 1-3 only.

Semantics (stated, per the slice brief):
- Save: debounced on input by the client; an empty text retires
  the draft (the store keeps no empty rows).
- Restore: the client fills the box from the draft ONLY when
  the box is still empty (or still holds exactly what it held
  when it was enhanced and that was empty) - a value the page
  itself loaded is never clobbered by a draft.
- Retire: the page's successful submit/send for that box, and
  a confirmed Clear, delete the draft.
"""
from __future__ import annotations

MAX_DRAFT_KEY = 200
MAX_DRAFT_TEXT = 200_000

DRAFT_WORDS = (
    "Drafts are saved on this account as you type and come "
    "back into the box when you return. Sending, saving, or a "
    "confirmed Clear retires the draft.")


def clean_key(raw) -> str | None:
    """A draft key, or None when it is not a usable key."""
    if not isinstance(raw, str):
        return None
    key = raw.strip()
    if not key or len(key) > MAX_DRAFT_KEY:
        return None
    if any(ch in key for ch in ("\x00", "\n", "\r")):
        return None
    return key


def save_draft(store, user_id: int, key, text):
    """(ok, payload). Empty text retires; oversize text is
    refused in words, never truncated silently."""
    k = clean_key(key)
    if k is None:
        return False, {"error": "a draft needs a usable key"}
    if not isinstance(text, str):
        return False, {"error": "a draft is text"}
    if len(text) > MAX_DRAFT_TEXT:
        return False, {"error": "that draft is too long to save"}
    store.set_draft(user_id, k, text)
    return True, {"key": k, "saved": text != "",
                  "words": "Draft saved." if text else "Draft retired."}


def get_draft(store, user_id: int, key):
    k = clean_key(key)
    if k is None:
        return {"key": None, "text": None}
    return {"key": k, "text": store.get_draft(user_id, k)}


def retire_draft(store, user_id: int, key):
    k = clean_key(key)
    if k is None:
        return {"key": None, "retired": False}
    return {"key": k, "retired": store.delete_draft(user_id, k)}


def list_drafts(store, user_id: int):
    return {"drafts": store.list_draft_keys(user_id),
            "words": DRAFT_WORDS}
