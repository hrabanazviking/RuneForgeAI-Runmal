"""Per-backend capability truth (P-053) — never fake sliders.

One accounting for every canonical sampler control, per backend: a
control is ``available`` only where the backend honestly serves it,
``greyed`` (visible, disabled, with the reason as data) where it does
not, and ``hidden`` — never offered — when it is not a canonical
control at all. The UI renders greying from THIS module's rows and
nothing else; there is no second, divergent opinion about what a
backend supports.

Truth sources, in the open (no row claims more than its source):

- ``declared`` — the adapter's own published sampler sets
  (``SAMPLERS`` / ``UNSUPPORTED_SAMPLERS`` / ``SUPPORTED``), imported
  from the adapter modules, never copied, so this layer cannot
  silently drift from the code that actually sends requests.
- ``ledger`` — Aesir only: Aesir's published v1 route matrix as
  recorded by the P-009 readiness check and carried in
  :mod:`runmal.backends.aesir`'s binding truth. The adapter speaks
  Aesir's OpenAI chat route, which serves a subset; Aesir's native
  ``/v1/generate`` route serves the full canonical set. Both rows of
  the ledger are data here (``AESIR_LEDGER``); a truth row always
  names the route it was judged against. Since P-060 the native
  row carries one explicit carve-out (logit_bias, unverified
  in-tree) instead of silently claiming the whole vocabulary.

No row claims ``measured``: nothing in this tree probes a live server
for sampler support, so no row says it did.

Consistency is enforced, not hoped for: :func:`audit_truth` fails
loud (returns findings) whenever an adapter's declared sets do not
partition the canonical vocabulary, a default model disagrees with
its adapter, an S208 compatibility profile disagrees with its
adapter's declaration, or the Aesir ledger drifts from the adapter.
"""

from __future__ import annotations

from dataclasses import dataclass

from runmal.backends.negotiation import CANONICAL_CONTROLS
from runmal.backends.models import ModelInfo

#: Control states (the only three a UI may render).
AVAILABLE = "available"
GREYED = "greyed"
HIDDEN = "hidden"

#: Provenance of a truth row.
SOURCE_DECLARED = "declared"
SOURCE_LEDGER = "ledger"

#: Reason codes (machine-readable; ``reason`` is the human sentence).
REASON_SUPPORTED = "supported"
REASON_NOT_DECLARED = "not_declared"
REASON_ROUTE_NOT_SERVED = "route_not_served"
REASON_UNKNOWN_CONTROL = "unknown_control"

_CANONICAL = frozenset(CANONICAL_CONTROLS)


@dataclass(frozen=True)
class LedgerRoute:
    """One row of a backend's published route ledger (Aesir, P-009)."""

    route: str
    served: frozenset[str]
    note: str

    def to_dict(self) -> dict:
        return {
            "route": self.route,
            "served": sorted(self.served),
            "note": self.note,
        }


@dataclass(frozen=True)
class ControlTruth:
    """One control's truth for one backend+model, as data."""

    name: str
    state: str  # AVAILABLE | GREYED | HIDDEN
    supported: bool
    reason_code: str
    reason: str
    source: str  # SOURCE_DECLARED | SOURCE_LEDGER
    backend_key: str
    model_id: str
    wire_name: str | None = None
    route: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "supported": self.supported,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "source": self.source,
            "backend_key": self.backend_key,
            "model_id": self.model_id,
            "wire_name": self.wire_name,
            "route": self.route,
        }


def _adapter_sets() -> dict[str, tuple[frozenset[str], frozenset[str] | None]]:
    """backend_key -> (declared samplers, explicit unsupported or None).

    Imported from the adapters themselves — the single place each
    backend publishes what it serves. ``None`` unsupported means the
    adapter publishes no explicit set; the complement is derived and
    the derivation is visible in the rows' reason text.
    """
    from runmal.backends import aesir, fake, ollama, openai_compat, openrouter

    return {
        "fake": (fake.SUPPORTED, None),
        "ollama": (ollama.SAMPLERS, None),
        "openrouter": (openrouter.SAMPLERS, None),
        "aesir": (aesir.SAMPLERS, aesir.UNSUPPORTED_SAMPLERS),
        "openai": (openai_compat.SAMPLERS, openai_compat.UNSUPPORTED_SAMPLERS),
    }


