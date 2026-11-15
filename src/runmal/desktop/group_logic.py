"""Group-room logic for the desktop shell (R-11) — Qt-free.

Everything the Groups dialog shows that is not a widget lives
here: the speaker-strategy words, the deepening compose (the
form's fields laid over the stored document so the engine's
selection ``state`` and any unknown keys ride through a save
untouched), per-member override words, turn-result words, and
presence words. :class:`GroupFlow` wraps the typed client so
the window layer only ever calls verbs.
"""

from __future__ import annotations

from typing import Any

from runmal.desktop.client import (
    GroupMemberView,
    GroupMessageView,
    GroupView,
    RunmalClient,
)

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


def group_line(group: GroupView) -> str:
    """One list line for a room."""
    return (
        f"{group.name or 'Untitled room'} — {group.member_count} "
        f"member{'s' if group.member_count != 1 else ''} · "
        f"{group.message_count} messages"
    )


def member_line(member: GroupMemberView) -> str:
    bits = [member.name or member.character_id]
    bits.append(f"talkativeness {member.talkativeness:.1f}")
    if member.muted:
        bits.append("muted")
    return " · ".join(bits)


def transcript_lines(messages: list[GroupMessageView]) -> list[str]:
    lines: list[str] = []
    for message in messages:
        who = message.speaker_name or (
            "You" if message.speaker_id in (None, "user") else "?"
        )
        lines.append(f"{who}: {message.content}")
    return lines


def turn_words(result: dict[str, Any]) -> str:
    """The words for one ``next`` result."""
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


def run_words(result: dict[str, Any]) -> str:
    turns = result.get("turns_run")
    if turns is None:
        return "The run finished."
    lines = [f"Ran {turns} turn{'s' if turns != 1 else ''}."]
    for entry in result.get("results") or []:
        if isinstance(entry, dict):
            lines.append(turn_words(entry))
    return "\n".join(lines)


def presence_words(records: list[dict[str, Any]]) -> list[str]:
    """One line per member from the presence records."""
    lines: list[str] = []
    for record in records:
        name = (
            record.get("name")
            or record.get("character_name")
            or record.get("character_id")
            or "?"
        )
        if "present" in record:
            if record.get("present"):
                lines.append(f"{name}: here")
            else:
                missed = record.get("missed_count") or 0
                lines.append(
                    f"{name}: away"
                    + (f" · {missed} missed" if missed else "")
                )
            continue
        state = str(record.get("state") or record.get("status") or "")
        if state in ("absent", "away", "left"):
            lines.append(f"{name}: away")
        elif state:
            lines.append(f"{name}: here ({state})")
        else:
            lines.append(f"{name}: here")
    return lines


def digest_words(digest: dict[str, Any]) -> str:
    """Words for a return digest: what the member missed."""
    if not digest:
        return "Nothing was missed."
    entries = digest.get("entries") or digest.get("missed") or []
    if isinstance(entries, list) and entries:
        lines = [f"While away, {len(entries)} thing(s) happened:"]
        for entry in entries[:10]:
            if isinstance(entry, dict):
                who = entry.get("speaker_name") or entry.get("speaker") or ""
                text = str(
                    entry.get("excerpt") or entry.get("content") or ""
                )
                lines.append(f"- {who}: {text}" if who else f"- {text}")
            else:
                lines.append(f"- {entry}")
        return "\n".join(lines)
    count = (
        digest.get("missed_count")
        or digest.get("count")
        or (digest.get("window") or {}).get("missed_count")
    )
    if count:
        return f"While away, {count} message(s) were posted."
    return "Nothing was missed."


def peek_words(peek: dict[str, Any]) -> str:
    if not peek:
        return "Nothing to show."
    member = peek.get("member") or {}
    name = member.get("name") or "Member"
    source = peek.get("persona_source")
    lines = [
        f"{name} — persona comes from "
        + ("their in-room override." if source == "override" else "their card.")
    ]
    persona = str(peek.get("effective_persona") or "").strip()
    lines.append(persona if persona else "(no persona text)")
    return "\n".join(lines)


