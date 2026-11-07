"""Group deepening (roadmap P-070): activation strategies honoured by
the persistent room road, per-member overrides, group lore/persona
handling — measured against the delta census (ST-11 depth, ST-13,
ST-14).

What existed before this slice: S210 persistent rooms with stored
``speaker_policy`` / ``speaker_config``; S211 speaker policies
(manual / natural / list / pooled) as PURE selection functions over
a ``SelectionContext`` — stored config that no persistent-room road
ever consumed; S305's stateless ``/group/turn`` with its own separate
mention / round-robin / broadcast strategies. What this module adds:

- a validated deepening document stored in the existing
  ``groups.speaker_config`` JSON under the ``"p070"`` key (NO
  migration; the S211 top-level keys ``order`` / ``seed`` are
  untouched): generation mode (swap vs join card assembly, ST-13),
  join prefix/suffix templates, a group scenario override (ST-14),
  the self-response rule, bounded auto-mode config, per-member
  overrides, and the persisted activation state (list cursor, pool).
- ``select_next``: builds the S211 SelectionContext from the REAL
  transcript (history speakers, last user text, persisted cursor /
  pool) and delegates to the S211 policies — with per-member
  overrides applied: ``never`` excludes a member everywhere
  (including a manual designation; distinct from muted, same
  silence), ``force`` pre-empts natural / list / pooled, and
  ``allow_self_responses=False`` filters the immediately-previous
  speaker when more than one member is eligible.
- prompt assembly: swap = only the speaker's persona is the system
  prompt; join = every member's persona joined with the configured
  templates, the speaker's block marked, the group scenario
  appended once (card scenarios dropped). A member's
  ``persona_override`` replaces their card persona for this room
  only — the card itself is never mutated.
- group lore: the P-040 scoped-lore road (``lorebooks.scopes``
  layered preview over the room chat: global -> character ->
  persona -> chat), scanned on the last user text. A member's
  ``lore_enabled=False`` drops the character layer for that member.

Honest boundaries: generation runs through the generation service's
default backend seam (the deterministic fake when unconfigured —
the S305 precedent) and does NOT route through the prompt composer
/ inspector; auto-mode is a driven, bounded loop behind an explicit
call, never a background daemon; activation state lives in
``speaker_config``, so concurrent next/run calls are
last-writer-wins, matching the room config's existing semantics.
"""

from __future__ import annotations

import copy
import json

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.cards import import_card
from runmal.characters.service import get_character
from runmal.db.models import ChatEvent, Group
from runmal.groupchat import store
from runmal.groupchat.policies import MemberState, SelectionContext, get_policy
from runmal.persona.slots import build_slot_manifest, render_system_prompt

__all__ = [
    "ACTIVATIONS",
    "GENERATION_MODES",
    "GenerationFailedError",
    "build_prompt_messages",
    "default_deepening",
    "normalise_deepening",
    "normalise_member_override",
    "select_next_pure",
    "get_deepening",
    "put_deepening",
    "patch_member_override",
    "member_peek",
    "resolve_group_lore",
    "next_turn",
    "run_turns",
]

ACTIVATIONS = ("default", "force", "never")
GENERATION_MODES = ("swap", "join")
MAX_TURNS = 10


class GenerationFailedError(RuntimeError):
    """Generation for a group turn errored or produced no text."""


# -- the deepening document (pure) ---------------------------------------


def default_member_override() -> dict:
    return {"activation": "default", "persona_override": None, "lore_enabled": True}


def default_deepening() -> dict:
    return {
        "generation_mode": "swap",
        "join_prefix": "",
        "join_suffix": "",
        "scenario_override": None,
        "allow_self_responses": False,
        "auto_mode": {"enabled": False, "max_turns": 3},
        "member_overrides": {},
        "state": {"list_cursor": 0, "pool_spoken": []},
    }


