"""P-168 Part X gate battery: Faces That Speak, whole.

Gate discipline (P-030 / P-048 / P-064 / P-080 / P-100 /
P-116 / P-130 / P-154 pattern): the gate builds no new
behaviour; it judges the banked Part X slices
(P-155..P-166) end to end through their own public
contracts, from measured evidence only, and accounts
for P-167 - banking in parallel from team-02 commit
c18d1e38, NOT in this base - by overlay: its committed
module is loaded read-only from the team-02 worktree
and reconciled against the in-base P-164 census and
P-166 board (the P-116 / P-154 precedent). Part X's
slice definitions are DERIVED (the filed roadmap gives
Part X only its part line, "X | Faces That Speak |
P-155 - P-168"); the census this gate judges is the
one the banked slice docs declare.

- Area A (census): every P-155..P-166 faces surface is
  present - modules, resolver functions, schema names
  (each accounted exactly once), HTTP roads, the faces
  __init__ module map, the slice docs - and app OpenAPI
  generation succeeds and names the faces roads. The
  P-167 road is honestly ABSENT on this base and named
  as the merged shape (13 roads after P-167 banks).
- Area B (together): one composed world exercises
  presentation + roster + speaking + history +
  censuses over the same characters and chats; the
  face a chat shows agrees in every document that
  names it, the voice a character speaks in agrees in
  every pairing that states it, census counts sum
  from the boards they compose, history rows reconcile
  across the per-chat, per-character and per-owner
  documents, and the P-167 overlay census reconciles
  row for row with the in-base P-164 census plus each
  character's own voice.
- Area C (custody / honesty): the laws hold as shipped
  - no voice key in any silent document (P-158 /
  P-162 / P-164 / P-165 and their silent siblings),
  voice current_only wherever history is involved
  (P-161 / P-163), no census-level voice in the P-167
  overlay (the blur pin), no image bytes anywhere
  (P-023 URLs as data only), no text scanning (P-092),
  no playback (P-027), and every resolve a pure read.
- Area D (accounting): every Part X carried item is
  named and pinned by measurement - the owner
  speaking-history census stays OPEN and unmade on
  both shapes, no renderer / stage / lip-sync surface
  exists anywhere in Part X (data only, by design),
  the P-109 affect rides consumed:False in every
  voice-bearing document, the kept window is named
  honestly, and the paired flags follow their law.
- Hygiene: migration head stays 0041; the gate world
  (ZqxGate168) lives only in this battery.

Clean-room note: the gate world is fresh-authored for
this gate (P-005 discipline); no SillyTavern or Voxta
source was inspected, and no real user files are read.
Plain pytest functions, no test classes.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.assets import service as assets_svc
from runmal.auth import get_or_create_credential
from runmal.characters import service as characters_svc
from runmal.chats import service as chats_svc
from runmal.chats.greetings import GreetingChoice
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.faces import census as census_mod
from runmal.faces import character_history as char_hist_mod
from runmal.faces import character_speaking_history as csh_mod
from runmal.faces import chats as chats_mod
from runmal.faces import history as history_mod
from runmal.faces import history_census as hist_census_mod
from runmal.faces import presentation as presentation_mod
from runmal.faces import roster as roster_mod
from runmal.faces import speaking as speaking_mod
from runmal.faces import speaking_chats as speaking_chats_mod
from runmal.faces import speaking_history as speaking_hist_mod
from runmal.faces import speaking_roster as speaking_roster_mod
from runmal.plugins import expressions as ex
from runmal.plugins import service as plugin_service
from runmal.plugins.image_generation import render_deterministic_png
from runmal.voice import profiles as voice_profiles

REPO = Path(__file__).parent.parent
Z = "ZqxGate168"
TEAM02 = Path.home() / "runmal-team-02"
PNG_BYTES = render_deterministic_png("gate sprite seed", "", 1, 32)

SCHEMAS = {
    "P-155": "runmal-p155-face-presentation-v1",
    "P-156": "runmal-p156-character-face-roster-v1",
    "P-157": "runmal-p157-speaking-face-v1",
    "P-158": "runmal-p158-face-history-v1",
    "P-159": "runmal-p159-speaking-roster-v1",
    "P-160": "runmal-p160-character-face-chats-v1",
    "P-161": "runmal-p161-speaking-history-v1",
    "P-162": "runmal-p162-character-face-history-v1",
    "P-163": "runmal-p163-character-speaking-history-v1",
    "P-164": "runmal-p164-face-census-v1",
    "P-165": "runmal-p165-face-history-census-v1",
    "P-166": "runmal-p166-character-speaking-chats-v1",
}
OVERLAY_SCHEMA = "runmal-p167-face-speaking-census-v1"

ROADS = {
    "/faces/presentation", "/faces/roster", "/faces/speaking",
    "/faces/history", "/faces/speaking-roster", "/faces/chats",
    "/faces/speaking-history", "/faces/character-history",
    "/faces/character-speaking-history", "/faces/census",
    "/faces/history-census", "/faces/speaking-chats",
}
OVERLAY_ROAD = "/faces/speaking-census"


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


def card_dict(name):
    return {
        "spec": "chara_card_v2", "spec_version": "2.0", "name": name,
        "description": "A keeper of the northern lighthouse.",
        "personality": "Steady.", "scenario": "A test hall.",
        "first_mes": "Hail!", "mes_example": "", "creator_notes": "",
        "system_prompt": "", "post_history_instructions": "",
        "alternate_greetings": [], "tags": [], "creator": "forge",
        "character_version": "1.0",
    }


async def seed_character(factory, uid, name):
    async with factory() as session:
        character = await characters_svc.create_character(
            session, uid, card_dict(name))
        await session.commit()
        return character.id


async def seed_chat(factory, uid, character_id, title):
    async with factory() as session:
        chat = await chats_svc.create_chat(
            session, uid, title=title, character_id=character_id,
            greeting=GreetingChoice(mode="quiet"))
        await session.commit()
        return chat.id


async def _add_asset(factory, uid, cid, *, kind, name):
    async with factory() as session:
        asset = await assets_svc.add_asset(
            session, uid, cid, kind=kind, name=name,
            filename=f"{name.replace(' ', '_')}.png", data=PNG_BYTES)
        return asset.id


async def _world(factory, uid):
    """The gate world: two characters, four chats.

    Asta (ZqxGate168): set neutral (unbound) / amused
    (bound sprite) / wrong (wrong-kind asset), default
    amused, and a stored voice profile whose affect is
    whispering. Bera: set smile (bound), default smile,
    and NO voice profile (the default voice). Chats:
    Asta-ready selects amused, Asta-unbound selects
    neutral, Asta-quiet selects nothing, Bera-ready
    selects smile. Selections are P-092 explicit acts;
    they are also the kept history the history
    documents judge.
    """
    asta = await seed_character(factory, uid, "Asta" + Z)
    bound = await _add_asset(factory, uid, asta, kind="expression",
                             name="amused")
    bg = await _add_asset(factory, uid, asta, kind="background",
                          name="stairs")
    ex.create_set(uid, {
        "character_id": asta,
        "entries": [
            {"name": "neutral", "label": "Neutral"},
            {"name": "amused", "label": "Amused", "asset_id": bound},
            {"name": "wrong", "label": "Wrong", "asset_id": bg},
        ],
        "default": "amused",
    })
    bera = await seed_character(factory, uid, "Bera" + Z)
    smile = await _add_asset(factory, uid, bera, kind="expression",
                             name="smile")
    ex.create_set(uid, {
        "character_id": bera,
        "entries": [
            {"name": "smile", "label": "Smile", "asset_id": smile},
        ],
        "default": "smile",
    })
    ready = await seed_chat(factory, uid, asta, "Asta ready")
    unbound = await seed_chat(factory, uid, asta, "Asta unbound")
    quiet = await seed_chat(factory, uid, asta, "Asta quiet")
    bera_chat = await seed_chat(factory, uid, bera, "Bera ready")
    async with factory() as session:
        await ex.select_for_chat(session, uid, ready, "amused")
        await ex.select_for_chat(session, uid, unbound, "neutral")
        await ex.select_for_chat(session, uid, bera_chat, "smile")
        await voice_profiles.set_character_voice(
            session, uid, asta, tts_backend="fake-tts",
            voice_id="narrator-1", language="en-gb",
            params={"affect": "whispering", "prompt_text": "Hush."})
    return {
        "asta": asta, "bera": bera, "ready": ready,
        "unbound": unbound, "quiet": quiet, "bera_chat": bera_chat,
    }


def _keys(node, acc=None):
    if acc is None:
        acc = set()
    if isinstance(node, dict):
        for key, value in node.items():
            acc.add(key)
            _keys(value, acc)
    elif isinstance(node, list):
        for item in node:
            _keys(item, acc)
    return acc


def _has_bytes(node):
    if isinstance(node, (bytes, bytearray)):
        return True
    if isinstance(node, dict):
        return any(_has_bytes(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_bytes(v) for v in node)
    return False


async def _docs(factory, uid, w):
    """Every in-base Part X document over the gate world."""
    async with factory() as session:
        out = {}
        out["presentation"] = await presentation_mod.resolve_presentation(
            session, uid, w["ready"])
        out["roster"] = await roster_mod.resolve_character_roster(
            session, uid, w["asta"])
        out["speaking"] = await speaking_mod.resolve_speaking_face(
            session, uid, w["ready"])
        out["history"] = await history_mod.resolve_face_history(
            session, uid, w["ready"])
        out["speaking_roster"] = (
            await speaking_roster_mod.resolve_character_speaking_roster(
                session, uid, w["asta"]))
        out["chats"] = await chats_mod.resolve_character_face_chats(
            session, uid, w["asta"])
        out["speaking_history"] = (
            await speaking_hist_mod.resolve_speaking_history(
                session, uid, w["ready"]))
        out["char_history"] = (
            await char_hist_mod.resolve_character_face_history(
                session, uid, w["asta"]))
        out["csh"] = await csh_mod.resolve_character_speaking_history(
            session, uid, w["asta"])
        out["census"] = await census_mod.resolve_face_census(
            session, uid)
        out["hist_census"] = await hist_census_mod.resolve_face_history_census(
            session, uid)
        out["speaking_chats"] = (
            await speaking_chats_mod.resolve_character_speaking_chats(
                session, uid, w["asta"]))
        out["bera_chats"] = await chats_mod.resolve_character_face_chats(
            session, uid, w["bera"])
        out["bera_speaking_chats"] = (
            await speaking_chats_mod.resolve_character_speaking_chats(
                session, uid, w["bera"]))
        return out


def _load_overlay():
    path = TEAM02 / "src" / "runmal" / "faces" / "speaking_census.py"
    assert path.exists(), "P-167 overlay module missing on team-02"
    spec = importlib.util.spec_from_file_location(
        "p167_speaking_census_overlay", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- Area A: the Part X census is present -------------------


def test_a_face_modules_and_services_present():
    expected = {
        presentation_mod: ("resolve_presentation", "PRESENTATION_SCHEMA"),
        roster_mod: ("resolve_character_roster", "ROSTER_SCHEMA"),
        speaking_mod: ("resolve_speaking_face", "SPEAKING_SCHEMA"),
        history_mod: ("resolve_face_history", "HISTORY_SCHEMA"),
        speaking_roster_mod: (
            "resolve_character_speaking_roster", "SPEAKING_ROSTER_SCHEMA"),
        chats_mod: ("resolve_character_face_chats", "CHATS_SCHEMA"),
        speaking_hist_mod: (
            "resolve_speaking_history", "SPEAKING_HISTORY_SCHEMA"),
        char_hist_mod: (
            "resolve_character_face_history", "CHARACTER_HISTORY_SCHEMA"),
        csh_mod: ("resolve_character_speaking_history",
                  "CHARACTER_SPEAKING_HISTORY_SCHEMA"),
        census_mod: ("resolve_face_census", "CENSUS_SCHEMA"),
        hist_census_mod: (
            "resolve_face_history_census", "HISTORY_CENSUS_SCHEMA"),
        speaking_chats_mod: (
            "resolve_character_speaking_chats", "SPEAKING_CHATS_SCHEMA"),
    }
    assert len(expected) == 12
    for module, (resolver, schema_name) in expected.items():
        assert callable(getattr(module, resolver)), module.__name__
        assert isinstance(getattr(module, schema_name), str)
        assert len(getattr(module, "NOTES")) == 5, module.__name__
    # Merged shape, pinned honestly (keeper heal at P-168 banking): the P-167 speaking-census
    # module IS in the merged tree; it arrived with P-167's
    # banking (the overlay shape, Area B, was its base shape).
    assert importlib.util.find_spec(
        "runmal.faces.speaking_census") is not None
    faces_dir = REPO / "src" / "runmal" / "faces"
    assert (faces_dir / "speaking_census.py").exists()
    assert (faces_dir / "speaking_census_router.py").exists()


def test_a_schemas_exact_and_accounted_once():
    mods = [presentation_mod, roster_mod, speaking_mod, history_mod,
            speaking_roster_mod, chats_mod, speaking_hist_mod,
            char_hist_mod, csh_mod, census_mod, hist_census_mod,
            speaking_chats_mod]
    names = ["PRESENTATION_SCHEMA", "ROSTER_SCHEMA", "SPEAKING_SCHEMA",
             "HISTORY_SCHEMA", "SPEAKING_ROSTER_SCHEMA", "CHATS_SCHEMA",
             "SPEAKING_HISTORY_SCHEMA", "CHARACTER_HISTORY_SCHEMA",
             "CHARACTER_SPEAKING_HISTORY_SCHEMA", "CENSUS_SCHEMA",
             "HISTORY_CENSUS_SCHEMA", "SPEAKING_CHATS_SCHEMA"]
    values = [getattr(m, n) for m, n in zip(mods, names)]
    assert sorted(values) == sorted(SCHEMAS.values())
    assert len(set(values)) == 12
    faces_src = ""
    for path in (REPO / "src" / "runmal" / "faces").glob("*.py"):
        faces_src += path.read_text(encoding="utf-8")
    for value in list(SCHEMAS.values()) + [OVERLAY_SCHEMA]:
        if value == OVERLAY_SCHEMA:
            assert faces_src.count(value) == 1  # merged shape: P-167 banked, keeper heal
        else:
            assert faces_src.count(value) == 1, value


def test_a_http_roads_present_base_shape():
    import runmal.faces.census_router as census_router
    import runmal.faces.character_history_router as ch_router
    import runmal.faces.character_speaking_history_router as csh_router
    import runmal.faces.chats_router as chats_router
    import runmal.faces.history_census_router as hc_router
    import runmal.faces.history_router as history_router
    import runmal.faces.roster_router as roster_router
    import runmal.faces.router as presentation_router
    import runmal.faces.speaking_chats_router as sc_router
    import runmal.faces.speaking_history_router as sh_router
    import runmal.faces.speaking_roster_router as sr_router
    import runmal.faces.speaking_router as speaking_router
    import runmal.faces.speaking_census_router as sfc_router
    routers = [presentation_router, roster_router, speaking_router,
               history_router, sr_router, chats_router, sh_router,
               ch_router, csh_router, census_router, hc_router,
               sc_router, sfc_router]
    paths = set()
    for module in routers:
        for route in module.router.routes:
            paths.add(route.path)
    assert paths == ROADS | {OVERLAY_ROAD}
    assert len(paths) == 13
    assert OVERLAY_ROAD in paths


def test_a_module_map_slice_docs_and_part_line():
    import runmal.faces as faces_pkg
    for name in faces_pkg.__all__:
        assert hasattr(faces_pkg, name), name
    for resolver in ("resolve_presentation", "resolve_character_roster",
                     "resolve_speaking_face", "resolve_face_history",
                     "resolve_character_speaking_roster",
                     "resolve_character_face_chats",
                     "resolve_speaking_history",
                     "resolve_character_face_history",
                     "resolve_character_speaking_history",
                     "resolve_face_census", "resolve_face_history_census",
                     "resolve_character_speaking_chats"):
        assert resolver in faces_pkg.__all__, resolver
    assert "resolve_face_speaking_census" in faces_pkg.__all__
    docs = {
        "FACE_PRESENTATION_2026-11-08.md",
        "CHARACTER_FACE_ROSTER_2026-11-08.md",
        "SPEAKING_FACE_2026-11-08.md",
        "FACE_HISTORY_2026-11-08.md",
        "SPEAKING_ROSTER_2026-11-08.md",
        "CHARACTER_FACE_CHATS_2026-11-08.md",
        "SPEAKING_HISTORY_2026-11-08.md",
        "CHARACTER_FACE_HISTORY_2026-11-08.md",
        "CHARACTER_SPEAKING_HISTORY_2026-11-08.md",
        "FACE_CENSUS_2026-11-08.md",
        "FACE_HISTORY_CENSUS_2026-11-08.md",
        "CHARACTER_SPEAKING_CHATS_2026-11-08.md",
    }
    for name in docs:
        assert (REPO / "docs" / name).exists(), name
    assert (REPO / "docs" / "FACE_SPEAKING_CENSUS_2026-11-08.md").exists()
    assert (TEAM02 / "docs" / "FACE_SPEAKING_CENSUS_2026-11-08.md").exists()
    roadmap = (REPO / "docs"
               / "RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md"
               ).read_text(encoding="utf-8")
    assert "Faces That Speak" in roadmap
    assert "P-155" in roadmap and "P-168" in roadmap


def test_a_openapi_succeeds_and_names_face_roads(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    paths = set(spec.json()["paths"])
    for road in ROADS:
        assert f"/api/v1{road}" in paths, road
    # Merged shape: 13 faces roads; the 13th arrived with P-167 (keeper heal).
    assert f"/api/v1{OVERLAY_ROAD}" in paths


# -- Area B: the citizens compose ---------------------------


async def test_b_one_chat_face_agrees_everywhere(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    w = await _world(factory, uid)
    docs = await _docs(factory, uid, w)
    face = docs["presentation"]["face"]
    assert docs["presentation"]["state"] == "ready"
    assert face is not None and face["name"] == "amused"
    assert face["renderable"] is True and face["bound"] is True
    # The speaking document names the same face.
    assert docs["speaking"]["face"] == face
    assert docs["speaking"]["state"] == "ready"
    # The chats board row for the chat names the same face.
    board_row = next(r for r in docs["chats"]["chats"]
                     if r["chat_id"] == w["ready"])
    assert board_row["face"] == face
    assert board_row["presentation_state"] == "ready"
    # The speaking-chats board composes the same board whole.
    assert docs["speaking_chats"]["chats"] == docs["chats"]["chats"]
    # The census row for Asta carries the same board rows whole.
    census_row = next(r for r in docs["census"]["characters"]
                      if r["character_id"] == w["asta"])
    assert census_row["chats"] == docs["chats"]["chats"]
    assert census_row["board_state"] == docs["chats"]["state"]
    # History judges the same selection still ready, same descriptor.
    event = docs["history"]["events"][0]
    assert event["entry_state"] == "still_ready"
    assert event["descriptor"] == face


async def test_b_roster_composes_with_presentation(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    w = await _world(factory, uid)
    docs = await _docs(factory, uid, w)
    roster = docs["roster"]
    assert roster["entries"] == docs["presentation"]["entries"]
    assert roster["entry_count"] == 3
    assert roster["renderable_count"] == 1
    assert roster["selection_scope"] == "per_chat"
    # The roster is chat-less: it names no current face.
    assert "face" not in roster and "current" not in roster
    # The speaking roster composes the same roster whole.
    sr = docs["speaking_roster"]
    for key in ("state", "set", "entries", "entry_count", "bound_count",
                "renderable_count", "unbound_count", "selection_scope",
                "default_entry", "avatar"):
        assert sr[key] == roster[key], key


async def test_b_boards_and_censuses_reconcile(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    w = await _world(factory, uid)
    docs = await _docs(factory, uid, w)
    asta_board, bera_board = docs["chats"], docs["bera_chats"]
    assert (asta_board["chat_count"], asta_board["ready_count"],
            asta_board["selection_count"], asta_board["unbound_count"]) \
        == (3, 1, 2, 1)
    assert asta_board["state"] == "some_ready"
    assert (bera_board["chat_count"], bera_board["ready_count"]) == (1, 1)
    assert bera_board["state"] == "all_ready"
    census = docs["census"]
    assert census["state"] == "some_ready"
    counts = census["counts"]
    assert counts["character_count"] == 2
    assert counts["characters_with_chats_count"] == 2
    for key in ("chat_count", "ready_count", "selection_count",
                "unbound_count"):
        assert counts[key] == asta_board[key] + bera_board[key], key
    assert (counts["chat_count"], counts["ready_count"],
            counts["selection_count"], counts["unbound_count"]) \
        == (4, 2, 3, 1)
    bera_row = next(r for r in census["characters"]
                    if r["character_id"] == w["bera"])
    assert bera_row["chats"] == bera_board["chats"]
    assert bera_row["board_state"] == "all_ready"


async def test_b_history_documents_reconcile(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    w = await _world(factory, uid)
    docs = await _docs(factory, uid, w)
    history = docs["history"]
    assert history["event_count"] == 1
    assert history["still_ready_count"] == 1
    # The character history board carries the same chat row whole.
    board = docs["char_history"]
    assert board["state"] == "some_history"
    assert (board["event_count"], board["selection_count"],
            board["cleared_count"], board["still_ready_count"]) \
        == (2, 2, 0, 1)
    row = next(r for r in board["chats"] if r["chat_id"] == w["ready"])
    assert row["events"] == history["events"]
    assert row["event_count"] == history["event_count"]
    # The speaking history's history half is the same document.
    sh = docs["speaking_history"]
    for key in ("presentation_state", "current", "events", "event_count",
                "selection_count", "cleared_count", "still_ready_count",
                "kept_limit", "at_kept_limit"):
        assert sh[key] == history[key], key
    # The speaking-history board carries the same rows.
    csh_row = next(r for r in docs["csh"]["chats"]
                   if r["chat_id"] == w["ready"])
    assert csh_row["events"] == history["events"]
    # The history census sums the boards' own arithmetic.
    hc = docs["hist_census"]
    assert hc["state"] == "some_history"
    hcounts = hc["counts"]
    assert hcounts["character_count"] == 2
    assert hcounts["chat_count"] == 4
    assert hcounts["chats_with_history_count"] == 3
    assert (hcounts["event_count"], hcounts["selection_count"],
            hcounts["cleared_count"], hcounts["still_ready_count"]) \
        == (3, 3, 0, 2)
    hc_row = next(r for r in hc["characters"]
                  if r["character_id"] == w["asta"])
    assert hc_row["chats"] == board["chats"]
    assert hc_row["board_state"] == board["state"]


async def test_b_voice_agrees_across_every_pairing(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    w = await _world(factory, uid)
    docs = await _docs(factory, uid, w)
    voice = docs["speaking"]["voice"]
    assert voice["state"] == "profile"
    assert voice["voice_id"] == "narrator-1"
    assert voice["tts_backend"] == "fake-tts"
    for doc in (docs["speaking_roster"], docs["speaking_history"],
                docs["csh"], docs["speaking_chats"]):
        assert doc["voice"] == voice
        assert doc["paired"] is True
    assert docs["speaking"]["paired"] is True
    # Bera speaks in the default voice, stated once at board level.
    bera_voice = docs["bera_speaking_chats"]["voice"]
    assert bera_voice["state"] == "default_voice"
    assert bera_voice["profile_exists"] is False
    assert bera_voice["voice_id"] == voice_profiles.DEFAULT_VOICE.voice_id
    assert docs["bera_speaking_chats"]["paired"] is True
    assert bera_voice != voice


async def test_b_speaking_census_overlay_reconciles(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    w = await _world(factory, uid)
    docs = await _docs(factory, uid, w)
    overlay = _load_overlay()
    assert overlay.SPEAKING_CENSUS_SCHEMA == OVERLAY_SCHEMA
    async with factory() as session:
        census = await overlay.resolve_face_speaking_census(session, uid)
    assert census["schema"] == OVERLAY_SCHEMA
    assert census["state"] == docs["census"]["state"] == "some_ready"
    base_counts = docs["census"]["counts"]
    for key, value in base_counts.items():
        assert census["counts"][key] == value, key
    assert census["counts"]["paired_character_count"] == 2
    assert len(census["characters"]) == 2
    base_rows = {r["character_id"]: r
                 for r in docs["census"]["characters"]}
    for row in census["characters"]:
        base = base_rows[row["character_id"]]
        for key in ("character", "board_state", "chats", "chat_count",
                    "ready_count", "selection_count", "unbound_count"):
            assert row[key] == base[key], key
        assert row["paired"] is True
    asta_row = next(r for r in census["characters"]
                    if r["character_id"] == w["asta"])
    assert asta_row["voice"] == docs["speaking_chats"]["voice"]
    bera_row = next(r for r in census["characters"]
                    if r["character_id"] == w["bera"])
    assert bera_row["voice"] == docs["bera_speaking_chats"]["voice"]
    assert asta_row["voice"] != bera_row["voice"]
    # The overlay's own battery ships with it: 19 tests.
    battery = (TEAM02 / "tests" / "test_p167_face_speaking_census.py"
               ).read_text(encoding="utf-8")
    assert battery.count("def test") == 19


# -- Area C: custody and honesty hold as shipped ------------


async def test_c_silent_documents_carry_no_voice(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    w = await _world(factory, uid)
    docs = await _docs(factory, uid, w)
    silent = ("presentation", "roster", "history", "chats",
              "char_history", "census", "hist_census")
    for name in silent:
        keys = _keys(docs[name])
        assert "voice" not in keys, name
        assert "paired" not in keys, name
        assert "voice_scope" not in keys, name


async def test_c_history_pairings_are_current_only(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    w = await _world(factory, uid)
    docs = await _docs(factory, uid, w)
    for doc in (docs["speaking_history"], docs["csh"]):
        assert doc["voice_scope"] == "current_only"
        assert doc["voice"]["state"] == "profile"
    # No kept event or chat row anywhere carries a voice field:
    # S512 stores no voice history, so none can be claimed.
    for event in docs["speaking_history"]["events"]:
        assert "voice" not in event
    for row in docs["csh"]["chats"]:
        assert "voice" not in row
        for event in row["events"]:
            assert "voice" not in event
    # Current-only pairings carry no voice_scope: both halves
    # are current, so there is no past for a voice to dress.
    for doc in (docs["speaking"], docs["speaking_roster"],
                docs["speaking_chats"]):
        assert "voice_scope" not in doc
        assert "voice" in doc


async def test_c_speaking_census_blur_pin_overlay(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    w = await _world(factory, uid)
    overlay = _load_overlay()
    async with factory() as session:
        census = await overlay.resolve_face_speaking_census(session, uid)
    # The blur pin: voice lives inside character rows ONLY.
    assert set(census) == {"schema", "state", "characters",
                           "counts", "notes"}
    assert "voice" not in census and "paired" not in census
    assert "voice_scope" not in census and "face" not in census
    voice_counts = {k for k in census["counts"] if "voice" in k}
    assert voice_counts == set()
    assert census["counts"]["paired_character_count"] == 2
    for row in census["characters"]:
        assert "voice" in row and "paired" in row
        for chat_row in row["chats"]:
            assert "voice" not in chat_row
    assert len(census["notes"]) == 5


async def test_c_no_image_bytes_urls_are_data(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    w = await _world(factory, uid)
    docs = await _docs(factory, uid, w)
    for name, doc in docs.items():
        assert not _has_bytes(doc), name
        keys = _keys(doc)
        for forbidden in ("audio", "waveform", "lip_sync", "animation"):
            assert forbidden not in keys, (name, forbidden)
    face = docs["presentation"]["face"]
    assert face["content_url"].startswith("/api/v1/characters/")
    assert face["content_url"].endswith("/content")
    assert face["thumbnail_url"].endswith("/thumbnail")
    assert isinstance(face["content_url"], str)
    unbound_entry = next(e for e in docs["presentation"]["entries"]
                         if e["name"] == "neutral")
    assert unbound_entry["content_url"] is None
    assert unbound_entry["thumbnail_url"] is None
    assert unbound_entry["renderable"] is False


async def test_c_message_text_never_selects_a_face(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    w = await _world(factory, uid)
    async with factory() as session:
        await chats_svc.append_message(
            session, uid, w["quiet"], "user",
            "I feel amused, neutral, wrong and smile today.")
        await session.commit()
        doc = await presentation_mod.resolve_presentation(
            session, uid, w["quiet"])
        history = await history_mod.resolve_face_history(
            session, uid, w["quiet"])
    # P-092's law: selection is an explicit act; no text scan.
    assert doc["state"] == "no_selection"
    assert doc["face"] is None
    assert history["event_count"] == 0


async def test_c_resolves_are_pure_reads(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    w = await _world(factory, uid)
    store = ex.store_path(uid)
    before = store.read_bytes()
    async with factory() as session:
        row = await voice_profiles.get_character_voice(
            session, uid, w["asta"])
        voice_before = (row.tts_backend, row.voice_id, row.params_json)
    await _docs(factory, uid, w)
    overlay = _load_overlay()
    async with factory() as session:
        await overlay.resolve_face_speaking_census(session, uid)
        row = await voice_profiles.get_character_voice(
            session, uid, w["asta"])
        voice_after = (row.tts_backend, row.voice_id, row.params_json)
    assert store.read_bytes() == before
    assert voice_after == voice_before
    assert len(ex.list_history(uid, chat_id=w["ready"])) == 1


# -- Area D: carried items, named and pinned ----------------


async def test_d_affect_consumed_false_everywhere(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    w = await _world(factory, uid)
    docs = await _docs(factory, uid, w)
    voices = [docs["speaking"]["voice"], docs["speaking_roster"]["voice"],
              docs["speaking_history"]["voice"], docs["csh"]["voice"],
              docs["speaking_chats"]["voice"],
              docs["bera_speaking_chats"]["voice"]]
    overlay = _load_overlay()
    async with factory() as session:
        census = await overlay.resolve_face_speaking_census(session, uid)
    voices += [row["voice"] for row in census["characters"]]
    assert len(voices) == 8
    for voice in voices:
        # P-109: the affect is carried data, consumed False,
        # in every voice-bearing document Part X ships.
        assert voice["affect"]["consumed"] is False
    asta_affect = docs["speaking"]["voice"]["affect"]
    assert asta_affect["affect"] == "whispering"
    assert asta_affect["source"] == "profile"
    bera_affect = docs["bera_speaking_chats"]["voice"]["affect"]
    assert bera_affect["affect"] == "neutral"
    assert bera_affect["source"] == "default"


def test_d_owner_speaking_history_census_unmade():
    # The one unmade cell, on BOTH shapes: no module and no
    # road for an owner speaking-HISTORY census exists in
    # this base or in P-167's committed tree.
    assert importlib.util.find_spec(
        "runmal.faces.speaking_history_census") is None
    for root in (REPO, TEAM02):
        faces = root / "src" / "runmal" / "faces"
        assert not (faces / "speaking_history_census.py").exists()
        assert not (faces / "speaking_history_census_router.py").exists()
        app_src = (root / "src" / "runmal" / "app.py").read_text(
            encoding="utf-8")
        assert "speaking-history-census" not in app_src
    # P-167's own doc names it open for this gate to carry.
    p167_doc = (TEAM02 / "docs" / "FACE_SPEAKING_CENSUS_2026-11-08.md"
                ).read_text(encoding="utf-8")
    assert "speaking-history census" in p167_doc.lower()
    assert "OPEN" in p167_doc


def test_d_no_renderer_stage_or_lipsync_surface():
    faces_dir = REPO / "src" / "runmal" / "faces"
    names = sorted(p.name for p in faces_dir.glob("*.py"))
    expected = sorted([
        "__init__.py", "census.py", "census_router.py",
        "character_history.py", "character_history_router.py",
        "character_speaking_history.py",
        "character_speaking_history_router.py", "chats.py",
        "chats_router.py", "history.py", "history_census.py",
        "history_census_router.py", "history_router.py",
        "presentation.py", "roster.py", "roster_router.py",
        "router.py", "speaking.py", "speaking_census.py",
        "speaking_census_router.py", "speaking_chats.py",
        "speaking_chats_router.py", "speaking_history.py",
        "speaking_history_router.py", "speaking_roster.py",
        "speaking_roster_router.py", "speaking_router.py",
    ])
    # Data only, by design: the faces package is exactly the
    # thirteen services and their thirteen router modules (merged shape, keeper heal)'
    # ground - no renderer, stage, animation or lip-sync
    # module exists anywhere in Part X.
    assert names == expected
    for name in names:
        for banned in ("render", "stage", "lip", "anim", "play"):
            assert banned not in name, name


async def test_d_kept_window_named_honestly(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    w = await _world(factory, uid)
    docs = await _docs(factory, uid, w)
    assert docs["history"]["kept_limit"] == ex.MAX_HISTORY_KEPT == 100
    assert docs["history"]["at_kept_limit"] is False
    assert docs["char_history"]["kept_limit"] == 100
    # The history census states the per-chat law once and
    # never sums it into an owner window.
    assert docs["hist_census"]["kept_limit"] == 100
    assert "kept_limit" not in docs["hist_census"]["counts"]
    notes = " ".join(docs["history"]["notes"])
    assert "complete record" in notes


async def test_d_paired_flags_follow_their_law(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    w = await _world(factory, uid)
    docs = await _docs(factory, uid, w)
    # Asta's unbound chat shows a selection that is not ready:
    # its speaking document never pairs on an unready face.
    async with factory() as session:
        unbound_speaking = await speaking_mod.resolve_speaking_face(
            session, uid, w["unbound"])
        quiet_speaking = await speaking_mod.resolve_speaking_face(
            session, uid, w["quiet"])
    assert unbound_speaking["state"] == "current_unbound"
    assert unbound_speaking["face"] is None
    assert unbound_speaking["paired"] is False
    assert quiet_speaking["state"] == "no_selection"
    assert quiet_speaking["paired"] is False
    # Both still state the character's voice: pairing judges
    # the face half, it never hides the voice half.
    assert unbound_speaking["voice"] == docs["speaking"]["voice"]
    assert quiet_speaking["voice"] == docs["speaking"]["voice"]


# -- Hygiene -------------------------------------------------


def test_h_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    db_path = tmp_path / "gate.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"


def test_h_gate_world_lives_only_in_this_battery():
    hits = []
    for root in (REPO / "src", REPO / "tests"):
        for path in root.rglob("*.py"):
            if Z in path.read_text(encoding="utf-8", errors="ignore"):
                hits.append(path)
    assert hits == [Path(__file__)]
