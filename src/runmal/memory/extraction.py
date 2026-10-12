"""Event/fact extraction (S405): async LLM-assisted candidate extraction.

Extraction NEVER blocks the reply path (MEMORY_ARCHITECTURE.md §3): the
chat flow enqueues messages and returns immediately; a background worker
runs the extractor and persists candidates with full extractor
provenance (provider/model/version/prompt-version) and source links.

The extractor is a seam. Tests use the deterministic FakeExtractor; a
real LLM extractor implements the same ``extract`` protocol.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.memory import service

EXTRACTOR_VERSION = "fake-rules-1"
PROMPT_VERSION = "extract-v1"

_PATTERNS = (
    (re.compile(r"^(.+?) lives in (.+?)\.?$"), "lives_in"),
    (re.compile(r"^(.+?) now lives in (.+?)\.?$"), "lives_in"),
    (re.compile(r"^(.+?) prefers (.+?)\.?$"), "prefers"),
    (re.compile(r"^(.+?) likes (.+?)\.?$"), "likes"),
    (re.compile(r"^(.+?) is a (.+?)\.?$"), "is_a"),
)


@dataclass(frozen=True)
class Candidate:
    content: str
    subject: str
    predicate: str
    object_text: str
    source_message_id: str
    confidence: float = 0.8

    def to_dict(self) -> dict:
        return {"content": self.content, "subject": self.subject,
                "predicate": self.predicate, "object": self.object_text,
                "source_message_id": self.source_message_id,
                "confidence": self.confidence}


class FakeExtractor:
    """Deterministic rule extractor (the test double for the LLM seam)."""

    provider = "fake"
    model = "fake-extractor"
    version = EXTRACTOR_VERSION
    prompt_version = PROMPT_VERSION

    def meta(self) -> dict:
        return {"provider": self.provider, "model": self.model,
                "version": self.version, "prompt_version": self.prompt_version}

    async def extract(self, messages: list) -> list[Candidate]:
        out: list[Candidate] = []
        for msg in messages:
            for sentence in re.split(r"(?<=[.!?])\s+", msg.content.strip()):
                sentence = sentence.strip()
                for pattern, predicate in _PATTERNS:
                    m = pattern.match(sentence)
                    if m:
                        subject, obj = m.group(1).strip(), m.group(2).strip()
                        out.append(Candidate(
                            content=sentence.rstrip(".") + ".",
                            subject=subject, predicate=predicate,
                            object_text=obj, source_message_id=msg.id))
                        break
        return out


@dataclass
class ExtractionJob:
    user_id: str
    chat_id: str
    messages: list
    witnesses: tuple[str, ...] = ()
    scope: str = "user"
    character_id: str | None = None


async def persist_candidates(
    session: AsyncSession, job: ExtractionJob, candidates: list[Candidate],
    extractor,
) -> list[str]:
    """Persist candidates as semantic memories with provenance."""
    ids = []
    for cand in candidates:
        memory = await service.create_memory(
            session, job.user_id, content=cand.content, kind="semantic",
            subject=cand.subject, predicate=cand.predicate,
            confidence=cand.confidence, scope=job.scope,
            witnesses=job.witnesses, character_id=job.character_id,
            chat_id=job.chat_id, extractor=extractor.meta(),
            sources=(("message", cand.source_message_id, job.chat_id),))
        ids.append(memory.id)
    return ids


class ExtractionQueue:
    """Background extraction worker: enqueue never waits on the extractor."""

    def __init__(self, session_factory, extractor=None):
        self._factory = session_factory
        self._extractor = extractor or FakeExtractor()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self.completed: list[list[str]] = []

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    def enqueue(self, job: ExtractionJob) -> None:
        """Fire-and-forget: returns immediately (the reply path's view)."""
        self.start()
        self._queue.put_nowait(job)

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                candidates = await self._extractor.extract(job.messages)
                async with self._factory() as session:
                    ids = await persist_candidates(
                        session, job, candidates, self._extractor)
                    await session.commit()
                self.completed.append(ids)
            finally:
                self._queue.task_done()

    async def drain(self) -> None:
        await self._queue.join()

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None


__all__ = [
    "Candidate", "ExtractionJob", "ExtractionQueue", "FakeExtractor",
    "persist_candidates",
]