def normalise_member_override(raw, *, partial: bool = False) -> dict:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("member override must be an object")
    out = default_member_override() if not partial else {}
    if "activation" in raw:
        if raw["activation"] not in ACTIVATIONS:
            raise ValueError(f"activation must be one of {list(ACTIVATIONS)}")
        out["activation"] = raw["activation"]
    elif not partial:
        out["activation"] = "default"
    if "persona_override" in raw:
        value = raw["persona_override"]
        if value is not None and not isinstance(value, str):
            raise ValueError("persona_override must be a string or null")
        out["persona_override"] = value
    if "lore_enabled" in raw:
        if not isinstance(raw["lore_enabled"], bool):
            raise ValueError("lore_enabled must be a boolean")
        out["lore_enabled"] = raw["lore_enabled"]
    unknown = set(raw) - {"activation", "persona_override", "lore_enabled"}
    if unknown:
        raise ValueError(f"unknown member override keys: {sorted(unknown)}")
    return out


def normalise_deepening(raw) -> dict:
    """Validate a deepening document; missing keys take defaults."""
    if raw is None:
        return default_deepening()
    if not isinstance(raw, dict):
        raise ValueError("deepening must be an object")
    unknown = set(raw) - {
        "generation_mode", "join_prefix", "join_suffix", "scenario_override",
        "allow_self_responses", "auto_mode", "member_overrides", "state",
    }
    if unknown:
        raise ValueError(f"unknown deepening keys: {sorted(unknown)}")
    out = default_deepening()
    if "generation_mode" in raw:
        if raw["generation_mode"] not in GENERATION_MODES:
            raise ValueError(f"generation_mode must be one of {list(GENERATION_MODES)}")
        out["generation_mode"] = raw["generation_mode"]
    for key in ("join_prefix", "join_suffix"):
        if key in raw:
            if not isinstance(raw[key], str):
                raise ValueError(f"{key} must be a string")
            out[key] = raw[key]
    if "scenario_override" in raw:
        value = raw["scenario_override"]
        if value is not None and not isinstance(value, str):
            raise ValueError("scenario_override must be a string or null")
        out["scenario_override"] = value
    if "allow_self_responses" in raw:
        if not isinstance(raw["allow_self_responses"], bool):
            raise ValueError("allow_self_responses must be a boolean")
        out["allow_self_responses"] = raw["allow_self_responses"]
    if "auto_mode" in raw:
        auto = raw["auto_mode"]
        if not isinstance(auto, dict):
            raise ValueError("auto_mode must be an object")
        if "enabled" in auto and not isinstance(auto["enabled"], bool):
            raise ValueError("auto_mode.enabled must be a boolean")
        if "max_turns" in auto:
            if not isinstance(auto["max_turns"], int) or isinstance(auto["max_turns"], bool):
                raise ValueError("auto_mode.max_turns must be an integer")
            if not 1 <= auto["max_turns"] <= MAX_TURNS:
                raise ValueError(f"auto_mode.max_turns must be in [1, {MAX_TURNS}]")
        out["auto_mode"] = {
            "enabled": bool(auto.get("enabled", False)),
            "max_turns": int(auto.get("max_turns", 3)),
        }
    if "member_overrides" in raw:
        overrides = raw["member_overrides"]
        if not isinstance(overrides, dict):
            raise ValueError("member_overrides must be an object")
        out["member_overrides"] = {
            str(cid): normalise_member_override(value)
            for cid, value in overrides.items()
        }
    if "state" in raw:
        state = raw["state"]
        if not isinstance(state, dict):
            raise ValueError("state must be an object")
        cursor = state.get("list_cursor", 0)
        if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
            raise ValueError("state.list_cursor must be a non-negative integer")
        pool = state.get("pool_spoken", [])
        if not isinstance(pool, list) or not all(isinstance(x, str) for x in pool):
            raise ValueError("state.pool_spoken must be a list of character ids")
        out["state"] = {"list_cursor": cursor, "pool_spoken": list(pool)}
    return out


