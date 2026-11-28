"use strict";
/* Runmal web face - Backups tab (W-09). Desktop R-14
   Backups parity over the engine's own roads: online
   database + full backups, restore STAGING only (never
   applied - no shell surface applies a restore), archive
   import into staging, and downloads read from the
   engine's own backups folder on this host (the engine
   has no HTTP download road, and no delete road exists,
   so this page offers none and says so). */
const $ = (id) => document.getElementById(id);
async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let d = "request failed (" + resp.status + ")"; try { const b = await resp.json(); if (b.error) d = b.error; } catch (e) {} throw new Error(d); }
  return resp.json();
}
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }
function post(path, body) { return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }); }
let backups = [];
let selected = null;
function render() {
  const list = $("b-list"); list.innerHTML = "";
  backups.forEach((row) => {
    const li = el("li", row.line, "roster-row");
    const btn = el("button", "Select", "btn small ghost");
    btn.type = "button";
    btn.addEventListener("click", () => { selected = row; render(); });
    if (selected && selected.name === row.name) li.classList.add("active");
    li.appendChild(btn); list.appendChild(li);
  });
  const link = $("b-download");
  if (selected) {
    link.hidden = false;
    link.href = "/webface/backups/download?name=" + encodeURIComponent(selected.name);
    link.textContent = "Download " + selected.name;
  } else { link.hidden = true; }
}
async function load() {
  const view = await api("/webface/backups");
  backups = view.backups; selected = backups[0] || null;
  $("b-words").textContent = view.words;
  $("b-download-note").textContent = view.notes.download;
  $("b-delete-note").textContent = view.notes.delete;
  $("b-restore-note").textContent = view.notes.restore;
  render();
}
async function create(full) {
  const btn = full ? $("b-create-full") : $("b-create");
  btn.disabled = true;
  $("b-create-status").textContent = full
    ? "Making the full backup - bundling the database and the asset tree; this can take a little while..."
    : "Making the database backup - the engine copies the live database safely while it runs...";
  try {
    const view = await post("/webface/backups", { full: full });
    $("b-created").textContent = view.words;
    $("b-create-status").textContent = "";
    await load();
    selected = backups.find((row) => row.name === view.backup.name) || selected;
    render();
  } finally { btn.disabled = false; }
}
async function stage(full) {
  if (!selected) { $("b-stage-status").textContent = "Select a backup first."; return; }
  if ((selected.kind === "full") !== full) {
    $("b-stage-status").textContent = full
      ? "That row is a database backup - Stage restore is its road. Full bundles are staged by the name their creation returned."
      : "That row is a full bundle - Stage full restore is its road.";
    return;
  }
  if (!$("b-stage-confirm").checked) {
    $("b-stage-status").textContent = "Tick the staging understanding first - staging verifies a copy and restores nothing over the live data.";
    return;
  }
  const view = await post("/webface/backups/stage", { name: selected.name, full: full });
  $("b-stage-out").textContent = view.words;
  $("b-stage-status").textContent = "Restore of " + selected.name + " staged for review - the live data was NOT overwritten.";
}
async function doImport() {
  const view = await post("/webface/backups/import", {
    path: $("b-import-path").value, confirm: $("b-import-confirm").checked });
  $("b-import-out").textContent = view.words;
}
$("b-create").addEventListener("click", () => create(false).catch((e) => { $("b-create-status").textContent = e.message; }));
$("b-create-full").addEventListener("click", () => create(true).catch((e) => { $("b-create-status").textContent = e.message; }));
$("b-stage").addEventListener("click", () => stage(false).catch((e) => { $("b-stage-status").textContent = e.message; }));
$("b-stage-full").addEventListener("click", () => stage(true).catch((e) => { $("b-stage-status").textContent = e.message; }));
$("b-import").addEventListener("click", () => doImport().catch((e) => { $("b-import-out").textContent = e.message; }));
load().catch((e) => { $("b-status").textContent = e.message; });
