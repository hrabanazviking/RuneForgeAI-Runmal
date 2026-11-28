"use strict";
/* Rúnmál web face — Chat tab. One shared script for the chat page:
   character list -> chat list -> open chat renders engine history ->
   send streams tokens live over the webface SSE relay -> Stop cancels
   the exact request id. History always comes from the engine. */
const els = {
  chars: document.getElementById("char-select"),
  chats: document.getElementById("chat-list"),
  messages: document.getElementById("messages"),
  composer: document.getElementById("composer"),
  send: document.getElementById("send"),
  stop: document.getElementById("stop"),
  newChat: document.getElementById("new-chat"),
  status: document.getElementById("chat-status"),
};
const state = { chatId: null, sending: false, requestId: null };

function setStatus(text) { els.status.textContent = text || ""; }

/* FIX-STUB: who answers this chat, and the honest no-mind walk.
   The disclosure line is refreshed whenever the chat or its pin
   changes; a no-mind outcome renders IN the chat with one Connect
   button per real profile — connecting never touches the composer. */
const mindEls = { line: document.getElementById("mind-line"), box: document.getElementById("no-mind") };
const mindState = { mind: null };
function renderMindLine() {
  if (mindEls.line) mindEls.line.textContent = mindState.mind ? (mindState.mind.words || "") : "";
  renderModelSelect();
}
async function loadMind() {
  if (!state.chatId) { mindState.mind = null; renderMindLine(); return null; }
  const mind = await api("/webface/chats/" + state.chatId + "/mind");
  mindState.mind = mind;
  renderMindLine();
  return mind;
}
function renderNoMind(payload, container) {
  const box = container || mindEls.box;
  if (!box) { setStatus(payload.words || "No mind is connected to this chat yet"); return; }
  box.innerHTML = "";
  box.dataset.chatId = payload.chat_id || state.chatId || "";
  const card = document.createElement("div"); card.className = "card no-mind-card";
  const p = document.createElement("p"); p.textContent = payload.words || "No mind is connected to this chat yet"; card.appendChild(p);
  for (const c of payload.connect || []) {
    const b = document.createElement("button"); b.className = "btn small"; b.type = "button";
    b.textContent = "Connect " + (c.name || c.profile_id);
    b.addEventListener("click", async () => {
      try {
        await api("/webface/chats/" + (payload.chat_id || state.chatId) + "/backend-profile", jsonOptions("POST", { profile_id: c.profile_id }));
        box.innerHTML = "";
        await loadMind();
        setStatus("Connected " + (c.name || c.profile_id) + " — your typed message is still in the composer; press Send when ready.");
      } catch (e) { setStatus("Error: " + e.message); }
    });
    card.appendChild(b);
  }
  const link = document.createElement("a"); link.href = payload.connections_url || "/connections"; link.textContent = "Connections"; card.appendChild(link);
  if (!payload.has_real_profiles) {
    const p2 = document.createElement("p"); p2.className = "muted";
    p2.textContent = "No real mind exists yet — connect one in Connections or First-Run Setup.";
    card.appendChild(p2);
    const link2 = document.createElement("a"); link2.href = payload.firstrun_url || "/firstrun"; link2.textContent = "First-Run Setup"; card.appendChild(link2);
  }
  box.appendChild(card);
}

async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) {
    let detail = "request failed (" + resp.status + ")";
    try { const body = await resp.json(); if (body.error) detail = body.error; }
    catch (err) { /* keep the status words */ }
    throw new Error(detail);
  }
  return resp.json();
}

function renderMessage(msg) {
  const div = document.createElement("div");
  div.className = "msg " + (msg.role || "");
  const role = document.createElement("span");
  role.className = "role";
  role.textContent = msg.role || "";
  const text = document.createElement("span");
  text.textContent = msg.content || "";
  div.appendChild(role);
  div.appendChild(text);
  return div;
}

async function loadCharacters() {
  const chars = await api("/webface/characters");
  els.chars.innerHTML = "";
  for (const ch of chars) {
    const opt = document.createElement("option");
    opt.value = ch.id;
    opt.textContent = ch.name || ch.id;
    els.chars.appendChild(opt);
  }
  if (!chars.length) setStatus("No characters yet — the Characters tab arrives in W-02; characters can be created on the desktop or via the engine API.");
  return chars;
}

