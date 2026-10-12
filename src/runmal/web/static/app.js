/* Rúnmál chat UI (S109). Vanilla JS on purpose: no CDN, works fully offline.
   Same-origin API calls carry the bearer credential from local storage. */
"use strict";

const state = {
  token: localStorage.getItem("runmal_token") || "",
  chats: [],
  currentChatId: null,
  generating: false,
  requestId: null,
};

const $ = (id) => document.getElementById(id);

function showTokenGate() { $("token-gate").classList.remove("hidden"); }
function hideTokenGate() { $("token-gate").classList.add("hidden"); }
function showError(text) { $("error-text").textContent = text; $("error-banner").classList.remove("hidden"); }

/* Screen-reader announcements (S309): polite live region narrates stream
 * lifecycle without reading every token. */
function announce(text) {
  const region = $("sr-status");
  if (region) region.textContent = text;
}
function hideError() { $("error-banner").classList.add("hidden"); }

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: {
      Authorization: "Bearer " + state.token,
      "Content-Type": "application/json",
      ...(opts.headers || {}),
    },
  });
  if (res.status === 401) {
    showTokenGate();
    throw new Error("missing or invalid local credential");
  }
  if (!res.ok) throw new Error("request failed: " + res.status + " " + path);
  return res;
}

function renderChatList() {
  const ul = $("chat-list");
  ul.textContent = "";
  for (const chat of state.chats) {
    const li = document.createElement("li");
    if (chat.id === state.currentChatId) li.classList.add("active");
    const title = document.createElement("span");
    title.className = "title";
    title.textContent = chat.title || "(untitled)";
    title.addEventListener("click", () => selectChat(chat.id));
    li.appendChild(title);
    const glyphs = ["\u270E", "\u2913", "\uD83D\uDDD1"];
    const hints = ["Rename chat", "Export chat", "Delete chat"];
    const fns = [
      () => startRename(chat.id, li),
      () => exportChat(chat.id),
      () => askDeleteChat(chat.id),
    ];
    glyphs.forEach((glyph, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = glyph;
      btn.title = hints[i];
      btn.setAttribute("aria-label", hints[i]);
      if (hints[i] === "Delete chat") btn.classList.add("danger");
      btn.addEventListener("click", (e) => { e.stopPropagation(); fns[i](); });
      li.appendChild(btn);
    });
    ul.appendChild(li);
  }
}

function renderInto(div, text) {
  // Completed messages render as markdown-lite (renderer escapes first).
  div.innerHTML = window.RunmalRenderer.renderMarkdownLite(text);
}

function appendMessage(role, text, rendered) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  if (rendered) renderInto(div, text);
  else div.textContent = text;
  $("thread").appendChild(div);
  div.scrollIntoView({ block: "end" });
  return div;
}

const THREAD_WINDOW = 100; // S302: virtualized thread window size
state.allMessages = [];
state.windowShown = THREAD_WINDOW;

function renderThread() {
  const thread = $("thread");
  thread.textContent = "";
  const { visible, hidden } = window.RunmalRenderer.windowMessages(
    state.allMessages, state.windowShown
  );
  if (hidden > 0) {
    const more = document.createElement("button");
    more.type = "button";
    more.id = "show-earlier";
    more.textContent = "Show earlier messages (" + hidden + " hidden)";
    more.addEventListener("click", () => {
      state.windowShown += THREAD_WINDOW;
      renderThread();
    });
    thread.appendChild(more);
  }
  for (const m of visible) appendMessage(m.role, m.content, true);
}

async function loadPresets() {
  // S306: preset picker — presets applied per chat.
  try {
    const presets = await (await api("/api/v1/presets")).json();
    const sel = $("preset-select");
    sel.textContent = "";
    const none = document.createElement("option");
    none.value = "";
    none.textContent = "(none)";
    sel.appendChild(none);
    for (const p of presets) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      sel.appendChild(opt);
    }
  } catch (err) { /* picker is optional chrome; chat still works */ }
}

async function loadChats() {
  const chats = await (await api("/api/v1/chats")).json();
  state.chats = chats;
  renderChatList();
  if (!state.currentChatId && chats.length > 0) await selectChat(chats[0].id);
}