def deepening_of(group: Group) -> dict:
    config = json.loads(group.speaker_config or "{}")
    return normalise_deepening(config.get("p070"))


def _store_deepening(group: Group, deepening: dict) -> None:
    config = json.loads(group.speaker_config or "{}")
    config["p070"] = deepening
    group.speaker_config = json.dumps(config)


# -- selection (pure) -----------------------------------------------------


def _override(deepening: dict, character_id: str) -> dict:
    return deepening["member_overrides"].get(character_id, default_member_override())


def select_next_pure(
    members: list[MemberState],
    *,
    policy_name: str,
    speaker_config: dict,
    deepening: dict,
    history_speakers: list[str],
    last_user_text: str = "",
    manual_speaker_id: str | None = None,
) -> tuple[str | None, str, dict]:
    """Pick the next speaker. Returns (character_id|None, reason,
    new_state). ``members`` is the roster in order (muted flags set);
    ``history_speakers`` holds character ids / "user" oldest first."""
    state = copy.deepcopy(deepening["state"])
    overrides = deepening["member_overrides"]
    never_ids = {
        cid for cid, o in overrides.items() if o.get("activation") == "never"
    }
    eligible = [
        m for m in members if not m.muted and m.character_id not in never_ids
    ]
    if not eligible:
        return None, "no_eligible_members", state

    if policy_name == "manual":
        if manual_speaker_id is None:
            return None, "manual_no_designation", state
        if manual_speaker_id in never_ids:
            return None, "manual_speaker_never", state
        ctx = SelectionContext(
            members=eligible, manual_speaker_id=manual_speaker_id
        )
        picked = get_policy("manual").select(ctx)
        if picked is None:
            return None, "manual_speaker_unavailable", state
        return picked, "manual", state

    # Self-response rule: filter the immediately-previous speaker when
    # someone else could speak instead.
    pool_members = eligible
    if not deepening["allow_self_responses"] and history_speakers:
        last = next(
            (s for s in reversed(history_speakers) if s != "user"), None
        )
        if last is not None and len(eligible) > 1:
            filtered = [m for m in eligible if m.character_id != last]
            if filtered:
                pool_members = filtered

    forced = [
        m for m in pool_members
        if overrides.get(m.character_id, {}).get("activation") == "force"
    ]
    list_order = speaker_config.get("order") or speaker_config.get("list_order")
    if not isinstance(list_order, list) or not list_order:
        list_order = [m.character_id for m in members]
    seed = speaker_config.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        seed = len(history_speakers)

    if forced:
        if policy_name == "list":
            rank = {cid: i for i, cid in enumerate(list_order)}
            forced.sort(key=lambda m: rank.get(m.character_id, len(rank)))
        picked = forced[0].character_id
        _advance_state(policy_name, eligible, list_order, state, picked)
        return picked, "forced", state

    ctx = SelectionContext(
        members=pool_members,
        seed=seed,
        last_user_text=last_user_text,
        list_order=list(list_order),
        list_cursor=state["list_cursor"],
        pool_spoken=set(state["pool_spoken"]),
        history_speakers=list(history_speakers),
    )
    policy = get_policy(policy_name)
    picked = policy.select(ctx)
    if picked is None:
        return None, f"{policy_name}_silence", state
    policy.note_selected(ctx, picked)
    state = {"list_cursor": ctx.list_cursor, "pool_spoken": sorted(ctx.pool_spoken)}
    reason = policy_name
    if policy_name == "natural" and last_user_text:
        from runmal.groupchat.core import _is_mentioned

        name = next(m.name for m in pool_members if m.character_id == picked)
        if _is_mentioned(last_user_text, name):
            reason = "natural_mention"
    return picked, reason, state