# -- deepening compose -----------------------------------------------------

#: The deepening fields the Room Settings form edits. Everything
#: else in the document (``state``, unknown keys) is carried.
DEEPENING_TEXT_FIELDS = ("join_prefix", "join_suffix", "scenario_override")


def compose_deepening(
    stored: dict[str, Any],
    *,
    generation_mode: str,
    allow_self_responses: bool,
    auto_enabled: bool,
    auto_max_turns: int,
    join_prefix: str,
    join_suffix: str,
    scenario_override: str,
) -> dict[str, Any]:
    """Lay the form's values over the stored deepening document."""
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


class GroupFlow:
    """The Groups dialog's verbs over the typed client."""

    def __init__(self, client: RunmalClient) -> None:
        self._client = client

    def groups(self) -> list[GroupView]:
        return self._client.list_groups()

    def create(self, name: str, member_ids: list[str]) -> GroupView:
        return self._client.create_group(name.strip(), list(member_ids))

    def rename(self, group: GroupView, name: str) -> GroupView:
        return self._client.update_group(group.id, name=name.strip())

    def set_policy(self, group: GroupView, policy: str) -> GroupView:
        return self._client.update_group(group.id, speaker_policy=policy)

    def delete(self, group: GroupView) -> None:
        self._client.delete_group(group.id)

    def refresh(self, group: GroupView) -> GroupView:
        return self._client.get_group(group.id)

    def add_member(self, group: GroupView, character_id: str) -> GroupView:
        self._client.add_group_member(group.id, character_id)
        return self.refresh(group)

    def remove_member(self, group: GroupView, character_id: str) -> GroupView:
        self._client.remove_group_member(group.id, character_id)
        return self.refresh(group)

    def set_member(
        self,
        group: GroupView,
        character_id: str,
        *,
        talkativeness: float | None = None,
        muted: bool | None = None,
    ) -> GroupView:
        self._client.update_group_member(
            group.id,
            character_id,
            talkativeness=talkativeness,
            muted=muted,
        )
        return self.refresh(group)

    def messages(self, group: GroupView) -> list[GroupMessageView]:
        return self._client.list_group_messages(group.id)

    def say(self, group: GroupView, text: str) -> None:
        self._client.post_group_message(group.id, "user", text.strip())

    def next_turn(
        self,
        group: GroupView,
        *,
        user_text: str | None = None,
        manual_speaker_id: str | None = None,
        generate: bool = False,
    ) -> dict[str, Any]:
        return self._client.group_next(
            group.id,
            user_text=user_text,
            manual_speaker_id=manual_speaker_id,
            generate=generate,
        )

    def run_turns(
        self, group: GroupView, *, turns: int, generate: bool
    ) -> dict[str, Any]:
        return self._client.group_run(group.id, turns=turns, generate=generate)

    def deepening(self, group: GroupView) -> dict[str, Any]:
        return self._client.get_group_deepening(group.id)

    def save_deepening(
        self, group: GroupView, document: dict[str, Any]
    ) -> dict[str, Any]:
        return self._client.put_group_deepening(group.id, document)

    def member_override(
        self, group: GroupView, character_id: str
    ) -> dict[str, Any]:
        deepening = self.deepening(group)
        overrides = deepening.get("member_overrides") or {}
        override = overrides.get(character_id)
        return dict(override) if isinstance(override, dict) else {}

    def set_member_override(
        self, group: GroupView, character_id: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        return self._client.patch_group_member_override(
            group.id, character_id, patch
        )

    def peek(self, group: GroupView, character_id: str) -> dict[str, Any]:
        return self._client.peek_group_member(group.id, character_id)

    def leave(self, group: GroupView, character_id: str) -> None:
        self._client.leave_group_member(group.id, character_id)

    def back(self, group: GroupView, character_id: str) -> dict[str, Any]:
        return self._client.return_group_member(group.id, character_id)

    def presence(self, group: GroupView) -> list[dict[str, Any]]:
        return self._client.group_presence(group.id)
