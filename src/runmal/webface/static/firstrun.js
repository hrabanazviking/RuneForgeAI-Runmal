"use strict";
/* Runmal web face - First-Run Setup (W-04, R-05 parity).
   Connect a mind -> prove it -> meet someone -> your name.
   Choosing a different mind after a draft was connected deletes
   the draft (the server composes that; this script passes the
   draft id along). Demo is labelled not-a-real-model in its
   title, blurb and the confirmation line. */
const $ = (id) => document.getElementById(id);
const state = { options: [], chosen: null, draftId: "", profileId: "", chatId: "" };
async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let d = "request failed (" + resp.status + ")"; try { const b = await resp.json(); if (b.error) d = b.error; } catch (e) {} throw new Error(d); }
  return resp.json();
}
function jsonOpts(method, body) { return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }; }
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }
function setStatus(t) { $("fr-status").textContent = t || ""; }

async function loadState() {
  const s = await api("/webface/firstrun/status");
  $("fr-state").textContent = s.first_run ? "This Runmal has no backend profile and no character yet - this is a first run. Walk the four steps below." : "This Runmal is already set up (" + s.profile_count + " profile(s), " + s.character_count + " character(s)). You can still run the flow again here.";
  const name = await api("/webface/user-name");
  if (name.user_name) $("fr-name").placeholder = name.user_name;
}
async function loadOptions() {
  state.options = await api("/webface/firstrun/options");
  const box = $("fr-minds"); box.innerHTML = "";
  for (const o of state.options) {
    const b = el("button", o.title, "btn ghost"); b.type = "button";
    b.addEventListener("click", () => choose(o));
    box.appendChild(b);
  }
}
function choose(o) {
  state.chosen = o;
  const box = $("fr-connect"); box.innerHTML = "";
  box.appendChild(el("h3", o.title));
  box.appendChild(el("p", o.blurb, "muted"));
  const fields = {};
  function addField(label, key, value, password) {
    const input = document.createElement("input"); input.value = value || ""; if (password) input.type = "password";
    const l = el("label", label); l.appendChild(input); box.appendChild(l); fields[key] = input;
  }
  if (o.needs_base_url) addField("Server address", "base_url", o.default_base_url);
  addField("Model name", "chat_model", o.default_model);
  if (o.needs_api_key) addField("API key (write-only - stored, never shown back)", "api_key", "", true);
  const go = el("button", "Connect this mind", "btn"); go.type = "button";
  go.addEventListener("click", async () => {
    try {
      const body = { kind: o.kind, draft_id: state.draftId };
      for (const k of Object.keys(fields)) body[k] = fields[k].value;
      const profile = await api("/webface/firstrun/connect", jsonOpts("POST", body));
      if (fields.api_key) fields.api_key.value = "";
      if (!state.profileId) state.draftId = profile.id;
      state.profileId = profile.id;
      const confirm = o.kind === "fake" ? "Connected: Demo mode - not a real model. Its replies are canned." : "Connected: " + profile.name + " (" + profile.backend_label + "). Chat key: " + profile.secret_words.chat + ".";
      setStatus(confirm);
      await prove(profile.id);
      buildMeet();
      loadState();
    } catch (e) { setStatus("Connect failed: " + e.message); }
  });
  box.appendChild(go);
}
async function prove(profileId) {
  $("fr-prove").textContent = "Proving the connection...";
  try { const r = await api("/webface/firstrun/prove", jsonOpts("POST", { profile_id: profileId })); $("fr-prove").textContent = r.words; }
  catch (e) { $("fr-prove").textContent = "Prove failed: " + e.message; }
}
function buildMeet() {
  const box = $("fr-meet"); box.innerHTML = "";
  const name = document.createElement("input");
  const nameL = el("label", "Character name"); nameL.appendChild(name); box.appendChild(nameL);
  const desc = document.createElement("textarea");
  const descL = el("label", "A few lines about them"); descL.appendChild(desc); box.appendChild(descL);
  const greet = document.createElement("input");
  const greetL = el("label", "Their first greeting"); greetL.appendChild(greet); box.appendChild(greetL);
  const create = el("button", "Create and open our first chat", "btn"); create.type = "button";
  create.addEventListener("click", async () => {
    try {
      const r = await api("/webface/firstrun/meet", jsonOpts("POST", { mode: "create", name: name.value, description: desc.value, first_mes: greet.value, profile_id: state.profileId }));
      state.chatId = r.chat.id;
      setStatus("Met " + (r.character.name || "your character") + ". The greeted chat is open and " + (r.pinned ? "the chosen mind is pinned to it." : "ready.") + (r.greeting ? " They say: " + r.greeting : ""));
      $("fr-finish").disabled = false;
      loadState();
    } catch (e) { setStatus("Meet failed: " + e.message); }
  });
  box.appendChild(create);
  box.appendChild(el("p", "Or import a character card (JSON or PNG):", "muted"));
  const file = document.createElement("input"); file.type = "file"; file.accept = ".json,.png"; box.appendChild(file);
  const imp = el("button", "Import card and open our first chat", "btn ghost"); imp.type = "button";
  imp.addEventListener("click", async () => {
    try {
      if (!file.files.length) { setStatus("Pick a card file first."); return; }
      const fd = new FormData(); fd.append("files", file.files[0]);
      const report = await api("/webface/firstrun/import", { method: "POST", body: fd });
      const cid = (report.created_ids || [])[0];
      if (!cid) { setStatus("Import: " + (report.words || "nothing landed.")); return; }
      const r = await api("/webface/firstrun/meet", jsonOpts("POST", { mode: "import", character_id: cid, profile_id: state.profileId }));
      state.chatId = r.chat.id; $("fr-finish").disabled = false;
      setStatus("Imported and met " + (r.character.name || "your character") + ". " + (report.words || ""));
      loadState();
    } catch (e) { setStatus("Import failed: " + e.message); }
  });
  box.appendChild(imp);
}
$("fr-name-save").addEventListener("click", async () => {
  try {
    const r = await api("/webface/user-name", jsonOpts("PUT", { user_name: $("fr-name").value }));
    setStatus(r.kept ? "The field was empty, so your name stays '" + r.user_name + "' - an empty field never clears it." : "Your name is saved as '" + r.user_name + "'.");
  } catch (e) { setStatus("Name not saved: " + e.message); }
});
$("fr-finish").addEventListener("click", () => { window.location = "/chat" + (state.chatId ? "#" + state.chatId : ""); });
loadOptions().then(loadState).catch((e) => setStatus("Could not load: " + e.message));