async function loadChats(selectId) {
  const chats = await api("/webface/chats");
  els.chats.innerHTML = "";
  for (const chat of chats) {
    const li = document.createElement("li");
    li.textContent = chat.title || ("Chat " + chat.id.slice(0, 8));
    if (chat.id === state.chatId) li.className = "active";
    li.addEventListener("click", () => openChat(chat.id));
    els.chats.appendChild(li);
  }
  if (selectId) await openChat(selectId);
  return chats;
}

async function openChat(chatId) {
  state.chatId = chatId;
  // W-11: the composer draft is PER CHAT.
  if (window.RunmalEntryBox) window.RunmalEntryBox.bindDraft(els.composer, "chat:" + chatId + ":composer");
  else els.composer.setAttribute("data-draft-key", "chat:" + chatId + ":composer");
  if (mindEls.box && mindEls.box.dataset.chatId !== chatId) mindEls.box.innerHTML = "";
  loadMind().catch(() => {});
  const messages = await api("/webface/chats/" + chatId + "/messages");
  els.messages.innerHTML = "";
  for (const msg of messages) els.messages.appendChild(renderMessage(msg));
  els.messages.scrollTop = els.messages.scrollHeight;
  await loadChats();
}

async function newChat() {
  const characterId = els.chars.value;
  if (!characterId) { setStatus("Pick a character first."); return; }
  const chat = await api("/webface/chats", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ character_id: characterId }),
  });
  await loadChats(chat.id);
}

function newRequestId() {
  if (window.crypto && crypto.randomUUID) {
    return crypto.randomUUID().replace(/-/g, "");
  }
  return String(Date.now()) + Math.random().toString(16).slice(2);
}

async function send() {
  const content = els.composer.value.trim();
  if (!content) { setStatus("Write a message first."); return; }
  if (!state.chatId) { setStatus("Open or create a chat first."); return; }
  if (state.sending) return;
  state.sending = true;
  state.requestId = newRequestId();
  els.send.disabled = true;
  els.stop.disabled = false;
  els.messages.appendChild(renderMessage({ role: "user", content: content }));
  const bubble = renderMessage({ role: "assistant", content: "" });
  const bubbleText = bubble.querySelectorAll("span")[1];
  els.messages.appendChild(bubble);
  els.messages.scrollTop = els.messages.scrollHeight;
  setStatus("Thinking…");
  try {
    const resp = await fetch("/webface/chats/" + state.chatId + "/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: content, request_id: state.requestId }),
    });
    if (!resp.ok) throw new Error("send failed (" + resp.status + ")");
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let backend = "";
    let noMind = null;
    for (;;) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      let idx = buffer.indexOf("\n\n");
      while (idx >= 0) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        for (const line of frame.split("\n")) {
          if (!line.startsWith("data:")) continue;
          const event = JSON.parse(line.slice(5).trim());
          if (event.type === "token") {
            bubbleText.textContent += event.text || "";
            els.messages.scrollTop = els.messages.scrollHeight;
          } else if (event.type === "started") {
            backend = event.backend_key || "";
            setStatus("Streaming from " + (backend || "the engine") + "…");
          } else if (event.type === "error") {
            setStatus("Error: " + (event.message || "generation failed") +
              " — no reply was saved.");
          } else if (event.type === "landed") {
            setStatus("Reply saved to the engine history.");
          } else if (event.type === "no_mind") {
            noMind = event;
            renderNoMind(event);
            setStatus(event.words || "No mind is connected to this chat yet");
          }
        }
        idx = buffer.indexOf("\n\n");
      }
    }
    if (!noMind) { els.composer.value = ""; if (window.RunmalEntryBox) window.RunmalEntryBox.retireDraft(els.composer); }
    await openChat(state.chatId);
  } catch (err) {
    setStatus("Error: " + err.message);
  } finally {
    state.sending = false;
    state.requestId = null;
    els.send.disabled = false;
    els.stop.disabled = true;
  }
}

async function stop() {
  if (!state.chatId || !state.requestId) return;
  try {
    await api("/webface/chats/" + state.chatId + "/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: state.requestId }),
    });
    setStatus("Stop sent — a stopped stream saves no reply.");
  } catch (err) {
    setStatus("Error: " + err.message);
  }
}

