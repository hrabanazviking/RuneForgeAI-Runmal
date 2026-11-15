"""R-09 acceptance (settings logic): the Qt-free Connections &
Generation layer over a MockTransport engine.

Gates: the sampler catalogue is exactly the engine's canonical
29 bag keys; bag split/merge is lossless for unknown keys;
validation mirrors the values that can take effect; the profile
flow composes config (base_url merged, other keys preserved)
and drives the secret tri-state through the write-only roads
(INV-023: a canary key never appears in any payload the engine
returns); the bundle flow composes over the stored document so
structural sections are carried verbatim; overrides + resolve
render with per-field sources.

No Qt here: the widgets are gated separately
(``test_r09_desktop_window.py``) and the live engine end-to-end
in ``test_r09_settings_live.py``.
"""

import json

import httpx
import pytest

from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.client.errors import ClientError
from runmal.desktop.settings_logic import (
    SAMPLER_FIELDS,
    SettingsFlow,
    bias_to_text,
    carried_sections,
    effective_rows,
    merge_bag,
    resolve_notes,
    split_bag,
    strings_to_text,
    text_to_bias,
    text_to_strings,
    validate_bag,
)
from runmal.presets.service import _CANONICAL

TOKEN = "test-" + "token-r09"
CANARY = "CANARY-KEY-9f3e7a-never-echo"


