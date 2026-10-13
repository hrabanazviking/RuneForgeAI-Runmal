"""Bridge credential service (S601, BRIDGE_PROTOCOL §2, INV-029).

Each bridge gets its own credential: a high-entropy token whose
plaintext is returned exactly once at creation. Only the SHA-256 hash
is stored, so the database — and therefore logs, exports and backups —
never contains a usable bridge secret (INV-023). Revocation is a
timestamp; a revoked credential authenticates nothing.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.bridge.scopes import validate_scopes
from runmal.db.models import BridgeCredential

TOKEN_PREFIX = "rmb_"
TOKEN_BYTES = 32


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def credential_to_dict(credential: BridgeCredential) -> dict:
    """Public view of a credential — never the token, never its hash."""
    return {
        "id": credential.id,
        "name": credential.name,
        "scopes": json.loads(credential.scopes_json),
        "created_at": credential.created_at,
        "revoked_at": credential.revoked_at,
        "last_used_at": credential.last_used_at,
    }


async def create_credential(
    session: AsyncSession, user_id: str, name: str, scopes: list[str]
) -> tuple[BridgeCredential, str]:
    """Create a credential; returns (row, plaintext token shown once).

    Raises ValueError on an invalid scope set (router maps to 422).
    """
    normalized = validate_scopes(scopes)
    if not normalized:
        raise ValueError("a bridge credential needs at least one scope")
    token = TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)
    credential = BridgeCredential(
        user_id=user_id,
        name=name,
        token_hash=hash_token(token),
        scopes_json=json.dumps(normalized),
        created_at=_now_iso(),
    )
    session.add(credential)
    await session.flush()
    await session.commit()
    return credential, token


async def list_credentials(session: AsyncSession, user_id: str) -> list[BridgeCredential]:
    result = await session.execute(
        select(BridgeCredential)
        .where(BridgeCredential.user_id == user_id)
        .order_by(BridgeCredential.created_at)
    )
    return list(result.scalars().all())


async def revoke_credential(
    session: AsyncSession, user_id: str, credential_id: str
) -> BridgeCredential | None:
    """Revoke a credential (idempotent: re-revoking keeps the first stamp)."""
    result = await session.execute(
        select(BridgeCredential).where(
            BridgeCredential.id == credential_id, BridgeCredential.user_id == user_id
        )
    )
    credential = result.scalar_one_or_none()
    if credential is None:
        return None
    if credential.revoked_at is None:
        credential.revoked_at = _now_iso()
        await session.commit()
    return credential


async def authenticate(session: AsyncSession, presented: str) -> BridgeCredential | None:
    """Resolve a presented bearer token to a live credential, or None.

    The lookup key is the token hash; the comparison is still done in
    constant time so the check does not lean on index timing alone.
    Successful authentication stamps `last_used_at`.
    """
    if not presented or not presented.startswith(TOKEN_PREFIX):
        return None
    digest = hash_token(presented)
    result = await session.execute(
        select(BridgeCredential).where(BridgeCredential.token_hash == digest)
    )
    credential = result.scalar_one_or_none()
    if credential is None or not hmac.compare_digest(credential.token_hash, digest):
        return None
    if credential.revoked_at is not None:
        return None
    credential.last_used_at = _now_iso()
    await session.commit()
    return credential