els.newChat.addEventListener("click", () => newChat().catch((e) => setStatus("Error: " + e.message)));
els.send.addEventListener("click", send);
els.stop.addEventListener("click", stop);
els.composer.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); send(); }
});
(async () => {
  try {
    await loadCharacters();
    const chats = await loadChats();
    if (chats.length) await openChat(chats[0].id);
  } catch (err) {
    setStatus("Error: " + err.message);
  }
})();

/* ---- W-03: message actions + chat actions (R-07 parity) ---- */
const w03 = {
  messages: [], selectedId: null,
  msgList: document.getElementById("msg-list"),
  msgPanel: document.getElementById("msg-panel"),
  chatPanel: document.getElementById("chat-panel"),
};

function selectedMessage() {
  return w03.messages.find((m) => m.id === w03.selectedId) || null;
}

function msgLabel(m) {
  let label = (m.role || "") + ": " + (m.content || "").slice(0, 80);
  const deck = (m.swipes || []).length;
  if (deck > 1) label += " · swipe " + ((m.swipe_id || 0) + 1) + " of " + deck;
  if (m.pinned) label += " · pinned";
  return label;
}

function renderMsgList() {
  w03.msgList.innerHTML = "";
  for (const m of w03.messages) {
    const li = document.createElement("li");
    li.textContent = msgLabel(m);
    if (m.id === w03.selectedId) li.className = "active";
    li.addEventListener("click", () => { w03.selectedId = m.id; renderMsgList(); });
    w03.msgList.appendChild(li);
  }
}

const _openChatW01 = openChat;
openChat = async function (chatId) {
  await _openChatW01(chatId);
  try {
    w03.messages = await api("/webface/chats/" + chatId + "/messages");
    if (!selectedMessage()) w03.selectedId = w03.messages.length ? w03.messages[w03.messages.length - 1].id : null;
    renderMsgList();
  } catch (err) { setStatus("Error: " + err.message); }
};

async function refreshChat() { if (state.chatId) await openChat(state.chatId); }

function needSelection() {
  const m = selectedMessage();
  if (!m) { setStatus("Pick a message in the message list first."); return null; }
  return m;
}

function panel(parent, title) {
  parent.innerHTML = "";
  const box = document.createElement("div");
  box.className = "card";
  const h = document.createElement("h3");
  h.textContent = title;
  box.appendChild(h);
  parent.appendChild(box);
  return box;
}

function panelText(box, text) {
  const p = document.createElement("p");
  p.textContent = text;
  box.appendChild(p);
  return p;
}

function panelButton(box, label, fn) {
  const b = document.createElement("button");
  b.className = "btn small"; b.type = "button"; b.textContent = label;
  b.addEventListener("click", () => fn().catch((e) => setStatus("Error: " + e.message)));
  box.appendChild(b);
  return b;
}

function jsonOptions(method, body) {
  return { method: method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) };
}

async function actEdit() {
  const m = needSelection(); if (!m) return;
  const box = panel(w03.msgPanel, "Edit message");
  const ta = document.createElement("textarea");
  ta.rows = 4; ta.value = m.content || ""; ta.classList.add("entry-box");
  ta.setAttribute("data-draft-key", "chat:" + state.chatId + ":edit:" + m.id); box.appendChild(ta);
  panelButton(box, "Save edit", async () => {
    await api("/webface/chats/" + state.chatId + "/messages/" + m.id, jsonOptions("PATCH", { content: ta.value }));
    if (window.RunmalEntryBox) window.RunmalEntryBox.retireDraft(ta);
    setStatus("Message edited."); w03.msgPanel.innerHTML = ""; await refreshChat();
  });
}

async function actDelete() {
  const m = needSelection(); if (!m) return;
  if (!window.confirm("Delete this message? The engine journals the delete, so Undo can bring it back.")) return;
  await api("/webface/chats/" + state.chatId + "/messages/" + m.id, { method: "DELETE" });
  w03.selectedId = null; setStatus("Message deleted (journaled — see Checkpoints & Undo)."); await refreshChat();
}

async function actSwipe(action) {
  const m = needSelection(); if (!m) return;
  await api("/webface/chats/" + state.chatId + "/messages/" + m.id + "/swipes/select", jsonOptions("POST", { action: action }));
  await refreshChat();
}

