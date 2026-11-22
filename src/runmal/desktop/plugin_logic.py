"""Plugin logic for the desktop shell (R-14) — Qt-free.

The words over the engine's plugin surface (P-081/P-083/P-089/
P-092/P-093/P-099): the registry list and detail, the manager's
permission cards (the grant decision is made on exactly what
the card shows), failure reports in plain words, and the two
citizen stores that ride the same router — quick replies and
expression sets — plus the per-chat variables store.
"""

from __future__ import annotations

from typing import Any

from runmal.desktop.client import (
    ExpressionSetView,
    PluginFailureReportView,
    PluginView,
    QuickReplyView,
    RunmalClient,
)


def plugin_line(view: PluginView) -> str:
    """One plugin, one line: name, version, state, and its
    declared surface in counts."""
    bits = [view.name or view.id]
    if view.version:
        bits.append(f"v{view.version}")
    bits.append(view.state or "unknown state")
    bits.append(
        f"{len(view.capabilities)} capabilit(ies), "
        f"{len(view.permissions)} permission(s)"
    )
    if view.consecutive_failures:
        bits.append(f"{view.consecutive_failures} consecutive failure(s)")
    if view.last_error:
        bits.append(f"last error: {view.last_error.get('error_type', '')}")
    return " · ".join(bits)


def plugin_detail_words(detail: dict[str, Any]) -> str:
    """The plugin detail pane: identity and state, what it
    declares, what is reserved, and its retained failures."""
    if not detail:
        return "No plugin selected."
    lines: list[str] = []
    name = detail.get("name") or detail.get("id") or "plugin"
    heading = str(name)
    if detail.get("version"):
        heading += f" · v{detail['version']}"
    if detail.get("state"):
        heading += f" · {detail['state']}"
    lines.append(heading)
    manifest = detail.get("manifest")
    if isinstance(manifest, dict):
        description = manifest.get("description")
        if description:
            lines.append(str(description))
        author = manifest.get("author")
        if author:
            lines.append(f"Author: {author}")
    capabilities = detail.get("capabilities")
    if isinstance(capabilities, list) and capabilities:
        lines.append("Capabilities: " + ", ".join(str(c) for c in capabilities))
    permissions = detail.get("permissions")
    if isinstance(permissions, list) and permissions:
        lines.append("Permissions: " + ", ".join(str(p) for p in permissions))
    reserved = detail.get("reserved_permissions")
    if isinstance(reserved, list) and reserved:
        lines.append(
            "Reserved (honoured by nothing in v1): "
            + ", ".join(str(p) for p in reserved)
        )
    failures = detail.get("failure_log")
    if isinstance(failures, list):
        lines.append(f"Recorded failures: {len(failures)}")
        for failure in failures:
            if not isinstance(failure, dict):
                continue
            lines.append(
                f"- {failure.get('surface', '')}/"
                f"{failure.get('hook', '')}: "
                f"{failure.get('error_type', '')} at "
                f"{failure.get('at', '')}"
            )
    return "\n".join(lines)


def permission_words(card: dict[str, Any]) -> str:
    """The permission card in words — the grant surface. Every
    declared permission with its plain-language effect, what is
    reserved, and the card's own honesty notes, verbatim."""
    if not card:
        return "No permission card."
    lines: list[str] = []
    name = card.get("name") or card.get("plugin_id") or "plugin"
    heading = f"Permissions for {name}"
    if card.get("version"):
        heading += f" v{card['version']}"
    lines.append(heading)
    description = card.get("description")
    if description:
        lines.append(str(description))
    if card.get("requires_grant"):
        lines.append(
            "Installing or updating proceeds only when the granted "
            "set equals the declared set exactly."
        )
    else:
        lines.append("This plugin declares no permissions to grant.")
    rows = card.get("permissions")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            line = f"- {row.get('name', '')}"
            if row.get("reserved"):
                line += " (RESERVED — grants nothing today)"
            granted = row.get("granted")
            if granted is True:
                line += " · granted"
            elif granted is False:
                line += " · not granted"
            effect = row.get("effect")
            if effect:
                line += f": {effect}"
            lines.append(line)
    capabilities = card.get("capabilities")
    if isinstance(capabilities, list) and capabilities:
        named = ", ".join(
            str(c.get("name", "")) for c in capabilities if isinstance(c, dict)
        )
        if named:
            lines.append(f"Capabilities: {named}")
    changes = card.get("changes")
    if isinstance(changes, dict):
        lines.append(
            f"Update: v{changes.get('from_version', '')} → "
            f"v{changes.get('to_version', '')}"
        )
        for key, label in (
            ("permissions_added", "permissions added"),
            ("permissions_removed", "permissions removed"),
            ("capabilities_added", "capabilities added"),
            ("capabilities_removed", "capabilities removed"),
        ):
            values = changes.get(key)
            if isinstance(values, list) and values:
                lines.append(f"- {label}: {', '.join(str(v) for v in values)}")
    notes = card.get("notes")
    if isinstance(notes, list):
        lines.extend(
            f"Note: {n}" for n in notes if isinstance(n, str)
        )
    return "\n".join(lines)


