"""P-062 Multi-model prompt profiles battery.

Pins: profile data validation + fixed point + extensions carriage;
selection shapes shared with P-054; builtins honest (no invented
model ids); sampler partition against P-053 declared truth (fake
backend: temperature offered, top_k greyed; unknown keys carried,
never offered; no backend = no partition claimed); the switch diff
(what changes / what always carries); resolution precedence
explicit > profile > model_default/default; inspect integration
(profile drives template/layout/model echoes, explicit wins, the
model_profile echo is metadata-only under S214, and the no-profile
pipeline is unchanged apart from the echo); the API surface.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.prompt import (
    ModelProfile,
    diff_profiles,
    get_profile,
    list_profiles,
    partition_profile_sampler,
    profile_from_data,
    profile_to_data,
)
from runmal.prompt.model_profiles import CARRIES, PROFILE_ORDER

SECRET_TEXT = "ZqxProfileSecret62 must never surface"


def _profile_data(**overrides):
    data = {
        "name": "my-llama",
        "description": "test profile",
        "model_id": "llama-3.1-8b",
        "backend_key": "fake",
        "instruct_template": {"kind": "builtin", "name": "llama3"},
        "context_template": {"kind": "builtin", "name": "default"},
        "prompt_layout": None,
        "sampler": {"temperature": 0.5, "top_k": 40},
    }
    data.update(overrides)
    return data


# ---------------- 1. data validation ----------------

def test_roundtrip_fixed_point():
    profile = profile_from_data(_profile_data())
    data = profile_to_data(profile)
    assert profile_from_data(data) == profile
    assert profile_to_data(profile_from_data(data)) == data
    assert data["name"] == "my-llama"


def test_minimal_profile_defaults():
    profile = profile_from_data({"name": "bare"})
    assert profile.model_id is None and profile.backend_key is None
    assert profile.instruct_template is None
    assert profile.sampler == {} and profile.extensions == {}


def test_unknown_top_level_keys_become_extensions():
    profile = profile_from_data(_profile_data(vendor_flag={"x": 1}))
    assert profile.extensions == {"vendor_flag": {"x": 1}}
    assert profile_to_data(profile)["extensions"] == {"vendor_flag": {"x": 1}}


def test_bad_profiles_refuse():
    with pytest.raises(ValueError):
        profile_from_data({"name": ""})
    with pytest.raises(ValueError):
        profile_from_data({"name": "x", "model_id": 7})
    with pytest.raises(ValueError):
        profile_from_data({"name": "x", "sampler": {"temperature": "hot"}})
    with pytest.raises(ValueError):
        profile_from_data({"name": "x", "sampler": {"temperature": 99 - 100}})
    with pytest.raises(ValueError):
        profile_from_data({"name": "x", "instruct_template": {"kind": "builtin", "name": "nope"}})
    with pytest.raises(ValueError):
        profile_from_data({"name": "x", "instruct_template": {"kind": "weird"}})
    with pytest.raises(ValueError):
        profile_from_data({"name": "x", "prompt_layout": {"blocks": [{"block": "nope"}]}})
    with pytest.raises(ValueError):
        profile_from_data("not-a-dict")


def test_custom_and_story_string_selections():
    profile = profile_from_data(_profile_data(
        instruct_template={"kind": "custom", "template": {
            "name": "mine", "wrappers": {"user": {"prefix": "U: ", "suffix": ""}}}},
        context_template={"kind": "story_string",
                          "text": "{{system}}\n{{chatHistory}}"},
    ))
    again = profile_from_data(profile_to_data(profile))
    assert again == profile


# ---------------- 2. builtins ----------------

def test_builtins_honest_and_ordered():
    profiles = list_profiles()
    assert [p.name for p in profiles] == list(PROFILE_ORDER)
    assert get_profile("default").model_id is None
    for profile in profiles:
        # no builtin invents a concrete model id
        assert profile.model_id is None
        profile_from_data(profile_to_data(profile))
    with pytest.raises(ValueError):
        get_profile("nope")


# ---------------- 3. sampler partition (P-053 truth) ----------------

def test_partition_fake_backend_greys_undeclared():
    profile = profile_from_data(_profile_data())
    part = partition_profile_sampler(profile)
    assert part["partitioned"] is True
    assert part["offered"] == ["temperature"]
    greyed_names = [row["name"] for row in part["greyed"]]
    assert greyed_names == ["top_k"]
    assert part["greyed"][0]["supported"] is False
    assert part["carried_unknown"] == []


def test_partition_carries_unknown_keys_unoffered():
    profile = profile_from_data(_profile_data(
        sampler={"temperature": 0.5, "vendor_knob": 3}))
    part = partition_profile_sampler(profile)
    assert part["carried_unknown"] == ["vendor_knob"]
    assert "vendor_knob" not in part["offered"]


def test_partition_no_backend_claims_nothing():
    profile = profile_from_data(_profile_data(backend_key=None))
    part = partition_profile_sampler(profile)
    assert part["partitioned"] is False
    assert part["offered"] == [] and part["greyed"] == []
    assert sorted(part["unpartitioned"]) == ["temperature", "top_k"]


def test_partition_unknown_backend_refuses():
    profile = profile_from_data(_profile_data(backend_key="nope-backend"))
    with pytest.raises(ValueError):
        partition_profile_sampler(profile)


# ---------------- 4. switch diff ----------------

def test_diff_reports_changes_and_carries():
    before = get_profile("chatml-general")
    after = profile_from_data(_profile_data())
    diff = diff_profiles(before, after)
    fields = {row["field"] for row in diff["changes"]}
    assert "instruct_template" in fields
    assert "model_id" in fields
    assert "sampler.temperature" in fields
    assert diff["carries"] == list(CARRIES)
    assert "history" in diff["carries"]


def test_diff_same_profile_no_changes_except_name_free():
    profile = get_profile("default")
    diff = diff_profiles(profile, profile)
    assert diff["changes"] == []
    assert diff["carries"] == list(CARRIES)


# ---------------- 5. inspect integration ----------------

from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head


@pytest.fixture()
def client_env(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "p062.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    return client, {"Authorization": f"Bearer {token}"}


def _inspect(client, headers, **kwargs):
    body = {"messages": ["hello"], **kwargs}
    resp = client.post("/api/v1/debug/prompt-inspect", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_inspect_no_profile_echo_and_baseline(client_env):
    client, headers = client_env
    result = _inspect(client, headers)
    echo = result["model_profile"]
    assert echo["applied"] is False and echo["source"] == "none"
    assert echo["name"] is None
    assert result["instruct_template"]["name"] == "plain"


def test_inspect_profile_drives_template_and_model(client_env):
    client, headers = client_env
    result = _inspect(client, headers, model_profile="llama3-instruct")
    echo = result["model_profile"]
    assert echo["applied"] is True and echo["source"] == "explicit"
    assert echo["name"] == "llama3-instruct"
    assert echo["fields"]["instruct_template"] == "profile"
    assert result["instruct_template"]["name"] == "llama3"
    assert result["instruct_template"]["source"] == "profile"


def test_inspect_profile_model_default_chain(client_env):
    client, headers = client_env
    # profile names only a model: its model's P-050 default applies
    result = _inspect(client, headers, model_profile={
        "name": "just-model", "model_id": "meta-llama-3-8b"})
    assert result["instruct_template"]["name"] == "llama3"
    assert result["instruct_template"]["source"] == "model_default"
    assert result["model_profile"]["fields"]["model_id"] == "profile"


def test_inspect_explicit_beats_profile(client_env):
    client, headers = client_env
    result = _inspect(
        client, headers, model_profile="llama3-instruct",
        instruct_template="chatml", model_id="someone-else")
    assert result["instruct_template"]["name"] == "chatml"
    assert result["instruct_template"]["source"] == "explicit"
    assert result["model_profile"]["fields"]["instruct_template"] == "explicit"
    assert result["model_profile"]["fields"]["model_id"] == "explicit"


def test_inspect_profile_sampler_echo_is_metadata_only(client_env):
    client, headers = client_env
    result = _inspect(client, headers, model_profile=_profile_data(
        sampler={"temperature": 0.5, "top_k": 40, "vendor_knob": 3},
        extensions={"note": SECRET_TEXT}))
    echo = result["model_profile"]
    assert echo["sampler"]["partitioned"] is True
    assert echo["sampler"]["offered"] == ["temperature"]
    assert [r["name"] for r in echo["sampler"]["greyed"]] == ["top_k"]
    assert echo["sampler"]["carried_unknown"] == ["vendor_knob"]
    assert echo["extension_keys"] == ["note"]
    import json as _json
    assert SECRET_TEXT not in _json.dumps(result)
    assert "0.5" not in _json.dumps(echo["sampler"])


def test_inspect_unknown_profile_is_422(client_env):
    client, headers = client_env
    resp = client.post("/api/v1/debug/prompt-inspect",
                       json={"model_profile": "nope"}, headers=headers)
    assert resp.status_code == 422


# ---------------- 6. API surface ----------------

def test_api_list_and_diff(client_env):
    client, headers = client_env
    resp = client.get("/api/v1/debug/model-profiles", headers=headers)
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()["profiles"]]
    assert names == list(PROFILE_ORDER)
    resp = client.post("/api/v1/debug/model-profile-diff", headers=headers,
                       json={"from_profile": "chatml-general",
                             "to_profile": _profile_data()})
    assert resp.status_code == 200
    diff = resp.json()
    assert diff["from_profile"] == "chatml-general"
    assert diff["to_profile"] == "my-llama"
    assert diff["carries"] == list(CARRIES)
    resp = client.post("/api/v1/debug/model-profile-diff", headers=headers,
                       json={"from_profile": "nope", "to_profile": "default"})
    assert resp.status_code == 422