async function actSwipes() {
  const m = needSelection(); if (!m) return;
  const fresh = await api("/webface/chats/" + state.chatId + "/messages");
  const cur = fresh.find((x) => x.id === m.id) || m;
  const box = panel(w03.msgPanel, "Swipes for the selected message");
  const deck = cur.swipes && cur.swipes.length ? cur.swipes : [cur.content || ""];
  deck.forEach((text, idx) => {
    const row = document.createElement("div"); row.className = "row";
    const label = document.createElement("span");
    label.textContent = (idx === (cur.swipe_id || 0) ? "● " : "") + "Swipe " + (idx + 1) + ": " + String(text).slice(0, 60);
    row.appendChild(label);
    const use = document.createElement("button"); use.className = "btn small ghost"; use.type = "button"; use.textContent = "Use";
    use.addEventListener("click", async () => {
      await api("/webface/chats/" + state.chatId + "/messages/" + m.id + "/swipes/select", jsonOptions("POST", { index: idx }));
      w03.msgPanel.innerHTML = ""; await refreshChat();
    });
    row.appendChild(use);
    if (deck.length > 1) {
      const del = document.createElement("button"); del.className = "btn small ghost"; del.type = "button"; del.textContent = "Delete";
      del.addEventListener("click", async () => {
        await api("/webface/chats/" + state.chatId + "/messages/" + m.id + "/swipes/" + idx, { method: "DELETE" });
        await actSwipes(); await refreshChat();
      });
      row.appendChild(del);
    }
    box.appendChild(row);
  });
  const ta = document.createElement("textarea"); ta.rows = 2; ta.placeholder = "New alternate text…"; ta.classList.add("entry-box"); box.appendChild(ta);
  panelButton(box, "Add swipe (becomes the active one)", async () => {
    await api("/webface/chats/" + state.chatId + "/messages/" + m.id + "/swipes", jsonOptions("POST", { content: ta.value }));
    setStatus("Swipe added — the new alternate is now active."); await actSwipes(); await refreshChat();
  });
}

async function actBranch() {
  const m = needSelection(); if (!m) return;
  const name = window.prompt("Name for the branched chat (blank keeps the engine's name):", "");
  if (name === null) return;
  const chat = await api("/webface/chats/" + state.chatId + "/branches", jsonOptions("POST", { message_id: m.id, name: name }));
  setStatus("Branched into a new chat: " + (chat.title || chat.id));
  await loadChats(chat.id);
}

async function actPin() {
  const m = needSelection(); if (!m) return;
  const method = m.pinned ? "DELETE" : "POST";
  const out = await api("/webface/chats/" + state.chatId + "/messages/" + m.id + "/pin", { method: method });
  setStatus(out.pinned ? "Pinned (verified by re-reading the pinned list)." : "Unpinned (verified by re-reading the pinned list).");
  await refreshChat();
}

async function actCopy() {
  const m = needSelection(); if (!m) return;
  await navigator.clipboard.writeText(m.content || "");
  setStatus("Message copied to the clipboard.");
}

async function streamAction(path, busyWords) {
  if (state.sending) { setStatus("A stream is already running."); return; }
  state.sending = true; state.requestId = newRequestId();
  els.stop.disabled = false; setStatus(busyWords);
  try {
    const resp = await fetch(path, jsonOptions("POST", { request_id: state.requestId }));
    if (!resp.ok) throw new Error("request failed (" + resp.status + ")");
    const reader = resp.body.getReader(); const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const chunk = await reader.read(); if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      let idx = buffer.indexOf("\n\n");
      while (idx >= 0) {
        const frame = buffer.slice(0, idx); buffer = buffer.slice(idx + 2);
        for (const line of frame.split("\n")) {
          if (!line.startsWith("data:")) continue;
          const event = JSON.parse(line.slice(5).trim());
          if (event.type === "started") setStatus("Streaming from " + (event.backend_key || "the engine") + "…");
          else if (event.type === "landed") setStatus("New reply saved to the engine history.");
          else if (event.type === "restored") setStatus(event.message);
          else if (event.type === "no_mind") { renderNoMind(event, w03.chatPanel); setStatus(event.words || "No mind is connected to this chat yet"); }
          else if (event.type === "error") setStatus("Error: " + (event.message || "stream failed"));
        }
        idx = buffer.indexOf("\n\n");
      }
    }
  } finally {
    state.sending = false; state.requestId = null; els.stop.disabled = true;
    await refreshChat();
  }
}