class FakeEngine:
    """A stateful in-memory stand-in for the R-09 roads.

    Secrets live in their own store and are NEVER part of a
    profile payload — the fake mirrors INV-023 so the canary
    assertions measure the shell, not the fake's honesty.
    Every response body is recorded in ``responses`` so tests
    can prove the canary crosses none of them.
    """

    def __init__(self):
        self.profiles: dict[str, dict] = {}
        self.secrets: dict[str, dict[str, str]] = {}
        self.presets: dict[str, dict] = {}
        self.bundles: dict[str, dict] = {}
        self.overrides: dict[tuple[str, str], dict] = {}
        self.chats: dict[str, dict] = {}
        self.responses: list[str] = []
        self.requests: list[tuple[str, str, dict]] = []
        self._seq = 0

    def _id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}{self._seq}"

    def _profile_row(self, row: dict) -> dict:
        stored = self.secrets.get(row["id"], {})
        return {
            "id": row["id"],
            "name": row["name"],
            "chat_backend": row["chat_backend"],
            "chat_model": row["chat_model"],
            "embedding_backend": row["embedding_backend"],
            "embedding_model": row["embedding_model"],
            "has_chat_secret": "chat" in stored,
            "has_embedding_secret": "embedding" in stored,
            "config": dict(row["config"]),
        }

    def _preset_row(self, row: dict) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "params": dict(row["params"]),
            "template_ref": row["template_ref"],
            "source_format": row.get("source_format", "native"),
            "prompts": list(row.get("prompts", [])),
        }

    def _bundle_row(self, bundle_id: str) -> dict:
        row = self.bundles[bundle_id]
        return {"id": bundle_id, "name": row["name"], "bundle": row}

    def _respond(self, status: int, payload) -> httpx.Response:
        text = json.dumps(payload)
        self.responses.append(text)
        return httpx.Response(status, json=payload)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/healthz":
            return self._respond(200, {"status": "ok", "version": "0.1.0"})
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return self._respond(401, {"detail": "no auth"})
        body = {}
        if request.content and "json" in request.headers.get("content-type", ""):
            try:
                body = json.loads(request.content)
            except ValueError:
                body = {}
        self.requests.append((request.method, path, body))
        parts = [p for p in path.split("/") if p]
        # parts: ['api', 'v1', ...]
        if parts[:3] == ["api", "v1", "backend-profiles"]:
            return self._profiles_road(request, parts, body)
        if parts[:3] == ["api", "v1", "presets"]:
            return self._presets_road(request, parts, body)
        if parts[:3] == ["api", "v1", "chats"]:
            return self._chats_road(request, parts, body)
        return self._respond(404, {"detail": f"no road {path}"})

    # ------------------------------------------------------- profiles

    def _profiles_road(self, request, parts, body):
        if len(parts) == 3:
            if request.method == "GET":
                return self._respond(
                    200, [self._profile_row(r) for r in self.profiles.values()]
                )
            if request.method == "POST":
                row = {
                    "id": self._id("p"),
                    "name": body.get("name", ""),
                    "chat_backend": body.get("chat_backend", ""),
                    "chat_model": body.get("chat_model", ""),
                    "embedding_backend": body.get("embedding_backend", ""),
                    "embedding_model": body.get("embedding_model", ""),
                    "config": dict(body.get("config") or {}),
                }
                self.profiles[row["id"]] = row
                return self._respond(201, self._profile_row(row))
        row = self.profiles.get(parts[3]) if len(parts) > 3 else None
        if row is None:
            return self._respond(404, {"detail": "profile not found"})
        if len(parts) == 4:
            if request.method == "GET":
                return self._respond(200, self._profile_row(row))
            if request.method == "PATCH":
                for key in (
                    "name", "chat_backend", "chat_model",
                    "embedding_backend", "embedding_model", "config",
                ):
                    if key in body:
                        row[key] = body[key]
                return self._respond(200, self._profile_row(row))
            if request.method == "DELETE":
                del self.profiles[row["id"]]
                self.secrets.pop(row["id"], None)
                return self._respond(200, {"ok": True})
        if len(parts) == 5 and parts[4] == "health":
            ok = row["chat_backend"] in ("fake", "ollama")
            return self._respond(200, {
                "ok": ok,
                "detail": "reachable" if ok else "connection refused",
            })
        if len(parts) == 5 and parts[4] == "models":
            return self._respond(200, {"models": [
                {"model_id": "fake-1"}, {"model_id": "fake-2"},
            ]})
        if len(parts) == 5 and parts[4] in ("chat-secret", "embedding-secret"):
            kind = "chat" if parts[4] == "chat-secret" else "embedding"
            if request.method == "PUT":
                self.secrets.setdefault(row["id"], {})[kind] = body.get("value", "")
                return self._respond(200, self._profile_row(row))
            if request.method == "DELETE":
                self.secrets.get(row["id"], {}).pop(kind, None)
                return self._respond(200, self._profile_row(row))
        return self._respond(404, {"detail": "no profile road"})

    # ------------------------------------------------------- presets

    def _presets_road(self, request, parts, body):
        if len(parts) == 3:
            if request.method == "GET":
                return self._respond(
                    200, [self._preset_row(r) for r in self.presets.values()]
                )
            if request.method == "POST":
                row = {
                    "id": self._id("pr"),
                    "name": body.get("name", ""),
                    "params": dict(body.get("params") or {}),
                    "template_ref": body.get("template_ref", ""),
                    "prompts": [],
                }
                self.presets[row["id"]] = row
                return self._respond(201, self._preset_row(row))
        if len(parts) == 4 and parts[3] == "import" and request.method == "POST":
            name = request.url.params.get("name") or body.get("name") or "Imported"
            row = {
                "id": self._id("pr"),
                "name": name,
                "params": dict(body.get("params") or {}),
                "template_ref": body.get("template_ref", ""),
                "prompts": list(body.get("prompts") or []),
                "source_format": "st",
            }
            self.presets[row["id"]] = row
            return self._respond(201, self._preset_row(row))
        if len(parts) == 4 and parts[3] == "bundles":
            if request.method == "GET":
                return self._respond(
                    200, [self._bundle_row(b) for b in self.bundles]
                )
            if request.method == "POST":
                document = dict(body.get("bundle") or {})
                bundle_id = self._id("b")
                document.setdefault("name", "")
                self.bundles[bundle_id] = document
                return self._respond(201, self._bundle_row(bundle_id))
        if len(parts) == 5 and parts[3] == "bundles" and parts[4] == "import":
            document = dict(body or {})
            bundle_id = self._id("b")
            self.bundles[bundle_id] = document
            return self._respond(201, self._bundle_row(bundle_id))
        if len(parts) == 5 and parts[3] == "bundles":
            bundle_id = parts[4]
            if bundle_id not in self.bundles:
                return self._respond(404, {"detail": "bundle not found"})
            if request.method == "GET":
                return self._respond(200, self._bundle_row(bundle_id))
            if request.method in ("PUT", "PATCH"):
                document = dict(body.get("bundle") or {})
                self.bundles[bundle_id] = document
                return self._respond(200, self._bundle_row(bundle_id))
            if request.method == "DELETE":
                del self.bundles[bundle_id]
                return self._respond(200, {"ok": True})
        if len(parts) == 6 and parts[3] == "bundles" and parts[5] == "share":
            return self._respond(200, dict(self.bundles[parts[4]]))
        if len(parts) == 4 and parts[3] == "overrides" and request.method == "GET":
            return self._respond(200, list(self.overrides.values()))
        if len(parts) == 6 and parts[3] == "overrides":
            scope_kind, owner_id = parts[4], parts[5]
            if request.method == "PUT":
                row = {
                    "id": self._id("ov"),
                    "bundle_id": body.get("bundle_id", ""),
                    "scope_kind": scope_kind,
                    "owner_id": owner_id,
                    "overrides": body.get("overrides") or {},
                }
                self.overrides[(scope_kind, owner_id)] = row
                return self._respond(200, row)
            if request.method == "DELETE":
                self.overrides.pop((scope_kind, owner_id), None)
                return self._respond(200, {"ok": True})
        if len(parts) == 5 and parts[3] == "packs":
            action = parts[4]
            if action == "inspect":
                return self._respond(200, {"ok": True, "presets": 1, "bundles": 1})
            if action == "import":
                return self._respond(200, {"ok": True, "imported": 2, "skipped": 0})
            if action == "export":
                return self._respond(200, {
                    "name": body.get("name", "pack"),
                    "presets": [self._preset_row(r) for r in self.presets.values()],
                    "bundles": [self._bundle_row(b) for b in self.bundles],
                })
        if len(parts) == 4 and parts[3] == "resolve" and request.method == "GET":
            return self._respond(200, {"effective": self._resolve(request)})
        if len(parts) == 4:
            row = self.presets.get(parts[3])
            if row is None:
                return self._respond(404, {"detail": "preset not found"})
            if request.method == "GET":
                return self._respond(200, self._preset_row(row))
            if request.method == "PATCH":
                for key in ("name", "params", "template_ref"):
                    if key in body:
                        row[key] = body[key]
                return self._respond(200, self._preset_row(row))
            if request.method == "DELETE":
                del self.presets[row["id"]]
                return self._respond(200, {"ok": True})
        if len(parts) == 5 and parts[4] == "export":
            row = self.presets.get(parts[3])
            if row is None:
                return self._respond(404, {"detail": "preset not found"})
            return self._respond(200, self._preset_row(row))
        return self._respond(404, {"detail": "no preset road"})

    def _resolve(self, request):
        chat_id = request.url.params.get("chat_id")
        character_id = request.url.params.get("character_id")
        chat_row = self.overrides.get(("chat", chat_id or ""))
        char_row = self.overrides.get(("character", character_id or ""))
        if chat_row is None and char_row is None:
            return None
        if (
            chat_row is not None and char_row is not None
            and chat_row["bundle_id"] != char_row["bundle_id"]
        ):
            bundle = self.bundles[chat_row["bundle_id"]]
            effective, sources = self._merge(bundle, chat_row)
            return {
                "bundle_id": chat_row["bundle_id"],
                "bundle_name": bundle.get("name", ""),
                "effective": effective,
                "sources": sources,
                "applied": [{
                    "scope_kind": "chat", "owner_id": chat_id,
                    "bundle_id": chat_row["bundle_id"],
                }],
                "shadowed": [{
                    "scope_kind": "character", "owner_id": character_id,
                    "bundle_id": char_row["bundle_id"],
                    "reason": "chat assignment names a different bundle",
                }],
            }
        chosen = chat_row if chat_row is not None else char_row
        label = "chat" if chat_row is not None else "character"
        owner = chat_id if chat_row is not None else character_id
        bundle = self.bundles[chosen["bundle_id"]]
        effective, sources = self._merge(bundle, chosen, label=label)
        return {
            "bundle_id": chosen["bundle_id"],
            "bundle_name": bundle.get("name", ""),
            "effective": effective,
            "sources": sources,
            "applied": [{
                "scope_kind": label, "owner_id": owner,
                "bundle_id": chosen["bundle_id"],
            }],
            "shadowed": [],
        }

    @staticmethod
    def _merge(bundle, override_row, label="chat"):
        effective = dict(bundle)
        sampler = dict(bundle.get("sampler") or {})
        sources = {key: "bundle" for key in sampler}
        delta = (override_row.get("overrides") or {}).get("sampler") or {}
        for key, value in delta.items():
            if value is None:
                sampler.pop(key, None)
                sources.pop(key, None)
            else:
                sampler[key] = value
                sources[key] = label
        effective["sampler"] = sampler
        return effective, {"sampler": sources}

    # ------------------------------------------------------- chats

    def _chats_road(self, request, parts, body):
        if len(parts) == 3 and request.method == "POST":
            chat = {
                "id": self._id("c"), "title": body.get("title", ""),
                "character_id": body.get("character_id"),
                "backend_profile_id": None, "preset_id": None,
                "message_count": 0,
            }
            self.chats[chat["id"]] = chat
            return self._respond(201, chat)
        if len(parts) >= 4:
            chat = self.chats.get(parts[3])
            if chat is None:
                return self._respond(404, {"detail": "chat not found"})
            if len(parts) == 4 and request.method == "GET":
                return self._respond(200, chat)
            if len(parts) == 5 and parts[4] == "backend-profile":
                chat["backend_profile_id"] = body.get("profile_id")
                return self._respond(200, chat)
            if len(parts) == 5 and parts[4] == "preset":
                chat["preset_id"] = body.get("preset_id")
                return self._respond(200, chat)
        return self._respond(404, {"detail": "no chat road"})