def _advance_state(policy_name, eligible, list_order, state, picked) -> None:
    """Mirror the stateful policies' note_selected for a forced pick."""
    if policy_name == "list":
        effective = [
            cid for cid in list_order
            if cid in {m.character_id for m in eligible}
        ]
        if picked in effective:
            state["list_cursor"] = effective.index(picked) + 1
    elif policy_name == "pooled":
        spoken = set(state["pool_spoken"])
        spoken.add(picked)
        if {m.character_id for m in eligible} <= spoken:
            spoken.clear()
        state["pool_spoken"] = sorted(spoken)


# -- prompt assembly (pure) -----------------------------------------------


def _persona_text(member: dict, deepening: dict, *, for_join: bool) -> str:
    """Effective persona text for one member dict {character_id, name,
    manifest, override}."""
    override = member.get("override") or default_member_override()
    if override.get("persona_override"):
        text = override["persona_override"]
        if deepening["scenario_override"] and not for_join:
            text = f"{text}\n\n{deepening['scenario_override']}"
        return text
    manifest = dict(member.get("manifest") or {})
    if deepening["scenario_override"]:
        if for_join:
            manifest.pop("scenario", None)
        else:
            manifest["scenario"] = deepening["scenario_override"]
    elif for_join:
        manifest.pop("scenario", None)
    return render_system_prompt(manifest)


def build_prompt_messages(
    speaker_id: str,
    roster: list[dict],
    deepening: dict,
    history: list[dict],
    lore_texts: list[str] | None = None,
) -> list[dict]:
    """Assemble the generation messages for ``speaker_id``.

    ``roster`` entries: {character_id, name, manifest, override}.
    ``history`` entries: {role, speaker_id, speaker_name, content}.
    """
    by_id = {m["character_id"]: m for m in roster}
    speaker = by_id[speaker_id]
    if deepening["generation_mode"] == "join":
        blocks = []
        for member in roster:
            prefix = deepening["join_prefix"].replace("{{char}}", member["name"])
            suffix = deepening["join_suffix"].replace("{{char}}", member["name"])
            block = f"{prefix}{_persona_text(member, deepening, for_join=True)}{suffix}"
            if member["character_id"] == speaker_id:
                block = f"[Now speaking: {member['name']}]\n{block}"
            blocks.append(block)
        system = "\n\n".join(blocks)
        if deepening["scenario_override"]:
            system = f"{system}\n\n{deepening['scenario_override']}"
    else:  # swap
        system = _persona_text(speaker, deepening, for_join=False)
    if lore_texts:
        system = f"{system}\n\nGroup lore:\n" + "\n\n".join(lore_texts)
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    for msg in history:
        if msg.get("speaker_id") == speaker_id:
            messages.append({"role": "assistant", "content": msg["content"]})
        elif msg.get("role") == "user":
            messages.append({"role": "user", "content": msg["content"]})
        else:
            messages.append(
                {"role": "user", "content": f"{msg.get('speaker_name')}: {msg['content']}"}
            )
    return messages


# -- async service ----------------------------------------------------------


async def _roster(session: AsyncSession, user_id: str, group: Group, deepening: dict):
    """Roster dicts with card manifests + member rows, in roster order."""
    rows = await store._member_rows(session, group.id)
    roster = []
    member_rows = {}
    for member, name in rows:
        character = await get_character(session, user_id, member.character_id)
        manifest: dict = {}
        card = None
        if character is not None:
            try:
                card = import_card(character.card_json.encode(), "card.json")
                manifest = build_slot_manifest(card)
            except Exception:
                manifest = {}
        roster.append(
            {
                "character_id": member.character_id,
                "name": name,
                "manifest": manifest,
                "card": card,
                "override": _override(deepening, member.character_id),
                "member": member,
            }
        )
        member_rows[member.character_id] = member
    return roster, member_rows


async def get_deepening(session: AsyncSession, user_id: str, group_id: str) -> dict | None:
    group = await store._get_owned_group(session, user_id, group_id)
    if group is None:
        return None
    return deepening_of(group)