async function actContinue() {
  if (!state.chatId) { setStatus("Open a chat first."); return; }
  try {
    const out = await api("/webface/chats/" + state.chatId + "/continue", jsonOptions("POST", { mode: "auto" }));
    setStatus("Continued (" + (out.mode || "auto") + ") — the engine landed the continuation.");
    await refreshChat();
  } catch (e) {
    const mind = await loadMind().catch(() => null);
    if (mind && mind.state === "none" && mind.no_mind) { renderNoMind(mind.no_mind, w03.chatPanel); setStatus(mind.no_mind.words); }
    else setStatus("Error: " + e.message);
  }
}

async function actImpersonate() {
  if (!state.chatId) { setStatus("Open a chat first."); return; }
  let draft;
  try {
    draft = await api("/webface/chats/" + state.chatId + "/impersonate", jsonOptions("POST", {}));
  } catch (e) {
    const mind = await loadMind().catch(() => null);
    if (mind && mind.state === "none" && mind.no_mind) { renderNoMind(mind.no_mind, w03.chatPanel); setStatus(mind.no_mind.words); return; }
    throw e;
  }
  const box = panel(w03.chatPanel, "Impersonate — draft of your next line");
  panelText(box, "Drafted by " + (draft.backend || "the engine") + ". Nothing is stored unless you accept it.");
  const ta = document.createElement("textarea"); ta.rows = 3; ta.value = draft.content || ""; ta.classList.add("entry-box"); box.appendChild(ta);
  panelButton(box, "Accept as my message", async () => {
    await api("/webface/chats/" + state.chatId + "/impersonate/accept", jsonOptions("POST", { content: ta.value, draft_id: draft.id }));
    setStatus("Impersonation accepted as a real user message."); w03.chatPanel.innerHTML = ""; await refreshChat();
  });
  panelButton(box, "Discard (stores nothing)", async () => {
    await api("/webface/chats/" + state.chatId + "/impersonate/discard", jsonOptions("POST", { draft_id: draft.id }));
    setStatus("Draft discarded — nothing was stored."); w03.chatPanel.innerHTML = "";
  });
}

async function actNote() {
  if (!state.chatId) { setStatus("Open a chat first."); return; }
  const note = await api("/webface/chats/" + state.chatId + "/authors-note");
  const box = panel(w03.chatPanel, "Author's Note");
  const ta = document.createElement("textarea"); ta.rows = 3; ta.value = note.text || ""; ta.classList.add("entry-box");
  ta.setAttribute("data-draft-key", "chat:" + state.chatId + ":authors-note"); box.appendChild(ta);
  const num = (label, val) => { const l = document.createElement("label"); l.textContent = label; const i = document.createElement("input"); i.type = "number"; i.classList.add("entry-box"); i.value = val; l.appendChild(i); box.appendChild(l); return i; };
  const depth = num("Depth", note.depth != null ? note.depth : 4);
  const freq = num("Frequency", note.frequency != null ? note.frequency : 1);
  const roleL = document.createElement("label"); roleL.textContent = "Role";
  const role = document.createElement("select"); role.classList.add("entry-box");
  for (const r of ["system", "user", "assistant"]) { const o = document.createElement("option"); o.value = r; o.textContent = r; if (r === note.role) o.selected = true; role.appendChild(o); }
  roleL.appendChild(role); box.appendChild(roleL);
  const enL = document.createElement("label"); enL.className = "check";
  const en = document.createElement("input"); en.type = "checkbox"; en.checked = note.enabled !== false;
  enL.appendChild(en); enL.appendChild(document.createTextNode(" Enabled")); box.appendChild(enL);
  panelButton(box, "Save note", async () => {
    const saved = await api("/webface/chats/" + state.chatId + "/authors-note", jsonOptions("POST", { text: ta.value, depth: Number(depth.value), frequency: Number(freq.value), role: role.value, enabled: en.checked }));
    if (window.RunmalEntryBox) window.RunmalEntryBox.retireDraft(ta);
    panelText(box, "Saved. The engine now holds: \"" + (saved.text || "") + "\" (depth " + saved.depth + ", every " + saved.frequency + ", role " + saved.role + ", " + (saved.enabled ? "enabled" : "disabled") + ").");
  });
}