def make_flow():
    engine = FakeEngine()
    session = DesktopSession("http://127.0.0.1:9", bearer_token=TOKEN)
    http = httpx.Client(
        base_url="http://127.0.0.1:9",
        transport=httpx.MockTransport(engine),
        trust_env=False,
    )
    client = RunmalClient(session, http=http)
    return SettingsFlow(client), client, engine


# ------------------------------------------------------------ catalogue


def test_catalogue_is_exactly_the_canonical_bag() -> None:
    mine = {field.key for field in SAMPLER_FIELDS}
    assert mine == set(_CANONICAL)
    assert len(SAMPLER_FIELDS) == 29


def test_split_merge_is_lossless_for_unknown_keys() -> None:
    bag = {"temperature": 0.7, "vendor_thing": {"nested": [1, 2]}, "zz": "x"}
    known, extra = split_bag(bag)
    assert known == {"temperature": 0.7}
    assert extra == {"vendor_thing": {"nested": [1, 2]}, "zz": "x"}
    assert merge_bag(known, extra) == bag
    # A known key in the form wins over a stale extra of the same name.
    assert merge_bag({"temperature": 0.9}, {"temperature": 0.1}) == {
        "temperature": 0.9
    }


def test_validate_bag_mirrors_effective_ranges() -> None:
    assert validate_bag({"temperature": 0.9, "top_p": 0.95}) == []
    problems = validate_bag({
        "temperature": -0.5,
        "top_p": 0.0,
        "seed": -3,
        "logit_bias": {"12": 500.0},
        "mirostat_mode": 7,
    })
    joined = " ".join(problems)
    assert "Temperature" in joined
    assert "Top P" in joined
    assert "Seed" in joined
    assert "Logit bias" in joined
    assert "Mirostat mode" in joined


