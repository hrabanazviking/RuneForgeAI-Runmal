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
          }
        }
        idx = buffer.indexOf("\n\n");
      }
    }
    els.composer.value = "";
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