async function actSearch() {
  const q = window.prompt("Search all chats for:", "");
  if (!q) return;
  const out = await api("/webface/chats/search?q=" + encodeURIComponent(q));
  const box = panel(w03.chatPanel, "Search results for \"" + q + "\"");
  const hits = out.results || [];
  if (!hits.length) panelText(box, "No matches.");
  for (const hit of hits) {
    const row = document.createElement("div"); row.className = "row";
    const label = document.createElement("span");
    label.textContent = (hit.chat_title || hit.chat_id) + " — " + (hit.snippet || "");
    row.appendChild(label);
    const open = document.createElement("button"); open.className = "btn small ghost"; open.type = "button"; open.textContent = "Open chat";
    open.addEventListener("click", async () => { await loadChats(hit.chat_id); });
    row.appendChild(open); box.appendChild(row);
  }
}

async function actCheckpoints() {
  if (!state.chatId) { setStatus("Open a chat first."); return; }
  const box = panel(w03.chatPanel, "Checkpoints & Undo");
  const cps = await api("/webface/chats/" + state.chatId + "/checkpoints");
  for (const cp of cps) {
    const row = document.createElement("div"); row.className = "row";
    const label = document.createElement("span");
    label.textContent = (cp.name || cp.id) + " — " + (cp.message_count || 0) + " messages, " + (cp.created_at || "");
    row.appendChild(label);
    const restore = document.createElement("button"); restore.className = "btn small ghost"; restore.type = "button"; restore.textContent = "Restore as new chat";
    restore.addEventListener("click", async () => {
      const chat = await api("/webface/chats/" + state.chatId + "/checkpoints/" + cp.id + "/restore", jsonOptions("POST", {}));
      setStatus("Checkpoint restored as a new chat."); await loadChats(chat.id);
    });
    row.appendChild(restore);
    const del = document.createElement("button"); del.className = "btn small ghost"; del.type = "button"; del.textContent = "Delete";
    del.addEventListener("click", async () => {
      await api("/webface/chats/" + state.chatId + "/checkpoints/" + cp.id, { method: "DELETE" });
      await actCheckpoints();
    });
    row.appendChild(del); box.appendChild(row);
  }
  if (!cps.length) panelText(box, "No checkpoints yet.");
  panelButton(box, "Create checkpoint", async () => {
    await api("/webface/chats/" + state.chatId + "/checkpoints", jsonOptions("POST", {}));
    await actCheckpoints();
  });
  const undo = await api("/webface/chats/" + state.chatId + "/undo");
  const entries = undo.entries || [];
  panelText(box, entries.length ? "Undo journal (newest first):" : "The undo journal is empty.");
  for (const entry of entries) {
    panelText(box, "• " + (entry.operation || "operation") + (entry.detail ? " — " + entry.detail : ""));
  }
  if (entries.length) {
    panelButton(box, "Undo last", async () => {
      await api("/webface/chats/" + state.chatId + "/undo", jsonOptions("POST", {}));
      setStatus("Last journaled operation undone."); await actCheckpoints(); await refreshChat();
    });
  }
}

const on = (id, fn) => document.getElementById(id).addEventListener("click", () => fn().catch((e) => setStatus("Error: " + e.message)));
on("m-edit", actEdit); on("m-delete", actDelete);
on("m-prev", () => actSwipe("prev")); on("m-next", () => actSwipe("next"));
on("m-swipes", actSwipes); on("m-branch", actBranch);
on("m-pin", actPin); on("m-copy", actCopy);
on("a-regen", () => streamAction("/webface/chats/" + state.chatId + "/regenerate", "Regenerating…"));
on("a-continue", actContinue); on("a-impersonate", actImpersonate);
on("a-note", actNote); on("a-search", actSearch); on("a-checkpoints", actCheckpoints);

