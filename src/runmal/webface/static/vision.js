"use strict";
/* Runmal web face - Vision tab (W-08). Desktop R-13 Vision
   parity over the engine's own roads: the provider truth
   (image facts only - no semantic caption provider exists),
   chat attachments stored/shown/described as facts, watch
   folders, and sending words with a picture bound to the
   sent message through the ordinary guarded send road. The
   pinned mind does not see attachments - the page says so. */
const $ = (id) => document.getElementById(id);
async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let d = "request failed (" + resp.status + ")"; try { const b = await resp.json(); if (b.error) d = b.error; } catch (e) {} throw new Error(d); }
  return resp.json();
}
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }
function post(path, body) { return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }); }
/* Upload with real progress (the FIX-AVATAR pattern): fetch
   cannot report upload progress, so uploads go through
   XMLHttpRequest; failures surface the server's own words. */
function uploadWithProgress(path, fd, statusEl, btn, file) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    if (btn) btn.disabled = true;
    const label = "Uploading " + (file ? file.name : "file") + "…";
    if (statusEl) statusEl.textContent = label;
    xhr.upload.addEventListener("progress", (ev) => {
      if (!statusEl) return;
      statusEl.textContent = ev.lengthComputable
        ? label + " " + Math.round((ev.loaded / ev.total) * 100) + "%"
        : label + " " + ev.loaded + " bytes sent";
    });
    xhr.addEventListener("load", () => {
      if (btn) btn.disabled = false;
      let body = null;
      try { body = JSON.parse(xhr.responseText); } catch (e) {}
      if (xhr.status >= 200 && xhr.status < 300) { resolve(body); return; }
      reject(new Error((body && body.error) || ("upload failed (" + xhr.status + ")")));
    });
    xhr.addEventListener("error", () => { if (btn) btn.disabled = false; reject(new Error("upload failed -- the connection dropped")); });
    xhr.addEventListener("abort", () => { if (btn) btn.disabled = false; reject(new Error("upload cancelled")); });
    xhr.send(fd);
  });
}
function chatId() { return $("s-chat").value; }

