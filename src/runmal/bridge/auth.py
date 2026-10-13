"""Bridge authentication dependencies (S601).

Bridge routes are NOT behind the local application credential: a bridge
token is a separate, scoped credential (INV-029), and the local
credential is not a bridge token. `get_bridge_identity` authenticates
the bearer token; `require_bridge_scope` builds a dependency that also
enforces one capability (and resource, taken from a path parameter) on
every operation (BRIDGE_PROTOCOL §13).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.bridge import service
from runmal.bridge.scopes import scope_allows
from runmal.db.deps import get_session

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class BridgeIdentity:
    credential_id: str
    user_id: str
    name: str
    scopes: tuple[str, ...]


async def get_bridge_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> BridgeIdentity:
    presented = credentials.credentials if credentials else ""
    credential = await service.authenticate(session, presented)
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing, invalid, or revoked bridge credential",
        )
    return BridgeIdentity(
        credential_id=credential.id,
        user_id=credential.user_id,
        name=credential.name,
        scopes=tuple(json.loads(credential.scopes_json)),
    )


def require_bridge_scope(capability: str, *, resource_param: str | None = None):
    """Dependency factory: authenticated bridge identity + scope check.

    `resource_param` names the path parameter holding the resource id
    (e.g. "chat_id"); omitted for resource-less capabilities such as
    `tts:request`. Raises 403 when the token's scopes do not allow the
    operation — a valid token never widens its own grant (INV-029).
    """

    async def guard(
        request: Request,
        identity: BridgeIdentity = Depends(get_bridge_identity),
    ) -> BridgeIdentity:
        resource = request.path_params.get(resource_param) if resource_param else None
        if not scope_allows(identity.scopes, capability, resource):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"bridge credential lacks required scope: {capability}",
            )
        return identity

    return guard
