"""Virtual-cable / device routing (S513).

Persisted LOGICAL routes on top of the S501 device/role plumbing:

- ``companion_output`` — where the companion's voice goes (headset, or a
  virtual cable into a game/VRChat);
- ``room_ingress`` / ``game_ingress`` — optional capture routes feeding
  room/game audio into STT (S611 builds on these);
- ``user_mic`` / ``monitor`` — the user's own channels.

Acceptance: routing SURVIVES RESTART when devices remain (the store is
a versioned JSON document, reloaded and re-resolved against a fresh
enumeration); a missing device is EXPLICIT — the route reports
``DEVICE_MISSING`` with no target bound. A route is never silently
rerouted to another device or the OS default (INV-022): rerouting is a
human decision made through :meth:`RouteStore.set_route`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from runmal.voice.audio import AudioDevice, DeviceProvider, SavedDeviceRef

ROUTE_STORE_VERSION = 1


class RouteKind(StrEnum):
    COMPANION_OUTPUT = "companion_output"
    ROOM_INGRESS = "room_ingress"
    GAME_INGRESS = "game_ingress"
    USER_MIC = "user_mic"
    MONITOR = "monitor"

    @property
    def direction(self) -> str:
        return (
            "input"
            if self in (RouteKind.ROOM_INGRESS, RouteKind.GAME_INGRESS, RouteKind.USER_MIC)
            else "output"
        )


class RouteStatus(StrEnum):
    ACTIVE = "active"
    UNASSIGNED = "unassigned"
    DEVICE_MISSING = "device_missing"  # explicit — never silently rerouted


@dataclass(frozen=True)
class LogicalRoute:
    kind: RouteKind
    device: SavedDeviceRef
    label: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind.value, "device": self.device.to_dict(), "label": self.label}

    @classmethod
    def from_dict(cls, data: dict) -> LogicalRoute:
        return cls(
            kind=RouteKind(data["kind"]),
            device=SavedDeviceRef.from_dict(data.get("device") or {}),
            label=str(data.get("label", "")),
        )


@dataclass(frozen=True)
class RouteResolution:
    kind: RouteKind
    status: RouteStatus
    route: LogicalRoute | None = None
    device: AudioDevice | None = None  # set only when ACTIVE

    @property
    def usable(self) -> bool:
        return self.status is RouteStatus.ACTIVE and self.device is not None


@dataclass
class RouteStore:
    """Versioned, JSON-persisted set of logical routes."""

    routes: dict[RouteKind, LogicalRoute] = field(default_factory=dict)

    def set_route(self, kind: RouteKind, device: AudioDevice, label: str = "") -> None:
        if device.direction != kind.direction:
            raise ValueError(
                f"{kind.value} needs a {kind.direction} device, got {device.direction}"
            )
        self.routes[kind] = LogicalRoute(kind, SavedDeviceRef.of(device), label)

    def clear_route(self, kind: RouteKind) -> None:
        self.routes.pop(kind, None)

    def resolve(self, provider: DeviceProvider) -> dict[RouteKind, RouteResolution]:
        present = {d.device_id: d for d in provider.list_devices()}
        out: dict[RouteKind, RouteResolution] = {}
        for kind in RouteKind:
            route = self.routes.get(kind)
            if route is None:
                out[kind] = RouteResolution(kind, RouteStatus.UNASSIGNED)
                continue
            device = present.get(route.device.device_id)
            if device is None or device.direction != kind.direction:
                out[kind] = RouteResolution(kind, RouteStatus.DEVICE_MISSING, route=route)
            else:
                out[kind] = RouteResolution(kind, RouteStatus.ACTIVE, route=route, device=device)
        return out

    def open_playback(self, provider: DeviceProvider, kind: RouteKind):
        """Open the route's sink — raises (never substitutes) when the
        route is missing/unassigned."""
        resolution = self.resolve(provider)[kind]
        if not resolution.usable:
            raise RuntimeError(
                f"route {kind.value} is {resolution.status.value}; refusing to "
                "reroute silently — remap the route explicitly"
            )
        return provider.open_playback(resolution.device.device_id)

    def open_capture(self, provider: DeviceProvider, kind: RouteKind):
        resolution = self.resolve(provider)[kind]
        if not resolution.usable:
            raise RuntimeError(
                f"route {kind.value} is {resolution.status.value}; refusing to "
                "reroute silently — remap the route explicitly"
            )
        return provider.open_capture(resolution.device.device_id)

    # ------------------------------------------------------------ persist

    def to_dict(self) -> dict:
        return {
            "version": ROUTE_STORE_VERSION,
            "routes": [route.to_dict() for route in self.routes.values()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> RouteStore:
        if int(data.get("version", 0)) != ROUTE_STORE_VERSION:
            raise ValueError(f"unsupported route store version: {data.get('version')}")
        store = cls()
        for item in data.get("routes", []):
            route = LogicalRoute.from_dict(item)
            store.routes[route.kind] = route
        return store

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))

    @classmethod
    def load(cls, path: Path) -> RouteStore:
        if not path.exists():
            return cls()
        return cls.from_dict(json.loads(path.read_text()))
