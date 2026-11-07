"""P-064 Part IV gate: an ST preset pack drives Runmal chats with
visibly identical prompt assembly (preview-diffed), sampler truth
table published per backend.

Roadmap line: *P-064 Part IV gate: an ST preset pack drives
Runmal chats with visibly identical prompt assembly
(preview-diffed), sampler truth table published per backend.*

This is the Part IV gate battery, in the P-030 / P-048 gate
discipline. Part IV is P-049..P-064: prompt manager, instruct /
context templates, sampler surface, capability truth, preset
bundles, macros, author's note, post-history, budget governor,
prompt preview, logit bias / stop, structured output, model
profiles, prompt packs. The gate builds no new behaviour; it
judges the banked slices end to end through their own public
contracts. Clean-room note: the pack below is shaped ONLY from
the in-tree P-005 corpus fixture (preset_st_chatcompletion.json,
the mirrors' public interchange shape as modelled by P-021) and
the P-063 pack format; no SillyTavern or Voxta source was
inspected.

Per-area "passes means" contracts:

- Area A (pack drives the chat) passes means: the P-021 chat
  fixture parses through preset interop; a P-054 bundle built
  FROM that parsed preset (bag, prompts, prompt_order,
  template_ref carried verbatim) rides a P-063 pack as a fixed
  point; import stores bundle + preset value-identically; and a
  P-062 profile built from the STORED bundle drives the P-059
  preview of a real character + chat IDENTICALLY - all 11
  preview keys, field by field - to the directly-assembled
  equivalent supplied without the pack/profile road, while a
  no-layout control preview differs exactly by the persona the
  pack's layout disables.
- Area B (sampler truth table) passes means: for every chat
  backend, every one of the 29 canonical controls (P-052/P-060)
  and every structured mode (P-061) is accounted for exactly
  once as available or greyed-with-a-reason; the audits are
  clean; available always names a wire shape and agrees with
  the serving layer (nothing offered that no backend serves);
  partition_bag over the full canonical bag drops nothing
  silently; and the published endpoints return the same table.
- Area C (citizens compose) passes means: in ONE previewed
  assembly, layout (P-049), instruct + context templates
  (P-050/P-051), macros (P-055, expanded at the text layer
  before history), author's note (P-056, at depth, active),
  post-history (P-057, chat beats character, baseline-last)
  and the governor (P-058, reconciled budget + recorded trim)
  all hold together - note / post-history text lives only in
  the preview, never in slots/ledger (S214) - and a model
  profile switch (P-062) changes exactly what the profile owns
  (template framing + echo) while chat-carried state (history,
  note, post-history) carries unchanged.

Plain pytest functions, no test classes. Fixed names and texts
are fresh-authored for this gate (Gatehall); no real user files
are read.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.capabilities import (
    AVAILABLE,
    GREYED,
    audit_truth,
    capability_matrix,
    declared_samplers,
    default_model,
    partition_bag,
    truth_for_backend,
)
from runmal.backends.negotiation import CANONICAL_CONTROLS
from runmal.backends.profiles import CHAT_BACKENDS
from runmal.backends.structured import (
    MODES,
    StructuredOutput,
    audit_structured_truth,
    structured_matrix,
    wire_payload,
)
from runmal.backends.structured import (
    truth_for_backend as structured_truth_for_backend,
)
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.presets import packs as packs_mod
from runmal.presets.bundles import validate_bundle
from runmal.presets.interop import parse_preset
from runmal.presets.packs import build_pack, parse_pack
from runmal.prompt.context import context_to_data
from runmal.prompt.instruct import template_to_data
from runmal.prompt.macros import MacroContext, expand_macros
from runmal.prompt.model_profiles import (
    CARRIES,
    diff_profiles,
    get_profile,
    selection_to_context_template,
    selection_to_template,
)

CORPUS = Path(__file__).parent / "fixtures" / "interop"
CHAT_FIXTURE = CORPUS / "preset_st_chatcompletion.json"
PREVIEW_KEYS = {
    "available", "backend_key", "model_id", "form", "messages",
    "wire_messages", "text", "template_name", "stop_strings",
    "rendered_tokens", "note",
}
CHAR_NAME = "Sigrun"
USER_NAME = "Volmarr"
NOTE_TEXT = "ZqxGateNote64 hold the hall scene steady."
PH_CHAT_TEXT = "ZqxGatePostHistory64 chat wins the last word."
PH_CARD_TEXT = "ZqxGateCardPostHistory64 from the card."
MACRO_RAW = "Hail {{char}}, {{user}} keeps the gate."
MACRO_EXPANDED = "Hail Sigrun, Volmarr keeps the gate."


# ---------------------------------------------------------------- harness


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, factory


def _preview(client, **kw):
    resp = client.post("/api/v1/debug/prompt-preview", json=kw)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _make_character(client, ph_text=PH_CARD_TEXT, name=CHAR_NAME):
    payload = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": name,
        "description": "A gate seer of the hall.",
        "personality": "Calm.",
        "scenario": "A test hall.",
        "first_mes": "Hail!",
        "mes_example": "",
        "creator_notes": "",
        "system_prompt": "",
        "post_history_instructions": ph_text,
        "alternate_greetings": [],
        "tags": [],
        "creator": "test",
        "extensions": {},
    }
    resp = client.post("/api/v1/characters", json={"card": payload})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _make_chat(client, title="Gatehall"):
    resp = client.post("/api/v1/chats", json={"title": title})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _set_note(client, chat_id, payload):
    resp = client.post(f"/api/v1/chats/{chat_id}/authors-note", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _set_ph(client, chat_id, payload):
    resp = client.post(f"/api/v1/chats/{chat_id}/post-history", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ------------------------------------------------------- Area A: the pack


def _fixture_view():
    return parse_preset(CHAT_FIXTURE.read_bytes())


def _gate_bundle_payload(view):
    """A P-054 bundle built FROM the parsed P-021 preset: the
    fixture's bag, prompts and prompt_order carried verbatim;
    the layout disables the persona block so the pack's effect
    on assembly is visible in the preview diff."""
    return {
        "name": "Gatehall ST Bundle",
        "sampler": copy.deepcopy(view.params),
        "prompt_layout": {"blocks": [{"block": "persona", "enabled": False}]},
        "instruct_template": {"kind": "builtin", "name": "chatml"},
        "context_template": {"kind": "builtin", "name": "default"},
        "template_ref": view.template_ref,
        "prompts": copy.deepcopy(view.prompts),
        "prompt_order": copy.deepcopy(view.prompt_order),
    }


def _gate_preset_payload(view):
    return {
        "name": "Gatehall ST Preset",
        "params": copy.deepcopy(view.params),
        "template_ref": view.template_ref,
        "source_format": view.source_format,
        "raw": copy.deepcopy(view.raw),
        "prompts": copy.deepcopy(view.prompts),
        "prompt_order": copy.deepcopy(view.prompt_order),
    }


def _gate_pack():
    view = _fixture_view()
    items = [
        {"kind": "bundle", "name": "Gatehall ST Bundle",
         "payload": _gate_bundle_payload(view)},
        {"kind": "preset", "name": "Gatehall ST Preset",
         "payload": _gate_preset_payload(view)},
    ]
    return build_pack("Gatehall ST Pack", items,
                      exported_at="2026-11-07T00:00:00+00:00"), view


def test_a_pack_1_fixture_to_pack_fixed_point():
    view = _fixture_view()
    # The P-021 road: the ST-shaped chat fixture parses with its
    # bag, prompts and order intact (P-021's own pins, re-proven
    # at the gate because the pack is built from them).
    assert view.source_format == "st-chat"
    assert view.params["temperature"] == 0.85
    assert view.params["max_tokens"] == 900
    order_ids = [row["identifier"] for row in view.prompt_order]
    assert order_ids[0] == "main" and order_ids[-1] == "jailbreak"
    main = [p for p in view.prompts if p["identifier"] == "main"]
    assert main and "expert actor" in main[0]["content"]
    pack, _ = _gate_pack()
    parsed = parse_pack(pack)
    assert parsed["manifest"]["pack_name"] == "Gatehall ST Pack"
    assert parsed["manifest"]["item_count"] == 2
    assert parsed["manifest"]["kind_counts"] == {"bundle": 1, "preset": 1}
    # Fixed point: parsing a parsed pack changes nothing, and the
    # bundle inside is the validated bundle of the fixture data.
    assert parse_pack(parsed) == parsed
    by_kind = {it["kind"]: it for it in parsed["items"]}
    assert by_kind["bundle"]["payload"] == validate_bundle(
        _gate_bundle_payload(view))
    assert by_kind["bundle"]["payload"]["sampler"] == view.params
    assert by_kind["bundle"]["payload"]["prompts"] == view.prompts
    assert by_kind["preset"]["payload"]["params"] == view.params
    report = packs_mod.inspect_pack(pack)
    assert report["valid"] is True and report["checksum_verified"] is True
    stored = {r["kind"]: r["stored_on_import"] for r in report["items"]}
    assert stored == {"bundle": True, "preset": True}


def test_a_pack_2_import_stores_bundle_and_preset(tmp_path, monkeypatch):
    client, _factory = make_client(tmp_path, monkeypatch)
    pack, view = _gate_pack()
    resp = client.post("/api/v1/presets/packs/import", json=pack)
    assert resp.status_code == 200, resp.text
    report = resp.json()["import_report"]
    assert report["checksum_verified"] is True
    assert report["counts"]["created"] == 2
    assert report["counts"]["rejected"] == 0
    # The stored bundle is value-identical to the pack's
    # normalised bundle payload.
    resp = client.get("/api/v1/presets/bundles")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [r["bundle"]["name"] for r in rows] == ["Gatehall ST Bundle"]
    stored_bundle = rows[0]["bundle"]
    assert stored_bundle == validate_bundle(_gate_bundle_payload(view))
    blocks = {r["block"]: r["enabled"]
              for r in stored_bundle["prompt_layout"]["blocks"]}
    assert blocks["persona"] is False and blocks["history"] is True
    # The stored preset's params equal the fixture bag exactly.
    resp = client.get("/api/v1/presets")
    assert resp.status_code == 200, resp.text
    presets = resp.json()
    named = [p for p in presets if p["name"] == "Gatehall ST Preset"]
    assert len(named) == 1
    assert named[0]["params"] == view.params


def test_a_pack_3_pack_drives_preview_identically(tmp_path, monkeypatch):
    client, _factory = make_client(tmp_path, monkeypatch)
    pack, view = _gate_pack()
    resp = client.post("/api/v1/presets/packs/import", json=pack)
    assert resp.status_code == 200, resp.text
    resp = client.get("/api/v1/presets/bundles")
    stored_bundle = resp.json()[0]["bundle"]
    char = _make_character(client)
    chat = _make_chat(client)
    messages = ["Hail, keeper of the hall."]
    # The pack road: a P-062 profile built from the STORED bundle
    # (its sampler, layout and template selections verbatim).
    profile = {
        "name": "gatehall-from-pack",
        "model_id": "gatehall-model",
        "backend_key": "fake",
        "instruct_template": stored_bundle["instruct_template"],
        "context_template": stored_bundle["context_template"],
        "prompt_layout": stored_bundle["prompt_layout"],
        "sampler": stored_bundle["sampler"],
    }
    via_pack = _preview(
        client, character_id=char["id"], chat_id=chat["id"],
        messages=messages, model_profile=profile)
    assert via_pack["model_profile"]["applied"] is True
    assert via_pack["model_profile"]["fields"]["instruct_template"] == "profile"
    # The direct road: the same values supplied explicitly, with
    # no pack and no profile anywhere in the request.
    template = selection_to_template(stored_bundle["instruct_template"])
    ctx_template = selection_to_context_template(
        stored_bundle["context_template"])
    direct = _preview(
        client, character_id=char["id"], chat_id=chat["id"],
        messages=messages, model_id="gatehall-model", backend_key="fake",
        instruct_template=template_to_data(template),
        context_template=context_to_data(ctx_template),
        prompt_layout=stored_bundle["prompt_layout"])
    assert direct["model_profile"]["applied"] is False
    # THE DIFF: the two previews are identical, field by field,
    # across the whole P-059 preview payload.
    pack_preview = via_pack["prompt_preview"]
    direct_preview = direct["prompt_preview"]
    assert set(pack_preview.keys()) == PREVIEW_KEYS
    assert set(direct_preview.keys()) == PREVIEW_KEYS
    for key in sorted(PREVIEW_KEYS):
        assert pack_preview[key] == direct_preview[key], key
    assert pack_preview == direct_preview
    # Visible assembly facts: chatml framing, the fixture model,
    # and NO persona message - the pack layout disabled it.
    assert pack_preview["template_name"] == "chatml"
    assert pack_preview["model_id"] == "gatehall-model"
    slot_ids = [m["slot_id"] for m in pack_preview["messages"]]
    assert not any(s and s.startswith("persona/") for s in slot_ids)
    assert "gate seer" not in pack_preview["text"]
    # Control: without the pack layout the persona IS composed,
    # so the difference above is the pack's doing, not the data's.
    control = _preview(
        client, character_id=char["id"], chat_id=chat["id"],
        messages=messages, model_id="gatehall-model", backend_key="fake",
        instruct_template=template_to_data(template),
        context_template=context_to_data(ctx_template))
    control_ids = [m["slot_id"] for m in control["prompt_preview"]["messages"]]
    assert any(s and s.startswith("persona/") for s in control_ids)
    assert "gate seer" in control["prompt_preview"]["text"]
    assert control["prompt_preview"] != pack_preview


# ------------------------------------------------- Area B: the truth table

FULL_BAG = {
    "temperature": 0.7, "top_p": 0.9, "top_k": 40, "min_p": 0.05,
    "repetition_penalty": 1.1, "presence_penalty": 0.2,
    "frequency_penalty": 0.1, "typical_p": 0.95, "top_a": 0.2,
    "tfs_z": 0.95, "epsilon_cutoff": 0.0003, "eta_cutoff": 0.0003,
    "dry_multiplier": 0.8, "dry_base": 1.75, "dry_allowed_length": 2,
    "dry_penalty_last_n": 0, "dry_sequence_breakers": ["\n"],
    "xtc_probability": 0.5, "xtc_threshold": 0.1, "mirostat_mode": 2,
    "mirostat_tau": 5.0, "mirostat_eta": 0.1,
    "dynamic_temperature_range": 0.4, "dynamic_temperature_exponent": 1.0,
    "max_tokens": 256, "stop": ["END"], "seed": 42,
    "context_length": 8192, "logit_bias": {"7": -2.0, "42": 1.5},
}


def _truth_table():
    """The combined Part IV truth table, built only from the
    published in-tree surfaces: P-053 sampler truth, P-060's
    logit_bias row inside it, and P-061 structured modes."""
    table = {}
    for backend in CHAT_BACKENDS:
        controls = {r.name: r for r in truth_for_backend(backend)}
        modes = {r.mode: r for r in structured_truth_for_backend(backend)}
        table[backend] = {"controls": controls, "modes": modes}
    return table


def test_b_truth_1_matrix_complete_and_declared():
    assert audit_truth() == []
    matrix = capability_matrix()
    assert [row["backend_key"] for row in matrix["backends"]] == list(CHAT_BACKENDS)
    assert len(CANONICAL_CONTROLS) == 29
    for backend in CHAT_BACKENDS:
        rows = truth_for_backend(backend)
        # Every canonical control, exactly once, in canonical order.
        assert [r.name for r in rows] == list(CANONICAL_CONTROLS)
        available = {r.name for r in rows if r.state == AVAILABLE}
        greyed = {r.name for r in rows if r.state == GREYED}
        assert available | greyed == set(CANONICAL_CONTROLS)
        assert not (available & greyed)
        # Available == what the backend itself declares (P-053).
        assert available == set(declared_samplers(backend)), backend
        for row in rows:
            # Every row carries its reason CODE; greyed rows also
            # carry prose. Available rows carry code 'supported'
            # with empty prose by the banked P-053 design.
            assert row.reason_code
            if row.state == GREYED:
                assert row.reason
            if row.state == AVAILABLE:
                assert row.supported is True and row.wire_name
            else:
                assert row.supported is False


def test_b_truth_2_combined_table_accounts_for_everything():
    assert audit_structured_truth() == []
    table = _truth_table()
    assert set(table) == set(CHAT_BACKENDS)
    control_rows = sum(len(t["controls"]) for t in table.values())
    mode_rows = sum(len(t["modes"]) for t in table.values())
    assert control_rows == 29 * len(CHAT_BACKENDS)
    assert mode_rows == len(MODES) * len(CHAT_BACKENDS)
    for entry in table.values():
        assert set(entry["modes"]) == set(MODES)
        for row in entry["modes"].values():
            assert row.state in (AVAILABLE, GREYED)
            assert row.reason_code
            if row.state == GREYED:
                assert row.reason
    matrix = structured_matrix()
    assert [r["backend_key"] for r in matrix["backends"]] == list(CHAT_BACKENDS)
    for row in matrix["backends"]:
        assert set(row["available"]) | set(row["greyed"]) == set(MODES)
        assert not (set(row["available"]) & set(row["greyed"]))


def test_b_truth_3_nothing_offered_that_no_backend_serves():
    table = _truth_table()
    # logit_bias (P-060): served exactly where the wire carries it.
    bias_available = {b for b, t in table.items()
                      if t["controls"]["logit_bias"].state == AVAILABLE}
    assert bias_available == {"openai", "openrouter"}
    # stop: available exactly on the backends whose truth says so,
    # and the P-060 resolution path honours it there.
    for backend, entry in table.items():
        for name, row in entry["controls"].items():
            if row.state == AVAILABLE:
                # An offered control is declared by ITS backend -
                # never a global invention (the fake-slider test).
                assert name in declared_samplers(backend), (backend, name)
    # Structured modes agree with the wire layer: an available
    # active mode builds a payload; a greyed active mode refuses.
    samples = {
        "json_object": StructuredOutput(mode="json_object"),
        "json_schema": StructuredOutput(
            mode="json_schema", schema={"type": "object"}),
        "grammar": StructuredOutput(mode="grammar", grammar='root ::= "x"'),
    }
    for backend, entry in table.items():
        for mode, sample in samples.items():
            if entry["modes"][mode].state == AVAILABLE:
                assert wire_payload(backend, sample), (backend, mode)
            else:
                with pytest.raises(ValueError):
                    wire_payload(backend, sample)
    # Grammar is served by NO backend and greyed on all, with a
    # reason on every row (the P-061 recorded finding, re-proven).
    grammar_states = {t["modes"]["grammar"].state for t in table.values()}
    assert grammar_states == {GREYED}


def test_b_truth_4_partition_bag_drops_nothing_silently():
    assert set(FULL_BAG) == set(CANONICAL_CONTROLS)
    for backend in CHAT_BACKENDS:
        offered, greyed = partition_bag(
            copy.deepcopy(FULL_BAG), default_model(backend))
        greyed_names = {r.name for r in greyed}
        assert set(offered) | greyed_names == set(CANONICAL_CONTROLS), backend
        assert not (set(offered) & greyed_names), backend
        assert set(offered) == set(declared_samplers(backend)), backend
        for row in greyed:
            assert row.state == GREYED and row.reason_code
        with pytest.raises(ValueError):
            partition_bag({"vendor_magic": 1}, default_model(backend))


def test_b_truth_5_table_is_published(tmp_path, monkeypatch):
    client, _factory = make_client(tmp_path, monkeypatch)
    resp = client.get("/api/v1/debug/backend-capabilities")
    assert resp.status_code == 200, resp.text
    published = resp.json()
    local = capability_matrix()
    assert [r["backend_key"] for r in published["backends"]] == list(CHAT_BACKENDS)
    for pub_row, local_row in zip(published["backends"], local["backends"], strict=True):
        assert pub_row["backend_key"] == local_row["backend_key"]
        assert pub_row["available"] == local_row["available"]
        assert pub_row["greyed"] == local_row["greyed"]
        assert [c["name"] for c in pub_row["controls"]] == list(CANONICAL_CONTROLS)
    resp = client.get("/api/v1/debug/structured-modes")
    assert resp.status_code == 200, resp.text
    modes = resp.json()
    local_modes = structured_matrix()
    pub = {r["backend_key"]: r for r in modes["backends"]}
    for row in local_modes["backends"]:
        assert pub[row["backend_key"]]["available"] == row["available"]
        assert pub[row["backend_key"]]["greyed"] == row["greyed"]


# ------------------------------------------- Area C: citizens compose


def _gatehall_client(tmp_path, monkeypatch):
    client, _factory = make_client(tmp_path, monkeypatch)
    char = _make_character(client)
    chat = _make_chat(client)
    _set_note(client, chat["id"], {
        "text": NOTE_TEXT, "depth": 0, "frequency": 1,
        "enabled": True, "role": "system"})
    _set_ph(client, chat["id"], {
        "text": PH_CHAT_TEXT, "enabled": True, "role": "user"})
    return client, char, chat


def _expanded_messages():
    ctx = MacroContext(char_name=CHAR_NAME, user_name=USER_NAME,
                       now=datetime(2026, 11, 7, 9, 30, 0))
    out = expand_macros(MACRO_RAW, ctx)
    assert out.text == MACRO_EXPANDED
    assert out.report.unknown == [] and out.report.errors == []
    return [out.text, "The longship waits at the shore.", "We sail at dawn."]


def test_c_comp_1_layout_templates_and_render(tmp_path, monkeypatch):
    client, char, chat = _gatehall_client(tmp_path, monkeypatch)
    messages = _expanded_messages()
    layout = {"blocks": [{"block": "persona", "enabled": False}]}
    result = _preview(
        client, character_id=char["id"], chat_id=chat["id"],
        messages=messages, prompt_layout=layout,
        instruct_template="chatml")
    # P-049: the disabled persona block is composed OUT and the
    # discard is recorded with its reason; the layout echo shows it.
    persona_rows = [s for s in result["slots"]
                    if s["slot_id"].startswith("persona/")]
    assert persona_rows and all(
        s["status"] == "discarded" for s in persona_rows)
    assert all(s["reason"] == "prompt_manager_disabled"
               for s in persona_rows)
    blocks = {b["block"]: b["enabled"]
              for b in result["prompt_layout"]["blocks"]}
    assert blocks["persona"] is False
    preview = result["prompt_preview"]
    assert not any(m["slot_id"] and m["slot_id"].startswith("persona/")
                   for m in preview["messages"])
    # P-050 + P-051 echoes name what is in play, and the preview
    # text is the chatml render of exactly the composed messages.
    assert result["instruct_template"]["name"] == "chatml"
    assert result["instruct_template"]["source"] == "explicit"
    assert result["context_template"]["source"] in ("default", "explicit")
    assert preview["template_name"] == "chatml"
    assert preview["text"].startswith("<|im_start|>system")
    assert preview["rendered_tokens"] == result["rendered_tokens"]


def test_c_comp_2_macros_note_and_post_history(tmp_path, monkeypatch):
    client, char, chat = _gatehall_client(tmp_path, monkeypatch)
    messages = _expanded_messages()
    result = _preview(
        client, character_id=char["id"], chat_id=chat["id"],
        messages=messages, instruct_template="chatml")
    preview = result["prompt_preview"]
    slot_ids = [m["slot_id"] for m in preview["messages"]]
    # P-055: the macro-expanded text is the history content; no
    # raw macro survives into the assembled prompt.
    assert MACRO_EXPANDED in preview["text"]
    assert "{{" not in preview["text"]
    # P-056: the note is present + active, spliced after ALL
    # history (depth 0) and before the post-history block.
    assert result["authors_note"]["present"] is True
    assert result["authors_note"]["active"] is True
    assert result["authors_note"]["source"] == "chat"
    note_idx = slot_ids.index("authors_note/chat")
    hist_idxs = [i for i, s in enumerate(slot_ids) if s == "history"]
    assert hist_idxs and max(hist_idxs) < note_idx
    assert preview["messages"][note_idx]["content"] == NOTE_TEXT
    # P-057: the CHAT's post-history wins over the character
    # card's, and it is the last composed message.
    assert result["post_history"] == {
        "present": True, "enabled": True, "role": "user", "source": "chat"}
    ph_idx = slot_ids.index("post_history/chat")
    assert ph_idx == len(slot_ids) - 1 and note_idx < ph_idx
    assert preview["messages"][ph_idx]["content"] == PH_CHAT_TEXT
    assert PH_CARD_TEXT not in preview["text"]
    # S214: note / post-history text lives ONLY in the preview -
    # never in the trace slots or the ledger.
    trace_dump = json.dumps(result["slots"]) + json.dumps(result["ledger"])
    assert NOTE_TEXT not in trace_dump
    assert PH_CHAT_TEXT not in trace_dump
    assert NOTE_TEXT in preview["text"] and PH_CHAT_TEXT in preview["text"]


def test_c_comp_3_governor_reconciles_and_trims(tmp_path, monkeypatch):
    client, char, chat = _gatehall_client(tmp_path, monkeypatch)
    messages = ["a" * 40, "b" * 40, "c" * 40, "d" * 40]
    base = _preview(
        client, character_id=char["id"], chat_id=chat["id"],
        messages=messages)
    budget = base["budget"]
    assert set(budget["sections"]) == {"context", "lore", "memory", "history"}
    included = sum(s["included_tokens"]
                   for s in budget["sections"].values())
    assert included == base["ledger"]["total_input_tokens"]
    assert base["budget_governor"]["applied"] is False
    governed = _preview(
        client, character_id=char["id"], chat_id=chat["id"],
        messages=messages, budget_policy={"section_caps": {"history": 20}})
    gov = governed["budget_governor"]
    assert gov["applied"] is True and gov["source"] == "explicit"
    trims = [a for a in gov["actions"]
             if a["action"] == "trimmed" and a["slot_id"] == "history"]
    assert trims and trims[0]["reason"] == "governor_section_cap"
    assert governed["ledger"]["total_input_tokens"] < base["ledger"]["total_input_tokens"]
    # Required framing survives the trim: system + note +
    # post-history are still composed in the governed preview.
    gov_ids = [m["slot_id"] for m in governed["prompt_preview"]["messages"]]
    assert "system/main" in gov_ids
    assert "authors_note/chat" in gov_ids
    assert "post_history/chat" in gov_ids


def test_c_comp_4_profile_switch_moves_only_what_it_owns(tmp_path, monkeypatch):
    client, char, chat = _gatehall_client(tmp_path, monkeypatch)
    messages = _expanded_messages()
    before = get_profile("chatml-general")
    after = get_profile("llama3-instruct")
    diff = diff_profiles(before, after)
    fields = {row["field"] for row in diff["changes"]}
    assert "instruct_template" in fields
    assert "sampler.top_k" in fields
    assert diff["carries"] == list(CARRIES)
    assert list(CARRIES) == [
        "history", "character", "lorebooks", "authors_note", "post_history"]
    run_a = _preview(
        client, character_id=char["id"], chat_id=chat["id"],
        messages=messages, model_profile="chatml-general")
    run_b = _preview(
        client, character_id=char["id"], chat_id=chat["id"],
        messages=messages, model_profile="llama3-instruct")
    # What the profile owns changes: template echo + framing.
    assert run_a["instruct_template"]["name"] == "chatml"
    assert run_b["instruct_template"]["name"] == "llama3"
    assert run_a["instruct_template"]["source"] == "profile"
    assert run_b["instruct_template"]["source"] == "profile"
    assert run_a["prompt_preview"]["text"] != run_b["prompt_preview"]["text"]
    assert run_a["prompt_preview"]["template_name"] == "chatml"
    assert run_b["prompt_preview"]["template_name"] == "llama3"
    # What it must carry does not: same chat state in both runs.
    for run in (run_a, run_b):
        assert run["authors_note"]["present"] is True
        assert run["authors_note"]["active"] is True
        assert run["post_history"]["source"] == "chat"
        assert MACRO_EXPANDED in run["prompt_preview"]["text"]
        assert NOTE_TEXT in run["prompt_preview"]["text"]
        assert PH_CHAT_TEXT in run["prompt_preview"]["text"]
    # The composed message CONTENTS are identical across the
    # switch - only the framing (render) differs.
    contents_a = [(m["role"], m["content"]) for m in run_a["prompt_preview"]["messages"]]
    contents_b = [(m["role"], m["content"]) for m in run_b["prompt_preview"]["messages"]]
    assert contents_a == contents_b


# ------------------------------------------------- gate hygiene


def test_gate_hygiene_migration_head_stays_0036():
    assert MIGRATIONS[-1][0] == "0039"
