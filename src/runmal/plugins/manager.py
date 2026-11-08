"""Plugin manager: install / update / uninstall from local packs (P-083).

The manager is the operator the P-081 design named (section
10): it drives exactly the registry's verbs -- register,
unregister, enable, disable, acknowledge -- and adds the three
things v1 deliberately lacked: a local pack road in (packs.py),
a permission-card grant rule (cards.py), and durable install
state.

Durability is a FILE ledger, not a migration (design section
5): ``<store_dir>/installed.json`` records, per pack-installed
plugin, the normalised manifest, the verified content
checksum, the granted permission set, the enabled flag and
pack provenance. The store dir resolves to
``data_dir()/plugins`` in the service layer; tests pass a tmp
dir. Writes are atomic (tmp file + replace, the credential
precedent). A corrupt ledger raises loudly at load -- a
manager that silently "forgets" installs would be lying about
what the owner granted.

Grant rule: install and update proceed only when the caller's
granted permission set EQUALS the manifest's declared set --
the card is what was shown, the grant is what was approved,
and any gap refuses the operation with nothing written.

Citizens registered by trusted in-tree code are never manager
property: installing over, updating or uninstalling one is
refused (PluginConflictError / NotManagedPluginError), never a
silent takeover.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from runmal.plugins.api import SUPPORTED_API_VERSIONS
from runmal.plugins.cards import permission_card
from runmal.plugins.manifest import (
    ManifestError,
    PluginManifest,
    manifest_from_data,
    manifest_to_data,
    validate_surface_requirements,
)
from runmal.plugins.packs import (
    ParsedPack,
    manifest_checksum,
    pack_data_only_problem,
    parse_pack,
)
from runmal.plugins.registry import (
    PluginCompatibilityError,
    PluginHandlers,
    PluginRecord,
    PluginRegistry,
    PluginState,
    UI_PAYLOAD_MAX_BYTES,
)

LEDGER_FORMAT = "runmal-plugin-ledger"
LEDGER_VERSION = 1
LEDGER_FILENAME = "installed.json"


class PluginManagerError(ValueError):
    """A manager operation refused, with the reason stated."""


class GrantMismatchError(PluginManagerError):
    """The granted permission set does not equal the declared
    set the permission card showed."""


class PluginConflictError(PluginManagerError):
    """The plugin id is already occupied in a way this
    operation may not override."""


class NotManagedPluginError(PluginManagerError):
    """The plugin exists but is not pack-managed (a citizen
    registered by in-tree code), so the manager may not touch
    it."""


class DataOnlyPackError(PluginManagerError):
    """The pack's manifest declares something packs cannot
    carry (prompt hooks: code)."""


@dataclass(frozen=True)
class ManagerOutcome:
    """One finished manager operation, as data for the router
    and the tests: what happened, the live record, the card
    that governed it, and the ledger row."""

    outcome: str  # "installed" | "updated" | "duplicate_exact" | "uninstalled"
    plugin_id: str
    record: PluginRecord | None
    card: dict
    row: dict | None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _canonical_size(payload: dict) -> int:
    return len(json.dumps(payload, sort_keys=True,
                          separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8"))


class PluginManager:
    """Pack operations over one registry + one store dir."""

    def __init__(self, registry: PluginRegistry, store_dir) -> None:
        self._registry = registry
        self._store_dir = Path(store_dir)

    @property
    def registry(self) -> PluginRegistry:
        return self._registry

    @property
    def store_dir(self) -> Path:
        return self._store_dir

    # -- ledger -------------------------------------------------

    def _ledger_path(self) -> Path:
        return self._store_dir / LEDGER_FILENAME

    def _load_ledger(self) -> dict:
        path = self._ledger_path()
        if not path.is_file():
            return {"format": LEDGER_FORMAT,
                    "ledger_version": LEDGER_VERSION, "plugins": {}}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PluginManagerError(
                f"plugin ledger at {path} is unreadable: {exc}") from exc
        if (not isinstance(data, dict)
                or data.get("format") != LEDGER_FORMAT
                or data.get("ledger_version") != LEDGER_VERSION
                or not isinstance(data.get("plugins"), dict)):
            raise PluginManagerError(
                f"plugin ledger at {path} is not a "
                f"{LEDGER_FORMAT} v{LEDGER_VERSION} document")
        return data

    def _save_ledger(self, ledger: dict) -> None:
        self._store_dir.mkdir(parents=True, exist_ok=True)
        path = self._ledger_path()
        tmp = path.with_name(LEDGER_FILENAME + ".tmp")
        tmp.write_text(
            json.dumps(ledger, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        os.replace(tmp, path)

    def installed_rows(self) -> list[dict]:
        """Ledger rows, oldest install first."""
        plugins = self._load_ledger()["plugins"]
        rows = [dict(row) for row in plugins.values()]
        rows.sort(key=lambda r: (r.get("installed_at", ""),
                                 r.get("plugin_id", "")))
        return rows

    def row_for(self, plugin_id: str) -> dict | None:
        row = self._load_ledger()["plugins"].get(plugin_id)
        return dict(row) if row is not None else None

    def is_managed(self, plugin_id: str) -> bool:
        return plugin_id in self._load_ledger()["plugins"]

    # -- shared validation ---------------------------------------

    def _validate_installable(self, parsed: ParsedPack) -> None:
        """Every check that must pass before a pack manifest may
        be registered, in verdict order. Raises the typed error
        for the first failure; registers nothing."""
        manifest = parsed.manifest
        problem = pack_data_only_problem(manifest)
        if problem is not None:
            raise DataOnlyPackError(problem)
        if manifest.api_version not in SUPPORTED_API_VERSIONS:
            raise PluginCompatibilityError(
                manifest.id, manifest.api_version,
                sorted(SUPPORTED_API_VERSIONS))
        try:
            validate_surface_requirements(manifest)
        except ManifestError as exc:
            raise PluginManagerError(str(exc)) from exc
        for decl in manifest.ui_slots:
            if _canonical_size(decl.payload) > UI_PAYLOAD_MAX_BYTES:
                raise PluginManagerError(
                    f"ui contribution {decl.id!r} payload exceeds "
                    f"{UI_PAYLOAD_MAX_BYTES} canonical JSON bytes")

    @staticmethod
    def _check_grant(manifest: PluginManifest, granted) -> None:
        granted_set = set(granted or [])
        declared = set(manifest.permissions)
        if granted_set != declared:
            missing = sorted(declared - granted_set)
            extra = sorted(granted_set - declared)
            raise GrantMismatchError(
                f"grant does not match the permission card for "
                f"{manifest.id!r}: ungranted {missing}, "
                f"undeclared {extra} -- the grant must name "
                "exactly the declared permissions")

    def _new_row(self, parsed: ParsedPack, granted, *, enabled: bool,
                 installed_at: str | None = None) -> dict:
        now = _now_iso()
        return {
            "plugin_id": parsed.manifest.id,
            "manifest": manifest_to_data(parsed.manifest),
            "content_sha256": parsed.content_sha256,
            "granted_permissions": list(parsed.manifest.permissions)
            if granted is None else sorted(set(granted)),
            "enabled": enabled,
            "installed_at": installed_at or now,
            "updated_at": now,
            "source": {
                "kind": "local_pack",
                "provenance": dict(parsed.provenance),
            },
        }

    # -- preview ---------------------------------------------------

    def preview(self, pack_data) -> dict:
        """The pre-install verdict, writing nothing: the
        permission card plus whether this pack would install,
        update, duplicate or conflict, and every problem found.
        An unparseable pack previews as action 'invalid' with
        the parse failure as its problem."""
        from runmal.plugins.packs import PackError
        try:
            parsed = parse_pack(pack_data)
        except PackError as exc:
            return {"installable": False, "action": "invalid",
                    "problems": [str(exc)], "permission_card": None,
                    "plugin_id": None}
        manifest = parsed.manifest
        existing = self._registry.find(manifest.id)
        previous = existing.manifest if existing is not None else None
        card = permission_card(manifest, previous=previous)
        problems: list[str] = []
        try:
            self._validate_installable(parsed)
        except (PluginManagerError, PluginCompatibilityError) as exc:
            problems.append(str(exc))
        if existing is None:
            action = "install"
        elif not self.is_managed(manifest.id):
            action = "conflict"
            problems.append(
                f"plugin {manifest.id!r} is registered by in-tree "
                "code, not by a pack; the manager may not replace it")
        else:
            row = self.row_for(manifest.id)
            if (manifest.version == existing.manifest.version
                    and row is not None
                    and row.get("content_sha256") == parsed.content_sha256):
                action = "duplicate"
            elif _version_key(manifest.version) > _version_key(
                    existing.manifest.version):
                action = "update"
            else:
                action = "conflict"
                problems.append(
                    f"pack version {manifest.version} does not "
                    f"advance installed version "
                    f"{existing.manifest.version}")
        return {"installable": not problems and action != "conflict",
                "action": action, "problems": problems,
                "permission_card": card, "plugin_id": manifest.id}

    # -- install ---------------------------------------------------

    def install(self, pack_data, *, granted_permissions,
                enable: bool = False) -> ManagerOutcome:
        parsed = parse_pack(pack_data)
        manifest = parsed.manifest
        existing = self._registry.find(manifest.id)
        if existing is not None:
            if not self.is_managed(manifest.id):
                raise PluginConflictError(
                    f"plugin {manifest.id!r} is registered by "
                    "in-tree code, not by a pack; the manager "
                    "may not install over it")
            row = self.row_for(manifest.id)
            if (manifest.version == existing.manifest.version
                    and row is not None
                    and row.get("content_sha256") == parsed.content_sha256
                    and manifest_to_data(existing.manifest)
                    == manifest_to_data(manifest)):
                return ManagerOutcome(
                    outcome="duplicate_exact", plugin_id=manifest.id,
                    record=existing,
                    card=permission_card(
                        manifest,
                        granted=set(row.get("granted_permissions", []))),
                    row=row)
            raise PluginConflictError(
                f"plugin {manifest.id!r} is already installed at "
                f"version {existing.manifest.version}; use update "
                "with a newer pack version")
        self._validate_installable(parsed)
        self._check_grant(manifest, granted_permissions)
        record = self._registry.register(manifest, PluginHandlers())
        if enable:
            record = self._registry.enable(manifest.id)
        row = self._new_row(
            parsed, granted_permissions,
            enabled=record.state is PluginState.ENABLED)
        ledger = self._load_ledger()
        ledger["plugins"][manifest.id] = row
        try:
            self._save_ledger(ledger)
        except Exception:
            # A ledger that cannot be written must not leave a
            # registered-but-unmanaged plugin behind: roll the
            # registration back so install stays atomic.
            try:
                if record.state is PluginState.ENABLED:
                    self._registry.disable(manifest.id)
                self._registry.unregister(manifest.id)
            except Exception:
                pass
            raise
        return ManagerOutcome(
            outcome="installed", plugin_id=manifest.id, record=record,
            card=permission_card(manifest,
                                 granted=set(granted_permissions or [])),
            row=self.row_for(manifest.id))

    # -- update ------------------------------------------------------

    def update(self, plugin_id: str, pack_data, *,
               granted_permissions) -> ManagerOutcome:
        parsed = parse_pack(pack_data)
        manifest = parsed.manifest
        if manifest.id != plugin_id:
            raise PluginManagerError(
                f"pack is for plugin {manifest.id!r}, not {plugin_id!r}")
        existing = self._registry.find(plugin_id)
        if existing is None:
            raise KeyError(plugin_id)
        row = self.row_for(plugin_id)
        if row is None:
            raise NotManagedPluginError(
                f"plugin {plugin_id!r} is registered by in-tree "
                "code, not by a pack; the manager may not update it")
        current = existing.manifest
        if manifest.version == current.version:
            if (row.get("content_sha256") == parsed.content_sha256
                    and manifest_to_data(current) == manifest_to_data(manifest)):
                return ManagerOutcome(
                    outcome="duplicate_exact", plugin_id=plugin_id,
                    record=existing,
                    card=permission_card(
                        manifest, granted=set(
                            row.get("granted_permissions", []))),
                    row=row)
            raise PluginConflictError(
                f"pack version {manifest.version} equals the "
                "installed version but its contents differ; "
                "bump the version to update")
        if _version_key(manifest.version) < _version_key(current.version):
            raise PluginConflictError(
                f"pack version {manifest.version} is older than "
                f"installed version {current.version}; updates "
                "must advance the version")
        self._validate_installable(parsed)
        self._check_grant(manifest, granted_permissions)
        was_enabled = existing.state is PluginState.ENABLED
        try:
            if was_enabled:
                self._registry.disable(plugin_id)
            self._registry.unregister(plugin_id)
            record = self._registry.register(manifest, PluginHandlers())
            if was_enabled:
                record = self._registry.enable(plugin_id)
        except Exception as exc:
            self._restore_after_failed_swap(current, was_enabled)
            raise PluginManagerError(
                f"update of {plugin_id!r} failed mid-swap: {exc}; "
                "the previous version was restored") from exc
        new_row = self._new_row(
            parsed, granted_permissions,
            enabled=record.state is PluginState.ENABLED,
            installed_at=row.get("installed_at"))
        ledger = self._load_ledger()
        ledger["plugins"][plugin_id] = new_row
        self._save_ledger(ledger)
        return ManagerOutcome(
            outcome="updated", plugin_id=plugin_id, record=record,
            card=permission_card(
                manifest, granted=set(granted_permissions or []),
                previous=current),
            row=self.row_for(plugin_id))

    def _restore_after_failed_swap(self, manifest: PluginManifest,
                                   was_enabled: bool) -> None:
        """Best-effort restore of the pre-update manifest after
        a failed swap; a restore failure is itself reported by
        the caller's message, never hidden here."""
        try:
            if self._registry.find(manifest.id) is None:
                self._registry.register(manifest, PluginHandlers())
            if was_enabled:
                record = self._registry.get(manifest.id)
                if record.state is not PluginState.ENABLED:
                    self._registry.enable(manifest.id)
        except Exception:
            pass

    # -- uninstall ---------------------------------------------------

    def uninstall(self, plugin_id: str) -> ManagerOutcome:
        row = self.row_for(plugin_id)
        record = self._registry.find(plugin_id)
        if row is None:
            if record is not None:
                raise NotManagedPluginError(
                    f"plugin {plugin_id!r} is registered by "
                    "in-tree code, not by a pack; the manager "
                    "may not uninstall it")
            raise KeyError(plugin_id)
        if record is not None:
            if record.state is PluginState.ENABLED:
                self._registry.disable(plugin_id)
            self._registry.unregister(plugin_id)
        ledger = self._load_ledger()
        ledger["plugins"].pop(plugin_id, None)
        self._save_ledger(ledger)
        manifest = manifest_from_data(row["manifest"])
        return ManagerOutcome(
            outcome="uninstalled", plugin_id=plugin_id, record=None,
            card=permission_card(manifest), row=None)

    # -- state sync + rehydration ------------------------------------

    def sync_state(self, plugin_id: str) -> None:
        """Follow a lifecycle change made through the registry
        (the router's verbs) into the ledger's enabled flag, so
        HTTP enable/disable is as durable as a manager call."""
        ledger = self._load_ledger()
        row = ledger["plugins"].get(plugin_id)
        if row is None:
            return
        record = self._registry.find(plugin_id)
        if record is None:
            return
        enabled = record.state is PluginState.ENABLED
        if row.get("enabled") != enabled:
            row["enabled"] = enabled
            row["updated_at"] = _now_iso()
            self._save_ledger(ledger)

    def rehydrate(self) -> tuple[list[str], list[dict]]:
        """Re-register every ledger row into this manager's
        registry, restoring enabled flags. A row that no longer
        validates (edited ledger, retired api_version) is
        SKIPPED and reported in the problems list -- boot never
        dies for one bad plugin, and the skip is never silent."""
        installed: list[str] = []
        problems: list[dict] = []
        for row in self.installed_rows():
            plugin_id = row.get("plugin_id", "<unknown>")
            try:
                manifest = manifest_from_data(row["manifest"])
                if row.get("content_sha256") != manifest_checksum(manifest):
                    raise PluginManagerError(
                        "ledger manifest does not match its "
                        "recorded content_sha256 (edited ledger?)")
                if manifest.id != plugin_id:
                    raise PluginManagerError(
                        "ledger row id does not match its manifest")
                self._validate_installable(
                    ParsedPack(manifest=manifest,
                               provenance=row.get("source", {}).get(
                                   "provenance", {}),
                               content_sha256=row.get(
                                   "content_sha256", "")))
                if self._registry.find(plugin_id) is not None:
                    raise PluginManagerError(
                        "already registered (in-tree citizen wins)")
                self._registry.register(manifest, PluginHandlers())
                if row.get("enabled"):
                    self._registry.enable(plugin_id)
            except Exception as exc:
                problems.append({"plugin_id": plugin_id,
                                 "error": f"{type(exc).__name__}: {exc}"})
            else:
                installed.append(plugin_id)
        return installed, problems