async def put_deepening(
    session: AsyncSession, user_id: str, group_id: str, raw
) -> dict | None:
    group = await store._get_owned_group(session, user_id, group_id)
    if group is None:
        return None
    deepening = normalise_deepening(raw)
    rows = await store._member_rows(session, group.id)
    known = {m.character_id for m, _ in rows}
    unknown = set(deepening["member_overrides"]) - known
    if unknown:
        raise ValueError(f"overrides for non-members: {sorted(unknown)}")
    _store_deepening(group, deepening)
    await session.commit()
    return deepening


async def patch_member_override(
    session: AsyncSession, user_id: str, group_id: str, character_id: str, raw
) -> dict | None:
    group = await store._get_owned_group(session, user_id, group_id)
    if group is None:
        return None
    rows = await store._member_rows(session, group.id)
    if character_id not in {m.character_id for m, _ in rows}:
        return None
    deepening = deepening_of(group)
    merged = _override(deepening, character_id)
    merged.update(normalise_member_override(raw, partial=True))
    deepening["member_overrides"][character_id] = normalise_member_override(merged)
    _store_deepening(group, deepening)
    await session.commit()
    return deepening["member_overrides"][character_id]


async def member_peek(
    session: AsyncSession, user_id: str, group_id: str, character_id: str
) -> dict | None:
    """In-group card peek (ST-14): member + override + effective
    persona. Reads only — the card is never mutated."""
    group = await store._get_owned_group(session, user_id, group_id)
    if group is None:
        return None
    deepening = deepening_of(group)
    roster, _ = await _roster(session, user_id, group, deepening)
    entry = next((r for r in roster if r["character_id"] == character_id), None)
    if entry is None:
        return None
    override = entry["override"]
    return {
        "member": store.member_to_dict(entry["member"], entry["name"]),
        "override": override,
        "persona_source": "override" if override.get("persona_override") else "card",
        "effective_persona": _persona_text(entry, deepening, for_join=False),
        "card": {
            "id": character_id,
            "name": entry["name"],
            "slots": entry["manifest"],
        },
    }


async def resolve_group_lore(
    session: AsyncSession,
    user_id: str,
    group: Group,
    speaker_id: str,
    scan_texts: list[str],
    lore_enabled: bool,
) -> tuple[list[str], list[dict]]:
    """Activated scoped lore for a speaker. Returns (texts, report)."""
    from runmal.lorebooks.scopes import layered_preview

    chat = await store._room_chat(session, group.id)
    if chat is None:
        return [], []
    preview = await layered_preview(
        session,
        user_id,
        chat_id=chat.id,
        character_id=speaker_id,
        messages=list(scan_texts),
    )
    if preview is None:
        return [], []
    texts: list[str] = []
    report: list[dict] = []
    for kind, layer in (preview.get("layers") or {}).items():
        if kind == "character" and not lore_enabled:
            continue
        for row in layer.get("entries", []):
            if row.get("status") == "included" and row.get("content"):
                texts.append(str(row["content"]))
                report.append(
                    {
                        "scope": kind,
                        "lorebook_id": row.get("lorebook_id"),
                        "entry_id": row.get("entry_id"),
                    }
                )
    return texts, report


async def _record_event(session, chat_id, kind, data) -> None:
    session.add(
        ChatEvent(chat_id=chat_id, message_id=None, kind=kind, data=json.dumps(data))
    )


