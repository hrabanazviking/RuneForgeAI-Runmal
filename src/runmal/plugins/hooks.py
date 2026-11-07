"""Prompt hooks: ordered transforms with abstention + isolation (P-081).

Design section 4. Two stages, both applied by the wiring inside
``prompt/inspect.py`` at the one composition choke point:

- ``slots`` (pre-compose, additive only): a hook receives the
  current slots read-only and returns slots to ADD, or None to
  abstain. Host post-processing forces provenance
  ``"plugin:<plugin_id>"`` (PLG-07), namespaces ids
  ``"<plugin_id>:<local>"``, and rejects ``required=True`` and
  foreign-namespace claims -- any violation discards the WHOLE
  contribution and records a ``surface="prompt"`` failure.
- ``messages`` (post-compose): a hook returns a replacement
  message iterable, or None to abstain. Entries must be
  :class:`ComposedMessage` with a valid role; ``slot_id`` is
  namespaced to the plugin likewise.

Ordering is data (PLG-04): the registry's ``prompt_hook_plan``
sorts (priority ASC, registration_index ASC). Isolation is total
(PLG-01): an exception, an invalid return or a validation
violation discards that hook's contribution entirely, records the
failure, and composition continues with the next hook. Echo rows
are metadata only (PLG-05) -- ids, outcomes, counts; never content.
"""

from __future__ import annotations

import dataclasses
import inspect
from dataclasses import dataclass

from runmal.plugins.api import PLUGIN_API_VERSION
from runmal.prompt.composer import ComposedMessage
from runmal.prompt.slots import VALID_ROLES, Slot


@dataclass(frozen=True)
class PromptHookContext:
    """What a hook is told about the run: metadata only (PLG-05).

    No session, no registry, no credentials -- a hook gets data,
    not the host.
    """

    plugin_id: str
    hook_id: str
    stage: str
    chat_id: str | None = None
    character_id: str | None = None
    model_id: str | None = None
    api_version: int = PLUGIN_API_VERSION


def _context(base_ctx: dict, *, plugin_id: str, hook_id: str,
             stage: str) -> PromptHookContext:
    base = dict(base_ctx or {})
    return PromptHookContext(
        plugin_id=plugin_id, hook_id=hook_id, stage=stage,
        chat_id=base.get("chat_id"),
        character_id=base.get("character_id"),
        model_id=base.get("model_id"),
        api_version=base.get("api_version", PLUGIN_API_VERSION))


async def _call(handler, ctx: PromptHookContext, items: tuple):
    result = handler(ctx, items)
    if inspect.isawaitable(result):
        result = await result
    return result


def _as_list(result, stage: str) -> list:
    if isinstance(result, (str, bytes)) or not hasattr(result, "__iter__"):
        raise TypeError(
            f"{stage} hook must return an iterable or None, "
            f"got {type(result).__name__}")
    return list(result)


def _rewrite_slot(plugin_id: str, slot) -> Slot:
    """Validate + namespace + force provenance for one added slot."""
    if not isinstance(slot, Slot):
        raise TypeError(
            f"slots hook returned a non-Slot value: "
            f"{type(slot).__name__}")
    if slot.required:
        raise ValueError(
            "plugin slots may not be required (composer budget "
            "inclusion stays host-only)")
    if slot.role not in VALID_ROLES:
        raise ValueError(f"invalid slot role: {slot.role!r}")
    prefix = f"{plugin_id}:"
    if ":" in slot.id:
        claimed = slot.id.split(":", 1)[0]
        if claimed != plugin_id:
            raise ValueError(
                f"slot id claims a foreign namespace: {slot.id!r}")
        new_id = slot.id
    else:
        new_id = prefix + slot.id
    return dataclasses.replace(
        slot, id=new_id, provenance=f"plugin:{plugin_id}")


