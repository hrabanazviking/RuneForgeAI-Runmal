"""W-03 compositions over the engine API (the R-07 + R-11 roads).

Chat actions and group rooms, composed exactly as the desktop
shell composes them (chat_logic.ChatFlow / group_logic.GroupFlow):

- pin state is verified by re-reading the pinned list, never
  assumed from the pin call's own answer;
- regenerate is the desktop's lossless composition (journaled
  delete -> composed stream -> land only on a clean finish;
  otherwise restore via the undo journal, re-append fallback);
- the room deepening save lays the form's fields over the stored
  document so engine ``state`` and unknown keys ride through;
- every result the UI shows is rendered into plain words here
  (speaker names, pick + reason, presence, peek source) so no
  meaning rides on colour alone.

No new engine routes: everything goes through the existing
chats/*, groups/* and /group roads via the engine client.
"""
from __future__ import annotations

from typing import Any

from .engine import EngineError

# ------------------------------------------------------------ words

POLICIES: tuple[tuple[str, str], ...] = (
    ("natural", "Natural — mentions and the flow of talk decide"),
    ("list", "In order — take turns round the roster"),
    ("pooled", "Pooled — weighted by talkativeness"),
    ("manual", "Manual — you pick each speaker"),
)

GENERATION_MODES: tuple[tuple[str, str], ...] = (
    ("swap", "Swap — one voice at a time, in turn"),
    ("join", "Join — members speak into one shared reply"),
)

ACTIVATIONS: tuple[tuple[str, str], ...] = (
    ("default", "Default — the strategy may pick them"),
    ("force", "Force — pick them whenever possible"),
    ("never", "Never — never pick them"),
)


def policy_label(policy: str) -> str:
    for key, label in POLICIES:
        if key == policy:
            return label
    return policy


def message_label(message: dict) -> str:
    """One selectable row for a chat message, in words: role,
    swipe position and pin state are all spelled out."""
    role = str(message.get("role") or "")
    content = str(message.get("content") or "")
    snippet = content if len(content) <= 80 else content[:77] + "…"
    bits = [f"{role}: {snippet}" if role else snippet]
    swipes = message.get("swipes")
    deck = len(swipes) if isinstance(swipes, list) else 0
    if deck > 1:
        active = message.get("swipe_id", 0)
        active = active if isinstance(active, int) else 0
        bits.append(f"swipe {active + 1} of {deck}")
    if message.get("pinned"):
        bits.append("pinned")
    return " · ".join(bits)


def turn_words(result: dict) -> str:
    """The words for one group ``next`` result: pick + reason."""
    if not result:
        return "No turn ran."
    name = result.get("speaker_name") or result.get("speaker_id")
    if not name:
        return "No speaker was picked (everyone may be muted or away)."
    reason = str(result.get("reason") or "")
    words = f"Next speaker: {name}"
    if reason:
        words += f" — {reason}"
    message = result.get("message")
    if isinstance(message, dict) and message.get("content"):
        words += "\nThey said: " + str(message["content"])
    return words


def run_words(result: dict) -> str:
    turns = result.get("turns_run")
    if turns is None:
        return "The run finished."
    lines = [f"Ran {turns} turn{'s' if turns != 1 else ''}."]
    for entry in result.get("results") or []:
        if isinstance(entry, dict):
            lines.append(turn_words(entry))
    return "\n".join(lines)


def presence_words(records: list) -> list[str]:
    lines: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        name = (record.get("name") or record.get("character_name")
                or record.get("character_id") or "?")
        if "present" in record:
            if record.get("present"):
                lines.append(f"{name}: here")
            else:
                missed = record.get("missed_count") or 0
                lines.append(f"{name}: away"
                             + (f" · {missed} missed" if missed else ""))
            continue
        state = str(record.get("state") or record.get("status") or "")
        if state in ("absent", "away", "left"):
            lines.append(f"{name}: away")
        elif state:
            lines.append(f"{name}: here ({state})")
        else:
            lines.append(f"{name}: here")
    return lines


def digest_words(digest: dict) -> str:
    if not digest:
        return "Nothing was missed."
    entries = digest.get("entries") or digest.get("missed") or []
    if isinstance(entries, list) and entries:
        lines = [f"While away, {len(entries)} thing(s) happened:"]
        for entry in entries[:10]:
            if isinstance(entry, dict):
                who = entry.get("speaker_name") or entry.get("speaker") or ""
                text = str(entry.get("excerpt") or entry.get("content") or "")
                lines.append(f"- {who}: {text}" if who else f"- {text}")
            else:
                lines.append(f"- {entry}")
        return "\n".join(lines)
    count = (digest.get("missed_count") or digest.get("count")
             or (digest.get("window") or {}).get("missed_count"))
    if count:
        return f"While away, {count} message(s) were posted."
    return "Nothing was missed."


