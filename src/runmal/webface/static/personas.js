"use strict";
/* Runmal web face - Personas tab (W-05). Text-entry elements
   carry the shared "entry-box" class (W-11 sweep hook). Two engine mechanisms
   only (R-03/R-10): the persisted {{user}} name and a chat's
   persona character. Empty never clears the name; clearing is
   its own button. Persona-file interop has no engine route, so
   there are deliberately no import/export controls here. */
const $ = (id) => document.getElementById(id);
const state = { chats: [], characters: [] };

async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let d = "request failed (" + resp.status + ")"; try { const b = await resp.json(); if (b.error) d = b.error; } catch (e) {} throw new Error(d); }
  return resp.json();
}
function jsonOpts(method, body) { return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }; }
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }

async function loadName() {
  const s = await api("/webface/persona/user-name");
  $("pn-current").textContent = s.words;
  $("pn-name").value = s.is_set ? s.user_name : "";
  $("pn-name").placeholder = s.is_set ? "" : s.user_name + " (default)";
}
async function loadPersona() {
  const chatId = $("pp-chat").value;
  if (!chatId) { $("pp-current").textContent = "No chats yet."; return; }
  const view = await api("/webface/chats/" + chatId + "/persona");
  $("pp-current").textContent = view.words + " " + view.note;
  if (view.persona && view.persona.character_id) $("pp-char").value = view.persona.character_id;
}
async function loadAll() {
  state.chats = await api("/webface/chats");
  state.characters = await api("/webface/characters");
  const chatSel = $("pp-chat"); chatSel.innerHTML = "";
  for (const c of state.chats) { const o = el("option", c.title || c.id); o.value = c.id; chatSel.appendChild(o); }
  const charSel = $("pp-char"); charSel.innerHTML = "";
  for (const ch of state.characters) { const o = el("option", ch.name || ch.id); o.value = ch.id; charSel.appendChild(o); }
  await loadName();
  await loadPersona();
}

$("pn-save").addEventListener("click", async () => {
  try {
    const s = await api("/webface/persona/user-name", jsonOpts("PUT", { user_name: $("pn-name").value }));
    $("pn-status").textContent = s.words;
    await loadName();
  } catch (e) { $("pn-status").textContent = e.message; }
});
$("pn-clear").addEventListener("click", async () => {
  try {
    const s = await api("/webface/persona/user-name", jsonOpts("PUT", { clear: true }));
    $("pn-status").textContent = s.words;
    await loadName();
  } catch (e) { $("pn-status").textContent = e.message; }
});
$("pp-chat").addEventListener("change", () => loadPersona().catch((e) => { $("pp-status").textContent = e.message; }));
$("pp-switch").addEventListener("click", async () => {
  try {
    const s = await api("/webface/chats/" + $("pp-chat").value + "/persona", jsonOpts("POST", { character_id: $("pp-char").value }));
    $("pp-status").textContent = s.words + " " + s.note;
    await loadPersona();
  } catch (e) { $("pp-status").textContent = e.message; }
});
$("pp-clear").addEventListener("click", async () => {
  try {
    const s = await api("/webface/chats/" + $("pp-chat").value + "/persona", jsonOpts("POST", { character_id: null }));
    $("pp-status").textContent = s.words + " " + s.note;
    await loadPersona();
  } catch (e) { $("pp-status").textContent = e.message; }
});
loadAll().catch((e) => { $("pn-status").textContent = e.message; });
