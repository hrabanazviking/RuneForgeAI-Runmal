"""P-053 Per-backend capability truth battery.

Pins the honesty contract: for every backend, every canonical sampler
control is accounted for exactly once — available only where the
backend's own declaration (or Aesir's ledger) serves it, greyed with
a reason as data where it does not, and non-canonical names are never
offered at all. Also pins the cross-source audit (adapters vs S208
profiles vs the Aesir ledger) and the /debug API surface.
"""

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.backends import aesir as aesir_mod
from runmal.backends import ollama as ollama_mod
from runmal.backends import openai_compat as openai_mod
from runmal.backends.capabilities import (
    AESIR_LEDGER,
    AVAILABLE,
    GREYED,
    HIDDEN,
    REASON_NOT_DECLARED,
    REASON_ROUTE_NOT_SERVED,
    REASON_SUPPORTED,
    REASON_UNKNOWN_CONTROL,
    SOURCE_DECLARED,
    SOURCE_LEDGER,
    audit_truth,
    backend_truth_dict,
    capability_matrix,
    declared_samplers,
    partition_bag,
    truth_for_backend,
    truth_for_control,
    truth_for_model,
    unsupported_samplers,
)
from runmal.backends.models import Capabilities, ModelInfo
from runmal.backends.negotiation import CANONICAL_CONTROLS, clamp_params
from runmal.backends.params import SamplingParams
from runmal.backends.profiles import CHAT_BACKENDS
from runmal.generation.compat import filter_for_backend

CANONICAL = frozenset(CANONICAL_CONTROLS)

EXPECTED_AVAILABLE = {
    "fake": {"temperature", "top_p", "max_tokens", "stop", "seed"},
    "ollama": {
        "temperature", "top_p", "top_k", "min_p", "seed", "stop",
        "max_tokens", "repetition_penalty", "context_length",
    },
    "openrouter": {
        "temperature", "top_p", "max_tokens", "frequency_penalty",
        "presence_penalty", "stop", "seed",
    },
    "aesir": {"temperature", "top_p", "max_tokens", "seed"},
    "openai": {
        "temperature", "top_p", "max_tokens", "frequency_penalty",
        "presence_penalty", "stop", "seed",
    },
}


# ---------------- accounting: exactly one state per control ----------------

@pytest.mark.parametrize("backend", list(CHAT_BACKENDS))
def test_every_canonical_control_accounted_for_once(backend):
    rows = truth_for_backend(backend)
    assert [r.name for r in rows] == list(CANONICAL_CONTROLS)
    available = {r.name for r in rows if r.state == AVAILABLE}
    greyed = {r.name for r in rows if r.state == GREYED}
    assert available == EXPECTED_AVAILABLE[backend]
    assert greyed == CANONICAL - available
    assert not (available & greyed)
    for row in rows:
        assert row.backend_key == backend
        assert row.state in (AVAILABLE, GREYED)  # canonical rows never hidden
        if row.state == AVAILABLE:
            assert row.supported is True
            assert row.reason_code == REASON_SUPPORTED
            assert row.wire_name  # an offered control names its wire shape
        else:
            assert row.supported is False
            assert row.reason_code in (REASON_NOT_DECLARED,
                                       REASON_ROUTE_NOT_SERVED)
            assert row.reason  # greyed always carries its reason as data
            assert row.wire_name is None  # never a wire shape for a fake send


@pytest.mark.parametrize("backend", list(CHAT_BACKENDS))
def test_declared_sets_match_adapter_modules(backend):
    assert declared_samplers(backend) == EXPECTED_AVAILABLE[backend]
    assert unsupported_samplers(backend) == CANONICAL - EXPECTED_AVAILABLE[backend]
    assert declared_samplers(backend) & unsupported_samplers(backend) == frozenset()
    assert declared_samplers(backend) | unsupported_samplers(backend) == CANONICAL


def test_unknown_backend_rejected():
    with pytest.raises(ValueError):
        truth_for_backend("nope")
    with pytest.raises(ValueError):
        declared_samplers("nope")