def peek_words(peek: dict) -> str:
    if not peek:
        return "Nothing to show."
    member = peek.get("member") or {}
    name = member.get("name") or "Member"
    source = peek.get("persona_source")
    lines = [f"{name} — persona comes from "
             + ("their in-room override." if source == "override"
                else "their card.")]
    persona = str(peek.get("effective_persona") or "").strip()
    lines.append(persona if persona else "(no persona text)")
    return "\n".join(lines)


def transcript_lines(messages: list) -> list[str]:
    lines: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        who = message.get("speaker_name") or (
            "You" if message.get("speaker_id") in (None, "user") else "?")
        lines.append(f"{who}: {message.get('content') or ''}")
    return lines


# ------------------------------------------------- deepening compose

DEEPENING_TEXT_FIELDS = ("join_prefix", "join_suffix", "scenario_override")


def compose_deepening(stored: dict, *, generation_mode: str,
                      allow_self_responses: bool, auto_enabled: bool,
                      auto_max_turns: int, join_prefix: str,
                      join_suffix: str, scenario_override: str) -> dict:
    """Lay the Room Settings form over the stored deepening
    document — engine state and unknown keys carried verbatim."""
    document = dict(stored)
    document["generation_mode"] = generation_mode
    document["allow_self_responses"] = bool(allow_self_responses)
    auto = dict(document.get("auto_mode") or {})
    auto["enabled"] = bool(auto_enabled)
    auto["max_turns"] = max(1, int(auto_max_turns))
    document["auto_mode"] = auto
    document["join_prefix"] = join_prefix
    document["join_suffix"] = join_suffix
    document["scenario_override"] = scenario_override.strip() or None
    return document


def member_override(deepening: dict, character_id: str) -> dict:
    overrides = deepening.get("member_overrides") or {}
    override = overrides.get(character_id) if isinstance(overrides, dict) else None
    return dict(override) if isinstance(override, dict) else {}


# ------------------------------------------------------- chat actions

def set_pinned(engine, chat_id: str, message_id: str, pinned: bool) -> dict:
    """Pin/unpin, then VERIFY by re-reading the pinned list
    (the R-07 discipline: the answer is the re-read, not the call)."""
    if pinned:
        engine.request("POST", f"/api/v1/chats/{chat_id}/messages/{message_id}/pin")
    else:
        engine.request("DELETE", f"/api/v1/chats/{chat_id}/messages/{message_id}/pin")
    rows = engine.request("GET", f"/api/v1/chats/{chat_id}/pinned-messages")
    ids = {str(r.get("id")) for r in rows if isinstance(r, dict)} \
        if isinstance(rows, list) else set()
    return {"message_id": message_id, "pinned": message_id in ids,
            "pinned_ids": sorted(ids)}


def save_authors_note(engine, chat_id: str, body: dict) -> Any:
    """Save the note, then read it back — what returns is what
    the engine actually stored."""
    engine.request("POST", f"/api/v1/chats/{chat_id}/authors-note", json_body={
        "text": str(body.get("text") or ""),
        "depth": int(body.get("depth", 4)),
        "frequency": int(body.get("frequency", 1)),
        "enabled": bool(body.get("enabled", True)),
        "role": str(body.get("role") or "system"),
    })
    return engine.request("GET", f"/api/v1/chats/{chat_id}/authors-note")


def regenerate_plan(engine, chat_id: str) -> dict:
    """The regenerate pre-flight: the chat's last message must be
    an assistant reply. Returns that message (the one the journaled
    delete will set aside)."""
    rows = engine.request("GET", f"/api/v1/chats/{chat_id}/messages")
    history = rows if isinstance(rows, list) else []
    if not history:
        raise EngineError("there is nothing to regenerate yet", status=422)
    last = history[-1]
    if not isinstance(last, dict) or last.get("role") != "assistant":
        raise EngineError(
            "only a chat whose last message is the assistant's reply "
            "can be regenerated", status=422)
    return last


def restore_reply(engine, chat_id: str, old: dict) -> bool:
    """Restore a set-aside reply after a failed regenerate: the
    undo journal first (exact before-image, original id), then a
    plain re-append of its text."""
    try:
        engine.request("POST", f"/api/v1/chats/{chat_id}/undo", json_body={})
        rows = engine.request("GET", f"/api/v1/chats/{chat_id}/messages")
        if isinstance(rows, list) and any(
                isinstance(m, dict) and m.get("id") == old.get("id")
                for m in rows):
            return True
    except EngineError:
        pass
    try:
        engine.request("POST", f"/api/v1/chats/{chat_id}/messages",
                       json_body={"role": "assistant",
                                  "content": str(old.get("content") or "")})
        return True
    except EngineError:
        return False