def _wire_names() -> dict[str, dict[str, str]]:
    """backend_key -> {canonical key: wire name} where published."""
    from runmal.backends import aesir, ollama, openai_compat, openrouter

    return {
        "aesir": dict(aesir.WIRE_NAMES),
        "ollama": dict(ollama._OPTION_NAMES),
        "openai": dict(openai_compat.WIRE_NAMES),
        "openrouter": dict(openrouter._WIRE_NAMES),
        "fake": {},
    }


def _profile_reasons() -> dict[str, dict[str, str]]:
    """backend_key -> {control: published reason} from the S208 layer."""
    from runmal.generation.compat import PROFILES

    out: dict[str, dict[str, str]] = {}
    for name, profile in PROFILES.items():
        out[name] = dict(profile.unsupported)
    return out


def _aesir_ledger() -> tuple[LedgerRoute, ...]:
    from runmal.backends import aesir

    return (
        LedgerRoute(
            route="openai-chat",
            served=aesir.SAMPLERS,
            note=(
                "Aesir's OpenAI-compatible chat route serves exactly this "
                "subset (P-009 D2, from Aesir's own v1 matrix); controls "
                "outside it are rejected fields on that route."
            ),
        ),
        LedgerRoute(
            route="native-generate",
            served=_CANONICAL - {"logit_bias"},
            note=(
                "Aesir's native /v1/generate route serves the full "
                "canonical sampler set (P-009 D2). This adapter speaks "
                "the OpenAI chat route; the native row is the ledger's "
                "record, not a promise this adapter keeps. P-060 "
                "carve-out: logit_bias service on the native route "
                "is NOT recorded by the P-009 matrix and is "
                "unverified in-tree, so the row does not claim it."
            ),
        ),
    )


#: Aesir's route ledger as data (P-009 D2). See :func:`_aesir_ledger`.
AESIR_LEDGER: tuple[LedgerRoute, ...] = _aesir_ledger()


def declared_samplers(backend_key: str) -> frozenset[str]:
    """The sampler set the named adapter itself declares."""
    sets = _adapter_sets()
    if backend_key not in sets:
        raise ValueError(f"unknown backend: {backend_key!r}")
    return sets[backend_key][0]


def unsupported_samplers(backend_key: str) -> frozenset[str]:
    """Canonical controls the named backend does not serve.

    The adapter's explicit set where it publishes one; otherwise the
    exact complement of its declared set (never a hand-kept list).
    """
    sets = _adapter_sets()
    if backend_key not in sets:
        raise ValueError(f"unknown backend: {backend_key!r}")
    declared, explicit = sets[backend_key]
    if explicit is not None:
        return explicit
    return _CANONICAL - declared


def _greyed_reason(backend_key: str, model_id: str, name: str,
                   route: str | None) -> tuple[str, str, str]:
    """(reason_code, reason, source) for a canonical-but-unserved row."""
    if backend_key == "aesir":
        return (
            REASON_ROUTE_NOT_SERVED,
            f"Aesir's {route or 'openai-chat'} route does not serve "
            f"{name} (Aesir ledger, P-009 D2)",
            SOURCE_LEDGER,
        )
    profile_reason = _profile_reasons().get(backend_key, {}).get(name)
    if profile_reason:
        return REASON_NOT_DECLARED, profile_reason, SOURCE_DECLARED
    return (
        REASON_NOT_DECLARED,
        f"backend {backend_key!r} does not declare {name} "
        f"for model {model_id}",
        SOURCE_DECLARED,
    )


