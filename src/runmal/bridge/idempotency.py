"""Idempotency store for retried bridge writes (S610, INV-030).

Semantics (BRIDGE_PROTOCOL §4):

- Same credential + operation + key + **same request** -> the stored
  response is replayed; the operation does not run twice.
- Same key, **different request** -> a conflict (the router answers
  409). A key is a name for one logical operation, not a bucket.
- Keys are scoped per credential and per operation: two bridges may
  use the same key string independently, and a turn key never
  collides with a generation key.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import BridgeIdempotencyKey

MAX_KEY_LENGTH = 200

OP_TURN_APPEND = "turns.append"
OP_GENERATE = "chats.generate"


def fingerprint(operation: str, payload: dict) -> str:
    canonical = json.dumps(
        {"operation": operation, "payload": payload}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_key(raw: str | None) -> str | None:
    """Empty/absent keys mean 'no idempotency'; over-long keys are a
    client error (ValueError -> 422 at the router)."""
    if raw is None:
        return None
    key = raw.strip()
    if not key:
        return None
    if len(key) > MAX_KEY_LENGTH:
        raise ValueError(f"idempotency key exceeds {MAX_KEY_LENGTH} characters")
    return key


async def lookup(
    session: AsyncSession, credential_id: str, operation: str, key: str
) -> BridgeIdempotencyKey | None:
    return await session.get(BridgeIdempotencyKey, (credential_id, operation, key))


async def store(
    session: AsyncSession,
    credential_id: str,
    operation: str,
    key: str,
    request_hash: str,
    status_code: int,
    response: dict,
) -> BridgeIdempotencyKey:
    row = BridgeIdempotencyKey(
        credential_id=credential_id,
        operation=operation,
        key=key,
        request_hash=request_hash,
        status_code=status_code,
        response_json=json.dumps(response),
        created_at=datetime.now(UTC).isoformat(),
    )
    session.add(row)
    await session.commit()
    return row
