"use strict";
/* Rúnmál web face — Groups tab (W-03, R-11 parity). Rooms over the
   engine's groups roads: roster create, transcript in words (speaker
   names, never colour alone), say-as-user, next/run turns with the
   pick + reason in words, per-member settings + deepening overrides,
   peek, leave/return with digest, presence in words, room settings
   saved composed over the stored document. */
const gels = {
  name: document.getElementById("g-name"),
  create: document.getElementById("g-create"),
  pick: document.getElementById("g-roster-pick"),
  list: document.getElementById("g-list"),
  status: document.getElementById("g-status"),
  room: document.getElementById("g-room"),
};
const gstate = { groupId: null, group: null, characters: [] };
const POLICIES = [["natural", "Natural — mentions and the flow of talk decide"], ["list", "In order — take turns round the roster"], ["pooled", "Pooled — weighted by talkativeness"], ["manual", "Manual — you pick each speaker"]];
const MODES = [["swap", "Swap — one voice at a time, in turn"], ["join", "Join — members speak into one shared reply"]];
const ACTIVATIONS = [["default", "Default — the strategy may pick them"], ["force", "Force — pick them whenever possible"], ["never", "Never — never pick them"]];

function gStatus(t) { gels.status.textContent = t || ""; }
async function gapi(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) {
    let detail = "request failed (" + resp.status + ")";
    try { const b = await resp.json(); if (b.error) detail = b.error; } catch (e) { /* keep */ }
    throw new Error(detail);
  }
  return resp.json();
}
function jopt(method, body) { return { method: method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }; }
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }
function btn(label, fn, ghost) { const b = el("button", label, "btn small" + (ghost ? " ghost" : "")); b.type = "button"; b.addEventListener("click", () => fn().catch((e) => gStatus("Error: " + e.message))); return b; }
function selectOf(options, value) { const s = document.createElement("select"); for (const [v, l] of options) { const o = el("option", l); o.value = v; if (v === value) o.selected = true; s.appendChild(o); } return s; }

async function loadGroups(openId) {
  const groups = await gapi("/webface/groups");
  gels.list.innerHTML = "";
  for (const g of groups) {
    const li = el("li", null, "roster-row");
    li.appendChild(el("span", (g.name || "Untitled room") + " — " + (g.member_count || 0) + " member(s) · " + (g.message_count || 0) + " messages"));
    li.appendChild(btn("Open", async () => openRoom(g.id), true));
    gels.list.appendChild(li);
  }
  if (openId) await openRoom(openId);
  return groups;
}

async function loadRosterPick() {
  gstate.characters = await gapi("/webface/characters");
  gels.pick.innerHTML = "";
  for (const ch of gstate.characters) {
    const label = el("label", null, "check");
    const box = document.createElement("input"); box.type = "checkbox"; box.value = ch.id; box.className = "g-pick";
    label.appendChild(box); label.appendChild(document.createTextNode(" " + (ch.name || ch.id)));
    gels.pick.appendChild(label);
  }
}

async function createRoom() {
  const ids = Array.from(document.querySelectorAll(".g-pick:checked")).map((b) => b.value);
  const group = await gapi("/webface/groups", jopt("POST", { name: gels.name.value, member_character_ids: ids }));
  gStatus("Room created: " + (group.name || group.id));
  await loadGroups(group.id);
}

function renderGroupNoMind(payload) {
  const box = gstate.noMindBox; if (!box) { gStatus(payload.words || ""); return; }
  box.innerHTML = "";
  const card = el("div", null, "card no-mind-card");
  card.appendChild(el("p", payload.words || "No mind is connected to this chat yet"));
  for (const c of payload.connect || []) {
    card.appendChild(btn("Connect " + (c.name || c.profile_id), async () => {
      await gapi("/webface/chats/" + payload.chat_id + "/backend-profile", jopt("POST", { profile_id: c.profile_id }));
      gStatus("Connected " + (c.name || c.profile_id) + " to this room.");
      await openRoom(gstate.groupId);
    }));
  }
  const link = el("a", "Connections"); link.href = payload.connections_url || "/connections"; card.appendChild(link);
  if (!payload.has_real_profiles) {
    card.appendChild(el("p", "No real mind exists yet — connect one in Connections or First-Run Setup.", "muted"));
    const l2 = el("a", "First-Run Setup"); l2.href = payload.firstrun_url || "/firstrun"; card.appendChild(l2);
  }
  box.appendChild(card);
}
async function groupBlocked(err, groupId) {
  try {
    const mind = await gapi("/webface/groups/" + groupId + "/mind");
    if (mind && mind.state === "none" && mind.no_mind) { renderGroupNoMind(mind.no_mind); gStatus(mind.no_mind.words); return; }
  } catch (e) { /* fall through to the plain error */ }
  gStatus("Error: " + err.message);
}