def truth_for_model(model: ModelInfo, *,
                    aesir_route: str = "openai-chat") -> list[ControlTruth]:
    """Truth rows for every canonical control, for one model.

    Judged by the MODEL's declared ``supported_samplers`` (so a
    profile-selected model is judged by its own declaration), with
    provenance and reasons from the backend's published truth source.
    For Aesir models, ``aesir_route`` selects the ledger row to judge
    against; the adapter's own route (``openai-chat``) is the default
    because that is the route this code actually speaks.
    """
    backend_key = model.backend_key
    wires = _wire_names().get(backend_key, {})
    route: str | None = None
    supported = model.capabilities.supported_samplers
    source = SOURCE_DECLARED
    if backend_key == "aesir":
        ledger = {entry.route: entry for entry in AESIR_LEDGER}
        if aesir_route not in ledger:
            raise ValueError(f"unknown aesir route: {aesir_route!r}")
        route = aesir_route
        supported = ledger[aesir_route].served
        source = SOURCE_LEDGER
    rows: list[ControlTruth] = []
    for name in CANONICAL_CONTROLS:
        if name in supported:
            rows.append(ControlTruth(
                name=name, state=AVAILABLE, supported=True,
                reason_code=REASON_SUPPORTED, reason="",
                source=source, backend_key=backend_key,
                model_id=model.model_id,
                wire_name=wires.get(name, name), route=route,
            ))
        else:
            code, reason, row_source = _greyed_reason(
                backend_key, model.model_id, name, route)
            rows.append(ControlTruth(
                name=name, state=GREYED, supported=False,
                reason_code=code, reason=reason, source=row_source,
                backend_key=backend_key, model_id=model.model_id,
                wire_name=None, route=route,
            ))
    return rows


def truth_for_control(model: ModelInfo, name: str, *,
                      aesir_route: str = "openai-chat") -> ControlTruth:
    """Truth for one named control; non-canonical names are HIDDEN."""
    if name not in _CANONICAL:
        return ControlTruth(
            name=name, state=HIDDEN, supported=False,
            reason_code=REASON_UNKNOWN_CONTROL,
            reason=f"{name!r} is not a canonical control; never offered",
            source=SOURCE_DECLARED, backend_key=model.backend_key,
            model_id=model.model_id, wire_name=None,
            route=aesir_route if model.backend_key == "aesir" else None,
        )
    for row in truth_for_model(model, aesir_route=aesir_route):
        if row.name == name:
            return row
    raise AssertionError("canonical control missing from truth rows")


def default_model(backend_key: str) -> ModelInfo:
    """The named backend's default model (constructed offline)."""
    from runmal.backends.aesir import AesirChatBackend
    from runmal.backends.fake import FakeChatBackend
    from runmal.backends.ollama import OllamaChatBackend
    from runmal.backends.openai_compat import OpenAICompatibleChatBackend
    from runmal.backends.openrouter import OpenRouterChatBackend

    builders = {
        "fake": FakeChatBackend,
        "ollama": OllamaChatBackend,
        "openrouter": OpenRouterChatBackend,
        "aesir": AesirChatBackend,
        "openai": OpenAICompatibleChatBackend,
    }
    if backend_key not in builders:
        raise ValueError(f"unknown backend: {backend_key!r}")
    return builders[backend_key]().default_model


def truth_for_backend(backend_key: str, *,
                      aesir_route: str = "openai-chat") -> list[ControlTruth]:
    """Truth rows for the named backend's default model."""
    return truth_for_model(default_model(backend_key),
                           aesir_route=aesir_route)


def truth_dict(model: ModelInfo, *,
               aesir_route: str = "openai-chat") -> dict:
    """JSON-ready truth surface for one model (UI consumption)."""
    rows = truth_for_model(model, aesir_route=aesir_route)
    out = {
        "backend_key": model.backend_key,
        "model_id": model.model_id,
        "controls": [r.to_dict() for r in rows],
        "available": [r.name for r in rows if r.state == AVAILABLE],
        "greyed": [r.name for r in rows if r.state == GREYED],
    }
    if model.backend_key == "aesir":
        out["ledger"] = [entry.to_dict() for entry in AESIR_LEDGER]
        out["route"] = aesir_route
    return out