async function selectChat(chatId) {
  if (state.generating) return;
  state.currentChatId = chatId;
  if (window.RunmalDrawer) window.RunmalDrawer.close();
  renderChatList();
  const chat = await (await api("/api/v1/chats/" + chatId)).json();
  state.allMessages = chat.messages;
  state.windowShown = THREAD_WINDOW;
  if ($("preset-select")) $("preset-select").value = chat.preset_id || "";
  renderThread();
}

async function newChat() {
  if (state.generating) return;
  const chat = await (await api("/api/v1/chats", {
    method: "POST",
    body: JSON.stringify({ title: "Chat " + new Date().toLocaleString() }),
  })).json();
  state.chats.push(chat);
  await selectChat(chat.id);
}

function setGenerating(on) {
  state.generating = on;
  $("stop").classList.toggle("hidden", !on);
  $("send").disabled = on;
}

function setRetryVisible(on) {
  $("retry").classList.toggle("hidden", !on);
}

/* Stream one generation for the chat's current history into a fresh
 * assistant bubble (S302: shared by send + retry; completed bubbles are
 * re-rendered as markdown-lite, stopped/failed runs expose Retry). */
async function streamGeneration(chatId) {
  const history = await (await api("/api/v1/chats/" + chatId + "/messages")).json();
  const requestId = crypto.randomUUID();
  state.requestId = requestId;
  setGenerating(true);
  announce("Generating reply\u2026");
  setRetryVisible(false);
  const bubble = appendMessage("assistant", "");
  let full = "";
  let stopped = false;
  try {
    const res = await fetch("/api/v1/generate", {
      method: "POST",
      headers: {
        Authorization: "Bearer " + state.token,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        messages: history.map((m) => ({ role: m.role, content: m.content })),
        request_id: requestId,
      }),
    });
    if (!res.ok) throw new Error("generate failed: HTTP " + res.status);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        for (const line of block.split("\n")) {
          if (!line.startsWith("data:")) continue;
          const event = JSON.parse(line.slice(5));
          if (event.type === "token") {
            full += event.text;
            bubble.textContent = full; // incremental token rendering
          } else if (event.type === "done") {
            if (event.finish_reason === "cancelled") stopped = true;
          }
        }
      }
    }
    const finalText = stopped ? full + " \u2014 stopped" : full;
    renderInto(bubble, finalText || "(no output)");
    announce(stopped ? "Generation stopped." : "Reply received.");
    await api("/api/v1/chats/" + chatId + "/messages", {
      method: "POST",
      body: JSON.stringify({ role: "assistant", content: full || "(no output)" }),
    });
    state.allMessages.push({ role: "assistant", content: full || "(no output)" });
    if (stopped) setRetryVisible(true);
  } catch (err) {
    showError("Generation failed: " + err.message);
    announce("Generation failed.");
    setRetryVisible(true);
  } finally {
    state.requestId = null;
    setGenerating(false);
  }
}

async function sendMessage() {
  const input = $("input");
  const text = input.value.trim();
  if (!text || state.generating || !state.currentChatId) return;
  input.value = "";
  hideError();
  const chatId = state.currentChatId;
  try {
    await api("/api/v1/chats/" + chatId + "/messages", {
      method: "POST",
      body: JSON.stringify({ role: "user", content: text }),
    });
    state.allMessages.push({ role: "user", content: text });
    appendMessage("user", text, true);
    await streamGeneration(chatId);
  } catch (err) {
    showError("Generation failed: " + err.message);
  }
}

async function retryGeneration() {
  if (state.generating || !state.currentChatId) return;
  hideError();
  await streamGeneration(state.currentChatId);
}

async function stopGeneration() {
  if (!state.generating || !state.requestId) return;
  try {
    // Best effort: the stream ends on its own even if this fails.
    await api("/api/v1/generate/cancel", {
      method: "POST",
      body: JSON.stringify({ request_id: state.requestId }),
    });
  } catch (err) {
    showError("Stop failed: " + err.message);
  }
}

/* Destructive-action confirmation semantics (S111): deleting a chat is
   two-step. The modal states the action is irreversible; only the explicit
   Delete button performs it. Cancel, Escape, or clicking outside the card
   aborts with zero side effects. */
