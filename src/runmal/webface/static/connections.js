"use strict";
/* Runmal web face - Connections tab (W-04). Profiles over the
   R-02 roads via the webface. API keys are write-only: the form
   offers Leave / Set new / Clear per key and the page only ever
   displays stored-or-not words. A fake-kind profile is labelled
   Demo everywhere it appears. */
const $ = (id) => document.getElementById(id);
const state = { profiles: [], editing: null, models: [] };

async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) {
    let detail = "request failed (" + resp.status + ")";
    try { const b = await resp.json(); if (b.error) detail = b.error; } catch (e) {}
    throw new Error(detail);
  }
  return resp.json();
}
function jsonOpts(method, body) {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) };
}
function setStatus(t) { $("p-status").textContent = t || ""; }
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }

const KIND_LABELS = { fake: "Demo (canned replies, not a real model)", ollama: "Ollama (on this computer)", openrouter: "OpenRouter (online)", aesir: "Aesir (Runmal's own engine, local)", openai: "OpenAI-compatible (your own server)" };
const EMB_LABELS = { "": "None (no embeddings)", fake: "Demo (fake embeddings)", ollama: "Ollama (on this computer)", aesir: "Aesir (local)", openai: "OpenAI-compatible" };

async function loadProfiles() {
  state.profiles = await api("/webface/profiles");
  const list = $("p-list"); list.innerHTML = "";
  for (const p of state.profiles) {
    const li = el("li", null, "roster-row");
    const label = p.backend_label || KIND_LABELS[p.chat_backend] || p.chat_backend;
    li.appendChild(el("span", (p.name || p.id) + " - " + label + (p.chat_model ? " - model " + p.chat_model : "") + " - chat key: " + p.secret_words.chat + " - embedding key: " + p.secret_words.embedding));
    if (p.is_demo) li.appendChild(el("span", "Demo - not a real model", "tag"));
    const edit = el("button", "Edit", "btn small ghost"); edit.type = "button";
    edit.addEventListener("click", () => openEditor(p));
    const probe = el("button", "Test", "btn small ghost"); probe.type = "button";
    probe.addEventListener("click", () => doProbe(p.id));
    const del = el("button", "Delete", "btn small ghost"); del.type = "button";
    del.addEventListener("click", () => doDelete(p));
    li.appendChild(edit); li.appendChild(probe); li.appendChild(del);
    list.appendChild(li);
  }
  if (!state.profiles.length) setStatus("No profiles yet - create one below.");
  fillPinSelects();
}

function fillPinSelects() {
  const sel = $("pin-profile"); sel.innerHTML = "";
  for (const p of state.profiles) {
    const o = el("option", (p.name || p.id) + (p.is_demo ? " (Demo - not a real model)" : "")); o.value = p.id; sel.appendChild(o);
  }
}
async function fillChats() {
  const chats = await api("/webface/chats");
  const sel = $("pin-chat"); sel.innerHTML = "";
  for (const c of chats) { const o = el("option", c.title || ("Chat " + c.id.slice(0, 8))); o.value = c.id; sel.appendChild(o); }
  sel.addEventListener("change", showPinState);
  showPinState();
}
async function showPinState() {
  const chats = await api("/webface/chats");
  const chat = chats.find((c) => c.id === $("pin-chat").value);
  if (!chat) { $("pin-status").textContent = ""; return; }
  if (chat.backend_profile_id) {
    const p = state.profiles.find((x) => x.id === chat.backend_profile_id);
    $("pin-status").textContent = "This chat is pinned to: " + (p ? p.name : chat.backend_profile_id) + (p && p.is_demo ? " (Demo - not a real model)" : "");
    $("pin-profile").value = chat.backend_profile_id;
  } else $("pin-status").textContent = "No profile is pinned to this chat - the engine default answers.";
}

function field(labelText, input) { const l = el("label", labelText); l.appendChild(input); return l; }
function textInput(value) { const i = document.createElement("input"); i.value = value || ""; return i; }
function selectOf(labels, value) {
  const s = document.createElement("select");
  for (const k of Object.keys(labels)) { const o = el("option", labels[k]); o.value = k; s.appendChild(o); }
  s.value = value || ""; return s;
}
function secretControl(storedWords) {
  const wrap = el("span");
  const sel = document.createElement("select");
  for (const [v, t] of [["leave", "Leave as is"], ["set", "Set a new key"], ["clear", "Clear the stored key"]]) { const o = el("option", t); o.value = v; sel.appendChild(o); }
  const input = document.createElement("input"); input.type = "password"; input.placeholder = "new key (write-only)"; input.hidden = true;
  sel.addEventListener("change", () => { input.hidden = sel.value !== "set"; });
  wrap.appendChild(sel); wrap.appendChild(el("span", " - currently: " + storedWords, "muted")); wrap.appendChild(input);
  return { wrap, sel, input };
}

