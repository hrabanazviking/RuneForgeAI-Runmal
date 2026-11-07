"""P-048 acceptance (Part III GATE): cross-cutting inspector leg.

Roadmap line: *P-048 Part III gate -- the activation inspector
explains every firing across placement, scopes, vector match,
token accounting, RNG, scan windows, binding, packs, budget,
migration and the editor census (Areas A-D; this is Area D).*

Per-area contracts pinned here, all against the engine's real
surfaces (read from the code, not assumed):

- X-INS inspector (P-043): explanations == entries, every
  included row carries a reason in the inspector's included
  map and its kind's factual block; every other row carries a
  concrete reason code; facts_not_recorded is verbatim.
- X-PLC placement (P-038), X-SCO scopes (P-040), X-VEC vector
  match + keyword fallback (P-041), X-TOK token accounting
  (P-044), X-RNG probability determinism (P-036), X-WIN scan
  windows (P-037), X-BIND character-book binding (P-039),
  X-PACK sharing packs (P-045), X-PERF budget ceiling (P-046,
  light: no wall-clock), X-MIG upgrade (P-047, light),
  X-ED editor reach (P-042, light).

SPEC-vs-ENGINE adaptations (flagged, never silently weakened):
1. X-TOK-1: P-044's pinned contract is that with a counter the
   token_account recounts with the counter while preview rows
   and preview["tokens_used"] keep the budget-pass estimate
   (test_p044 test_preview_with_counter_exact_but_row_tokens_
   unchanged). A single equality chain across both regimes is
   therefore false in general; this leg asserts each regime's
   reconciliation separately, exactly as the engine keeps them.
2. X-VEC-2: scan_entries_windowed over RAW vectorised entries
   returns [] by design (the scanner skips vectorised kind);
   keyword_fallback_hits internally flips candidates to
   non-vectorised before scanning. Equality is asserted against
   the flipped scan -- the same entries/window, flipped kind --
   and the raw-scan emptiness is asserted as the reason.
3. X-PLC-1: the composer's baseline order places the persona
   (character definition) BEFORE lore_before, and an at_depth
   splice is measured from the end of the HISTORY, not the end
   of the whole prompt (an after_char message follows it).
   Index assertions pin that real ordering.
4. X-PACK-1: content_checksum() takes the NATIVE payload (it
   canonicalises internally); feeding it canonical_payload()'s
   dict would double-canonicalise. The checksum is asserted
   both as content_checksum(pack["lorebook"]) and as sha256 of
   the canonical bytes of canonical_payload(pack["lorebook"]).
5. X-WIN-1 DB leg: preview_activation takes caller-resolved
   settings (its own docstring); the stored-book leg resolves
   them with ScanSettings.from_book, the exact caller pattern
   prompt/inspect.py and scopes.layered_preview use.
6. Inspector's included-map code for via "vector_fallback" is
   "keyword_fallback" (inspector._INCLUDED_REASONS).
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import Character, Chat, User
from runmal.lorebooks import binding, editor, packs, scopes
from runmal.lorebooks import service as lore_service
from runmal.lorebooks import transfer, upgrade
from runmal.lorebooks.accounting import count_lore_tokens
from runmal.lorebooks.budget import BudgetCandidate, resolve_budget
from runmal.lorebooks.inspector import FACTS_NOT_RECORDED, inspect_activation
from runmal.lorebooks.placement import placement_for
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.rng import (
    derive_roll,
    explain_roll,
    probability_fraction,
    roll_probability,
)
from runmal.lorebooks.scan import (
    ScanEntry,
    scan_entries_windowed,
    scan_near_misses,
)
from runmal.lorebooks.service import entry_to_dict, lorebook_to_dict
from runmal.lorebooks.vector_match import (
    DEFAULT_VECTOR_THRESHOLD,
    LocalEmbeddingBackend,
    keyword_fallback_hits,
    match_vectorised_sync,
)
from runmal.lorebooks.windows import ScanSettings, build_scan_window
from runmal.prompt.composer import compose
from runmal.prompt.inspect import _lore_slot, inspect_prompt
from runmal.prompt.slots import make_slot
from runmal.tokens import estimate_tokens

SEED = 48048


def orm_entry(eid, name, content, keys=(), **kw):
    base = dict(
        id=eid, name=name, content=content, enabled=True, constant=False,
        vectorised=False, keys_json=json.dumps(list(keys)),
        secondary_keys_json="[]", whole_word=True, case_sensitive=False,
        selective_logic="and_any", sticky_prompts=0, cooldown_prompts=0,
        delay_prompts=0, inclusion_group="", group_weight=100,
        priority=100, probability=100, position="before_char",
        depth=None, role="system",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def gateworld():
    """One shared fresh-authored world: Gateworld."""
    return [
        orm_entry("gw-constant", "Always",
                  "The hall always hums beneath the stones.",
                  constant=True),
        orm_entry("gw-dragon", "Dragon",
                  "A dragon coils around the wyrm idol and breathes "
                  "warm smoke.", keys=("dragon",)),
        orm_entry("gw-wyrm", "Wyrm",
                  "The wyrm idol remembers old songs of the deep.",
                  keys=("wyrm",)),
        orm_entry("gw-gate-any", "GateAny",
                  "Iron-bound passage lore for travellers.",
                  keys=("gate",),
                  secondary_keys_json=json.dumps(["iron", "oak"]),
                  selective_logic="and_any"),
        orm_entry("gw-gate-all", "GateAll",
                  "Both timbers must answer before passage.",
                  keys=("gate",),
                  secondary_keys_json=json.dumps(["iron", "oak"]),
                  selective_logic="and_all"),
        orm_entry("gw-gate-notany", "GateNotAny",
                  "A passage barred when either timber shows.",
                  keys=("gate",),
                  secondary_keys_json=json.dumps(["iron", "oak"]),
                  selective_logic="not_any"),
        orm_entry("gw-gate-notall", "GateNotAll",
                  "A passage open unless both timbers show.",
                  keys=("gate",),
                  secondary_keys_json=json.dumps(["iron", "oak"]),
                  selective_logic="not_all"),
        orm_entry("gw-omen-a", "OmenA",
                  "First omen reading: ravens at dawn.",
                  keys=("omen",), inclusion_group="omens",
                  group_weight=100),
        orm_entry("gw-omen-b", "OmenB",
                  "Second omen reading: ravens at dusk.",
                  keys=("omen",), inclusion_group="omens",
                  group_weight=90),
        orm_entry("gw-omen-c", "OmenC",
                  "Third omen reading: ravens at noon.",
                  keys=("omen",), inclusion_group="omens",
                  group_weight=80),
        orm_entry("gw-fortune", "Fortune",
                  "A lantern hung beside the road glows amber.",
                  keys=("lantern",), probability=50),
        orm_entry("gw-starwhale", "Starwhale",
                  "Celestial whales swim the void between stars, "
                  "singing to sailors below; the great starwhale "
                  "carries dreams across the night sky.",
                  keys=("starwhale",), vectorised=True),
        orm_entry("gw-disabled", "Disabled", "Secret disabled lore.",
                  keys=("dragon",), enabled=False),
        orm_entry("gw-bread", "Bread", "Fresh bread lore.",
                  keys=("bread",)),
        orm_entry("gw-timed", "Timed", "A lighthouse keeper waits.",
                  keys=("lighthouse",), sticky_prompts=2,
                  cooldown_prompts=1),
        orm_entry("gw-before", "Before", "Before placement lore.",
                  keys=("beacon",), position="before_char"),
        orm_entry("gw-after", "After", "After placement lore.",
                  keys=("beacon",), position="after_char"),
        orm_entry("gw-deep", "Deep", "Deep placement lore.",
                  keys=("beacon",), position="at_depth", depth=1,
                  role="user"),
    ]


GW_MESSAGES = [
    "the dragon guards the gate of iron",
    "an omen and a lantern at the road",
    "celestial whales swimming among the stars singing",
]


def by_id(rows):
    return {row["entry_id"]: row for row in rows}


def gw(eid):
    return next(e for e in gateworld() if e.id == eid)


# --- DB helpers (test_p039/test_p040 patterns) ----------------------

def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


def run(coro):
    return asyncio.run(coro)


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


async def make_character(factory, user_id, name):
    async with factory() as session:
        character = Character(user_id=user_id, name=name)
        session.add(character)
        await session.commit()
        return character.id


# --- X-INS-1 / X-INS-2: the inspector explains every firing ---------

INCLUDED_REASONS = {
    "constant_active", "keyword_match", "sticky_carryover",
    "delay_fired", "reference_expansion", "recursive_trigger",
    "vector_match", "keyword_fallback",  # vector_fallback's code
}
NONINCLUDED_REASONS = {
    "disabled", "no_key_match", "inclusion_group_excluded",
    "secondary_gate_failed", "cooldown_suppressed", "delay_armed",
    "delay_pending", "vector_below_threshold", "vector_no_match",
}


def test_x_ins_1_inspector_explains_every_firing():
    entries = gateworld()
    embedder = LocalEmbeddingBackend().embed_sync
    preview = preview_activation(
        entries, GW_MESSAGES, 4, None, seed=SEED, roll_context="gate",
        recursive_scan=True, vector_embedder=embedder)
    result = inspect_activation(
        entries, GW_MESSAGES, 4, None, seed=SEED, roll_context="gate",
        recursive_scan=True, vector_embedder=embedder)
    rows = by_id(result["entries"])
    prow = by_id(preview["entries"])
    assert len(result["entries"]) == len(entries)
    assert result["facts_not_recorded"] == list(FACTS_NOT_RECORDED)
    assert tuple(result["facts_not_recorded"]) == FACTS_NOT_RECORDED
    for eid, row in rows.items():
        assert row["summary"], eid
        assert row["status"] == prow[eid]["status"], eid
        if row["status"] == "included":
            assert row["reason"] in INCLUDED_REASONS, (eid, row["reason"])
        else:
            assert (
                row["reason"] in NONINCLUDED_REASONS
                or prow[eid]["discard_reason"] in
                {"over_budget", "probability_skip"}
            ), (eid, row["reason"])
    # Kind factual blocks.
    dragon = rows["gw-dragon"]
    assert dragon["reason"] == "keyword_match"
    assert dragon["keys"]["matched_primary"] == ["dragon"]
    assert dragon["keys"]["message_indices"] == [0]
    assert rows["gw-constant"]["reason"] == "constant_active"
    wyrm = rows["gw-wyrm"]
    assert wyrm["reason"] == "recursive_trigger"
    assert wyrm["recursion"]["triggered_by"] == "gw-dragon"
    assert wyrm["recursion"]["depth"] == 1
    whale = rows["gw-starwhale"]
    assert whale["reason"] == "vector_match"
    assert whale["vector"]["score"] is not None
    assert whale["vector"]["score"] >= DEFAULT_VECTOR_THRESHOLD
    assert whale["vector"]["threshold"] == DEFAULT_VECTOR_THRESHOLD
    fortune = rows["gw-fortune"]
    assert fortune["status"] == "included"
    roll = fortune["probability"]["roll"]
    assert roll is not None and roll["seed"] == SEED
    assert roll["seeded"] is True and roll["passed"] is True
    assert roll["roll"] == derive_roll("gw-fortune", SEED, "gate")
    assert roll["probability"] == 0.5
    # Group loser, disabled, plain non-match.
    loser = rows["gw-omen-b"]
    assert loser["status"] == "group_excluded"
    assert loser["reason"] == "inclusion_group_excluded"
    assert loser["group"]["winner_id"] == "gw-omen-a"
    assert rows["gw-omen-c"]["status"] == "group_excluded"
    assert rows["gw-disabled"]["reason"] == "disabled"
    assert rows["gw-bread"]["reason"] == "no_key_match"
    totals = result["totals"]
    assert totals["entries"] == len(entries)
    assert (totals["included"] + totals["discarded"]
            + totals["not_triggered"] + totals["group_excluded"]
            + totals["disabled"]) == totals["entries"]


def test_x_ins_2_near_miss_first_class():
    entries = gateworld()
    settings = ScanSettings.normalised(scan_depth=4)
    view = [ScanEntry.from_orm(e) for e in entries]
    misses = {m.entry_id: m for m in
              scan_near_misses(view, GW_MESSAGES, settings)}
    assert "gw-gate-notany" in misses
    miss = misses["gw-gate-notany"]
    assert miss.matched_primary == ("gate",)
    assert "iron" in miss.matched_secondary
    result = inspect_activation(entries, GW_MESSAGES, 4, None, seed=SEED)
    row = by_id(result["entries"])["gw-gate-notany"]
    assert row["near_miss"] is True
    assert row["near_miss_kind"] == "secondary_gate_failed"
    assert row["stage_reached"] == "gate"
    # Vector below threshold is a first-class near miss too.
    whale = gw("gw-starwhale")
    low = inspect_activation(
        [whale], ["fresh bread is baked at dawn for copper coins"],
        4, None, vector_embedder=LocalEmbeddingBackend().embed_sync)
    vrow = low["entries"][0]
    assert vrow["near_miss"] is True
    assert vrow["near_miss_kind"] == "vector_below_threshold"
    assert vrow["stage_reached"] == "vector"
    assert vrow["vector"]["score"] is not None
    assert vrow["vector"]["score"] < DEFAULT_VECTOR_THRESHOLD


# --- X-PLC-1: placement ----------------------------------------------

def test_x_plc_1_placement():
    entries = [gw("gw-before"), gw("gw-after"), gw("gw-deep")]
    history = ["beacon rises", "m1", "m2", "m3"]
    preview = preview_activation(entries, history, 4, None)
    rows = by_id(preview["entries"])
    assert rows["gw-before"]["position"] == "before_char"
    assert rows["gw-after"]["position"] == "after_char"
    assert rows["gw-deep"]["position"] == "at_depth"
    assert rows["gw-deep"]["injection_depth"] == 1
    assert rows["gw-deep"]["role"] == "user"
    for eid in ("gw-before", "gw-after"):
        assert rows[eid]["injection_depth"] is None
        assert rows[eid]["role"] == "system"
    assert placement_for("at_depth", 1, "user").kind == "lore_before"
    assert placement_for("after_char", None, "system").kind == "lore_after"
    assert placement_for("before_char", None, "system").kind == "lore_before"
    # Composed prompt (real ordering; see adaptation note 3).
    slots = [make_slot("persona", "system", "CHARDEF",
                       id="persona/c1")]
    for eid in ("gw-before", "gw-after", "gw-deep"):
        slots.append(_lore_slot(rows[eid], f"lore/{eid}", "lorebook:G"))
    slots.append(make_slot("history", "user", "", id="history",
                           splittable=True, parts=tuple(history)))
    composed = compose(slots, context_limit=4096, reserve_response=512)
    contents = [m.content for m in composed.messages]
    idx = {c: i for i, c in enumerate(contents)}
    deep_i = idx["Deep placement lore."]
    assert composed.messages[deep_i].role == "user"
    # Exactly one history message follows the splice: the tail.
    assert contents[deep_i + 1] == "m3"
    assert "m2" in contents[deep_i - 1] and "m3" not in contents[deep_i - 1]
    assert idx["After placement lore."] > idx["CHARDEF"]
    # Real baseline order: persona precedes lore_before (flagged).
    assert idx["CHARDEF"] < idx["Before placement lore."]
    assert idx["Before placement lore."] < deep_i


def test_x_plc_1_at_depth_db_roundtrip(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        async with factory() as session:
            book = await lore_service.create_lorebook(
                session, uid, name="Placement")
            deep = await lore_service.create_entry(
                session, uid, book.id, name="Deep",
                content="Deep placement lore.", keys=["beacon"],
                position="at_depth", depth=1, role="user")
            await lore_service.create_entry(
                session, uid, book.id, name="Before",
                content="Before placement lore.", keys=["beacon"],
                position="before_char")
            stored = await lore_service.list_entries(
                session, uid, book.id)
            dicts = {d["name"]: d for d in
                     (entry_to_dict(e) for e in stored or [])}
            assert dicts["Deep"]["position"] == "at_depth"
            assert dicts["Deep"]["depth"] == 1
            assert dicts["Deep"]["role"] == "user"
            assert dicts["Deep"]["id"] == deep.id
            # Prompt inspector honours the placement end to end.
            char_id = await make_character(factory, uid, "Sigrun")
            trace = await inspect_prompt(
                session, uid, character_id=char_id,
                lorebook_ids=[book.id],
                messages=["beacon rises", "m1", "m2", "m3"])
            assert trace is not None
            slots = {s["slot_id"]: s for s in trace["slots"]}
            dslot = slots[f"lore/{deep.id}"]
            assert dslot["kind"] == "lore_before"
            assert dslot["role"] == "user"
            assert dslot["status"] == "included"

    run(main())


# --- X-SCO-1: scopes ---------------------------------------------------

def test_x_sco_1_scopes(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        char_a = await make_character(factory, uid, "Asta")
        char_b = await make_character(factory, uid, "Bera")
        async with factory() as session:
            chat_a = Chat(user_id=uid, title="A hall",
                          character_id=char_a)
            chat_b = Chat(user_id=uid, title="B hall",
                          character_id=char_b)
            session.add_all([chat_a, chat_b])
            await session.commit()
            chat_a_id, chat_b_id = chat_a.id, chat_b.id

            async def book(name, key, content, **kw):
                b = await lore_service.create_lorebook(
                    session, uid, name=name)
                await lore_service.create_entry(
                    session, uid, b.id, name=name, content=content,
                    keys=[key], **kw)
                return b.id

            g_id = await book("GlobalHaven", "haven",
                              "Global haven lore stands open to all "
                              "travellers here.")
            g2_id = await book("GlobalTide", "tide",
                               "Tide lore for the global layer.")
            c_id = await book("CharShield", "shield",
                              "Shield lore carried by the character.")
            c2_id = await book("CharAegis", "aegis",
                               "Aegis lore carried by the character.")
            p_id = await book("PersonaWard", "ward",
                              "Ward lore carried by the persona.")
            chat_id_book = await book(
                "ChatHaven", "haven",
                "Chat haven lore fills this hall with long "
                "remembered stories of the road and hearth fire.")
            other_id = await book("OtherHaven", "haven",
                                  "Other haven lore never applies.")
            await scopes.assign_scope(session, uid, g_id, "global")
            await scopes.assign_scope(
                session, uid, g2_id, "global", token_budget=500)
            await scopes.assign_scope(
                session, uid, c_id, "character", owner_id=char_a,
                token_budget=1000)
            await scopes.assign_scope(
                session, uid, c2_id, "character", owner_id=char_a,
                token_budget=300)
            await scopes.assign_scope(
                session, uid, p_id, "persona", owner_id=char_a,
                token_budget=900)
            await scopes.assign_scope(
                session, uid, chat_id_book, "chat",
                owner_id=chat_a_id, token_budget=5)
            await scopes.assign_scope(
                session, uid, other_id, "chat", owner_id=chat_b_id)
            result = await scopes.layered_preview(
                session, uid, chat_id=chat_a_id, character_id=char_a,
                persona_character_id=char_a,
                messages=["haven shield ward aegis tide"])
            assert result is not None
            assert scopes.LAYER_ORDER == (
                "global", "character", "persona", "chat")
            summaries = result["scopes"]
            assert [s["scope"] for s in summaries] == list(
                scopes.LAYER_ORDER)
            budget = {s["scope"]: s["budget"] for s in summaries}
            assert budget["global"] == 500  # min(None ignored, 500)
            assert budget["character"] == 300  # min(1000, 300)
            assert budget["persona"] == 900
            assert budget["chat"] == 5
            owners = {"global": "", "character": char_a,
                      "persona": char_a, "chat": chat_a_id}
            all_books = set()
            for kind, layer in result["layers"].items():
                for row in layer["entries"]:
                    assert row["scope"] == kind
                    assert row["lorebook_id"]
                    assert row["scope_owner_id"] == owners[kind]
                    all_books.add(row["lorebook_id"])
            assert other_id not in all_books
            grow = next(r for r in result["layers"]["global"]["entries"]
                        if r["lorebook_id"] == g_id)
            assert grow["status"] == "included"
            crow = next(r for r in result["layers"]["chat"]["entries"]
                        if r["lorebook_id"] == chat_id_book)
            assert crow["status"] == "discarded"
            assert crow["discard_reason"] == "scope_over_budget"
            assert crow["content"] != grow["content"]

    run(main())


# --- X-VEC-1 / X-VEC-2: vector match + fallback ------------------------

PARAPHRASE = "celestial whales swimming among the stars singing"


def test_x_vec_1_vector_match():
    assert DEFAULT_VECTOR_THRESHOLD == 0.30
    whale = gw("gw-starwhale")
    coral = orm_entry(
        "gw-coral", "Coral",
        "Coral gardens bloom beneath shallow lagoons where small "
        "silver fish dart between the branches.",
        keys=("coral",), vectorised=True)
    embedder = LocalEmbeddingBackend().embed_sync
    outcome = match_vectorised_sync(
        [whale, coral], [PARAPHRASE], embedder)
    assert outcome.mode == "vector"
    assert "gw-starwhale" in outcome.hit_ids
    assert outcome.scores["gw-starwhale"] >= DEFAULT_VECTOR_THRESHOLD
    scores = [s for _eid, s in outcome.ranked]
    assert scores == sorted(scores, reverse=True)
    assert outcome.ranked[0][0] == "gw-starwhale"
    preview = preview_activation(
        [whale, coral], [PARAPHRASE], 4, None, vector_embedder=embedder)
    row = by_id(preview["entries"])["gw-starwhale"]
    assert row["via"] == "vector" and row["status"] == "included"
    assert row["vector_score"] == outcome.scores["gw-starwhale"]
    # Unrelated control.
    control = match_vectorised_sync(
        [whale], ["fresh bread is baked at dawn for copper coins"],
        embedder)
    assert control.mode == "none" and control.hit_ids == ()
    crow = preview_activation(
        [whale], ["fresh bread is baked at dawn for copper coins"],
        4, None, vector_embedder=embedder)["entries"][0]
    assert crow["status"] == "not_triggered"


def test_x_vec_2_fallback_equivalence():
    whale = gw("gw-starwhale")
    messages = ["the starwhale appears"]

    def boom(texts):
        raise RuntimeError("embeddings down")

    fb = keyword_fallback_hits([whale], messages)
    assert {(h.entry_id, h.matched_primary) for h in fb} == {
        ("gw-starwhale", ("starwhale",))}
    # The raw scanner skips vectorised entries by design (note 2).
    raw = scan_entries_windowed(
        [ScanEntry.from_orm(whale)], messages,
        ScanSettings.normalised())
    assert raw == []
    clone = SimpleNamespace(**{**vars(whale), "vectorised": False})
    flipped = scan_entries_windowed(
        [ScanEntry.from_orm(clone)], messages,
        ScanSettings.normalised())
    assert {(h.entry_id, h.matched_primary) for h in fb} == {
        (h.entry_id, h.matched_primary) for h in flipped}
    outcome = match_vectorised_sync([whale], messages, boom)
    assert outcome.mode == "keyword_fallback"
    assert outcome.degraded is True and outcome.fallback_reason
    assert outcome.fallback_ids == ("gw-starwhale",)
    preview = preview_activation(
        [whale], messages, 4, None, vector_embedder=boom)
    row = preview["entries"][0]
    assert row["via"] == "vector_fallback" and row["via"] != "vector"
    assert row["status"] == "included"
    assert preview["vector_match"]["mode"] == "keyword_fallback"
    assert preview["vector_match"]["degraded"] is True
    assert preview["vector_match"]["fallback_reason"]
    # Converse: a landed vector hit suppresses the fallback, so a
    # keyed-but-low-vector entry stays unfired that tick.
    keyed = orm_entry(
        "gw-keyedvec", "KeyedVec",
        "Entirely unrelated zqx jkw lore about purple turnips and "
        "iron spoons in a cellar cupboard drawer.",
        keys=("celestial",), vectorised=True)
    embedder = LocalEmbeddingBackend().embed_sync
    out2 = match_vectorised_sync([whale, keyed], [PARAPHRASE], embedder)
    assert out2.mode == "vector" and out2.fallback_ids == ()
    prev2 = preview_activation(
        [whale, keyed], [PARAPHRASE], 4, None, vector_embedder=embedder)
    krow = by_id(prev2["entries"])["gw-keyedvec"]
    assert krow["status"] == "not_triggered"
    assert krow["vector_score"] < DEFAULT_VECTOR_THRESHOLD


# --- X-TOK-1: token accounting (see adaptation note 1) -----------------

def test_x_tok_1_token_accounting():
    subset = [gw("gw-dragon"), gw("gw-gate-any"), gw("gw-fortune"),
              gw("gw-bread")]
    messages = ["the dragon guards the gate of iron",
                "a lantern at the road"]
    counter = lambda t: len(t.split())  # noqa: E731
    preview = preview_activation(
        subset, messages, 4, 24, seed=SEED, roll_context="gate",
        counter=counter)
    rows = by_id(preview["entries"])
    included = [r for r in rows.values() if r["status"] == "included"]
    discarded = [r for r in rows.values() if r["status"] == "discarded"]
    assert len(included) == 2 and len(discarded) == 1
    assert discarded[0]["entry_id"] == "gw-fortune"
    account = preview["token_account"]
    acct = by_id(account["entries"])
    contents = {e.id: e.content for e in subset}
    # Budget-pass regime: preview totals reconcile with the rows.
    assert preview["tokens_used"] == sum(r["tokens"] for r in included)
    # Counter regime: the account recounts with the counter.
    assert account["count_quality"] == "exact"
    assert account["tokens_used"] == sum(
        a["spent"] for a in account["entries"])
    for eid, arow in acct.items():
        assert arow["tokens"] == count_lore_tokens(
            contents[eid], counter)
    assert acct["gw-fortune"]["spent"] == 0
    assert account["discarded_tokens"] == acct["gw-fortune"]["tokens"]
    assert account["budget_remaining"] == (
        account["token_budget"] - account["tokens_used"])
    assert account["token_budget"] == 24
    by_status = account["by_status"]
    assert by_status["included"]["count"] == 2
    assert by_status["included"]["spent"] == account["tokens_used"]
    assert by_status["discarded"]["tokens"] == (
        account["discarded_tokens"])
    assert by_status["not_triggered"]["spent"] == 0
    assert account["by_book"] == {}  # plain rows carry no book id
    # No-counter variant: estimate-labelled would-be costs.
    plain = preview_activation(
        subset, messages, 4, 24, seed=SEED, roll_context="gate")
    paccount = plain["token_account"]
    assert paccount["count_quality"] == "estimated"
    pacct = by_id(paccount["entries"])
    assert pacct["gw-bread"]["tokens"] == estimate_tokens(
        contents["gw-bread"])
    assert paccount["untriggered_tokens"] == estimate_tokens(
        contents["gw-bread"])
    assert paccount["tokens_used"] == plain["tokens_used"]


# --- X-RNG-1: probability determinism -----------------------------------

def test_x_rng_1_probability_determinism():
    assert probability_fraction(50) == 0.5
    roll = derive_roll("gw-fortune", SEED, "gate")
    assert roll == derive_roll("gw-fortune", SEED, "gate")
    assert 0.0 <= roll < 1.0
    record = roll_probability("gw-fortune", 0.5, seed=SEED,
                              context="gate")
    assert record.roll == roll and record.passed == (roll < 0.5)
    assert explain_roll("gw-fortune", 0.5, seed=SEED,
                        context="gate") == record.to_dict()
    assert derive_roll("gw-fortune", SEED, "other") != roll
    gated = [gw("gw-fortune"),
             orm_entry("gw-dice", "Dice", "Dice lore for the road.",
                       keys=("dice",), probability=50)]
    messages = ["a lantern and dice at the road"]
    first = preview_activation(gated, messages, 4, None, seed=SEED,
                               roll_context="gate")
    second = preview_activation(gated, messages, 4, None, seed=SEED,
                                roll_context="gate")
    assert first["probability_rolls"] == second["probability_rolls"]
    assert json.dumps(first["probability_rolls"]) == json.dumps(
        second["probability_rolls"])
    ids = lambda p: {r["entry_id"] for r in p["entries"]  # noqa: E731
                     if r["status"] == "included"}
    assert ids(first) == ids(second)
    # Permuted input order: per-entry rolls are unchanged.
    permuted = preview_activation(
        list(reversed(gated)), messages, 4, None, seed=SEED,
        roll_context="gate")
    rolls = {r["entry_id"]: r for r in first["probability_rolls"]}
    prolls = {r["entry_id"]: r for r in permuted["probability_rolls"]}
    assert rolls == prolls
    # Honesty pins.
    dragon = gw("gw-dragon")
    mixed = preview_activation(
        [dragon, gw("gw-fortune")],
        ["the dragon and a lantern"], 4, None, seed=SEED,
        roll_context="gate")
    assert {r["entry_id"] for r in mixed["probability_rolls"]} == {
        "gw-fortune"}
    zero = orm_entry("gw-zero", "Zero", "Zero lore.", keys=("zero",),
                     probability=0)
    zpreview = preview_activation([zero], ["zero hour"], 4, None,
                                  seed=SEED, roll_context="gate")
    zrow = zpreview["entries"][0]
    assert zrow["status"] == "discarded"
    assert zrow["discard_reason"] == "probability_skip"
    assert zrow["probability_roll"]["passed"] is False
    unseeded = preview_activation(
        [gw("gw-fortune")], ["a lantern"], 4, None, seed=None)
    uroll = unseeded["entries"][0]["probability_roll"]
    assert uroll["seeded"] is False and uroll["seed"] is None


# --- X-WIN-1: scan windows ----------------------------------------------

def test_x_win_1_scan_windows():
    entry = orm_entry("gw-lighthouse", "Lighthouse",
                      "Lighthouse lore.", keys=("lighthouse",))
    view = [ScanEntry.from_orm(entry)]
    messages = ["the lighthouse wakes", "m1", "m2", "m3", "m4", "m5"]
    depth = ScanSettings.normalised(scan_depth=2)
    window = build_scan_window(depth, messages)
    assert window.summary()["chat_messages"] == 2
    assert window.summary()["texts"] == 2
    assert scan_entries_windowed(view, messages, depth) == []
    whole = ScanSettings.normalised(scan_depth=2,
                                    scan_mode="whole_chat")
    hits = scan_entries_windowed(view, messages, whole)
    assert len(hits) == 1 and hits[0].message_indices == (0,)
    off = ScanSettings.normalised(scan_depth=2,
                                  scan_external_context=False)
    on = ScanSettings.normalised(scan_depth=2,
                                 scan_external_context=True)
    external = ["the lighthouse again"]
    assert scan_entries_windowed(view, ["calm sea"], off, external) == []
    ehits = scan_entries_windowed(view, ["calm sea"], on, external)
    assert len(ehits) == 1
    assert ehits[0].external_indices == (0,)
    assert ehits[0].message_indices == ()


def test_x_win_1_stored_book_window(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        async with factory() as session:
            book = await lore_service.create_lorebook(
                session, uid, name="WindowBook", scan_depth=2)
            await lore_service.create_entry(
                session, uid, book.id, name="Lighthouse",
                content="Lighthouse lore.", keys=["lighthouse"])
            stored = await lore_service.get_lorebook(
                session, uid, book.id)
            entries = await lore_service.list_entries(
                session, uid, book.id) or []
            settings = ScanSettings.from_book(stored)
            assert settings.scan_depth == 2
            messages = ["the lighthouse wakes", "m1", "m2", "m3"]
            scoped = preview_activation(
                entries, messages, settings.scan_depth, None,
                scan_mode=settings.scan_mode,
                scan_external_context=settings.scan_external_context)
            assert scoped["scan_window"]["chat_messages"] == 2
            assert scoped["entries"][0]["status"] == "not_triggered"
            wide = preview_activation(entries, messages, 4, None)
            assert wide["entries"][0]["status"] == "included"

    run(main())


# --- X-BIND-1: character-book binding ------------------------------------

def test_x_bind_1_binding(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        char_a = await make_character(factory, uid, "Asta")
        char_b = await make_character(factory, uid, "Bera")
        async with factory() as session:
            cbook = await lore_service.create_lorebook(
                session, uid, name="A Book")
            await lore_service.create_entry(
                session, uid, cbook.id, name="Oath",
                content="A's oath", keys=["oath"], priority=100)
            wbook = await lore_service.create_lorebook(
                session, uid, name="World Book")
            await lore_service.create_entry(
                session, uid, wbook.id, name="Oath",
                content="World oath", keys=["oath"], priority=200)
            await lore_service.create_entry(
                session, uid, wbook.id, name="WorldOnly",
                content="World only lore", keys=["worldkey"],
                priority=90)
            assert binding.DEFAULT_PRECEDENCE == "character_first"
            await binding.bind_book(session, uid, char_a, cbook.id)
            messages = ["oath worldkey"]
            merged = await binding.merged_preview(
                session, uid, char_a, wbook.id, messages)
            rows = by_id(merged["entries"])
            oath_rows = [r for r in merged["entries"]
                         if r["content"] in ("A's oath", "World oath")]
            assert len(oath_rows) == 1
            assert oath_rows[0]["content"] == "A's oath"
            assert any(r["content"] == "World only lore"
                       for r in merged["entries"])
            # Pure mirror.
            world_dicts = [entry_to_dict(e) for e in
                           await lore_service.list_entries(
                               session, uid, wbook.id) or []]
            char_dicts = [entry_to_dict(e) for e in
                          await lore_service.list_entries(
                              session, uid, cbook.id) or []]
            pure = binding.merge_entry_dicts(
                world_dicts, char_dicts, "character_first")
            winner = next(e for e in pure["entries"]
                          if e["name"] == "Oath")
            assert winner["content"] == "A's oath"
            assert winner["scope"] == "character"
            # world_first.
            await binding.set_precedence(
                session, uid, char_a, "world_first")
            merged_w = await binding.merged_preview(
                session, uid, char_a, wbook.id, messages)
            oath_w = [r for r in merged_w["entries"]
                      if r["content"] in ("A's oath", "World oath")]
            assert len(oath_w) == 1
            assert oath_w[0]["content"] == "World oath"
            pure_w = binding.merge_entry_dicts(
                world_dicts, char_dicts, "world_first")
            assert next(e for e in pure_w["entries"]
                        if e["name"] == "Oath")["content"] == "World oath"
            # priority: the higher-priority (world, 200) wins.
            await binding.set_precedence(
                session, uid, char_a, "priority")
            merged_p = await binding.merged_preview(
                session, uid, char_a, wbook.id, messages)
            oath_p = [r for r in merged_p["entries"]
                      if r["content"] in ("A's oath", "World oath")]
            assert len(oath_p) == 1
            assert oath_p[0]["content"] == "World oath"
            pure_p = binding.merge_entry_dicts(
                world_dicts, char_dicts, "priority")
            assert next(e for e in pure_p["entries"]
                        if e["name"] == "Oath")["content"] == "World oath"
            # Character B has no binding; after unbind, A neither.
            with pytest.raises(ValueError) as excinfo:
                await binding.merged_preview(
                    session, uid, char_b, wbook.id, messages)
            assert str(excinfo.value) == (
                "character has no bound lorebook")
            assert await binding.unbind(session, uid, char_a) is True
            with pytest.raises(ValueError) as excinfo2:
                await binding.merged_preview(
                    session, uid, char_a, wbook.id, messages)
            assert str(excinfo2.value) == (
                "character has no bound lorebook")

    run(main())


# --- X-PACK-1: sharing packs (see adaptation note 4) ---------------------

PACK_FIELDS = [
    "name", "content", "keys", "secondary_keys", "selective_logic",
    "inclusion_group", "group_weight", "probability", "priority",
    "position", "depth", "role", "enabled", "constant", "vectorised",
    "case_sensitive", "whole_word", "sticky_prompts",
    "cooldown_prompts", "delay_prompts",
]


def test_x_pack_1_packs(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory, "sender")
        uid2 = await make_user(factory, "receiver")
        async with factory() as session:
            book = await lore_service.create_lorebook(
                session, uid, name="Gate Pack",
                description="A pack from Gateworld.", scan_depth=3,
                token_budget=500)
            await lore_service.create_entry(
                session, uid, book.id, name="Pack Alpha",
                content="Alpha lore for the pack.", keys=["alpha"],
                secondary_keys=["beta"], selective_logic="and_all",
                inclusion_group="omens", group_weight=80,
                probability=50, priority=120, position="at_depth",
                depth=2, role="user", sticky_prompts=1,
                cooldown_prompts=3, delay_prompts=1,
                case_sensitive=True, whole_word=False)
            await lore_service.create_entry(
                session, uid, book.id, name="Pack Beta",
                content="Beta lore for the pack.", keys=["beta"],
                priority=90, position="after_char")
            entries = await lore_service.list_entries(
                session, uid, book.id) or []
            source_dicts = [entry_to_dict(e) for e in entries]
            pack = packs.build_pack(
                lorebook_to_dict(book, len(entries)), source_dicts,
                exported_at="2026-11-06T12:00:00+00:00")
            checksum = packs.content_checksum(pack["lorebook"])
            assert pack["manifest"]["content_sha256"] == checksum
            canonical = packs.canonical_payload(pack["lorebook"])
            digest = hashlib.sha256(json.dumps(
                canonical, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False).encode("utf-8")).hexdigest()
            assert pack["manifest"]["content_sha256"] == digest
            data = packs.pack_to_bytes(pack)
            parsed = packs.parse_pack(data)
            assert parsed["manifest"] == pack["manifest"]
            info = packs.inspect_pack(data)
            assert info["entry_count"] == 2
            assert info["book_name"] == "Gate Pack"
            assert info["content_sha256"] == checksum
            assert pack["provenance"]["source_book_id"] == book.id
            assert pack["provenance"]["content_sha256"] == checksum
            imported, report = await packs.import_pack(
                session, uid2, data, on_conflict="create_new")
            assert report["created"] is True
            assert report["duplicate_exact"] is False
            assert report["provenance"] == pack["provenance"]
            imported_entries = await lore_service.list_entries(
                session, uid2, imported.id) or []
            imported_dicts = {d["name"]: d for d in
                              (entry_to_dict(e)
                               for e in imported_entries)}
            assert set(imported_dicts) == {"Pack Alpha", "Pack Beta"}
            for source in source_dicts:
                target = imported_dicts[source["name"]]
                for field_name in PACK_FIELDS:
                    assert target[field_name] == source[field_name], (
                        source["name"], field_name)
            again, report2 = await packs.import_pack(
                session, uid2, data, on_conflict="create_new")
            assert again.id == imported.id
            assert report2["created"] is False
            assert report2["duplicate_exact"] is True
            assert report2["entry_count"] == 2
            books2 = await lore_service.list_lorebooks(session, uid2)
            assert len(books2) == 1

    run(main())


# --- X-PERF-1: budget ceiling (light, no wall-clock) ----------------------

def test_x_perf_1_budget_ceiling():
    contents = {}
    entries = []
    candidates = []
    for i in range(12):
        eid = f"perf-{i:02d}"
        content = (f"perf{i:02d} " + "x" * 33)[:40]
        assert len(content) == 40
        contents[eid] = content
        entries.append(orm_entry(
            eid, f"Perf{i}", content, keys=("surge",),
            priority=120 - 10 * i))
        candidates.append(BudgetCandidate(
            entry_id=eid, content=content, priority=120 - 10 * i))
    total = sum(estimate_tokens(c) for c in contents.values())
    assert total > 30 * 3  # summed estimates >> the small budget
    result = resolve_budget(list(reversed(candidates)), 30, seed=SEED)
    assert [b.entry_id for b in result.included] == [
        "perf-00", "perf-01", "perf-02"]
    assert result.tokens_used == 30
    preview = preview_activation(entries, ["surge"], 4, 30, seed=SEED)
    assert preview["tokens_used"] <= 30
    rows = by_id(preview["entries"])
    survivors = {eid for eid, r in rows.items()
                 if r["status"] == "included"}
    assert survivors == {"perf-00", "perf-01", "perf-02"}
    overflow = [r for r in rows.values() if r["status"] == "discarded"]
    assert len(overflow) == 9
    assert all(r["discard_reason"] == "over_budget" for r in overflow)
    generous = preview_activation(entries, ["surge"], 4, None, seed=SEED)
    assert all(r["status"] == "included"
               for r in generous["entries"])
    again = preview_activation(entries, ["surge"], 4, 30, seed=SEED)
    assert {r["entry_id"] for r in again["entries"]
            if r["status"] == "included"} == survivors


# --- X-MIG-1: upgrade (light) ----------------------------------------------

def _mig_entries(book_dict):
    _book_fields, entry_fields = transfer.parse_import(book_dict)
    out = []
    for i, fields in enumerate(entry_fields):
        out.append(orm_entry(
            f"mig-{i}", fields["name"], fields["content"],
            keys=tuple(fields["keys"]),
            secondary_keys_json=json.dumps(fields["secondary_keys"]),
            selective_logic=fields["selective_logic"],
            inclusion_group=fields["inclusion_group"],
            group_weight=fields["group_weight"],
            probability=fields["probability"],
            priority=fields["priority"], position=fields["position"],
            depth=fields["depth"], role=fields["role"],
            enabled=fields["enabled"], constant=fields["constant"],
            vectorised=fields["vectorised"],
            case_sensitive=fields["case_sensitive"],
            whole_word=fields["whole_word"],
            sticky_prompts=fields["sticky_prompts"],
            cooldown_prompts=fields["cooldown_prompts"],
            delay_prompts=fields["delay_prompts"]))
    return out


def _fired(book_dict):
    preview = preview_activation(
        _mig_entries(book_dict),
        ["the harbour shelters", "a gale rises"], 4, None, seed=SEED)
    return {r["entry_id"]: r["content"] for r in preview["entries"]
            if r["status"] == "included"}


def test_x_mig_1_upgrade():
    legacy = {
        "format": "runmal-lorebook", "version": 1,
        "name": "Legacy Gate",
        "entries": [
            {"name": "Harbour",
             "content": "The harbour shelters every ship.",
             "keys": ["harbour"], "priority": 100},
            {"name": "Gale", "content": "A gale lashes the coast.",
             "keys": ["gale"], "priority": 90},
        ],
    }
    before_copy = copy.deepcopy(legacy)
    report0 = upgrade.inspect_lorebook(legacy)
    assert report0["generation"] == "native-legacy"
    assert report0["behaviour_preserving"] is True
    upgraded, report = upgrade.upgrade_lorebook(legacy)
    assert legacy == before_copy  # input never mutated
    assert report["already_current"] is False
    assert _fired(legacy) == _fired(upgraded)
    assert set(_fired(legacy).values()) == {
        "The harbour shelters every ship.",
        "A gale lashes the coast."}
    assert upgraded["entries"][0]["depth"] is None
    assert upgraded["token_budget"] is None
    upgraded2, report2 = upgrade.upgrade_lorebook(upgraded)
    assert report2["already_current"] is True
    assert upgraded2 == upgraded
    assert json.dumps(upgraded2, sort_keys=True) == json.dumps(
        upgraded, sort_keys=True)


# --- X-ED-1: editor reach (light) ------------------------------------------

def test_x_ed_1_editor_reach():
    schema = editor.editor_schema()
    entry_names = editor.field_names("entry")
    for field_name in PACK_FIELDS:
        assert field_name in entry_names, field_name
        assert field_name in {
            f["name"] for f in schema["surfaces"]["entry"]}
    book_names = editor.field_names("book")
    for field_name in ("scan_depth", "scan_mode",
                       "scan_external_context", "token_budget"):
        assert field_name in book_names, field_name