def test_text_converters_round_trip() -> None:
    assert text_to_strings("alpha\n\n beta \n") == ["alpha", "beta"]
    assert strings_to_text(["a", "b"]) == "a\nb"
    parsed, errors = text_to_bias("12 = -5\n7=2.5")
    assert errors == []
    assert parsed == {"12": -5.0, "7": 2.5}
    assert bias_to_text(parsed) == "7 = 2.5\n12 = -5"
    _bad, errors = text_to_bias("not-a-bias-line")
    assert errors


# ------------------------------------------------------------ profiles


def test_save_profile_composes_config_and_preserves_other_keys() -> None:
    flow, _client, engine = make_flow()
    created = flow.save_profile(
        None,
        name="Hearth",
        chat_backend="ollama",
        chat_model="llama3",
        base_url="http://127.0.0.1:11434",
    )
    assert created.config == {"base_url": "http://127.0.0.1:11434"}
    # Another tool wrote a sibling config key; the flow's update
    # must preserve it while replacing base_url.
    engine.profiles[created.id]["config"]["other_tool"] = {"keep": True}
    updated = flow.save_profile(
        created.id,
        name="Hearth",
        chat_backend="ollama",
        chat_model="llama3",
        base_url="http://localhost:9999",
    )
    assert updated.config["base_url"] == "http://localhost:9999"
    assert updated.config["other_tool"] == {"keep": True}
    # Clearing the address removes only base_url.
    cleared = flow.save_profile(
        created.id, name="Hearth", chat_backend="ollama", base_url=""
    )
    assert "base_url" not in cleared.config
    assert cleared.config["other_tool"] == {"keep": True}