async function openRoom(groupId) {
  gstate.groupId = groupId;
  gstate.group = await gapi("/webface/groups/" + groupId);
  await renderRoom();
}

async function renderRoom() {
  const g = gstate.group; if (!g) return;
  const room = gels.room; room.hidden = false; room.innerHTML = "";
  room.appendChild(el("h2", g.name || "Untitled room"));
  room.appendChild(el("p", "Strategy: " + (g.speaker_policy || "natural"), "muted"));
  // FIX-STUB: the room's mind is its own chat's pinned profile.
  const noMindBox = el("div", null, "no-mind-box");
  try {
    const mind = await gapi("/webface/groups/" + g.id + "/mind");
    gstate.mind = mind;
    room.appendChild(el("p", mind.words || "", "mind-line"));
  } catch (e) { /* the guard still refuses honestly without the line */ }
  room.appendChild(noMindBox);
  gstate.noMindBox = noMindBox;
  const data = await gapi("/webface/groups/" + g.id + "/messages");
  const transcript = el("div", null, "messages");
  for (const line of data.lines || []) transcript.appendChild(el("p", line));
  if (!(data.lines || []).length) transcript.appendChild(el("p", "No one has spoken yet.", "muted"));
  room.appendChild(transcript);
  // say as user
  const sayRow = el("div", null, "row");
  const sayText = document.createElement("textarea"); sayText.rows = 2; sayText.placeholder = "Say something as yourself…";
  sayRow.appendChild(sayText);
  sayRow.appendChild(btn("Say it", async () => {
    await gapi("/webface/groups/" + g.id + "/messages", jopt("POST", { content: sayText.value }));
    await openRoom(g.id);
  }));
  room.appendChild(sayRow);
  // turns
  const turnRow = el("div", null, "row");
  const speakerPick = selectOf([["", "Speaker: strategy decides"]].concat((g.members || []).map((m) => [m.character_id, "Speaker: " + (m.name || m.character_id)])), "");
  turnRow.appendChild(speakerPick);
  const genLabel = el("label", null, "check"); const gen = document.createElement("input"); gen.type = "checkbox"; gen.checked = true;
  genLabel.appendChild(gen); genLabel.appendChild(document.createTextNode(" Generate the reply")); turnRow.appendChild(genLabel);
  const words = el("p", "", "muted");
  turnRow.appendChild(btn("Next turn", async () => {
    try {
      const out = await gapi("/webface/groups/" + g.id + "/next", jopt("POST", { generate: gen.checked, manual_speaker_id: speakerPick.value || undefined }));
      words.textContent = out.words || "";
      await openRoom(g.id); words.textContent = out.words || ""; gels.room.querySelector(".turn-words").textContent = out.words || "";
    } catch (e) { await groupBlocked(e, g.id); }
  }));
  const runCount = document.createElement("input"); runCount.type = "number"; runCount.value = 2; runCount.min = 1; runCount.max = 10;
  turnRow.appendChild(runCount);
  turnRow.appendChild(btn("Run turns", async () => {
    try {
      const out = await gapi("/webface/groups/" + g.id + "/run", jopt("POST", { turns: Number(runCount.value), generate: gen.checked }));
      await openRoom(g.id); gels.room.querySelector(".turn-words").textContent = out.words || "";
    } catch (e) { await groupBlocked(e, g.id); }
  }, true));
  room.appendChild(turnRow);
  words.className = "turn-words muted"; room.appendChild(words);
  // presence
  const presence = await gapi("/webface/groups/" + g.id + "/presence");
  const presBox = el("div"); presBox.appendChild(el("h3", "Presence"));
  for (const line of presence.lines || []) presBox.appendChild(el("p", line));
  room.appendChild(presBox);
  // roster
  const rosterBox = el("div"); rosterBox.appendChild(el("h3", "Roster"));
  for (const m of g.members || []) rosterBox.appendChild(memberRow(g, m));
  room.appendChild(rosterBox);
  // settings
  room.appendChild(await settingsBox(g));
}

