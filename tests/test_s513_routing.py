"""S513 — Virtual-cable/device routing: persisted logical routes survive
restart when devices remain; a missing device is explicit, never
silently rerouted."""

from __future__ import annotations

import pytest

from runmal.voice.audio import FixtureDeviceProvider
from runmal.voice.routing import RouteKind, RouteStatus, RouteStore


def make_store(provider) -> RouteStore:
    store = RouteStore()
    store.set_route(RouteKind.COMPANION_OUTPUT, provider.find("fix-cable"),
                    label="VRChat cable")
    store.set_route(RouteKind.GAME_INGRESS, provider.find("fix-room"),
                    label="game audio")
    store.set_route(RouteKind.USER_MIC, provider.find("fix-mic"))
    return store


def test_routes_survive_restart_when_devices_remain(tmp_path):
    provider = FixtureDeviceProvider()
    path = tmp_path / "routes.json"
    make_store(provider).save(path)
    # Restart: a brand-new store loaded from disk, a brand-new provider.
    reloaded = RouteStore.load(path)
    resolved = reloaded.resolve(FixtureDeviceProvider())
    assert resolved[RouteKind.COMPANION_OUTPUT].status is RouteStatus.ACTIVE
    assert resolved[RouteKind.COMPANION_OUTPUT].device.device_id == "fix-cable"
    assert resolved[RouteKind.COMPANION_OUTPUT].route.label == "VRChat cable"
    assert resolved[RouteKind.GAME_INGRESS].status is RouteStatus.ACTIVE
    assert resolved[RouteKind.MONITOR].status is RouteStatus.UNASSIGNED


def test_missing_device_is_explicit_never_rerouted(tmp_path):
    provider = FixtureDeviceProvider()
    path = tmp_path / "routes.json"
    make_store(provider).save(path)
    shrunk = FixtureDeviceProvider(devices=[
        d for d in provider.list_devices() if d.device_id != "fix-cable"])
    resolved = RouteStore.load(path).resolve(shrunk)
    entry = resolved[RouteKind.COMPANION_OUTPUT]
    assert entry.status is RouteStatus.DEVICE_MISSING
    assert entry.device is None  # NOT the headset, NOT the OS default
    assert entry.route.device.device_id == "fix-cable"  # intent preserved
    with pytest.raises(RuntimeError, match="refusing to reroute"):
        RouteStore.load(path).open_playback(shrunk, RouteKind.COMPANION_OUTPUT)


def test_open_route_uses_the_routed_device(tmp_path):
    provider = FixtureDeviceProvider()
    store = make_store(provider)
    sink = store.open_playback(provider, RouteKind.COMPANION_OUTPUT)
    sink.write_frame(b"\x00" * 1024)
    assert provider.last_playback is sink
    source = store.open_capture(provider, RouteKind.GAME_INGRESS)
    assert source is provider.last_capture


def test_wrong_direction_and_version_guards(tmp_path):
    provider = FixtureDeviceProvider()
    with pytest.raises(ValueError):
        RouteStore().set_route(RouteKind.COMPANION_OUTPUT, provider.find("fix-mic"))
    with pytest.raises(ValueError):
        RouteStore.from_dict({"version": 99, "routes": []})
    assert RouteStore.load(tmp_path / "absent.json").routes == {}


def test_clear_route_returns_to_unassigned():
    provider = FixtureDeviceProvider()
    store = make_store(provider)
    store.clear_route(RouteKind.USER_MIC)
    assert store.resolve(provider)[RouteKind.USER_MIC].status is RouteStatus.UNASSIGNED