let pendingDeleteId = null;

function askDeleteChat(chatId) {
  if (state.generating) return;
  pendingDeleteId = chatId;
  $("confirm-modal").classList.remove("hidden");
  $("confirm-ok").focus();
}

function closeConfirm() {
  pendingDeleteId = null;
  $("confirm-modal").classList.add("hidden");
}

async function doDeleteChat() {
  const chatId = pendingDeleteId;
  closeConfirm();
  if (!chatId) return;
  try {
    await api("/api/v1/chats/" + chatId, { method: "DELETE" });
    state.chats = state.chats.filter((c) => c.id !== chatId);
    if (state.currentChatId === chatId) {
      state.currentChatId = null;
      $("thread").textContent = "";
      if (state.chats.length > 0) await selectChat(state.chats[0].id);
    }
    renderChatList();
  } catch (err) {
    showError("Delete failed: " + err.message);
  }
}

function startRename(chatId, li) {
  if (state.generating) return;
  const chat = state.chats.find((c) => c.id === chatId);
  if (!chat) return;
  const input = document.createElement("input");
  input.value = chat.title || "";
  input.setAttribute("aria-label", "Chat title");
  li.textContent = "";
  li.appendChild(input);
  input.focus();
  input.select();
  let done = false;
  const finish = async (save) => {
    if (done) return;
    done = true;
    const title = input.value.trim();
    if (save && title && title !== chat.title) {
      try {
        const updated = await (
          await api("/api/v1/chats/" + chatId, {
            method: "PATCH",
            body: JSON.stringify({ title }),
          })
        ).json();
        chat.title = updated.title;
      } catch (err) {
        showError("Rename failed: " + err.message);
      }
    }
    renderChatList();
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") finish(true);
    else if (e.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(false));
}

async function exportChat(chatId) {
  try {
    const doc = await (await api("/api/v1/chats/" + chatId + "/export")).json();
    const blob = new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    const safe = (doc.chat.title || "chat").replace(/[^a-z0-9-_]+/gi, "_");
    a.href = URL.createObjectURL(blob);
    a.download = "runmal-" + safe + ".json";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  } catch (err) {
    showError("Export failed: " + err.message);
  }
}

function init() {
  $("send").addEventListener("click", sendMessage);
  $("stop").addEventListener("click", stopGeneration);
  $("retry").addEventListener("click", retryGeneration);
  // Code-block copy buttons (S302): rendered inside <pre class="code-block">.
  $("thread").addEventListener("click", (e) => {
    const btn = e.target.closest ? e.target.closest(".copy-btn") : null;
    if (!btn) return;
    const code = btn.parentElement.querySelector("code");
    if (code && navigator.clipboard) {
      navigator.clipboard.writeText(code.textContent).catch(() => {});
    }
  });
  $("new-chat").addEventListener("click", newChat);
  $("error-dismiss").addEventListener("click", hideError);
  $("confirm-ok").addEventListener("click", doDeleteChat);
  $("confirm-cancel").addEventListener("click", closeConfirm);
  $("confirm-modal").addEventListener("click", (e) => {
    if (e.target === $("confirm-modal")) closeConfirm();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("confirm-modal").classList.contains("hidden")) {
      closeConfirm();
    }
  });
  $("input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  $("preset-select").addEventListener("change", async (e) => {
    if (!state.currentChatId) return;
    try {
      await api("/api/v1/chats/" + state.currentChatId + "/preset", {
        method: "POST",
        body: JSON.stringify({ preset_id: e.target.value || null }),
      });
    } catch (err) {
      showError("Preset apply failed: " + err.message);
    }
  });
  $("token-save").addEventListener("click", () => {
    const value = $("token-input").value.trim();
    if (!value) return;
    state.token = value;
    localStorage.setItem("runmal_token", value);
    $("token-input").value = "";
    hideTokenGate();
    boot().catch((err) => showError(err.message));
  });
  if (!state.token) showTokenGate();
}

async function boot() {
  hideError();
  try {
    await loadPresets();
    await loadChats();
    if (state.chats.length === 0) await newChat();
  } catch (err) {
    showError("Could not reach the local API: " + err.message);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  init();
  boot().catch((err) => showError(err.message));
});
