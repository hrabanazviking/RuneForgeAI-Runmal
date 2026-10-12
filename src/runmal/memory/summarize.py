"""Chat auto-summarization (S404): rolling summaries of old history.

When a chat's history would exceed the prompt budget, the oldest
messages are folded into a versioned summary record. The summary keeps
its full provenance: the source range (first/last message id + count)
of everything it compresses (MEMORY_ARCHITECTURE.md §1 class 4), and a
``kind='summary'`` memory whose sources are the summarized messages,
so mutation sync (S409) and rebuild (S415) can reason about it.

The summarizer is a seam: tests use the deterministic extractive fake;
a real backend-driven summarizer implements the same callable shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import ChatSummary
from runmal.memory import service
from runmal.tokens import estimate_tokens

SUMMARIZER_VERSION = "fake-extractive-1"


class FakeSummarizer:
    """Deterministic extractive summarizer (test double for the seam)."""

    version = SUMMARIZER_VERSION

    def __call__(self, texts: list[str]) -> str:
        heads = [" ".join(t.split()[:8]) for t in texts]
        return f"Summary of {len(texts)} messages: " + " | ".join(heads)


@dataclass(frozen=True)
class RollResult:
    summary_id: str | None
    version: int
    summarized_count: int
    kept_ids: tuple[str, ...]
    total_tokens: int
    under_budget: bool

    def to_dict(self) -> dict:
        return {"summary_id": self.summary_id, "version": self.version,
                "summarized_count": self.summarized_count,
                "kept_ids": list(self.kept_ids), "total_tokens": self.total_tokens,
                "under_budget": self.under_budget}


async def latest_summary(session: AsyncSession, chat_id: str) -> ChatSummary | None:
    return await session.scalar(
        select(ChatSummary).where(ChatSummary.chat_id == chat_id)
        .order_by(ChatSummary.version.desc()).limit(1))


async def roll_summaries(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    messages: list,
    *,
    budget_tokens: int,
    keep_recent: int = 4,
    summarizer=None,
) -> RollResult:
    """Fold oldest history into a rolling summary until under budget.

    ``messages`` are ORM Message rows in chronological order. Messages
    already covered by the latest summary (its ``source_count``) are not
    re-folded; the new version folds the prior summary text in, so the
    recorded source range always spans from the first message.
    """
    summarizer = summarizer or FakeSummarizer()
    prior = await latest_summary(session, chat_id)
    covered = prior.source_count if prior else 0
    pending = list(messages[covered:])
    summary_text = prior.summary if prior else ""

    def total_tokens() -> int:
        kept = sum(estimate_tokens(m.content) for m in pending)
        return kept + (estimate_tokens(summary_text) if summary_text else 0)

    folded = 0
    while len(pending) > keep_recent and total_tokens() > budget_tokens:
        msg = pending.pop(0)
        folded += 1
        inputs = ([summary_text] if summary_text else []) + [msg.content]
        summary_text = summarizer(inputs)

    if folded == 0:
        total = total_tokens()
        if prior is None:
            return RollResult(None, 0, 0, tuple(m.id for m in pending), total,
                              total <= budget_tokens)
        return RollResult(prior.id, prior.version, covered,
                          tuple(m.id for m in pending), total,
                          total <= budget_tokens)

    n_summarized = covered + folded
    summarized_msgs = list(messages[:n_summarized])
    record = ChatSummary(
        user_id=user_id, chat_id=chat_id,
        version=(prior.version + 1 if prior else 1),
        summary=summary_text,
        source_first_id=summarized_msgs[0].id,
        source_last_id=summarized_msgs[-1].id,
        source_count=n_summarized)
    session.add(record)
    await session.flush()
    await service.create_memory(
        session, user_id, content=summary_text, kind="summary", chat_id=chat_id,
        extractor={"kind": "summarizer", "version": summarizer.version,
                   "summary_id": record.id},
        sources=tuple(("message", m.id, chat_id) for m in summarized_msgs))
    total = total_tokens()
    return RollResult(record.id, record.version, n_summarized,
                      tuple(m.id for m in pending), total, total <= budget_tokens)
