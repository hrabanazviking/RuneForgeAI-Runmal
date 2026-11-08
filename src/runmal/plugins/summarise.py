"""Memory Summarise plugin (P-084): the first P-081 citizen.

Roadmap line: "Memory Summarise plugin: rolling chat summary
into memory (the mirrors' most-loved extension), on the
founding memory stack." The manifest below is the P-081 slice
doc's own section 1 canonical example -- id
``runmal.summarise``, a ``summary-slot`` prompt hook, a
``summary-panel`` sidebar contribution -- made real and
registerable: the example was parse-shaped only, so the
citizen additionally declares the ``ui.slots`` capability +
``ui.contribute`` permission its UI contribution requires at
register() time (PLG-03).

What it does: on ``message.created`` / ``message.edited`` /
``message.deleted`` it re-reads the chat's committed history
and runs the founding S404 roll
(:func:`runmal.memory.summarize.roll_summaries`) under its
configured token budget, so the oldest history folds into a
versioned :class:`~runmal.db.models.ChatSummary` plus a
``kind='summary'`` memory with full message provenance. A
slots-stage prompt hook then offers the current summary back
to the composer as one plugin slot. Summaries are inspectable
end to end through :func:`summary_status` and the founding
``/api/v1/memories`` surface.

Honesty contract: the shipped summarizer is EXTRACTIVE and
DETERMINISTIC (``extractive-1``, the P-073 house id) -- every
word of a summary comes from the chat's own messages, no
model or backend is ever called, and nothing is invented.
A model-backed summarizer is a drop-in through
:class:`SummariseConfig`: any callable with the S404 seam
shape and a ``version`` attribute; the version is what lands
in the memory's extractor record, so provenance always names
the true generator.

Sandbox stance (P-082): the manifest declares only v1
surface permissions, so its derived resource grant set is
EMPTY (:func:`sandbox_grants` proves it) -- this citizen
touches no network, no files and no secrets. Its database
access is the host-supplied session factory handed to
trusted in-tree registration code: bootstrap wiring, not a
plugin resource grant.

Wiring: :func:`register_plugin` is the one-call trusted
registration road (the only registration road in v1).
``build_registry`` is deliberately unchanged -- P-081's
battery pins the empty boot registry, and P-083's plugin
manager (which banks before this slice) owns install/enable;
the keeper reconciles liveness at banking. See
``docs/MEMORY_SUMMARISE_PLUGIN_2026-11-07.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import Chat
from runmal.memory import service as memory_service
from runmal.memory.summarize import latest_summary, roll_summaries
from runmal.plugins.manifest import PluginManifest, manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRecord, PluginRegistry
from runmal.prompt.slots import Slot
from runmal.sandbox.policy import GrantSet, grants_from_manifest

PLUGIN_ID = "runmal.summarise"
PLUGIN_VERSION = "1.0.0"
SUMMARIZER_VERSION = "extractive-1"
HOOK_ID = "summary-slot"
SLOT_LOCAL_ID = "summary"
UI_LOCAL_ID = "summary-panel"

#: Defaults when neither an explicit config nor the manifest
#: settings name a value. The budget is in estimate_tokens
#: units (the founding S404 budget currency).
DEFAULT_BUDGET_TOKENS = 1200
DEFAULT_KEEP_RECENT = 6

#: Hard cap on one summary's characters; folding stays cheap
#: no matter how long the chat grows.
MAX_SUMMARY_CHARS = 1600
_WORDS_PER_TEXT = 10

#: Segments kept from the front when the cap elides the middle.
_HEAD_SEGMENTS = 8

_ELIDED_RE = re.compile(r"\[elided (\d+) messages\]")

#: Events that trigger a refresh. chat.created is declared
#: (the manifest tells the truth about what the citizen
#: subscribes to) but is a deliberate no-op: an empty chat
#: has nothing to summarise.
REFRESH_EVENTS = frozenset(
    {"message.created", "message.edited", "message.deleted"}
)
DECLARED_EVENTS = ("chat.created",) + tuple(sorted(REFRESH_EVENTS))

_SUMMARY_HEADER = (
    "Rolling summary of earlier conversation "
    "(extractive; generated from this chat's own messages):"
)


class ExtractiveSummarizer:
    """Deterministic extractive summarizer (S404 seam shape).

    Each raw text contributes one segment: its first ten
    whitespace-collapsed words. A text that IS a prior summary
    from this summarizer contributes its segments back --
    the founding roll folds incrementally (prior summary +
    one new message per step), so without segment recovery
    each re-fold would re-head the prior summary, nesting
    headers and pushing real message heads out of the cap.

    The cap (:data:`MAX_SUMMARY_CHARS`) elides the MIDDLE:
    the first segments and the newest segments are kept and
    the dropped count rides in an ``[elided N messages]``
    marker segment, which segment recovery reads back on the
    next fold -- so the loss is visible in the text itself,
    the header count (kept + elided) always names how many
    messages the summary spans, and no folded message ever
    vanishes silently. Pure string work over the supplied
    texts: no model, no backend, no invention.
    """

    version = SUMMARIZER_VERSION

    def __call__(self, texts: list[str]) -> str:
        segments: list[str] = []
        elided = 0
        for text in texts:
            if not text:
                continue
            cleaned = " ".join(text.split())
            if not cleaned:
                continue
            if cleaned.startswith("Summary of "):
                body = cleaned.split(": ", 1)[1] if ": " in cleaned else ""
                for segment in body.split(" | "):
                    segment = segment.strip()
                    match = _ELIDED_RE.fullmatch(segment)
                    if match:
                        elided += int(match.group(1))
                        continue
                    if segment.endswith(" ..."):
                        segment = segment[:-4].rstrip()
                    if segment:
                        segments.append(segment)
            else:
                segments.append(
                    " ".join(cleaned.split()[:_WORDS_PER_TEXT]))
        if not segments and elided == 0:
            return ""
        header = f"Summary of {elided + len(segments)} messages: "
        out = header + " | ".join(segments)
        if len(out) <= MAX_SUMMARY_CHARS:
            return out
        keep_head = segments[:_HEAD_SEGMENTS]
        tail = segments[_HEAD_SEGMENTS:]
        for keep_tail in range(len(tail), -1, -1):
            dropped = elided + (len(tail) - keep_tail)
            parts = (
                keep_head
                + [f"[elided {dropped} messages]"]
                + tail[len(tail) - keep_tail:]
            )
            out = header + " | ".join(parts)
            if len(out) <= MAX_SUMMARY_CHARS:
                return out
        out = header + " | ".join(
            keep_head + [f"[elided {elided + len(tail)} messages]"])
        if len(out) > MAX_SUMMARY_CHARS:  # pathological long words
            out = out[: MAX_SUMMARY_CHARS - 4].rsplit(" ", 1)[0] + " ..."
        return out


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class SummariseConfig:
    """The citizen's knobs: roll budget + the summarizer seam.

    ``summarizer=None`` selects :class:`ExtractiveSummarizer`.
    """

    budget_tokens: int = DEFAULT_BUDGET_TOKENS
    keep_recent: int = DEFAULT_KEEP_RECENT
    summarizer: object = None

    def __post_init__(self) -> None:
        if not _is_int(self.budget_tokens) or self.budget_tokens < 1:
            raise ValueError(
                f"budget_tokens must be an int >= 1: {self.budget_tokens!r}"
            )
        if not _is_int(self.keep_recent) or self.keep_recent < 0:
            raise ValueError(
                f"keep_recent must be an int >= 0: {self.keep_recent!r}"
            )
        if self.summarizer is not None and not callable(self.summarizer):
            raise ValueError("summarizer must be callable or None")

    @property
    def effective_summarizer(self):
        return self.summarizer or ExtractiveSummarizer()


def manifest_data() -> dict:
    """The citizen's manifest as plain data (PLG-02)."""
    return {
        "id": PLUGIN_ID,
        "name": "Memory Summarise",
        "version": PLUGIN_VERSION,
        "api_version": 1,
        "description": "Rolling chat summary into memory.",
        "author": "Rúnmál",
        "capabilities": ["chat.events", "prompt.hooks", "ui.slots"],
        "permissions": ["chat.read", "prompt.inject", "ui.contribute"],
        "events": list(DECLARED_EVENTS),
        "prompt_hooks": [
            {"id": HOOK_ID, "stage": "slots", "priority": 100}
        ],
        "ui_slots": [
            {
                "id": UI_LOCAL_ID,
                "slot": "chat.sidebar",
                "label": "Summary",
                "order": 100,
                "payload": {"kind": "panel", "route": "summary"},
            }
        ],
        "settings": {
            "schema": {
                "budget_tokens": {"type": "integer", "minimum": 1},
                "keep_recent": {"type": "integer", "minimum": 0},
            },
            "defaults": {
                "budget_tokens": DEFAULT_BUDGET_TOKENS,
                "keep_recent": DEFAULT_KEEP_RECENT,
            },
        },
        "enabled_by_default": False,
    }