def test_secret_tri_state_and_canary_never_echoed() -> None:
    flow, client, engine = make_flow()
    profile = flow.save_profile(
        None, name="Keyed", chat_backend="openrouter", chat_key=CANARY
    )
    assert profile.has_chat_secret is True
    assert engine.secrets[profile.id]["chat"] == CANARY
    # The canary appears in NO response the engine produced and
    # in NO object the client hands back (INV-023).
    assert all(CANARY not in text for text in engine.responses)
    assert CANARY not in repr(profile)
    assert CANARY not in repr(client.list_backend_profiles())
    assert CANARY not in repr(client.get_backend_profile(profile.id))
    # None = untouched: no secret road is hit at all.
    before = len([r for r in engine.requests if "secret" in r[1]])
    flow.save_profile(
        profile.id, name="Keyed", chat_backend="openrouter", chat_key=None
    )
    after = len([r for r in engine.requests if "secret" in r[1]])
    assert before == after
    assert engine.secrets[profile.id]["chat"] == CANARY
    # "" = cleared through the DELETE road.
    cleared = flow.save_profile(
        profile.id, name="Keyed", chat_backend="openrouter", chat_key=""
    )
    assert cleared.has_chat_secret is False
    assert "chat" not in engine.secrets.get(profile.id, {})


def test_probe_reports_words_and_models() -> None:
    flow, _client, _engine = make_flow()
    profile = flow.save_profile(
        None, name="Demo", chat_backend="fake", chat_model="fake-1"
    )
    result = flow.probe(profile.id)
    assert result.ok is True
    assert result.models == ["fake-1", "fake-2"]
    assert "Demo" in result.words


def test_pin_and_apply_roads() -> None:
    flow, client, engine = make_flow()
    chat = client.create_chat(title="Gate chat")
    profile = flow.save_profile(None, name="P", chat_backend="fake")
    flow.pin_profile(chat.id, profile.id)
    assert engine.chats[chat.id]["backend_profile_id"] == profile.id
    flow.pin_profile(chat.id, None)
    assert engine.chats[chat.id]["backend_profile_id"] is None
    preset = flow.save_preset(None, name="Warm", params={"temperature": 0.9})
    flow.apply_preset(chat.id, preset.id)
    assert engine.chats[chat.id]["preset_id"] == preset.id


# ------------------------------------------------------------ presets


