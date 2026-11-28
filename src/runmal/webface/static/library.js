"use strict";
/* Rúnmál web face — Library tab (W-02): card imports (JSON/PNG,
   read as-is, never deleted by the web face) + organisation
   (tags / favourites) over the engine library roads. */
const $ = (id) => document.getElementById(id);
const els = { files: $("l-files"), importBtn: $("l-import"), result: $("l-result"),
  lines: $("l-lines"), search: $("l-search"), tag: $("l-tag"), fav: $("l-fav"),
  roster: $("l-roster"), census: $("l-census"), status: $("l-status") };
async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let detail = "request failed (" + resp.status + ")";
    try { const b = await resp.json(); if (b.error) detail = b.error; } catch (e) {}
    throw new Error(detail); }
  return resp.json();
}
function el(tag, text, cls) { const n = document.createElement(tag);
  if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }
async function loadTags() {
  const data = await api("/webface/library/tags");
  const rows = (data && data.tags) || [];
  els.tag.innerHTML = "<option value=\"\">All tags</option>";
  for (const row of rows) { const o = el("option", row.tag + " (" + row.count + ")");
    o.value = row.tag; els.tag.appendChild(o); }
  els.census.textContent = rows.length
    ? "Tags: " + rows.map((r) => r.tag + " ×" + r.count).join(", ") : "No tags yet.";
}
async function loadRoster() {
  const params = new URLSearchParams();
  if (els.search.value) params.set("q", els.search.value);
  if (els.tag.value) params.set("tag", els.tag.value);
  params.set("favourites_only", els.fav.checked ? "true" : "false");
  const data = await api("/webface/library/cards?" + params.toString());
  const items = (data && data.items) || [];
  els.roster.innerHTML = "";
  for (const card of items) {
    const li = el("li", null, "roster-row");
    li.appendChild(el("b", card.name || card.id));
    if (card.is_favourite) li.appendChild(el("span", " ★ favourite", "tag"));
    if (card.tags && card.tags.length)
      li.appendChild(el("span", " tags: " + card.tags.join(", "), "muted"));
    const fav = el("button", card.is_favourite ? "Unfavourite" : "Favourite", "btn ghost small");
    fav.type = "button";
    fav.addEventListener("click", async () => {
      await api("/webface/library/cards/" + card.id + "/favourite", { method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_favourite: !card.is_favourite }) });
      loadRoster(); });
    li.appendChild(fav);
    const tagsBtn = el("button", "Set tags", "btn ghost small"); tagsBtn.type = "button";
    tagsBtn.addEventListener("click", async () => {
      const text = window.prompt("Tags, comma separated:", (card.tags || []).join(", "));
      if (text === null) return;
      const tags = text.split(",").map((t) => t.trim()).filter(Boolean);
      await api("/webface/library/cards/" + card.id + "/tags", { method: "PUT",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tags }) });
      loadTags(); loadRoster(); });
    li.appendChild(tagsBtn);
    els.roster.appendChild(li);
  }
  if (!items.length) els.roster.appendChild(el("li", "No cards match.", "muted"));
}
/* Upload with real progress (FIX-AVATAR): XMLHttpRequest, since
   fetch cannot report upload progress. The result line names the
   files and shows progress; failures show the server's words. */
function uploadWithProgress(path, fd, statusEl, btn, label) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    if (btn) btn.disabled = true;
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
      reject(new Error((body && body.error) ||
        ("import failed (" + xhr.status + ")")));
    });
    xhr.addEventListener("error", () => { if (btn) btn.disabled = false;
      reject(new Error("import failed -- the connection dropped")); });
    xhr.addEventListener("abort", () => { if (btn) btn.disabled = false;
      reject(new Error("import cancelled")); });
    xhr.send(fd);
  });
}
els.importBtn.addEventListener("click", async () => {
  if (!els.files.files.length) { els.result.textContent = "Pick at least one card file first."; return; }
  const fd = new FormData();
  const names = [];
  for (const file of els.files.files) { fd.append("files", file); names.push(file.name); }
  try {
    const report = await uploadWithProgress("/webface/library/imports", fd,
      els.result, els.importBtn, "Importing " + names.join(", ") + "…");
    els.result.textContent = (report && report.words) || "Import finished.";
    els.lines.innerHTML = "";
    for (const line of (report && report.lines) || []) els.lines.appendChild(el("li", line));
    loadTags(); loadRoster();
  } catch (err) { els.result.textContent = err.message; }
});
els.search.addEventListener("input", loadRoster);
els.tag.addEventListener("change", loadRoster);
els.fav.addEventListener("change", loadRoster);
loadTags().then(loadRoster).catch((err) => { els.status.textContent = err.message; });
