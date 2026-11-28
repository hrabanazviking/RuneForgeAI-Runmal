"use strict";
/* Runmal web face - Inspector tab (W-07). Desktop R-12 parity:
   pick a chat -> overview/events/reasoning documents in words;
   run the trace -> the engine's ledger, slot lines and lore
   account, plus the composed sections from the engine's own
   preview payload (the trace itself carries no prompt text,
   and the page says so). Reply provenance reads the engine's
   recorded document for one landed message. Read-only: the
   inspect roads compose a hypothetical turn and send nothing. */
const $ = (id) => document.getElementById(id);
async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let d = "request failed (" + resp.status + ")"; try { const b = await resp.json(); if (b.error) d = b.error; } catch (e) {} throw new Error(d); }
  return resp.json();
}
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }
function chatId() { return $("i-chat").value; }

async function loadChats() {
  const chats = await api("/webface/chats");
  const sel = $("i-chat"); sel.innerHTML = "";
  for (const c of chats) { const o = el("option", c.title || c.id); o.value = c.id; sel.appendChild(o); }
  if (!chats.length) $("i-status").textContent = "No chats yet - make one in the Chat tab first.";
}
async function loadDocs() {
  const id = chatId(); if (!id) return;
  const view = await api("/webface/inspector/chats/" + id);
  $("i-note").textContent = view.note;
  const box = $("i-docs"); box.hidden = false;
  $("i-overview").textContent = view.overview_words;
  $("i-events").textContent = view.events_words;
  $("i-reasoning").textContent = view.reasoning_words;
  await loadMessages(id);
}
async function loadMessages(id) {
  const msgs = await api("/webface/chats/" + id + "/messages");
  const list = $("i-messages"); list.innerHTML = "";
  for (const m of msgs) {
    if (m.role !== "assistant") continue;
    const li = el("li");
    const b = el("button", (m.content || "").slice(0, 80) || "(empty reply)", "btn ghost small"); b.type = "button";
    b.addEventListener("click", () => showProvenance(id, m.id));
    li.appendChild(b); list.appendChild(li);
  }
  if (!list.children.length) $("i-prov").textContent = "No landed replies in this chat yet.";
}
async function showProvenance(id, mid) {
  const view = await api("/webface/inspector/chats/" + id + "/messages/" + mid + "/provenance");
  $("i-prov").textContent = view.words;
}
async function runTrace() {
  const id = chatId(); if (!id) return;
  const view = await api("/webface/inspector/chats/" + id + "/trace", { method: "POST" });
  const box = $("i-trace-box"); box.hidden = false;
  $("i-ledger").textContent = view.ledger_words;
  const list = $("i-slots"); list.innerHTML = "";
  for (const line of view.slot_lines) list.appendChild(el("li", line));
  $("i-lore").textContent = view.lore_lines.length ? view.lore_lines.join("\n") : "No lore account in this trace.";
  $("i-content-note").textContent = view.content_note;
  const secs = $("i-sections"); secs.innerHTML = "";
  for (const s of view.sections) {
    secs.appendChild(el("h4", (s.slot_id || "section") + " · " + s.role));
    const pre = el("pre", s.content, "words"); secs.appendChild(pre);
  }
  if (!view.sections.length) secs.appendChild(el("p", "The preview carried no sections for this chat.", "muted"));
  $("i-preview-words").textContent = view.preview_words;
}
$("i-load").addEventListener("click", () => loadDocs().catch((e) => { $("i-status").textContent = e.message; }));
$("i-trace").addEventListener("click", () => runTrace().catch((e) => { $("i-status").textContent = e.message; }));
loadChats().then(() => loadDocs()).catch((e) => { $("i-status").textContent = e.message; });