def test_unknown_control_is_hidden_never_offered():
    from runmal.backends.capabilities import default_model

    model = default_model("ollama")
    row = truth_for_control(model, "vendor_magic")
    assert row.state == HIDDEN
    assert row.supported is False
    assert row.reason_code == REASON_UNKNOWN_CONTROL
    names = {r.name for r in truth_for_model(model)}
    assert "vendor_magic" not in names


# ---------------- provenance ----------------

@pytest.mark.parametrize("backend", ["fake", "ollama", "openrouter", "openai"])
def test_declared_backends_cite_declared_source(backend):
    for row in truth_for_backend(backend):
        assert row.source == SOURCE_DECLARED


def test_aesir_rows_cite_the_ledger():
    for row in truth_for_backend("aesir"):
        assert row.source == SOURCE_LEDGER
        assert row.route == "openai-chat"
        if row.state == GREYED:
            assert row.reason_code == REASON_ROUTE_NOT_SERVED
            assert "ledger" in row.reason


def test_no_row_claims_measured():
    for backend in CHAT_BACKENDS:
        for row in truth_for_backend(backend):
            assert row.source in (SOURCE_DECLARED, SOURCE_LEDGER)


# ---------------- Aesir ledger as data ----------------

def test_aesir_ledger_rows():
    ledger = {entry.route: entry for entry in AESIR_LEDGER}
    assert set(ledger) == {"openai-chat", "native-generate"}
    assert ledger["openai-chat"].served == aesir_mod.SAMPLERS
    assert ledger["native-generate"].served == CANONICAL
    assert all(entry.note for entry in AESIR_LEDGER)


def test_aesir_native_route_shows_full_set_without_changing_adapter():
    rows = truth_for_backend("aesir", aesir_route="native-generate")
    assert {r.name for r in rows if r.state == AVAILABLE} == CANONICAL
    assert all(r.route == "native-generate" for r in rows)
    # The adapter's own declaration is untouched by the ledger view.
    assert aesir_mod.SAMPLERS == EXPECTED_AVAILABLE["aesir"]
    with pytest.raises(ValueError):
        truth_for_backend("aesir", aesir_route="carrier-pigeon")


def test_aesir_accounting_partitions_canonical():
    assert aesir_mod.SAMPLERS | aesir_mod.UNSUPPORTED_SAMPLERS == CANONICAL
    assert aesir_mod.SAMPLERS & aesir_mod.UNSUPPORTED_SAMPLERS == frozenset()
    assert openai_mod.SAMPLERS | openai_mod.UNSUPPORTED_SAMPLERS == CANONICAL
    assert ollama_mod.SAMPLERS == EXPECTED_AVAILABLE["ollama"]


# ---------------- model-level truth ----------------

def test_truth_follows_the_models_own_declaration():
    model = ModelInfo(
        model_id="custom-1", display_name="Custom", backend_key="ollama",
        capabilities=Capabilities(supported_samplers=frozenset({"temperature"})),
    )
    rows = {r.name: r for r in truth_for_model(model)}
    assert rows["temperature"].state == AVAILABLE
    assert rows["top_k"].state == GREYED  # ollama serves it; this model doesn't
    assert rows["top_k"].model_id == "custom-1"


# ---------------- audit: truth sources cannot drift ----------------

def test_audit_is_clean():
    assert audit_truth() == []


def test_matrix_shape_and_audit():
    matrix = capability_matrix()
    assert [b["backend_key"] for b in matrix["backends"]] == list(CHAT_BACKENDS)
    assert matrix["audit"] == []
    for entry in matrix["backends"]:
        assert set(entry["available"]) | set(entry["greyed"]) == CANONICAL
        assert not set(entry["available"]) & set(entry["greyed"])
        assert len(entry["controls"]) == len(CANONICAL_CONTROLS)
    aesir_entry = next(b for b in matrix["backends"]
                       if b["backend_key"] == "aesir")
    assert aesir_entry["route"] == "openai-chat"
    assert {e["route"] for e in aesir_entry["ledger"]} == {
        "openai-chat", "native-generate"}