def failure_line(report: PluginFailureReportView | dict[str, Any]) -> str:
    """One plugin's failure report, one line: state, how many
    failures stand recorded, and the report's own plain words
    when it carries any."""
    if isinstance(report, dict):
        view = PluginFailureReportView.from_dict(report)
    else:
        view = report
    bits = [view.plugin_id or "plugin"]
    if view.state:
        bits.append(view.state)
    bits.append(f"{view.total_recorded} recorded failure(s)")
    if view.consecutive_failures:
        bits.append(f"{view.consecutive_failures} in a row")
    if view.self_disabled:
        bits.append("self-disabled")
    if view.plain:
        bits.append(view.plain)
    return " · ".join(bits)


def quick_reply_line(view: QuickReplyView) -> str:
    """One quick reply, one line: name, scope, step count, and
    whether it can fire."""
    bits = [view.name or view.id]
    bits.append(f"scope: {view.scope or 'user'}")
    if view.chat_id:
        bits.append(f"chat {view.chat_id}")
    bits.append(f"{view.step_count} step(s)")
    bits.append("enabled" if view.enabled else "disabled")
    return " · ".join(bits)


def expression_set_line(view: ExpressionSetView) -> str:
    """One expression set, one line: whose set, how many
    expressions it declares, and its default when it has one."""
    bits = [f"character {view.character_id}"]
    bits.append(f"{view.entry_count} expression(s)")
    if view.entry_names:
        bits.append(", ".join(view.entry_names))
    if view.default:
        bits.append(f"default: {view.default}")
    return " · ".join(bits)