async def next_turn(
    session: AsyncSession,
    user_id: str,
    group_id: str,
    *,
    user_text: str | None = None,
    manual_speaker_id: str | None = None,
    generate: bool = False,
) -> dict | None:
    """One activation tick on the persistent room. None -> no group."""
    group = await store._get_owned_group(session, user_id, group_id)
    if group is None:
        return None
    if user_text:
        await store.append_message(session, user_id, group_id, store.USER_SPEAKER, user_text)
    deepening = deepening_of(group)
    config = json.loads(group.speaker_config or "{}")
    roster, _ = await _roster(session, user_id, group, deepening)
    messages = await store.list_messages(session, user_id, group_id) or []
    history = [
        {
            "role": m.role,
            "speaker_id": m.speaker_id,
            "speaker_name": m.speaker_name,
            "content": m.content,
        }
        for m in messages
    ]
    history_speakers = [
        m.speaker_id if m.speaker_id else "user" for m in messages
    ]
    last_user_text = next(
        (m.content for m in reversed(messages) if m.role == "user"), ""
    )
    member_states = [
        MemberState(
            character_id=r["character_id"],
            name=r["name"],
            muted=bool(r["member"].muted),
            talkativeness=r["member"].talkativeness,
        )
        for r in roster
    ]
    picked, reason, new_state = select_next_pure(
        member_states,
        policy_name=group.speaker_policy,
        speaker_config=config,
        deepening=deepening,
        history_speakers=history_speakers,
        last_user_text=last_user_text or "",
        manual_speaker_id=manual_speaker_id,
    )
    deepening["state"] = new_state
    _store_deepening(group, deepening)
    chat = await store._room_chat(session, group.id)
    await _record_event(
        session,
        chat.id if chat else "",
        "group.next_selected",
        {"strategy": group.speaker_policy, "speaker_id": picked, "reason": reason},
    )
    await session.commit()
    result = {
        "group_id": group.id,
        "strategy": group.speaker_policy,
        "speaker_id": picked,
        "speaker_name": next(
            (r["name"] for r in roster if r["character_id"] == picked), None
        ),
        "reason": reason,
        "state": new_state,
        "message": None,
        "lore": [],
    }
    if picked is None or not generate:
        return result
    override = _override(deepening, picked)
    lore_texts, lore_report = await resolve_group_lore(
        session,
        user_id,
        group,
        picked,
        [last_user_text] if last_user_text else [],
        lore_enabled=override.get("lore_enabled", True),
    )
    prompt_messages = build_prompt_messages(picked, roster, deepening, history, lore_texts)
    text = await _generate(prompt_messages)
    message = await store.append_message(session, user_id, group_id, picked, text)
    chat = await store._room_chat(session, group.id)
    await _record_event(
        session,
        chat.id if chat else "",
        "group.turn_generated",
        {"strategy": group.speaker_policy, "speaker_id": picked, "chars": len(text)},
    )
    await session.commit()
    result["message"] = store.message_to_dict(message)
    result["lore"] = lore_report
    result["prompt"] = prompt_messages
    return result


async def _generate(prompt_messages: list[dict]) -> str:
    from runmal.generation import service as generation

    prompt_text = "\n".join(m["content"] for m in prompt_messages)
    text = ""
    request_id = generation.new_request_id()
    async for event in generation.generate_events(request_id, prompt_text):
        if event.get("type") == "token":
            text += event["text"]
        elif event.get("type") == "error":
            raise GenerationFailedError(str(event.get("message") or "generation error"))
    if not text.strip():
        raise GenerationFailedError("generation produced no text")
    return text


async def run_turns(
    session: AsyncSession,
    user_id: str,
    group_id: str,
    *,
    turns: int,
    generate: bool = False,
) -> dict | None:
    """Bounded auto run (ST-14): at most ``turns`` selections, further
    capped by auto_mode.max_turns when auto_mode is enabled. Stops
    early on silence. None -> no group."""
    if not 1 <= turns <= MAX_TURNS:
        raise ValueError(f"turns must be in [1, {MAX_TURNS}]")
    group = await store._get_owned_group(session, user_id, group_id)
    if group is None:
        return None
    deepening = deepening_of(group)
    cap = turns
    if deepening["auto_mode"]["enabled"]:
        cap = min(cap, deepening["auto_mode"]["max_turns"])
    results = []
    for _ in range(cap):
        result = await next_turn(session, user_id, group_id, generate=generate)
        if result is None:  # pragma: no cover - group resolved above
            break
        results.append(result)
        if result["speaker_id"] is None:
            break
    return {"group_id": group_id, "turns_run": len(results), "cap": cap, "results": results}
