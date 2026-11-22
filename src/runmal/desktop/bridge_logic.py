"""Bridge admin logic for the desktop shell (R-14) — Qt-free.

The words over the bridge credential admin surface (S601):
create, list, revoke. INV-023 governs everything here: a
created credential's token plaintext appears exactly once, in
the creation response the flow hands back raw to the caller
(the window shows it once); it is never stored by the flow,
never logged, and never rendered by any words function in
this module — credential views carry id/label/scopes/state
only, and the status words below are built from views alone.
"""

from __future__ import annotations

from typing import Any

from runmal.desktop.client import BridgeCredentialView, RunmalClient


def credential_line(view: BridgeCredentialView) -> str:
    """One credential, one line: label, state, scopes, and its
    stamps. Never a token — the view does not carry one."""
    bits = [view.label]
    bits.append(view.state)
    if view.scopes:
        bits.append("scopes: " + ", ".join(view.scopes))
    else:
        bits.append("no scopes")
    if view.created_at:
        bits.append(f"created {view.created_at}")
    if view.last_used_at:
        bits.append(f"last used {view.last_used_at}")
    if view.revoked_at:
        bits.append(f"revoked {view.revoked_at}")
    return " · ".join(bits)


def bridge_status_words(credentials: list[BridgeCredentialView]) -> str:
    """The bridge pane's summary: how many credentials exist,
    how many are active vs revoked, and every scope in force —
    counted from views only, so no token can appear here."""
    if not credentials:
        return (
            "No bridge credentials. A credential lets an external "
            "bridge act with exactly the scopes it is granted; its "
            "token is shown once, at creation, and never again."
        )
    active = [c for c in credentials if c.state == "active"]
    revoked = [c for c in credentials if c.state == "revoked"]
    lines = [
        f"{len(credentials)} bridge credential(s): "
        f"{len(active)} active, {len(revoked)} revoked."
    ]
    scopes = sorted({s for c in active for s in c.scopes})
    if scopes:
        lines.append("Scopes in force: " + ", ".join(scopes))
    lines.extend(f"- {credential_line(c)}" for c in credentials)
    return "\n".join(lines)


class BridgeFlow:
    """The Bridge dialog's verbs over the typed client."""

    def __init__(self, client: RunmalClient) -> None:
        self._client = client

    def credentials(self) -> list[BridgeCredentialView]:
        return self._client.list_bridge_credentials()

    def create_credential(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a credential and return the RAW creation
        result — token included, exactly as the engine answers.
        The WINDOW shows the token once; this flow retains
        nothing (the dict is the caller's to display and drop).

        The engine's body is ``name`` + ``scopes``; the
        window's form speaks of a label, so a ``label`` key is
        translated to ``name`` here when no name was given."""
        body = dict(payload)
        if "name" not in body and body.get("label"):
            body["name"] = body.pop("label")
        return self._client.create_bridge_credential(body)

    def revoke(self, credential_id: str) -> BridgeCredentialView:
        return self._client.revoke_bridge_credential(credential_id)