/* W-04: preset quick-apply + first-run banner. */
async function loadPresetQuickApply() {
  const sel = document.getElementById("preset-select");
  if (!sel) return;
  const presets = await api("/webface/presets");
  sel.innerHTML = "";
  const none = document.createElement("option"); none.value = ""; none.textContent = "No preset (engine defaults)"; sel.appendChild(none);
  for (const pr of presets) { const o = document.createElement("option"); o.value = pr.id; o.textContent = pr.name; sel.appendChild(o); }
  const chats = await api("/webface/chats");
  const chat = chats.find((c) => c.id === state.chatId);
  sel.value = chat && chat.preset_id ? chat.preset_id : "";
}
async function applyPresetQuick() {
  if (!state.chatId) { setStatus("Open a chat first, then apply a preset."); return; }
  const sel = document.getElementById("preset-select");
  const chat = await api("/webface/chats/" + state.chatId + "/preset", jsonOptions("POST", { preset_id: sel.value || null }));
  setStatus(chat.preset_id ? "Preset applied to this chat." : "Preset cleared - engine defaults apply.");
}
async function checkFirstRun() {
  const banner = document.getElementById("firstrun-banner");
  if (!banner) return;
  try {
    const s = await api("/webface/firstrun/status");
    banner.hidden = !(s.first_run && !sessionStorage.getItem("firstrun-dismissed"));
  } catch (e) { banner.hidden = true; }
}
const _qa = document.getElementById("preset-apply");
if (_qa) _qa.addEventListener("click", () => applyPresetQuick().catch((e) => setStatus("Error: " + e.message)));
const _fd = document.getElementById("firstrun-dismiss");
if (_fd) _fd.addEventListener("click", () => { sessionStorage.setItem("firstrun-dismissed", "1"); document.getElementById("firstrun-banner").hidden = true; });
const _origOpenChat = openChat;
openChat = async function (chatId) { await _origOpenChat(chatId); await loadPresetQuickApply().catch(() => {}); };
checkFirstRun();
loadPresetQuickApply().catch(() => {});
if (window.location.hash.length > 1) { loadChats(window.location.hash.slice(1)).catch(() => {}); }

/* W-12: the Model menu — pick which profile answers this chat,
   right where you chat. The menu renders from the mind the SERVER
   reports (never from UI memory): its value is the chat's own pin,
   or the "house default" entry when the chat rides the default.
   Changing it pins (or unpins) the chat at once through the
   engine's pin road, then the mind is re-read, so what you see is
   what the engine holds. "Make this the house default" names the
   selected profile as the default every unpinned chat answers
   through. */
const modelEls = {
  select: document.getElementById("model-select"),
  note: document.getElementById("model-note"),
  makeDefault: document.getElementById("model-default"),
};
function renderModelSelect() {
  const sel = modelEls.select;
  if (!sel) return;
  const mind = mindState.mind;
  sel.innerHTML = "";
  const def = mind && mind.default_profile;
  const defOpt = document.createElement("option");
  defOpt.value = "";
  defOpt.textContent = def
    ? "House default — " + (def.name || def.id) + " · " + (def.chat_model || def.chat_backend)
    : "House default (none set)";
  sel.appendChild(defOpt);
  for (const p of (mind && mind.profiles) || []) {
    const o = document.createElement("option");
    o.value = p.id;
    o.textContent = (p.name || p.id) + " · " + (p.chat_model || p.chat_backend) + (p.is_demo ? " (Demo — not a real model)" : "");
    sel.appendChild(o);
  }
  sel.value = mind && mind.pinned_profile_id ? mind.pinned_profile_id : "";
  sel.disabled = !state.chatId;
  if (modelEls.note) {
    if (!mind) modelEls.note.textContent = "";
    else if (mind.via === "pin") modelEls.note.textContent = "Pinned to this chat.";
    else if (mind.via === "default") modelEls.note.textContent = "This chat rides the house default.";
    else modelEls.note.textContent = "No mind connected yet — pick a model above.";
  }
  if (modelEls.makeDefault) {
    const cur = sel.value;
    const isDefault = Boolean(def && cur && def.id === cur);
    modelEls.makeDefault.disabled = !cur || isDefault;
    modelEls.makeDefault.textContent = isDefault ? "This is the house default" : "Make this the house default";
  }
}
if (modelEls.select) modelEls.select.addEventListener("change", async () => {
  if (!state.chatId) return;
  const pid = modelEls.select.value || null;
  try {
    await api("/webface/chats/" + state.chatId + "/backend-profile", jsonOptions("POST", { profile_id: pid }));
    await loadMind();
    setStatus(pid ? "Model pinned to this chat." : "Chat unpinned — it now rides the house default.");
  } catch (e) { setStatus("Error: " + e.message); await loadMind().catch(() => {}); }
});
if (modelEls.makeDefault) modelEls.makeDefault.addEventListener("click", async () => {
  const pid = modelEls.select.value;
  if (!pid) return;
  try {
    await api("/webface/default-profile", jsonOptions("POST", { profile_id: pid }));
    await loadMind();
    setStatus("House default set — every chat without its own model now answers through it.");
  } catch (e) { setStatus("Error: " + e.message); }
});
renderModelSelect();