def build_manifest() -> PluginManifest:
    """The validated manifest, built through the strict parser."""
    return manifest_from_data(manifest_data())


def config_from_manifest(manifest: PluginManifest) -> SummariseConfig:
    """Config from the manifest's settings defaults.

    Lenient by design (P-081 stores settings verbatim and
    leaves interpretation to the consumer): a missing or
    invalid value falls back to the module constant.
    """
    defaults: dict = {}
    if isinstance(manifest.settings, dict):
        raw = manifest.settings.get("defaults")
        if isinstance(raw, dict):
            defaults = raw
    budget = defaults.get("budget_tokens", DEFAULT_BUDGET_TOKENS)
    if not _is_int(budget) or budget < 1:
        budget = DEFAULT_BUDGET_TOKENS
    keep = defaults.get("keep_recent", DEFAULT_KEEP_RECENT)
    if not _is_int(keep) or keep < 0:
        keep = DEFAULT_KEEP_RECENT
    return SummariseConfig(budget_tokens=budget, keep_recent=keep)


def sandbox_grants() -> GrantSet:
    """The citizen's P-082 resource grants: empty, by construction."""
    return grants_from_manifest(manifest_to_data(build_manifest()))


async def summary_status(
    session: AsyncSession, user_id: str, chat_id: str
) -> dict | None:
    """The inspectable state of one chat's rolling summary.

    Owner-scoped: ``None`` when the chat is missing or not the
    user's. ``memory_id`` / ``summarizer_version`` are read
    from the ``kind='summary'`` memory whose extractor names
    the latest summary row -- the founding provenance chain.
    """
    from runmal.chats.service import get_chat

    if await get_chat(session, user_id, chat_id) is None:
        return None
    latest = await latest_summary(session, chat_id)
    base = {
        "plugin_id": PLUGIN_ID,
        "chat_id": chat_id,
        "has_summary": False,
        "version": 0,
        "summary": "",
        "source_first_id": None,
        "source_last_id": None,
        "source_count": 0,
        "memory_id": None,
        "summarizer_version": None,
    }
    if latest is None:
        return base
    base.update(
        has_summary=True,
        version=latest.version,
        summary=latest.summary,
        source_first_id=latest.source_first_id,
        source_last_id=latest.source_last_id,
        source_count=latest.source_count,
    )
    memories = await memory_service.list_memories(
        session, user_id, kind="summary"
    )
    for memory in memories:
        extractor = memory_service.memory_to_dict(memory)["extractor"]
        if extractor.get("summary_id") == latest.id:
            base["memory_id"] = memory.id
            base["summarizer_version"] = extractor.get("version")
    return base