function memberRow(g, m) {
  const box = el("div", null, "card");
  box.appendChild(el("h4", (m.name || m.character_id) + " · talkativeness " + m.talkativeness + (m.muted ? " · muted" : "")));
  const talk = document.createElement("input"); talk.type = "number"; talk.step = "0.1"; talk.min = 0; talk.max = 1; talk.value = m.talkativeness;
  const talkL = el("label", "Talkativeness "); talkL.appendChild(talk); box.appendChild(talkL);
  const muteL = el("label", null, "check"); const mute = document.createElement("input"); mute.type = "checkbox"; mute.checked = !!m.muted;
  muteL.appendChild(mute); muteL.appendChild(document.createTextNode(" Muted")); box.appendChild(muteL);
  box.appendChild(btn("Save member settings", async () => {
    await gapi("/webface/groups/" + g.id + "/members/" + m.character_id, jopt("PATCH", { talkativeness: Number(talk.value), muted: mute.checked }));
    gStatus("Member settings saved for " + (m.name || m.character_id) + "."); await openRoom(g.id);
  }, true));
  // deepening override editor
  const act = selectOf(ACTIVATIONS, "default"); act.dataset.member = m.character_id;
  const actL = el("label", "Activation override "); actL.appendChild(act); box.appendChild(actL);
  const lore = document.createElement("textarea"); lore.rows = 2; lore.placeholder = "Lore override…"; box.appendChild(lore);
  const persona = document.createElement("textarea"); persona.rows = 2; persona.placeholder = "Persona override…"; box.appendChild(persona);
  box.appendChild(btn("Save override", async () => {
    const patch = { activation: act.value };
    if (lore.value) patch.lore_override = lore.value;
    if (persona.value) patch.persona_override = persona.value;
    await gapi("/webface/groups/" + g.id + "/members/" + m.character_id + "/override", jopt("PATCH", patch));
    gStatus("Override saved for " + (m.name || m.character_id) + " (activation: " + act.value + ").");
  }, true));
  const peekOut = el("p", "", "muted");
  box.appendChild(btn("Peek", async () => {
    const out = await gapi("/webface/groups/" + g.id + "/members/" + m.character_id + "/peek");
    peekOut.textContent = out.words || "";
  }, true));
  box.appendChild(peekOut);
  const digestOut = el("p", "", "muted");
  box.appendChild(btn("Leave", async () => {
    await gapi("/webface/groups/" + g.id + "/members/" + m.character_id + "/leave", jopt("POST", {}));
    gStatus((m.name || m.character_id) + " has left the room."); await openRoom(g.id);
  }, true));
  box.appendChild(btn("Return", async () => {
    const out = await gapi("/webface/groups/" + g.id + "/members/" + m.character_id + "/return", jopt("POST", {}));
    gStatus((m.name || m.character_id) + " is back."); await openRoom(g.id);
    digestOut.textContent = out.words || "";
  }, true));
  box.appendChild(digestOut);
  return box;
}

async function settingsBox(g) {
  const box = el("div", null, "card");
  box.appendChild(el("h3", "Room Settings"));
  const nameL = el("label", "Name "); const name = document.createElement("input"); name.value = g.name || ""; nameL.appendChild(name); box.appendChild(nameL);
  const policy = selectOf(POLICIES, g.speaker_policy || "natural");
  const polL = el("label", "Speaker strategy "); polL.appendChild(policy); box.appendChild(polL);
  const deep = await gapi("/webface/groups/" + g.id + "/deepening");
  const mode = selectOf(MODES, deep.generation_mode || "swap");
  const modeL = el("label", "Generation mode "); modeL.appendChild(mode); box.appendChild(modeL);
  const selfL = el("label", null, "check"); const selfR = document.createElement("input"); selfR.type = "checkbox"; selfR.checked = !!deep.allow_self_responses;
  selfL.appendChild(selfR); selfL.appendChild(document.createTextNode(" Allow self-responses")); box.appendChild(selfL);
  const auto = deep.auto_mode || {};
  const autoL = el("label", null, "check"); const autoE = document.createElement("input"); autoE.type = "checkbox"; autoE.checked = !!auto.enabled;
  autoL.appendChild(autoE); autoL.appendChild(document.createTextNode(" Auto mode")); box.appendChild(autoL);
  const maxL = el("label", "Auto max turns "); const maxT = document.createElement("input"); maxT.type = "number"; maxT.value = auto.max_turns || 3; maxL.appendChild(maxT); box.appendChild(maxL);
  const fields = {};
  for (const key of ["join_prefix", "join_suffix", "scenario_override"]) {
    const l = el("label", key + " "); const t = document.createElement("textarea"); t.rows = 2; t.value = deep[key] || ""; l.appendChild(t); box.appendChild(l); fields[key] = t;
  }
  box.appendChild(btn("Save room settings", async () => {
    await gapi("/webface/groups/" + g.id, jopt("PATCH", { name: name.value, speaker_policy: policy.value }));
    await gapi("/webface/groups/" + g.id + "/deepening", jopt("PUT", {
      generation_mode: mode.value, allow_self_responses: selfR.checked,
      auto_enabled: autoE.checked, auto_max_turns: Number(maxT.value),
      join_prefix: fields.join_prefix.value, join_suffix: fields.join_suffix.value,
      scenario_override: fields.scenario_override.value }));
    gStatus("Room settings saved — name, strategy and deepening composed over the stored document.");
    await openRoom(g.id);
  }));
  return box;
}

gels.create.addEventListener("click", () => createRoom().catch((e) => gStatus("Error: " + e.message)));
(async () => {
  try { await loadRosterPick(); await loadGroups(); }
  catch (err) { gStatus("Error: " + err.message); }
})();