def test_preset_flow_keeps_unknown_keys_and_duplicates() -> None:
    flow, _client, _engine = make_flow()
    detail = flow.save_preset(
        None,
        name="Vendor",
        params={"temperature": 0.5, "vendor_flag": True},
        template_ref="tmpl-1",
    )
    assert detail.params == {"temperature": 0.5, "vendor_flag": True}
    edited = flow.save_preset(
        detail.id,
        name="Vendor",
        params={"temperature": 0.6, "vendor_flag": True},
        template_ref="tmpl-1",
    )
    assert edited.params["temperature"] == 0.6
    copy = flow.duplicate_preset(detail.id)
    assert copy.name == "Vendor (copy)"
    assert copy.params == edited.params
    exported = flow.export_preset(detail.id)
    assert exported["params"]["vendor_flag"] is True
    assert flow.delete_preset(detail.id) is True


def test_preset_flow_rejects_out_of_range_bag() -> None:
    flow, _client, _engine = make_flow()
    with pytest.raises(ClientError):
        flow.save_preset(None, name="Bad", params={"top_p": 1.5})


# ------------------------------------------------------------ bundles


def test_bundle_flow_carries_structural_sections_verbatim() -> None:
    flow, _client, engine = make_flow()
    base = {
        "name": "Story",
        "sampler": {"temperature": 0.3},
        "prompt_layout": [{"identifier": "main", "enabled": True}],
        "instruct_template": "alpaca",
        "extensions": {"vendor": {"keep": [1, 2, 3]}},
    }
    bundle_id = engine._id("b")
    engine.bundles[bundle_id] = dict(base)
    view = flow.save_bundle(
        bundle_id,
        name="Story II",
        sampler={"temperature": 0.8},
        template_ref="",
        base=flow.bundle_detail(bundle_id).bundle,
    )
    stored = engine.bundles[bundle_id]
    assert stored["name"] == "Story II"
    assert stored["sampler"] == {"temperature": 0.8}
    assert stored["prompt_layout"] == base["prompt_layout"]
    assert stored["instruct_template"] == "alpaca"
    assert stored["extensions"] == base["extensions"]
    assert view.name == "Story II"
    carried = carried_sections(stored)
    assert "prompt layout" in carried
    assert "extension data" in carried


def test_overrides_and_resolve_words() -> None:
    flow, client, _engine = make_flow()
    chat = client.create_chat(title="Resolve chat")
    character_id = "char-1"
    bundle = flow.save_bundle(
        None, name="Base", sampler={"temperature": 0.3, "top_k": 40}
    )
    flow.set_override(
        "chat", chat.id, bundle.id, overrides={"sampler": {"temperature": 0.7}}
    )
    rows = flow.list_overrides()
    assert len(rows) == 1 and rows[0].bundle_id == bundle.id
    view = flow.resolve(chat_id=chat.id)
    assert view is not None
    effective = effective_rows(view)
    by_label = {label: (value, source) for label, value, source in effective}
    assert by_label["Temperature (creativity)"] == ("0.7", "chat")
    assert by_label["Top K (word shortlist)"] == ("40", "bundle")
    notes = resolve_notes(view)
    assert any("Base" in note for note in notes)
    assert any("Applied" in note for note in notes)
    # Shadowing: a character assignment naming a DIFFERENT bundle
    # is reported, never silently dropped.
    other = flow.save_bundle(None, name="Other", sampler={"top_p": 0.5})
    flow.set_override("character", character_id, other.id)
    view = flow.resolve(chat_id=chat.id, character_id=character_id)
    notes = resolve_notes(view)
    assert any("Shadowed" in note for note in notes)
    assert flow.delete_override("chat", chat.id) is True
    assert flow.resolve(chat_id=chat.id) is None


def test_pack_roads_pass_through() -> None:
    flow, _client, _engine = make_flow()
    report = flow.inspect_pack({"name": "p"})
    assert report["ok"] is True
    imported = flow.import_pack({"name": "p"}, on_conflict="skip")
    assert imported["imported"] == 2
    exported = flow.export_pack("mypack")
    assert exported["name"] == "mypack"
