"""R-08 acceptance (characters logic): the Qt-free Characters
layer over a MockTransport engine — full-card read (summary +
version road), lossless edit overlay, create-from-scratch, tags
via the organisation road, favourites, library search, avatar /
asset bytes, lorebook binding, version history + composed
restore, duplicate, soft-delete with undo, export, bulk import.

No Qt here: the widgets are gated separately
(``test_r08_desktop_window.py``) and the live engine end-to-end
in ``test_r08_character_live.py``.
"""

import json
import re
import subprocess
import sys

import httpx
import pytest

from runmal.desktop.character_logic import (
    CharacterFlow,
    apply_card_edits,
    parse_tags,
)
from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.client.errors import ClientError

TOKEN = "r08-logic-token"
PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png-bytes"


def wrapped(data: dict) -> dict:
    return {"spec": "chara_card_v2", "spec_version": "2.0", "data": data}


class FakeEngine:
    """A stateful in-memory stand-in for the R-08 roads.

    Characters are rows {id, name, card (wrapped dict), deleted,
    version_no, lineage_id, avatar (filename|None)}; same-name
    creates with new content become the next version in the
    lineage, exact duplicates return the existing row — the
    P-025 semantics the shell composes over."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.orgs: dict[str, dict] = {}
        self.assets: dict[str, list[dict]] = {}
        self.bindings: dict[str, dict] = {}
        self.lorebooks = {
            "lb1": {"id": "lb1", "name": "Pass Lore", "entry_count": 2}
        }
        self.avatar_bytes: dict[str, bytes] = {}
        self._seq = 0

    def _id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}{self._seq}"

    def _summary(self, row: dict) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "created_at": "2026-11-14T00:00:00+00:00",
            "has_avatar": row["avatar"] is not None,
            "avatar_asset": row["avatar"],
            "version_no": row["version_no"],
            "lineage_id": row["lineage_id"],
            "content_hash": "x" * 64,
        }

    def _org(self, row: dict) -> dict:
        org = self.orgs.setdefault(
            row["id"],
            {
                "character_id": row["id"],
                "name": row["name"],
                "tags": list(row["card"]["data"].get("tags", [])),
                "is_favourite": False,
            },
        )
        org["name"] = row["name"]
        return org

    def seed(self, data: dict) -> dict:
        row, _duplicate = self._create(data, data.get("name", ""))
        return row

    def _create(self, card_data: dict, name: str) -> tuple[dict, bool]:
        card = wrapped(dict(card_data))
        for row in self.rows.values():
            if row["deleted"] or row["name"] != name:
                continue
            if row["card"] == card:
                return row, True
        siblings = [
            r for r in self.rows.values() if r["name"] == name
        ]
        lineage = siblings[0]["lineage_id"] if siblings else None
        version_no = max([r["version_no"] for r in siblings], default=0) + 1
        row = {
            "id": self._id("k"),
            "name": name,
            "card": card,
            "deleted": False,
            "avatar": None,
            "version_no": version_no,
            "lineage_id": lineage or "",
        }
        if not row["lineage_id"]:
            row["lineage_id"] = row["id"]
        self.rows[row["id"]] = row
        self.assets[row["id"]] = []
        return row, False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/healthz":
            return httpx.Response(200, json={"status": "ok"})
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"detail": "no auth"})
        body: dict = {}
        if request.content and "json" in request.headers.get(
            "content-type", ""
        ):
            try:
                body = json.loads(request.content)
            except ValueError:
                body = {}
        return self._route(request, path, body)

    def _route(self, request, path, body):
        method = request.method
        if path == "/api/v1/characters" and method == "POST":
            row, duplicate = self._create(
                body.get("card", {}), body.get("name") or body.get("card", {}).get("name", "")
            )
            payload = self._summary(row)
            if duplicate:
                payload["duplicate_exact"] = True
                return httpx.Response(200, json=payload)
            return httpx.Response(201, json=payload)
        if path == "/api/v1/characters" and method == "GET":
            return httpx.Response(
                200,
                json=[
                    self._summary(r)
                    for r in self.rows.values()
                    if not r["deleted"]
                ],
            )
        if path == "/api/v1/lorebooks":
            return httpx.Response(200, json=list(self.lorebooks.values()))
        if path == "/api/v1/library/imports" and method == "POST":
            names = re.findall(rb'filename="([^"]+)"', request.content)
            entries = []
            created = 0
            for raw_name in names:
                filename = raw_name.decode()
                stem = filename.rsplit(".", 1)[0].replace("-", " ").title()
                row, duplicate = self._create(
                    {"name": stem, "description": "Imported."}, stem
                )
                if duplicate:
                    entries.append({
                        "filename": filename, "outcome": "duplicate",
                        "created_id": None, "duplicate_of": row["id"],
                    })
                else:
                    created += 1
                    entries.append({
                        "filename": filename, "outcome": "accepted",
                        "created_id": row["id"], "created_name": row["name"],
                    })
            return httpx.Response(200, json={
                "totals": {
                    "total_seen": len(names), "accepted": created,
                    "repaired": 0, "refused": 0, "skipped": 0,
                },
                "entries": entries,
            })
        if path == "/api/v1/library/cards" and method == "GET":
            params = request.url.params
            q = (params.get("q") or "").lower()
            favourites_only = params.get("favourites_only") == "true"
            items = []
            for row in self.rows.values():
                if row["deleted"]:
                    continue
                org = self._org(row)
                if q and q not in row["name"].lower() and not any(
                    q in t.lower() for t in org["tags"]
                ):
                    continue
                if favourites_only and not org["is_favourite"]:
                    continue
                items.append({
                    "id": row["id"], "name": row["name"],
                    "created_at": "2026-11-14T00:00:00+00:00",
                    "has_avatar": row["avatar"] is not None,
                    "tags": list(org["tags"]),
                    "is_favourite": org["is_favourite"],
                })
            return httpx.Response(200, json={"total": len(items), "items": items})
        if path == "/api/v1/library/tags":
            counts: dict[str, int] = {}
            for row in self.rows.values():
                if row["deleted"]:
                    continue
                for tag in self._org(row)["tags"]:
                    counts[tag] = counts.get(tag, 0) + 1
            return httpx.Response(200, json={
                "tags": [
                    {"tag": t, "tag_key": t.lower(), "count": c}
                    for t, c in counts.items()
                ]
            })
        if path.startswith("/api/v1/library/cards/"):
            character_id = path.rsplit("/", 2)[-2] if path.endswith(
                ("/tags", "/favourite", "/organisation")
            ) else path.rsplit("/", 1)[-1]
            row = self.rows.get(character_id)
            if row is None or row["deleted"]:
                return httpx.Response(404, json={"detail": "not found"})
            org = self._org(row)
            if path.endswith("/organisation"):
                return httpx.Response(200, json=dict(org))
            if path.endswith("/tags") and method in ("PUT", "POST"):
                tags = list(body.get("tags", []))
                org["tags"] = tags
                row["card"]["data"]["tags"] = tags
                return httpx.Response(200, json=dict(org))
            if path.endswith("/favourite") and method == "PUT":
                org["is_favourite"] = bool(body.get("is_favourite"))
                return httpx.Response(200, json=dict(org))
        if path.startswith("/api/v1/characters/"):
            rest = path[len("/api/v1/characters/"):]
            character_id, _, tail = rest.partition("/")
            row = self.rows.get(character_id)
            return self._character_road(request, row, character_id, tail, body)
        return httpx.Response(404, json={"detail": "not found"})

    def _character_road(self, request, row, character_id, tail, body):
        method = request.method
        if tail == "restore" and method == "POST":
            if row is None:
                return httpx.Response(404, json={"detail": "not found"})
            if not row["deleted"]:
                return httpx.Response(409, json={"detail": "not deleted"})
            row["deleted"] = False
            return httpx.Response(200, json=self._summary(row))
        if row is None or row["deleted"]:
            return httpx.Response(404, json={"detail": "character not found"})
        if tail == "" and method == "GET":
            return httpx.Response(200, json=self._summary(row))
        if tail == "" and method == "PATCH":
            if "card" in body and body["card"] is not None:
                card = body["card"]
                row["card"] = (
                    card if "data" in card else wrapped(card)
                )
            if body.get("name"):
                row["name"] = body["name"]
                row["card"]["data"]["name"] = body["name"]
            return httpx.Response(200, json=self._summary(row))
        if tail == "" and method == "DELETE":
            row["deleted"] = True
            return httpx.Response(
                200, json={"deleted": True, "id": character_id, "undoable": True}
            )
        if tail == "duplicate" and method == "POST":
            clone, _ = self._create(
                dict(row["card"]["data"]), f"{row['name']} (copy)"
            )
            clone["avatar"] = row["avatar"]
            return httpx.Response(201, json=self._summary(clone))
        if tail == "versions" and method == "GET":
            lineage = [
                r for r in self.rows.values()
                if r["lineage_id"] == row["lineage_id"]
            ]
            lineage.sort(key=lambda r: r["version_no"])
            latest = max(r["version_no"] for r in lineage if not r["deleted"])
            return httpx.Response(200, json={
                "character_id": row["id"],
                "lineage_id": row["lineage_id"],
                "name": row["name"],
                "latest_version_no": latest,
                "versions": [
                    {
                        "character_id": r["id"], "name": r["name"],
                        "version_no": r["version_no"],
                        "lineage_id": r["lineage_id"],
                        "content_hash": "x" * 64,
                        "created_at": "2026-11-14T00:00:00+00:00",
                        "deleted": r["deleted"],
                        "is_latest": r["version_no"] == latest,
                    }
                    for r in lineage
                ],
            })
        if tail.startswith("versions/") and method == "GET":
            version_no = int(tail.split("/")[1])
            target = next(
                (
                    r for r in self.rows.values()
                    if r["lineage_id"] == row["lineage_id"]
                    and r["version_no"] == version_no
                ),
                None,
            )
            if target is None:
                return httpx.Response(404, json={"detail": "version not found"})
            return httpx.Response(200, json={
                "character_id": target["id"], "name": target["name"],
                "version_no": target["version_no"],
                "lineage_id": target["lineage_id"],
                "content_hash": "x" * 64,
                "created_at": "2026-11-14T00:00:00+00:00",
                "deleted": target["deleted"], "is_latest": False,
                "card": target["card"],
            })
        if tail == "avatar":
            if method == "POST":
                names = re.findall(rb'filename="([^"]+)"', request.content)
                filename = names[0].decode() if names else "avatar.png"
                row["avatar"] = filename
                self.avatar_bytes[character_id] = PNG_BYTES
                return httpx.Response(200, json={"filename": filename})
            if row["avatar"] is None:
                return httpx.Response(404, json={"detail": "avatar not found"})
            return httpx.Response(
                200, content=self.avatar_bytes[character_id],
                headers={"content-type": "image/png"},
            )
        if tail == "assets":
            if method == "GET":
                return httpx.Response(200, json=self.assets[character_id])
            names = re.findall(rb'filename="([^"]+)"', request.content)
            filename = names[0].decode() if names else "asset.bin"
            asset = {
                "id": self._id("a"), "character_id": character_id,
                "kind": "embedded", "name": filename,
                "source_type": "", "status": "stored", "format": "",
                "media_type": "", "width": None, "height": None,
                "byte_size": len(request.content),
                "has_thumbnail": False, "thumbnail_status": "not_applicable",
            }
            self.assets[character_id].append(asset)
            return httpx.Response(201, json=asset)
        if tail.startswith("assets/") and tail.endswith("/content"):
            return httpx.Response(200, content=b"asset-bytes")
        if tail == "character-book":
            book = row["card"]["data"].get("character_book")
            return httpx.Response(
                200, json=book if isinstance(book, dict) else {"entries": []}
            )
        if tail == "lorebook-binding":
            if method == "GET":
                binding = self.bindings.get(character_id)
                if binding is None:
                    return httpx.Response(
                        200, json={"bound": False, "character_id": character_id}
                    )
                return httpx.Response(200, json=binding)
            if method == "PUT":
                book = self.lorebooks[body["lorebook_id"]]
                binding = {
                    "bound": True, "character_id": character_id,
                    "lorebook_id": book["id"],
                    "precedence": body.get("precedence"),
                    "entry_count": book["entry_count"],
                    "lorebook": {"name": book["name"]},
                }
                self.bindings[character_id] = binding
                return httpx.Response(200, json=binding)
            if method == "PATCH":
                self.bindings[character_id]["precedence"] = body["precedence"]
                return httpx.Response(200, json=self.bindings[character_id])
            if method == "DELETE":
                if character_id not in self.bindings:
                    return httpx.Response(404, json={"detail": "no bound lorebook"})
                del self.bindings[character_id]
                return httpx.Response(200, json={"unbound": True})
        return httpx.Response(404, json={"detail": "not found"})


def make_flow(engine: FakeEngine | None = None):
    engine = engine or FakeEngine()
    session = DesktopSession("http://127.0.0.1:9", bearer_token=TOKEN)
    http = httpx.Client(
        base_url="http://127.0.0.1:9",
        transport=httpx.MockTransport(engine),
        trust_env=False,
    )
    client = RunmalClient(session, http=http)
    return CharacterFlow(client), client, engine


def seed_keeper(engine: FakeEngine) -> dict:
    return engine.seed({
        "name": "Gate Keeper",
        "description": "Guards the high pass.",
        "personality": "Calm, dry, kind.",
        "scenario": "A mountain pass.",
        "system_prompt": "You guard the pass.",
        "mes_example": "<START>\nKeeper: State your name.",
        "post_history_instructions": "Stay terse.",
        "first_mes": "Well met, traveller.",
        "alternate_greetings": ["Well met. State your name."],
        "creator_notes": "A test keeper.",
        "tags": ["guard", "pass"],
        "creator": "Yrsa",
        "character_version": "1.0",
        "nickname": "Keeper",
        "character_book": {"entries": [{"name": "The Pass"}]},
        "extensions": {"custom_flag": True},
    })


# ------------------------------------------------------------ pure helpers


def test_parse_tags_dedupes_and_trims() -> None:
    assert parse_tags(" guard, pass ,, guard\nkeeper ") == [
        "guard", "pass", "keeper",
    ]
    assert parse_tags("") == []


def test_apply_card_edits_overlays_data_level_and_preserves_unknowns() -> None:
    raw = wrapped({
        "name": "Gate Keeper",
        "description": "Old.",
        "extensions": {"custom_flag": True},
        "mystery_field": {"keep": [1, 2]},
    })
    raw["top_unknown"] = "stays"
    edited = apply_card_edits(raw, {"description": "New."})
    assert edited["data"]["description"] == "New."
    assert edited["data"]["extensions"] == {"custom_flag": True}
    assert edited["data"]["mystery_field"] == {"keep": [1, 2]}
    assert edited["top_unknown"] == "stays"
    assert raw["data"]["description"] == "Old."  # input untouched

    flat = {"name": "Flat", "description": "Old."}
    edited_flat = apply_card_edits(flat, {"description": "New."})
    assert edited_flat == {"name": "Flat", "description": "New."}


# ------------------------------------------------------------ the flow


def test_full_card_read_joins_summary_and_version_road() -> None:
    flow, client, engine = make_flow()
    row = seed_keeper(engine)
    card = client.get_character_card(row["id"])
    assert card.name == "Gate Keeper"
    assert card.description == "Guards the high pass."
    assert card.system_prompt == "You guard the pass."
    assert card.alternate_greetings == ["Well met. State your name."]
    assert card.tags == ["guard", "pass"]
    assert card.book_entry_count == 1
    assert card.raw_card["data"]["extensions"] == {"custom_flag": True}


def test_create_from_scratch_then_tags_road() -> None:
    flow, client, engine = make_flow()
    edits = {
        "name": "Ferryman",
        "description": "Rows the black river.",
        "personality": "Silent.",
        "first_mes": "Coin first.",
        "alternate_greetings": [],
    }
    created = flow.create_character(edits, ["river", "guide"])
    assert created.name == "Ferryman"
    card = client.get_character_card(created.id)
    assert card.description == "Rows the black river."
    assert card.first_mes == "Coin first."
    assert flow.organisation(created.id).tags == ["river", "guide"]
    with pytest.raises(ClientError):
        flow.create_character({"name": "  "}, [])


def test_save_overlays_and_syncs_tags_only_via_organisation() -> None:
    flow, client, engine = make_flow()
    row = seed_keeper(engine)
    bundle = flow.open_editor(row["id"])
    new_edits = {
        "name": "Gate Keeper",
        "description": "Now guards the LOW pass.",
        "personality": bundle.card.personality,
        "scenario": bundle.card.scenario,
        "system_prompt": bundle.card.system_prompt,
        "mes_example": bundle.card.mes_example,
        "post_history_instructions": bundle.card.post_history_instructions,
        "first_mes": bundle.card.first_mes,
        "creator_notes": bundle.card.creator_notes,
        "creator": bundle.card.creator,
        "character_version": "2.0",
        "nickname": bundle.card.nickname,
        "alternate_greetings": ["Halt. Name and business."],
    }
    saved = flow.save_character(bundle.card, new_edits, ["guard", "low-pass"])
    assert saved.description == "Now guards the LOW pass."
    assert saved.character_version == "2.0"
    assert saved.alternate_greetings == ["Halt. Name and business."]
    # Unknown fields survived the round trip (INV-009).
    assert saved.raw_card["data"]["extensions"] == {"custom_flag": True}
    assert saved.raw_card["data"]["character_book"]["entries"][0]["name"] == "The Pass"
    # Tags moved through the organisation road.
    assert flow.organisation(row["id"]).tags == ["guard", "low-pass"]


def test_library_search_tags_and_favourites() -> None:
    flow, _client, engine = make_flow()
    keeper = seed_keeper(engine)
    engine.seed({"name": "Ferryman", "description": "Rows.", "tags": ["river"]})
    total, items = flow.library()
    assert total == 2
    total, items = flow.library(q="pass")
    assert [i.name for i in items] == ["Gate Keeper"]
    assert "★ favourite" not in items[0].label
    flow.set_favourite(keeper["id"], True)
    total, items = flow.library(favourites_only=True)
    assert [i.name for i in items] == ["Gate Keeper"]
    assert "★ favourite" in items[0].label
    assert {t.tag for t in flow.library_tags()} == {"guard", "pass", "river"}


def test_editor_bundle_binding_assets_versions() -> None:
    flow, client, engine = make_flow()
    row = seed_keeper(engine)
    bundle = flow.open_editor(row["id"])
    assert bundle.book_entry_count == 1
    assert bundle.binding.bound is False
    bound = flow.bind(row["id"], "lb1", precedence="character_first")
    assert bound.bound is True and bound.lorebook_name == "Pass Lore"
    assert flow._client.get_lorebook_binding(row["id"]).precedence == "character_first"
    changed = flow.set_precedence(row["id"], "world_first")
    assert changed.precedence == "world_first"
    assert flow.unbind(row["id"]) is True
    assert flow._client.get_lorebook_binding(row["id"]).bound is False

    stored = flow.set_avatar(row["id"], "keeper.png", PNG_BYTES)
    assert stored == "keeper.png"
    data, media = flow.avatar_bytes(row["id"])
    assert data == PNG_BYTES and media == "image/png"
    asset = flow.add_asset(row["id"], "map.png", PNG_BYTES)
    assert asset.name == "map.png"
    assert [a.id for a in flow.assets(row["id"])] == [asset.id]


def test_versions_and_composed_restore() -> None:
    flow, client, engine = make_flow()
    v1 = seed_keeper(engine)
    # A second, different card under the same name = version 2.
    v2, duplicate = engine._create(
        {**v1["card"]["data"], "description": "Second telling."},
        "Gate Keeper",
    )
    assert duplicate is False and v2["version_no"] == 2
    history = flow.versions(v1["id"])
    assert history.latest_version_no == 2
    assert [v.version_no for v in history.versions] == [1, 2]
    # Restore v1's card onto the v2 row.
    restored = flow.restore_version(v2["id"], 1)
    assert restored.description == "Guards the high pass."


def test_duplicate_delete_undo_export_import() -> None:
    flow, client, engine = make_flow()
    row = seed_keeper(engine)
    clone = flow.duplicate(row["id"])
    assert clone.id != row["id"] and clone.name == "Gate Keeper (copy)"

    text = flow.export_text(row["id"])
    document = json.loads(text)
    assert document["data"]["name"] == "Gate Keeper"

    assert flow.delete(row["id"]) is True
    assert client.list_characters() == [
        c for c in client.list_characters() if c.id != row["id"]
    ]
    restored = flow.undo_delete(row["id"])
    assert restored.id == row["id"]

    outcome = flow.import_files([("river-guide.json", b"{}")])
    assert outcome.accepted == 1 and outcome.created_ids
    assert "1 character(s) landed" in outcome.status_words
    assert any("imported as" in line for line in outcome.lines)
    again = flow.import_files([("river-guide.json", b"{}")])
    assert again.accepted == 0  # exact duplicate is data, not a new row


def test_client_layer_stays_qt_free() -> None:
    result = subprocess.run(
        [
            sys.executable, "-c",
            "import runmal.desktop.character_logic, runmal.desktop.client; "
            "import sys; assert 'PySide6' not in sys.modules",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