class PluginFlow:
    """The Plugins dialog's verbs over the typed client."""

    def __init__(self, client: RunmalClient) -> None:
        self._client = client

    def manager(self) -> dict[str, Any]:
        return self._client.plugin_manager()

    def plugins(self) -> list[PluginView]:
        return self._client.list_plugins()

    def detail(self, plugin_id: str) -> dict[str, Any]:
        return self._client.plugin_detail(plugin_id)

    def permission_card(self, plugin_id: str) -> dict[str, Any]:
        return self._client.plugin_permission_card(plugin_id)

    def failure_reports(self) -> list[PluginFailureReportView]:
        return self._client.plugin_failure_reports()

    def failure_report(self, plugin_id: str) -> PluginFailureReportView:
        return self._client.plugin_failure_report(plugin_id)

    @staticmethod
    def _install_body(
        payload: dict[str, Any], *, for_preview: bool = False
    ) -> dict[str, Any]:
        """Resolve an install payload to the engine's body.

        The engine's roads require ``pack`` (the local pack
        envelope) + ``granted_permissions``. A payload already
        carrying ``pack`` passes through; a payload carrying
        ``source``/``path`` names a pack envelope file on disk
        (what the window's Install field holds) — the flow
        reads it and grants exactly the permissions the
        envelope's own manifest declares, which is what the
        preview card shows. Anything else is refused plainly.
        """
        if "pack" in payload:
            body = dict(payload)
            if for_preview:
                return {"pack": body["pack"]}
            if "granted_permissions" not in body:
                manifest = body["pack"].get("plugin", {})
                body["granted_permissions"] = list(
                    manifest.get("permissions", [])
                )
            return body
        source = payload.get("source") or payload.get("path")
        if not source:
            raise ValueError(
                "plugin install needs a pack: a 'pack' envelope "
                "or the path to a pack file"
            )
        import json
        from pathlib import Path

        try:
            envelope = json.loads(Path(str(source)).read_text())
        except OSError as exc:
            raise ValueError(
                f"could not read the pack file {source}: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"the pack file {source} is not JSON: {exc}"
            ) from exc
        if not isinstance(envelope, dict) or "plugin" not in envelope:
            raise ValueError(
                f"the file {source} is not a plugin pack envelope"
            )
        grants = payload.get("granted_permissions")
        if grants is None:
            grants = list(envelope["plugin"].get("permissions", []))
        if for_preview:
            return {"pack": envelope}
        body = {"pack": envelope, "granted_permissions": grants}
        if "enable" in payload:
            body["enable"] = bool(payload["enable"])
        return body

    def install_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.plugin_install_preview(
            self._install_body(payload, for_preview=True)
        )

    def install(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.install_plugin(self._install_body(payload))

    def update(
        self, plugin_id: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """The versioned swap (the engine's road requires the
        new pack in the body: ``pack`` + ``granted_permissions``).
        Called without a payload there is nothing truthful to
        send, so the flow refuses plainly instead of posting an
        empty update the engine would reject anyway."""
        if payload is None:
            raise ValueError(
                "plugin update requires the new pack payload "
                "({'pack': ..., 'granted_permissions': [...]})"
            )
        return self._client.update_plugin(
            plugin_id, self._install_body(payload)
        )

    def uninstall(self, plugin_id: str) -> dict[str, Any]:
        return self._client.uninstall_plugin(plugin_id)

    def enable(self, plugin_id: str) -> dict[str, Any]:
        return self._client.enable_plugin(plugin_id)

    def disable(self, plugin_id: str) -> dict[str, Any]:
        return self._client.disable_plugin(plugin_id)

    def acknowledge(self, plugin_id: str) -> dict[str, Any]:
        return self._client.acknowledge_plugin(plugin_id)

    # -- quick replies -------------------------------------------

    def quick_replies(self) -> list[QuickReplyView]:
        return self._client.list_quick_replies()

    def create_quick_reply(
        self, payload: dict[str, Any]
    ) -> QuickReplyView:
        return self._client.create_quick_reply(payload)

    def update_quick_reply(
        self, reply_id: str, payload: dict[str, Any]
    ) -> QuickReplyView:
        return self._client.update_quick_reply(reply_id, payload)

    def delete_quick_reply(self, reply_id: str) -> bool:
        return self._client.delete_quick_reply(reply_id)

    def execute_quick_reply(
        self, reply_id: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._client.execute_quick_reply(reply_id, payload)

    def quick_reply_executions(self) -> list[dict[str, Any]]:
        return self._client.quick_reply_executions()

    # -- expressions ----------------------------------------------

    def expression_sets(self) -> list[ExpressionSetView]:
        return self._client.list_expression_sets()

    def expression_set(self, character_id: str) -> ExpressionSetView:
        return self._client.get_expression_set(character_id)

    def save_expression_set(
        self, character_id: str, payload: dict[str, Any]
    ) -> ExpressionSetView:
        """Save a character's set: replace when one exists,
        declare when none does. The engine's PUT 404s on a
        missing set and its POST refuses a duplicate, so the
        flow tries the replace first and falls back to the
        declaration — the caller asked to SAVE, either way."""
        from runmal.desktop.client import NotFoundError

        body = dict(payload)
        body.setdefault("character_id", character_id)
        try:
            return self._client.update_expression_set(character_id, body)
        except NotFoundError:
            return self._client.create_expression_set(body)

    def delete_expression_set(self, character_id: str) -> bool:
        return self._client.delete_expression_set(character_id)

    def expressions_current(self, chat_id: str = "") -> dict[str, Any]:
        """A chat's current expression selection, raw. The
        engine's road is chat-scoped (``chat_id`` is required);
        with no chat named there is no current expression to
        read, and the flow says so with an empty document
        rather than inventing one."""
        if not chat_id:
            return {}
        return self._client.expressions_current(chat_id)

    # -- chat variables --------------------------------------------

    def chat_variables(self, chat_id: str) -> dict[str, Any]:
        return self._client.chat_variables(chat_id)

    def set_chat_variable(
        self,
        chat_id: str,
        key: str,
        *,
        value: Any = None,
        flag: bool | None = None,
    ) -> dict[str, Any]:
        return self._client.set_chat_variable(
            chat_id, key, value=value, flag=flag
        )

    def unset_chat_variable(self, chat_id: str, key: str) -> bool:
        return self._client.unset_chat_variable(chat_id, key)

    def clear_chat_variables(self, chat_id: str) -> dict[str, Any]:
        return self._client.clear_chat_variables(chat_id)