def backend_truth_dict(backend_key: str, *,
                       aesir_route: str = "openai-chat") -> dict:
    """JSON-ready truth surface for one backend's default model."""
    return truth_dict(default_model(backend_key), aesir_route=aesir_route)


def capability_matrix(*, aesir_route: str = "openai-chat") -> dict:
    """Truth surfaces for every chat backend, in registry order."""
    from runmal.backends.profiles import CHAT_BACKENDS

    return {
        "backends": [
            backend_truth_dict(key, aesir_route=aesir_route)
            for key in CHAT_BACKENDS
        ],
        "audit": audit_truth(),
    }


def partition_bag(bag: dict, model: ModelInfo, *,
                  aesir_route: str = "openai-chat",
                  ) -> tuple[dict, list[ControlTruth]]:
    """Split a canonical bag into (offered params, greyed truth rows).

    The pre-flight mirror of negotiation's ``clamp_params``: keys the
    truth calls available pass through under their canonical names;
    canonical-but-greyed keys are reported as rows (never silently
    kept); non-canonical keys raise, because offering one at all is
    the fake-slider failure this slice exists to prevent.
    """
    rows = {r.name: r for r in truth_for_model(model,
                                               aesir_route=aesir_route)}
    offered: dict = {}
    greyed: list[ControlTruth] = []
    for key in sorted(bag):
        if key not in rows:
            raise ValueError(f"unknown parameter is not offered: {key!r}")
        row = rows[key]
        if row.state == AVAILABLE:
            offered[key] = bag[key]
        else:
            greyed.append(row)
    return offered, greyed


def audit_truth() -> list[str]:
    """Drift findings across every truth source; [] means agreement.

    (a) Adapters publishing explicit SAMPLERS + UNSUPPORTED sets must
    partition the canonical vocabulary exactly. (b) Each adapter's
    declared set must equal its default model's supported_samplers.
    (c) Each S208 profile's wire+unsupported keys must agree with its
    adapter's declared set. (d) The Aesir ledger's openai-chat row
    must equal the Aesir adapter's declared set.
    """
    findings: list[str] = []
    sets = _adapter_sets()
    for key, (declared, explicit) in sorted(sets.items()):
        if explicit is not None:
            overlap = declared & explicit
            if overlap:
                findings.append(
                    f"{key}: controls declared both served and unserved: "
                    f"{sorted(overlap)}")
            gap = _CANONICAL - declared - explicit
            if gap:
                findings.append(
                    f"{key}: canonical controls unaccounted for: "
                    f"{sorted(gap)}")
        model = default_model(key)
        if model.capabilities.supported_samplers != declared:
            findings.append(
                f"{key}: default model declares "
                f"{sorted(model.capabilities.supported_samplers)} but the "
                f"adapter declares {sorted(declared)}")
    from runmal.generation.compat import PROFILES

    for name, profile in sorted(PROFILES.items()):
        if name not in sets:
            findings.append(f"compat profile {name!r} has no adapter")
            continue
        declared = sets[name][0]
        profile_served = frozenset(profile.wire_names)
        if profile_served != declared:
            findings.append(
                f"compat profile {name!r} serves {sorted(profile_served)} "
                f"but the {name} adapter declares {sorted(declared)}")
        unaccounted = _CANONICAL - profile_served - frozenset(profile.unsupported)
        if unaccounted:
            findings.append(
                f"compat profile {name!r} leaves canonical controls "
                f"unaccounted for: {sorted(unaccounted)}")
    ledger = {entry.route: entry for entry in AESIR_LEDGER}
    if ledger["openai-chat"].served != sets["aesir"][0]:
        findings.append(
            "aesir ledger openai-chat row disagrees with the adapter's "
            "declared SAMPLERS")
    if ledger["native-generate"].served != _CANONICAL - {"logit_bias"}:
        findings.append(
            "aesir ledger native-generate row is not the canonical "
            "set minus the P-060 logit_bias carve-out")
    return findings