async def refresh_summary(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    *,
    config: SummariseConfig,
) -> dict | None:
    """Roll one chat's summary forward; returns summary_status.

    ``None`` when the chat is missing or not the user's.
    Flush-only (the S404 pattern): the caller commits.
    """
    from runmal.chats.service import get_history

    messages = await get_history(session, user_id, chat_id)
    if messages is None:
        return None
    await roll_summaries(
        session,
        user_id,
        chat_id,
        list(messages),
        budget_tokens=config.budget_tokens,
        keep_recent=config.keep_recent,
        summarizer=config.effective_summarizer,
    )
    await session.flush()
    return await summary_status(session, user_id, chat_id)


class MemorySummarisePlugin:
    """The citizen: event-driven refresh + the summary slot.

    ``session_factory`` is host bootstrap wiring (trusted
    in-tree code binds it at registration); with no factory
    the citizen is inert -- handlers abstain quietly and the
    registry records no failure.
    """

    def __init__(
        self,
        session_factory=None,
        config: SummariseConfig | None = None,
    ) -> None:
        self._session_factory = session_factory
        self.config = config or config_from_manifest(build_manifest())

    @property
    def manifest(self) -> PluginManifest:
        return build_manifest()

    def bind_session_factory(self, session_factory) -> None:
        self._session_factory = session_factory

    def handlers(self) -> PluginHandlers:
        return PluginHandlers(
            on_event=self.on_event,
            prompt_hooks={HOOK_ID: self.summary_slot},
        )

    async def on_event(self, event) -> None:
        """Refresh on message mutation; a no-op otherwise.

        Opens its own session from the host factory (the host
        session is committed and closed by dispatch time),
        resolves the owner from the chat row, refreshes and
        commits. A vanished chat is a quiet return, never a
        failure; genuine errors propagate to the registry's
        failure rule (PLG-01 keeps them out of the chat path).
        """
        if event.name not in REFRESH_EVENTS or not event.chat_id:
            return
        if self._session_factory is None:
            return
        async with self._session_factory() as session:
            chat = await session.get(Chat, event.chat_id)
            if chat is None:
                return
            await refresh_summary(
                session, chat.user_id, chat.id, config=self.config
            )
            await session.commit()

    async def summary_slot(self, ctx, slots):
        """The slots-stage hook: offer the current summary.

        Abstains (None) when unbound, chat-less, or when no
        summary exists yet (PLG-06). The host namespaces the
        returned slot's id and forces its provenance (PLG-07).
        """
        if self._session_factory is None or ctx.chat_id is None:
            return None
        async with self._session_factory() as session:
            chat = await session.get(Chat, ctx.chat_id)
            if chat is None:
                return None
            latest = await latest_summary(session, chat.id)
            if latest is None or not latest.summary:
                return None
            return [
                Slot(
                    id=SLOT_LOCAL_ID,
                    kind="chat_summary",
                    role="system",
                    content=f"{_SUMMARY_HEADER}\n{latest.summary}",
                    order=4,
                    priority=100,
                    trigger="rolling-summary",
                )
            ]