# ---------------- the S208 drift fix ----------------

def test_ollama_profile_now_serves_min_p_and_context_length():
    result = filter_for_backend(
        {"min_p": 0.1, "context_length": 8192, "temperature": 0.7}, "ollama")
    assert result.params == {
        "min_p": 0.1, "num_ctx": 8192, "temperature": 0.7}
    assert result.dropped == ()
    assert [(m.source, m.dest) for m in result.mapped] == [
        ("context_length", "num_ctx")]


def test_openai_profile_names_its_unserved_reasons():
    result = filter_for_backend({"min_p": 0.1, "context_length": 8192},
                                "openai")
    assert result.params == {}
    reasons = {d.param: d.reason for d in result.dropped}
    assert "min_p" in reasons["min_p"]
    assert "unknown" not in reasons["min_p"]
    assert "unknown" not in reasons["context_length"]


# ---------------- truth agrees with enforcement ----------------

@pytest.mark.parametrize("backend", list(CHAT_BACKENDS))
def test_clamp_drops_exactly_the_greyed_set(backend):
    from runmal.backends.capabilities import default_model

    model = default_model(backend)
    full = SamplingParams(
        temperature=0.7, top_p=0.9, top_k=40, min_p=0.1,
        repetition_penalty=1.1, presence_penalty=0.1,
        frequency_penalty=0.1, max_output_tokens=128,
        stop=("END",), seed=42, context_length=4096,
    )
    _filtered, warnings = clamp_params(full, model)
    dropped = {w.rsplit(": ", 1)[-1] for w in warnings
               if w.startswith("unsupported parameter dropped")}
    # context_length is a limit, not a sampler: clamp handles it apart.
    greyed = {r.name for r in truth_for_model(model)
              if r.state == GREYED} - {"context_length"}
    assert dropped == greyed


@pytest.mark.parametrize("backend", list(CHAT_BACKENDS))
def test_partition_bag_offers_only_available(backend):
    from runmal.backends.capabilities import default_model

    model = default_model(backend)
    bag = {"temperature": 0.7, "top_k": 40, "seed": 7}
    offered, greyed = partition_bag(bag, model)
    available = EXPECTED_AVAILABLE[backend]
    assert set(offered) == {k for k in bag if k in available}
    assert {r.name for r in greyed} == {k for k in bag if k not in available}
    with pytest.raises(ValueError):
        partition_bag({"vendor_magic": 1}, model)


# ---------------- API surface ----------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from runmal.auth import get_or_create_credential
    from runmal.db.base import create_db_engine, create_session_factory
    from runmal.db.migrate import migrate_to_head

    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_api_matrix(client):
    resp = client.get("/api/v1/debug/backend-capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert [b["backend_key"] for b in body["backends"]] == list(CHAT_BACKENDS)
    assert body["audit"] == []


def test_api_single_backend_and_greying(client):
    resp = client.get("/api/v1/debug/backend-capabilities/aesir")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["available"]) == EXPECTED_AVAILABLE["aesir"]
    greyed = {c["name"]: c for c in body["controls"] if c["state"] == "greyed"}
    assert set(greyed) == CANONICAL - EXPECTED_AVAILABLE["aesir"]
    assert greyed["top_k"]["reason_code"] == REASON_ROUTE_NOT_SERVED
    assert greyed["top_k"]["source"] == SOURCE_LEDGER


def test_api_native_route_view(client):
    resp = client.get(
        "/api/v1/debug/backend-capabilities/aesir",
        params={"aesir_route": "native-generate"})
    assert resp.status_code == 200
    assert set(resp.json()["available"]) == CANONICAL


def test_api_unknown_backend_404(client):
    resp = client.get("/api/v1/debug/backend-capabilities/nope")
    assert resp.status_code == 404