function openEditor(p) {
  state.editing = p ? p.id : null;
  const box = $("p-editor"); box.hidden = false; box.innerHTML = "";
  box.appendChild(el("h2", p ? "Edit profile" : "New profile"));
  if (p && p.is_demo) box.appendChild(el("p", "Demo - not a real model.", "muted"));
  const name = textInput(p ? p.name : "");
  const kind = selectOf(KIND_LABELS, p ? p.chat_backend : "ollama");
  const model = textInput(p ? p.chat_model : "");
  const modelPick = document.createElement("select");
  const embKind = selectOf(EMB_LABELS, p ? p.embedding_backend : "");
  const embModel = textInput(p ? p.embedding_model : "");
  const baseUrl = textInput(p ? p.base_url : "");
  const stt = textInput(p ? p.stt_ref : "");
  const tts = textInput(p ? p.tts_ref : "");
  const chatKey = secretControl(p ? p.secret_words.chat : "no key stored");
  const embKey = secretControl(p ? p.secret_words.embedding : "no key stored");
  box.appendChild(field("Name", name));
  box.appendChild(field("Chat backend", kind));
  box.appendChild(field("Chat model (or pick from the probe list)", model));
  box.appendChild(field("Models this profile reports", modelPick));
  modelPick.addEventListener("change", () => { if (modelPick.value) model.value = modelPick.value; });
  box.appendChild(field("Embedding backend", embKind));
  box.appendChild(field("Embedding model", embModel));
  box.appendChild(field("Server address (base URL, from config)", baseUrl));
  box.appendChild(field("Speech-to-text reference", stt));
  box.appendChild(field("Text-to-speech reference", tts));
  box.appendChild(field("Chat API key", chatKey.wrap));
  box.appendChild(field("Embedding API key", embKey.wrap));
  const verdict = el("p", "", "muted"); box.appendChild(verdict);
  const save = el("button", "Save, then test", "btn"); save.type = "button";
  save.addEventListener("click", async () => {
    try {
      const body = { name: name.value, chat_backend: kind.value, chat_model: model.value, embedding_backend: embKind.value, embedding_model: embModel.value, base_url: baseUrl.value, stt_ref: stt.value, tts_ref: tts.value, chat_secret_action: chatKey.sel.value, chat_secret: chatKey.input.value, embedding_secret_action: embKey.sel.value, embedding_secret: embKey.input.value };
      const saved = state.editing ? await api("/webface/profiles/" + state.editing, jsonOpts("PATCH", body)) : await api("/webface/profiles", jsonOpts("POST", body));
      chatKey.input.value = ""; embKey.input.value = "";
      state.editing = saved.id;
      setStatus("Saved '" + saved.name + "'. Chat key: " + saved.secret_words.chat + ".");
      await loadProfiles();
      const probe = await api("/webface/profiles/" + saved.id + "/probe");
      verdict.textContent = probe.words;
      modelPick.innerHTML = "";
      for (const m of probe.models) { const o = el("option", m); o.value = m; modelPick.appendChild(o); }
      if (probe.models.length && !model.value) model.value = probe.models[0];
    } catch (e) { verdict.textContent = "Not saved: " + e.message; }
  });
  box.appendChild(save);
  const cancel = el("button", "Close", "btn ghost"); cancel.type = "button";
  cancel.addEventListener("click", () => { box.hidden = true; });
  box.appendChild(cancel);
}

async function doProbe(id) {
  setStatus("Testing...");
  try { const probe = await api("/webface/profiles/" + id + "/probe"); setStatus(probe.words); }
  catch (e) { setStatus("Test failed: " + e.message); }
}
async function doDelete(p) {
  if (!window.confirm("Delete profile '" + p.name + "'? Chats pinned to it fall back to the engine default.")) return;
  try { await api("/webface/profiles/" + p.id, { method: "DELETE" }); setStatus("Deleted '" + p.name + "'."); await loadProfiles(); }
  catch (e) { setStatus("Delete failed: " + e.message); }
}

async function pin(profileId) {
  const chatId = $("pin-chat").value;
  if (!chatId) { $("pin-status").textContent = "No chat to pin to."; return; }
  try {
    const chat = await api("/webface/chats/" + chatId + "/backend-profile", jsonOpts("POST", { profile_id: profileId }));
    $("pin-status").textContent = chat.backend_profile_id ? "Pinned. This chat now answers through the chosen profile." : "Unpinned. The engine default answers this chat.";
    showPinState();
  } catch (e) { $("pin-status").textContent = "Pin failed: " + e.message; }
}

const addBtn = el("button", "New profile", "btn"); addBtn.type = "button";
addBtn.addEventListener("click", () => openEditor(null));
document.querySelector("#p-list").before(addBtn);
$("pin-apply").addEventListener("click", () => pin($("pin-profile").value || null));
$("pin-clear").addEventListener("click", () => pin(null));
loadProfiles().then(fillChats).catch((e) => setStatus("Could not load: " + e.message));