def register_plugin(
    registry: PluginRegistry,
    session_factory=None,
    *,
    config: SummariseConfig | None = None,
    enable: bool = False,
) -> tuple[PluginRecord, MemorySummarisePlugin]:
    """Register the citizen into ``registry`` (trusted code only).

    Returns the record and the plugin instance. ``enable=True``
    performs the owner's enable verb immediately (bootstrap
    convenience); the default leaves the plugin REGISTERED,
    receiving and contributing nothing until enabled.
    """
    plugin = MemorySummarisePlugin(session_factory, config)
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID)
        record = registry.get(PLUGIN_ID)
    return record, plugin


__all__ = [
    "DECLARED_EVENTS",
    "DEFAULT_BUDGET_TOKENS",
    "DEFAULT_KEEP_RECENT",
    "HOOK_ID",
    "MAX_SUMMARY_CHARS",
    "PLUGIN_ID",
    "PLUGIN_VERSION",
    "REFRESH_EVENTS",
    "SLOT_LOCAL_ID",
    "SUMMARIZER_VERSION",
    "UI_LOCAL_ID",
    "ExtractiveSummarizer",
    "MemorySummarisePlugin",
    "SummariseConfig",
    "build_manifest",
    "config_from_manifest",
    "manifest_data",
    "refresh_summary",
    "register_plugin",
    "sandbox_grants",
    "summary_status",
]