async function loadProviders() {
  const view = await api("/webface/vision/providers");
  $("s-providers").textContent = view.words;
  $("s-send-note").textContent = view.send_note;
}
async function loadChats() {
  const chats = await api("/webface/chats");
  const sel = $("s-chat"); sel.innerHTML = "";
  chats.forEach((c) => { const o = el("option", c.title || c.id); o.value = c.id; sel.appendChild(o); });
  if (chats.length) await loadChat();
}
async function loadChat() {
  const id = chatId(); if (!id) return;
  const messages = await api("/webface/chats/" + id + "/messages");
  const atts = await api("/webface/vision/attachments?chat_id=" + encodeURIComponent(id));
  const byMessage = {};
  atts.attachments.forEach((a) => { if (a.message_id) { (byMessage[a.message_id] = byMessage[a.message_id] || []).push(a); } });
  const box = $("s-transcript"); box.innerHTML = "";
  messages.forEach((m) => {
    const row = el("div", null, "msg");
    row.appendChild(el("p", (m.role || "") + ": " + (m.content || "")));
    (byMessage[m.id] || []).forEach((a) => {
      const img = el("img"); img.src = "/webface/vision/attachments/" + a.id + "/content";
      img.alt = a.filename || "attached picture"; img.style.maxWidth = "240px";
      row.appendChild(img);
    });
    box.appendChild(row);
  });
  const list = $("s-attachments"); list.innerHTML = "";
  atts.attachments.forEach((a, i) => {
    const li = el("li", atts.lines[i]);
    const use = el("button", "Describe", "btn ghost small"); use.type = "button";
    use.addEventListener("click", () => { $("s-desc-attach").value = a.id; });
    const del = el("button", "Delete", "btn ghost small"); del.type = "button";
    del.addEventListener("click", () => api("/webface/vision/attachments/" + a.id, { method: "DELETE" }).then(loadChat).catch((e) => { $("s-status").textContent = e.message; }));
    li.appendChild(document.createTextNode(" ")); li.appendChild(use);
    li.appendChild(document.createTextNode(" ")); li.appendChild(del);
    list.appendChild(li);
  });
  const thumbs = $("s-thumbs"); thumbs.innerHTML = "";
  atts.attachments.forEach((a) => {
    const img = el("img"); img.src = "/webface/vision/attachments/" + a.id + "/content";
    img.alt = a.filename || "attached picture"; img.style.maxWidth = "160px";
    thumbs.appendChild(img);
  });
  const descs = await api("/webface/vision/descriptions?chat_id=" + encodeURIComponent(id));
  const dlist = $("s-descriptions"); dlist.innerHTML = "";
  descs.descriptions.forEach((d, i) => dlist.appendChild(el("li", descs.lines[i])));
  const watches = await api("/webface/vision/watch-folders?chat_id=" + encodeURIComponent(id));
  const wlist = $("s-watches"); wlist.innerHTML = "";
  watches.watch_folders.forEach((w, i) => {
    const li = el("li", watches.lines[i]);
    const scan = el("button", "Scan now", "btn ghost small"); scan.type = "button";
    scan.addEventListener("click", () => post("/webface/vision/watch-folders/" + w.id + "/scan", {}).then((view) => { $("s-watch-out").textContent = view.words; return loadChat(); }).catch((e) => { $("s-watch-out").textContent = e.message; }));
    const toggle = el("button", w.enabled ? "Disable" : "Enable", "btn ghost small"); toggle.type = "button";
    toggle.addEventListener("click", () => api("/webface/vision/watch-folders/" + w.id, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !w.enabled }) }).then(loadChat).catch((e) => { $("s-watch-out").textContent = e.message; }));
    const del = el("button", "Delete", "btn ghost small"); del.type = "button";
    del.addEventListener("click", () => api("/webface/vision/watch-folders/" + w.id, { method: "DELETE" }).then(loadChat).catch((e) => { $("s-watch-out").textContent = e.message; }));
    [scan, toggle, del].forEach((b) => { li.appendChild(document.createTextNode(" ")); li.appendChild(b); });
    wlist.appendChild(li);
  });
}
async function attach(file, extra) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("chat_id", chatId());
  Object.keys(extra || {}).forEach((k) => { if (extra[k]) fd.append(k, extra[k]); });
  return uploadWithProgress("/webface/vision/attachments", fd, $("s-attach-status"), $("s-attach"), file);
}
$("s-load").addEventListener("click", () => loadChat().catch((e) => { $("s-status").textContent = e.message; }));
$("s-chat").addEventListener("change", () => loadChat().catch((e) => { $("s-status").textContent = e.message; }));
$("s-attach").addEventListener("click", () => {
  const file = $("s-file").files[0];
  if (!file) { $("s-attach-status").textContent = "pick a picture file first"; return; }
  attach(file, { message_id: $("s-message-id").value.trim(), describe: $("s-describe").checked ? "true" : "" })
    .then((view) => { $("s-attach-out").textContent = view.line + (view.description_words ? "\n" + view.description_words : ""); return loadChat(); })
    .catch((e) => { $("s-attach-out").textContent = e.message; });
});
$("s-send").addEventListener("click", async () => {
  const out = $("s-send-out");
  const file = $("s-file").files[0];
  const text = $("s-send-text").value.trim();
  if (!file) { out.textContent = "pick a picture file first (the Attach section's picker)"; return; }
  if (!text) { out.textContent = "write the message first"; return; }
  try {
    const resp = await fetch("/webface/chats/" + chatId() + "/send", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content: text }) });
    const raw = await resp.text();
    if (!resp.ok) { let msg = "send failed (" + resp.status + ")"; try { const b = JSON.parse(raw); if (b.error) msg = b.error; } catch (e) {} throw new Error(msg); }
    if (!raw.includes("landed")) throw new Error("the send did not land - the picture was not attached");
    const messages = await api("/webface/chats/" + chatId() + "/messages");
    const mine = messages.filter((m) => m.role === "user").pop();
    if (!mine) throw new Error("the sent message could not be found - the picture was not attached");
    const view = await attach(file, { message_id: mine.id });
    out.textContent = "Sent. The picture is attached to your message: " + view.line + " The pinned mind did not see the picture - no chat backend declares vision.";
    await loadChat();
  } catch (e) { out.textContent = e.message; }
});
$("s-describe-btn").addEventListener("click", () => post("/webface/vision/describe", { chat_id: chatId(), attachment_id: $("s-desc-attach").value.trim(), question: $("s-desc-q").value, require_semantic: $("s-desc-semantic").checked }).then((view) => { $("s-desc-out").textContent = view.words; return loadChat(); }).catch((e) => { $("s-desc-out").textContent = e.message; }));
$("s-watch-add").addEventListener("click", () => post("/webface/vision/watch-folders", { chat_id: chatId(), path: $("s-watch-path").value, recursive: $("s-watch-recursive").checked }).then((view) => { $("s-watch-out").textContent = view.line; return loadChat(); }).catch((e) => { $("s-watch-out").textContent = e.message; }));
loadProviders().then(loadChats).catch((e) => { $("s-status").textContent = e.message; });
