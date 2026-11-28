"""W-03 acceptance: Chat actions + Groups tabs of the web face.

Unit half: the pure W-03 logic (words renderers, the lossless
deepening compose, message labels). Live half: a REAL served
engine (throwaway data dir) + the REAL webface + a REAL Ollama
backend over HTTP — every chat action from the slice scope and
the full group-room circuit, verified by re-reading the engine.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from runmal.webface import w03

REPO = Path(__file__).parent.parent


# ------------------------------------------------------------ unit: w03


def test_policy_and_activation_words():
    assert w03.policy_label("list").startswith("In order")
    assert w03.policy_label("mystery") == "mystery"
    assert {k for k, _ in w03.POLICIES} == {
        "natural", "list", "pooled", "manual"}
    assert {k for k, _ in w03.ACTIVATIONS} == {"default", "force", "never"}


def test_message_label_states_swipes_and_pin_in_words():
    label = w03.message_label({
        "role": "assistant", "content": "hello there",
        "swipes": ["a", "b", "c"], "swipe_id": 1, "pinned": True})
    assert "swipe 2 of 3" in label and "pinned" in label
    plain = w03.message_label({"role": "user", "content": "hi"})
    assert plain == "user: hi"


def test_turn_and_run_words_carry_pick_and_reason():
    words = w03.turn_words({"speaker_name": "Ann", "reason": "in order",
                            "message": {"content": "hey"}})
    assert "Ann" in words and "in order" in words and "hey" in words
    assert w03.turn_words({}) == "No turn ran."
    assert "No speaker" in w03.turn_words({"reason": "x"})
    run = w03.run_words({"turns_run": 2, "results": [
        {"speaker_name": "Ann"}, {"speaker_name": "Bo"}]})
    assert run.startswith("Ran 2 turns.") and "Ann" in run and "Bo" in run


def test_presence_peek_digest_words():
    lines = w03.presence_words([
        {"character_id": "a", "name": "Ann", "present": True},
        {"character_id": "b", "name": "Bo", "present": False,
         "missed_count": 3}])
    assert lines == ["Ann: here", "Bo: away · 3 missed"]
    peek = w03.peek_words({"member": {"name": "Ann"},
                           "persona_source": "override",
                           "effective_persona": "A pirate."})
    assert "override" in peek and "A pirate." in peek
    peek2 = w03.peek_words({"member": {"name": "Bo"},
                            "persona_source": "card",
                            "effective_persona": "A smith."})
    assert "their card" in peek2
    assert "2 thing" in w03.digest_words({"entries": [
        {"speaker_name": "Ann", "excerpt": "one"}, {"excerpt": "two"}]})
    assert w03.digest_words({}) == "Nothing was missed."


def test_transcript_lines_use_speaker_names():
    lines = w03.transcript_lines([
        {"speaker_id": "user", "speaker_name": "", "content": "hi all"},
        {"speaker_id": "c1", "speaker_name": "Ann", "content": "hello"}])
    assert lines == ["You: hi all", "Ann: hello"]


def test_compose_deepening_is_lossless():
    stored = {"generation_mode": "swap", "state": {"cursor": 2},
              "member_overrides": {"c1": {"activation": "force"}},
              "mystery_key": [1, 2]}
    out = w03.compose_deepening(
        stored, generation_mode="join", allow_self_responses=True,
        auto_enabled=True, auto_max_turns=0, join_prefix="<",
        join_suffix=">", scenario_override="  storm  ")
    assert out["generation_mode"] == "join"
    assert out["state"] == {"cursor": 2}  # engine state carried verbatim
    assert out["member_overrides"] == {"c1": {"activation": "force"}}
    assert out["mystery_key"] == [1, 2]  # unknown keys carried
    assert out["auto_mode"] == {"enabled": True, "max_turns": 1}
    assert out["scenario_override"] == "storm"
    assert stored["generation_mode"] == "swap"  # input unmutated
    assert w03.member_override(out, "c1") == {"activation": "force"}
    assert w03.member_override(out, "nope") == {}


# ------------------------------------------------------------ live pair


def _ollama_base() -> str | None:
    candidates = []
    if os.environ.get("RUNMAL_TEST_OLLAMA_URL"):
        candidates.append(os.environ["RUNMAL_TEST_OLLAMA_URL"])
    candidates.append("http://127.0.0.1:11434")
    try:
        ip = subprocess.run(["tailscale", "ip", "-4"], capture_output=True,
                            text=True, timeout=10).stdout.strip()
        if ip:
            candidates.append(f"http://{ip}:11434")
    except Exception:
        pass
    for base in candidates:
        try:
            if httpx.get(base + "/api/tags", timeout=5,
                         trust_env=False).status_code == 200:
                return base
        except Exception:
            continue
    return None


def _ollama_chat_model(base: str) -> str | None:
    resp = httpx.get(base + "/api/tags", timeout=5, trust_env=False)
    for m in resp.json().get("models", []):
        if "embed" not in m.get("name", ""):
            return m["name"]
    return None


def _free_port() -> int:
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_health(url: str, timeout_s: float = 60.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=3, trust_env=False).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


@pytest.fixture()
def live_pair(tmp_path):
    base = _ollama_base()
    if base is None:
        pytest.skip("no real Ollama backend answers on this machine")
    model = _ollama_chat_model(base)
    if model is None:
        pytest.skip("Ollama answers but lists no chat model")
    engine_port, webface_port = _free_port(), _free_port()
    env = dict(os.environ)
    env["RUNMAL_DATA_DIR"] = str(tmp_path / "engine-data")
    env["PYTHONPATH"] = str(REPO / "src")
    env["no_proxy"] = env["NO_PROXY"] = "127.0.0.1,localhost"
    engine = subprocess.Popen(
        [sys.executable, "-m", "runmal", "serve", "--host", "127.0.0.1",
         "--port", str(engine_port)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    face = None

    def start_face():
        proc = subprocess.Popen(
            [sys.executable, "-m", "runmal.webface", "--host", "127.0.0.1",
             "--port", str(webface_port), "--engine-url",
             f"http://127.0.0.1:{engine_port}", "--data-dir",
             str(tmp_path / "webface-data"), "--engine-data-dir",
             str(tmp_path / "engine-data")],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True)
        if not _wait_health(f"http://127.0.0.1:{webface_port}/"):
            raise RuntimeError("webface did not come up")
        return proc

    try:
        if not _wait_health(f"http://127.0.0.1:{engine_port}/healthz"):
            raise RuntimeError("engine did not come up")
        face = start_face()
        pair = {"engine": f"http://127.0.0.1:{engine_port}",
                "webface": f"http://127.0.0.1:{webface_port}",
                "ollama": base, "model": model,
                "data_dir": tmp_path / "engine-data"}

        def restart_face():
            nonlocal face
            face.terminate()
            face.wait(timeout=10)
            face = start_face()
        pair["restart_face"] = restart_face
        yield pair
    finally:
        for proc in (face, engine):
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()


def _headers(data_dir: Path) -> dict:
    token = (data_dir / "local_credential").read_text().strip()
    return {"Authorization": f"Bearer {token}"}


def _seed(live_pair):
    """Two characters + a pinned Ollama profile, via the engine API."""
    engine, headers = live_pair["engine"], _headers(live_pair["data_dir"])
    with httpx.Client(trust_env=False, timeout=60) as eng:
        profile = eng.post(f"{engine}/api/v1/backend-profiles", headers=headers,
                           json={"name": "w03-live", "chat_backend": "ollama",
                                 "chat_model": live_pair["model"],
                                 "config": {"base_url": live_pair["ollama"]}})
        assert profile.status_code in (200, 201), profile.text
        ids = {}
        for key, name, prompt in (
                ("ann", "W03 Ann", "You are Ann. Answer briefly."),
                ("bo", "W03 Bo", "You are Bo. Answer briefly.")):
            char = eng.post(f"{engine}/api/v1/characters", headers=headers,
                            json={"card": {
                                "name": name, "description": f"{name}.",
                                "system_prompt": prompt,
                                "first_mes": f"{name} at the gate."}})
            assert char.status_code in (200, 201), char.text
            ids[key] = char.json()["id"]
        return profile.json()["id"], ids


def _sse(web, path, payload):
    events = []
    with web.stream("POST", path, json=payload) as resp:
        assert resp.status_code == 200, resp.status_code
        for line in resp.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:"):].strip()))
    return events


def test_live_chat_actions_and_groups(live_pair):
    engine, face = live_pair["engine"], live_pair["webface"]
    headers = _headers(live_pair["data_dir"])
    profile_id, chars = _seed(live_pair)
    with httpx.Client(base_url=face, trust_env=False, timeout=300,
                      follow_redirects=False) as web:
        # Auth gating on the new roads + page.
        assert web.get("/webface/groups").status_code == 401
        assert web.get("/groups").status_code == 303
        reg = web.post("/register", data={
            "username": "w03live", "password": "long-enough-1"})
        assert reg.status_code == 303
        assert web.get("/groups").status_code == 200
        # Chat bound to Ann, profile pinned (engine road).
        chat = web.post("/webface/chats", json={"character_id": chars["ann"]})
        assert chat.status_code == 200, chat.text
        chat_id = chat.json()["id"]
        with httpx.Client(trust_env=False, timeout=30) as eng:
            pin = eng.post(f"{engine}/api/v1/chats/{chat_id}/backend-profile",
                           headers=headers, json={"profile_id": profile_id})
            assert pin.status_code == 200, pin.text
        # A real send-turn through the webface (real backend).
        events = _sse(web, f"/webface/chats/{chat_id}/send",
                      {"content": "Hello Ann, say one short sentence."})
        kinds = [e.get("type") for e in events]
        assert "landed" in kinds, kinds
        started = next(e for e in events if e.get("type") == "started")
        assert started["backend_key"] == "ollama", started
        msgs = web.get(f"/webface/chats/{chat_id}/messages").json()
        assert [m["role"] for m in msgs][-2:] == ["user", "assistant"]
        user_msg, asst_msg = msgs[-2], msgs[-1]
        # Edit persists (engine re-read).
        edited = web.patch(f"/webface/chats/{chat_id}/messages/{user_msg['id']}",
                           json={"content": "Edited: the gate word is EMBER."})
        assert edited.status_code == 200, edited.text
        msgs = web.get(f"/webface/chats/{chat_id}/messages").json()
        assert msgs[-2]["content"] == "Edited: the gate word is EMBER."
        # Swipes: add makes the NEW alternate active; select; delete.
        mid = asst_msg["id"]
        added = web.post(f"/webface/chats/{chat_id}/messages/{mid}/swipes",
                         json={"content": "Alternate reply text."})
        assert added.status_code == 200, added.text
        deck = added.json()
        assert deck["content"] == "Alternate reply text.", deck
        assert deck["swipe_id"] == len(deck["swipes"]) - 1
        back = web.post(
            f"/webface/chats/{chat_id}/messages/{mid}/swipes/select",
            json={"index": 0})
        assert back.json()["content"] == asst_msg["content"]
        nxt = web.post(
            f"/webface/chats/{chat_id}/messages/{mid}/swipes/select",
            json={"action": "next"})
        assert nxt.json()["content"] == "Alternate reply text."
        dropped = web.request(
            "DELETE", f"/webface/chats/{chat_id}/messages/{mid}/swipes/1")
        assert dropped.status_code == 200, dropped.text
        assert len(dropped.json()["swipes"]) == 1
        # Pin / unpin, verified by the pinned-list re-read.
        pinned = web.post(f"/webface/chats/{chat_id}/messages/{mid}/pin")
        assert pinned.json()["pinned"] is True
        assert mid in pinned.json()["pinned_ids"]
        listed = web.get(f"/webface/chats/{chat_id}/pinned").json()
        assert any(m["id"] == mid for m in listed)
        unpinned = web.request(
            "DELETE", f"/webface/chats/{chat_id}/messages/{mid}/pin")
        assert unpinned.json()["pinned"] is False
        # Branch from the selected message.
        branch = web.post(f"/webface/chats/{chat_id}/branches",
                          json={"message_id": user_msg["id"],
                                "name": "W03 branch"})
        assert branch.status_code == 200, branch.text
        assert branch.json()["id"] != chat_id
        # Author's note saves + reads back.
        note = web.post(f"/webface/chats/{chat_id}/authors-note", json={
            "text": "Keep answers short.", "depth": 2, "frequency": 1,
            "role": "system", "enabled": True})
        assert note.status_code == 200, note.text
        assert note.json()["text"] == "Keep answers short."
        assert note.json()["depth"] == 2
        # Impersonate: accept lands; discard stores nothing.
        draft = web.post(f"/webface/chats/{chat_id}/impersonate", json={})
        assert draft.status_code == 200, draft.text
        assert draft.json()["content"].strip()
        before = len(web.get(f"/webface/chats/{chat_id}/messages").json())
        accepted = web.post(f"/webface/chats/{chat_id}/impersonate/accept",
                            json={"content": "I accept this drafted line.",
                                  "draft_id": draft.json()["id"]})
        assert accepted.status_code == 200, accepted.text
        msgs = web.get(f"/webface/chats/{chat_id}/messages").json()
        assert len(msgs) == before + 1
        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "I accept this drafted line."
        draft2 = web.post(f"/webface/chats/{chat_id}/impersonate", json={})
        discarded = web.post(f"/webface/chats/{chat_id}/impersonate/discard",
                             json={"draft_id": draft2.json()["id"]})
        assert discarded.status_code == 200
        assert len(web.get(f"/webface/chats/{chat_id}/messages").json()) == before + 1
        # Continue lands a continuation (engine-side landing).
        cont = web.post(f"/webface/chats/{chat_id}/continue",
                        json={"mode": "auto"})
        assert cont.status_code == 200, cont.text
        after_cont = web.get(f"/webface/chats/{chat_id}/messages").json()
        assert after_cont[-1]["role"] == "assistant"
        assert after_cont[-1]["content"].strip()
        # Search finds the edited line and names its chat.
        hits = web.get("/webface/chats/search",
                       params={"q": "EMBER"}).json()
        assert any(h["chat_id"] == chat_id for h in hits["results"]), hits
        # Checkpoints: create / restore-as-new / delete.
        cp = web.post(f"/webface/chats/{chat_id}/checkpoints",
                      json={"name": "w03 mark"})
        assert cp.status_code == 200, cp.text
        cp_id = cp.json()["id"]
        assert any(c["id"] == cp_id for c in
                   web.get(f"/webface/chats/{chat_id}/checkpoints").json())
        restored = web.post(
            f"/webface/chats/{chat_id}/checkpoints/{cp_id}/restore", json={})
        assert restored.status_code == 200, restored.text
        assert restored.json()["id"] != chat_id
        gone = web.request(
            "DELETE", f"/webface/chats/{chat_id}/checkpoints/{cp_id}")
        assert gone.status_code == 200
        assert not any(c["id"] == cp_id for c in
                       web.get(f"/webface/chats/{chat_id}/checkpoints").json())
        # Delete a message, then Undo restores it with its original id.
        msgs = web.get(f"/webface/chats/{chat_id}/messages").json()
        victim = msgs[0]
        deleted = web.request(
            "DELETE", f"/webface/chats/{chat_id}/messages/{victim['id']}")
        assert deleted.json()["deleted"] is True
        assert not any(m["id"] == victim["id"] for m in
                       web.get(f"/webface/chats/{chat_id}/messages").json())
        journal = web.get(f"/webface/chats/{chat_id}/undo").json()
        assert journal["entries"], journal
        undone = web.post(f"/webface/chats/{chat_id}/undo", json={})
        assert undone.status_code == 200, undone.text
        msgs = web.get(f"/webface/chats/{chat_id}/messages").json()
        assert any(m["id"] == victim["id"] for m in msgs)
        # Regenerate: a NEW reply from the real backend replaces the old.
        msgs = web.get(f"/webface/chats/{chat_id}/messages").json()
        if msgs[-1]["role"] != "assistant":
            _sse(web, f"/webface/chats/{chat_id}/send",
                 {"content": "One more short reply, please."})
            msgs = web.get(f"/webface/chats/{chat_id}/messages").json()
        old_last = msgs[-1]
        assert old_last["role"] == "assistant"
        events = _sse(web, f"/webface/chats/{chat_id}/regenerate", {})
        kinds = [e.get("type") for e in events]
        assert "landed" in kinds, kinds
        started = next(e for e in events if e.get("type") == "started")
        assert started["backend_key"] == "ollama", started
        reply = "".join(e.get("text", "") for e in events
                        if e.get("type") == "token")
        msgs = web.get(f"/webface/chats/{chat_id}/messages").json()
        assert msgs[-1]["role"] == "assistant"
        assert msgs[-1]["id"] != old_last["id"]
        assert msgs[-1]["content"].strip() == reply.strip()
        assert all(m["id"] != old_last["id"] for m in msgs)
        # ---------------- groups ----------------
        room = web.post("/webface/groups", json={
            "name": "W03 Room", "member_character_ids": [chars["ann"], chars["bo"]]})
        assert room.status_code == 200, room.text
        gid = room.json()["id"]
        assert room.json()["member_count"] == 2
        # FIX-STUB heal (contract change, listed in the slice report):
        # a room generates through its own chat's pinned profile, so
        # pin the w03-live profile to the room chat — the same pin
        # the 1:1 chat above carries — or the guard honestly refuses
        # and these turns would be stub replies (they were, silently,
        # before FIX-STUB: deepening ignored every pin).
        pin = web.post(
            f"/webface/chats/{room.json()['chat_id']}/backend-profile",
            json={"profile_id": profile_id})
        assert pin.status_code == 200, pin.text
        # In-order strategy, then the user speaks.
        patched = web.patch(f"/webface/groups/{gid}",
                            json={"speaker_policy": "list"})
        assert patched.json()["speaker_policy"] == "list"
        said = web.post(f"/webface/groups/{gid}/messages",
                        json={"content": "Welcome, both of you."})
        assert said.status_code == 200, said.text
        # In-order turns cycle the roster (real generated replies).
        speakers = []
        for _ in range(2):
            turn = web.post(f"/webface/groups/{gid}/next",
                            json={"generate": True})
            assert turn.status_code == 200, turn.text
            speakers.append(turn.json()["result"]["speaker_id"])
            assert turn.json()["words"].startswith("Next speaker:")
            content = turn.json()["result"]["message"]["content"]
            assert "This is a stub" not in content
        assert speakers == [chars["ann"], chars["bo"]], speakers
        # Manual pick honoured.
        manual = web.post(f"/webface/groups/{gid}/next", json={
            "generate": False, "manual_speaker_id": chars["ann"]})
        assert manual.json()["result"]["speaker_id"] == chars["ann"]
        # Run turns returns words for every turn.
        ran = web.post(f"/webface/groups/{gid}/run",
                       json={"turns": 1, "generate": False})
        assert ran.json()["result"]["turns_run"] == 1
        assert "Ran 1 turn." in ran.json()["words"]
        # Member settings: talkativeness + mute persist.
        member = web.patch(f"/webface/groups/{gid}/members/{chars['bo']}",
                           json={"talkativeness": 0.9, "muted": False})
        assert member.status_code == 200, member.text
        # A "never" override removes Bo from selection; peek flips
        # to the override source once a persona override exists.
        over = web.patch(f"/webface/groups/{gid}/members/{chars['bo']}/override",
                         json={"activation": "never",
                               "persona_override": "Bo, the quiet smith."})
        assert over.status_code == 200, over.text
        for _ in range(2):
            turn = web.post(f"/webface/groups/{gid}/next",
                            json={"generate": False})
            assert turn.json()["result"]["speaker_id"] == chars["ann"]
        peek = web.get(f"/webface/groups/{gid}/members/{chars['bo']}/peek")
        assert "override" in peek.json()["words"], peek.json()
        assert "quiet smith" in peek.json()["words"]
        # Leave -> presence says away; return -> digest + here again.
        left = web.post(f"/webface/groups/{gid}/members/{chars['bo']}/leave",
                        json={})
        assert left.status_code == 200, left.text
        web.post(f"/webface/groups/{gid}/messages",
                 json={"content": "Bo, you missed a thing."})
        presence = web.get(f"/webface/groups/{gid}/presence").json()
        assert any("Bo" in line and "away" in line
                   for line in presence["lines"]), presence
        digest = web.get(f"/webface/groups/{gid}/members/{chars['bo']}/digest")
        assert digest.status_code == 200, digest.text
        assert "missed a thing" in digest.json()["words"], digest.json()
        back = web.post(f"/webface/groups/{gid}/members/{chars['bo']}/return",
                        json={})
        assert back.status_code == 200, back.text
        assert "missed a thing" in back.json()["words"], back.json()
        presence = web.get(f"/webface/groups/{gid}/presence").json()
        assert any("Bo" in line and "here" in line
                   for line in presence["lines"]), presence
        # Room settings: rename + strategy + deepening, composed.
        renamed = web.patch(f"/webface/groups/{gid}",
                            json={"name": "W03 Room Renamed",
                                  "speaker_policy": "pooled"})
        assert renamed.json()["name"] == "W03 Room Renamed"
        saved = web.put(f"/webface/groups/{gid}/deepening", json={
            "generation_mode": "join", "allow_self_responses": True,
            "auto_enabled": False, "auto_max_turns": 3,
            "join_prefix": "", "join_suffix": "", "scenario_override": ""})
        assert saved.status_code == 200, saved.text
        deep = web.get(f"/webface/groups/{gid}/deepening").json()
        assert deep["generation_mode"] == "join"
        assert deep["member_overrides"][chars["bo"]]["activation"] == "never"
        # Transcript in words carries speaker names.
        transcript = web.get(f"/webface/groups/{gid}/messages").json()
        assert any(line.startswith("You:") for line in transcript["lines"])
        assert len(transcript["messages"]) >= 4
        # Webface-only restart: room, transcript and chat actions'
        # results are all still served (engine-side state).
        live_pair["restart_face"]()
        reg2 = web.post("/login", data={
            "username": "w03live", "password": "long-enough-1"})
        assert reg2.status_code == 303
        room2 = web.get(f"/webface/groups/{gid}").json()
        assert room2["name"] == "W03 Room Renamed"
        transcript2 = web.get(f"/webface/groups/{gid}/messages").json()
        assert transcript2["lines"] == transcript["lines"]
        msgs2 = web.get(f"/webface/chats/{chat_id}/messages").json()
        assert msgs2[-1]["content"].strip() == reply.strip()
        note2 = web.get(f"/webface/chats/{chat_id}/authors-note").json()
        assert note2["text"] == "Keep answers short."