async def apply_slot_hooks(registry, base_ctx: dict,
                           slots: list[Slot]) -> tuple[list[Slot], list[dict]]:
    """Run the slots stage over ``slots``; returns the new slot
    list plus one metadata echo row per hook that ran."""
    current: list[Slot] = list(slots)
    echoes: list[dict] = []
    for plan_row in registry.prompt_hook_plan("slots"):
        plugin_id = plan_row["plugin_id"]
        hook_id = plan_row["hook_id"]
        record = registry.get(plugin_id)
        handler = registry.handler_for_hook(record, hook_id)
        if handler is None:
            continue
        ctx = _context(base_ctx, plugin_id=plugin_id,
                       hook_id=hook_id, stage="slots")
        try:
            result = await _call(handler, ctx, tuple(current))
            if result is None:
                registry.record_success(record)
                echoes.append({"plugin_id": plugin_id,
                               "hook_id": hook_id,
                               "outcome": "abstained",
                               "slots_added": 0})
                continue
            added = [_rewrite_slot(plugin_id, slot)
                     for slot in _as_list(result, "slots")]
        except Exception as exc:
            registry.record_failure(record, "prompt", hook_id, exc)
            echoes.append({"plugin_id": plugin_id,
                           "hook_id": hook_id,
                           "outcome": "failed",
                           "slots_added": 0})
            continue
        current.extend(added)
        registry.record_success(record)
        echoes.append({"plugin_id": plugin_id,
                       "hook_id": hook_id,
                       "outcome": "applied",
                       "slots_added": len(added)})
    return current, echoes


def _rewrite_message(plugin_id: str, message) -> ComposedMessage:
    if not isinstance(message, ComposedMessage):
        raise TypeError(
            f"messages hook returned a non-ComposedMessage value: "
            f"{type(message).__name__}")
    if message.role not in VALID_ROLES:
        raise ValueError(f"invalid message role: {message.role!r}")
    prefix = f"{plugin_id}:"
    slot_id = message.slot_id
    if ":" in slot_id and not slot_id.startswith(prefix):
        # A slot_id already carrying a namespace that is not this
        # plugin's own claims a foreign (host or other-plugin)
        # namespace -- a violation, mirroring the slots stage:
        # the whole contribution is discarded by the caller, never
        # re-prefixed into a nested forgery.
        raise ValueError(
            f"message slot_id claims a foreign namespace: {slot_id!r}")
    if not slot_id.startswith(prefix):
        slot_id = prefix + slot_id
    if slot_id == message.slot_id:
        return message
    return dataclasses.replace(message, slot_id=slot_id)


async def apply_message_hooks(registry, base_ctx: dict,
                              messages: list) -> tuple[list, list[dict]]:
    """Run the messages stage; a hook's iterable REPLACES the
    message list. A failed hook leaves the pre-hook list intact
    and flowing (no partial application)."""
    current: list = list(messages)
    echoes: list[dict] = []
    for plan_row in registry.prompt_hook_plan("messages"):
        plugin_id = plan_row["plugin_id"]
        hook_id = plan_row["hook_id"]
        record = registry.get(plugin_id)
        handler = registry.handler_for_hook(record, hook_id)
        if handler is None:
            continue
        ctx = _context(base_ctx, plugin_id=plugin_id,
                       hook_id=hook_id, stage="messages")
        try:
            result = await _call(handler, ctx, tuple(current))
            if result is None:
                registry.record_success(record)
                echoes.append({"plugin_id": plugin_id,
                               "hook_id": hook_id,
                               "outcome": "abstained",
                               "messages_added": 0,
                               "messages_removed": 0})
                continue
            replaced = [_rewrite_message(plugin_id, message)
                        for message in _as_list(result, "messages")]
        except Exception as exc:
            registry.record_failure(record, "prompt", hook_id, exc)
            echoes.append({"plugin_id": plugin_id,
                           "hook_id": hook_id,
                           "outcome": "failed",
                           "messages_added": 0,
                           "messages_removed": 0})
            continue
        added = max(0, len(replaced) - len(current))
        removed = max(0, len(current) - len(replaced))
        current = replaced
        registry.record_success(record)
        echoes.append({"plugin_id": plugin_id,
                       "hook_id": hook_id,
                       "outcome": "applied",
                       "messages_added": added,
                       "messages_removed": removed})
    return current, echoes
