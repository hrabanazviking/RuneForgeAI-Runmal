"""Independent embedding profiles + migration hook (S311) — INV-019.

The embedding axis is independent of chat (ADR-0001, BACKEND_CONTRACT
§1/§9):

- ``switch_active_embedding_profile`` changes ONLY the owner's embedding
  activation. It never reads or writes any chat field: the profile's
  chat backend/model and every chat's pinned profile are untouched.
- When the switch changes the embedding SPACE (provenance key), a
  re-embedding job is scheduled in the ``reembedding_jobs`` ledger and
  the optional migration hook fires. Until a job completes, retrieval
  keeps the FTS fallback available (``embed_or_fallback``, S304) — the
  switch degrades, it never breaks retrieval.
- ``VectorSpaceStore`` keys every stored vector by its FULL provenance
  key (provider, model, dims, version). A similarity query only ever
  searches the bucket of the query's own provenance, so incompatible
  spaces can never mix in one query.
"""

from __future__ import annotations

import inspect
import json
import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends.embeddings import (
    EmbeddingProvenance,
    EmbeddingResult,
    embed_or_fallback,
)
from runmal.backends.profiles import build_embedding_backend, get_profile
from runmal.db.models import EmbeddingActivation, ReembeddingJob, _utcnow

PROBE_TEXT = "runmal provenance probe"


def key_str(provenance: EmbeddingProvenance) -> str:
    """Stable string form of a provenance key (storage + bucket identity)."""
    return json.dumps(list(provenance.key()), separators=(",", ":"))


def job_to_dict(job: ReembeddingJob) -> dict:
    return {
        "id": job.id, "user_id": job.user_id, "from_key": job.from_key,
        "to_key": job.to_key, "status": job.status, "detail": job.detail,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


async def get_activation(
    session: AsyncSession, user_id: str
) -> EmbeddingActivation | None:
    return await session.get(EmbeddingActivation, user_id)


async def list_jobs(session: AsyncSession, user_id: str) -> list[dict]:
    rows = await session.scalars(
        select(ReembeddingJob)
        .where(ReembeddingJob.user_id == user_id)
        .order_by(ReembeddingJob.created_at))
    return [job_to_dict(job) for job in rows]


@dataclass(frozen=True)
class SwitchResult:
    profile_id: str
    provenance: EmbeddingProvenance | None
    provenance_key: str
    job: dict | None  # scheduled re-embedding job, when the space changed
    fts_fallback_available: bool = True

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "provenance_key": self.provenance_key,
            "job": self.job,
            "fts_fallback_available": self.fts_fallback_available,
        }


async def probe_provenance(session: AsyncSession, profile) -> EmbeddingProvenance | None:
    """The TRUE provenance of a profile's embedding space (dims included).

    A single probe embed — model_info alone cannot know dims for every
    adapter. Returns None when embeddings are unavailable (FTS mode).
    """
    backend = await build_embedding_backend(session, profile)
    result = await embed_or_fallback(backend, [PROBE_TEXT])
    if isinstance(result, EmbeddingResult):
        return result.provenance
    return None


async def switch_active_embedding_profile(
    session: AsyncSession,
    user_id: str,
    profile_id: str,
    *,
    on_job=None,
) -> SwitchResult:
    """Make `profile_id` the owner's active EMBEDDING profile.

    Chat is untouched by construction: this function reads only the
    profile's embedding side and writes only the S311 tables. Raises
    KeyError for a missing or foreign profile. Schedules a re-embedding
    job (and fires `on_job`) iff the provenance key changes.
    """
    profile = await get_profile(session, user_id, profile_id)
    if profile is None:
        raise KeyError(f"profile not found: {profile_id}")
    provenance = await probe_provenance(session, profile)
    new_key = key_str(provenance) if provenance is not None else ""

    activation = await get_activation(session, user_id)
    old_key = activation.provenance_key if activation is not None else ""
    created = activation is None
    if created:
        activation = EmbeddingActivation(user_id=user_id)
        session.add(activation)
    activation.profile_id = profile_id
    activation.provenance_key = new_key
    activation.updated_at = _utcnow()

    job: ReembeddingJob | None = None
    if new_key != old_key or (created and provenance is None):
        job = ReembeddingJob(
            user_id=user_id, from_key=old_key, to_key=new_key,
            status="scheduled",
            detail=("embeddings unavailable: FTS fallback active"
                    if provenance is None else "provenance changed"))
        session.add(job)
    await session.flush()
    job_dict = job_to_dict(job) if job is not None else None
    if job is not None and on_job is not None:
        outcome = on_job(job_dict)
        if inspect.isawaitable(outcome):
            await outcome
    return SwitchResult(
        profile_id=profile_id, provenance=provenance,
        provenance_key=new_key, job=job_dict, fts_fallback_available=True)


class VectorSpaceStore:
    """Vectors bucketed by FULL provenance key — spaces never mix."""

    def __init__(self) -> None:
        self._spaces: dict[str, dict[str, tuple[float, ...]]] = {}

    def put(self, doc_id: str, vector: tuple[float, ...],
            provenance: EmbeddingProvenance) -> None:
        expected = provenance.dims
        if len(vector) != expected:
            raise ValueError(
                f"vector dims {len(vector)} != provenance dims {expected}")
        self._spaces.setdefault(key_str(provenance), {})[doc_id] = tuple(vector)

    def spaces(self) -> list[str]:
        return sorted(self._spaces)

    def count(self, provenance: EmbeddingProvenance) -> int:
        return len(self._spaces.get(key_str(provenance), {}))

    def query(self, vector: tuple[float, ...], provenance: EmbeddingProvenance,
              top_k: int = 5) -> list[tuple[str, float]]:
        """Cosine similarity INSIDE one provenance bucket only (INV-019)."""
        if len(vector) != provenance.dims:
            raise ValueError("query vector dims do not match its provenance")
        bucket = self._spaces.get(key_str(provenance), {})
        scored = [(doc_id, _cosine(vector, stored))
                  for doc_id, stored in bucket.items()]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


__all__ = [
    "SwitchResult", "VectorSpaceStore", "get_activation", "key_str",
    "list_jobs", "probe_provenance", "switch_active_embedding_profile",
]
