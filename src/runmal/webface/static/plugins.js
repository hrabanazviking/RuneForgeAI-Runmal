"use strict";
/* Runmal web face - Plugins tab (W-09). Desktop R-14
   Plugins manager parity over the engine's own roads:
   registry + manager ledger, detail + permission card +
   failure report, enable / disable / acknowledge,
   uninstall behind its confirmation, install with the
   preview verdict, update with a new pack, and the
   plugin settings roads (the generated form's fields,
   saved through the engine's validated road). Quick
   replies and expression sets are listed, not edited -
   the page says so. */
const $ = (id) => document.getElementById(id);
async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let d = "request failed (" + resp.status + ")"; try { const b = await resp.json(); if (b.error) d = b.error; } catch (e) {} throw new Error(d); }
  return resp.json();
}
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }
function post(path, body) { return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }); }
let plugins = [];
let selectedId = null;
let settingsForm = null;
async function load() {
  const view = await api("/webface/plugins");
  plugins = view.plugins;
  $("p-manager").textContent = view.manager_words;
  $("p-words").textContent = view.words;
  $("p-citizen-note").textContent = view.citizen_note;
  const list = $("p-list"); list.innerHTML = "";
  plugins.forEach((row) => {
    const li = el("li", row.line, "roster-row");
    const btn = el("button", "Select", "btn small ghost");
    btn.type = "button";
    btn.addEventListener("click", () => selectPlugin(row.id));
    li.appendChild(btn); list.appendChild(li);
  });
  const fails = $("p-failures"); fails.innerHTML = "";
  view.failures.forEach((row) => fails.appendChild(el("li", row.line)));
  const qr = $("p-qr"); qr.innerHTML = "";
  view.quick_replies.forEach((row) => qr.appendChild(el("li", row.line)));
  const ex = $("p-expr"); ex.innerHTML = "";
  view.expression_sets.forEach((row) => ex.appendChild(el("li", row.line)));
  if (selectedId) await selectPlugin(selectedId);
}
function renderSettings(form, settings) {
  settingsForm = form;
  const box = $("p-settings"); box.innerHTML = "";
  if (!form) {
    box.appendChild(el("p", "The engine returned no settings form for this plugin.", "muted"));
    return;
  }
  if (!form.has_settings) {
    box.appendChild(el("p", form.message || "This plugin declares no settings.", "muted"));
    return;
  }
  (form.fields || []).forEach((field) => {
    const label = el("label", (field.label || field.name) + (field.help ? " - " + field.help : ""));
    let input;
    const value = settings && settings.values ? settings.values[field.name] : field.value;
    if (field.widget === "checkbox") {
      input = el("input"); input.type = "checkbox"; input.checked = !!value;
    } else if (field.widget === "select") {
      input = el("select");
      (field.enum || []).forEach((opt) => {
        const o = el("option", String(opt)); o.value = String(opt);
        if (String(value) === String(opt)) o.selected = true;
        input.appendChild(o);
      });
    } else {
      input = el("input"); input.type = field.widget === "number" ? "number" : "text";
      input.value = value == null ? "" : String(value);
    }
    input.id = "p-set-" + field.name;
    input.dataset.kind = field.type || "";
    label.appendChild(input); box.appendChild(label);
  });
}
async function selectPlugin(id) {
  selectedId = id;
  const view = await api("/webface/plugins/" + encodeURIComponent(id));
  $("p-detail").textContent = view.words;
  $("p-card").textContent = view.card_words;
  $("p-failure").textContent = view.failure_line;
  renderSettings(view.settings_form, view.settings);
  if (view.settings_error) $("p-settings-status").textContent = view.settings_error;
}
function packPayload() {
  const text = $("p-pack").value.trim();
  const path = $("p-pack-path").value.trim();
  if (text) {
    let pack;
    try { pack = JSON.parse(text); } catch (e) { throw new Error("the pack envelope is not JSON: " + e.message); }
    return { pack: pack };
  }
  if (path) return { path: path };
  throw new Error("paste a pack envelope or name a pack file first");
}
async function action(name) {
  if (!selectedId) { $("p-status").textContent = "Select a plugin first."; return; }
  const view = await post("/webface/plugins/" + encodeURIComponent(selectedId) + "/" + name, {});
  $("p-action-out").textContent = view.words;
  await load();
}
async function uninstall() {
  if (!selectedId) { $("p-status").textContent = "Select a plugin first."; return; }
  const view = await post("/webface/plugins/" + encodeURIComponent(selectedId) + "/uninstall",
    { confirm: $("p-uninstall-confirm").checked });
  $("p-action-out").textContent = view.words;
  selectedId = null;
  await load();
}
async function saveSettings() {
  if (!selectedId || !settingsForm || !settingsForm.has_settings) return;
  const values = {};
  (settingsForm.fields || []).forEach((field) => {
    const input = $("p-set-" + field.name);
    if (!input) return;
    if (field.widget === "checkbox") values[field.name] = input.checked;
    else if (field.type === "integer") values[field.name] = parseInt(input.value, 10);
    else if (field.type === "number") values[field.name] = parseFloat(input.value);
    else if (field.widget === "select" && field.type === "integer") values[field.name] = parseInt(input.value, 10);
    else values[field.name] = input.value;
  });
  const view = await post("/webface/plugins/" + encodeURIComponent(selectedId) + "/settings", { values: values });
  $("p-settings-status").textContent = "Settings saved: " + JSON.stringify(view.settings.values || {});
  await selectPlugin(selectedId);
}
async function deleteSettings() {
  if (!selectedId) return;
  await post("/webface/plugins/" + encodeURIComponent(selectedId) + "/settings/delete",
    { confirm: $("p-settings-del-confirm").checked });
  $("p-settings-status").textContent = "Stored settings deleted; the declared defaults remain.";
  await selectPlugin(selectedId);
}
$("p-enable").addEventListener("click", () => action("enable").catch((e) => { $("p-action-out").textContent = e.message; }));
$("p-disable").addEventListener("click", () => action("disable").catch((e) => { $("p-action-out").textContent = e.message; }));
$("p-ack").addEventListener("click", () => action("acknowledge").catch((e) => { $("p-action-out").textContent = e.message; }));
$("p-uninstall").addEventListener("click", () => uninstall().catch((e) => { $("p-action-out").textContent = e.message; }));
$("p-preview").addEventListener("click", async () => {
  try { const view = await post("/webface/plugins/install/preview", packPayload()); $("p-install-out").textContent = view.words; }
  catch (e) { $("p-install-out").textContent = e.message; }
});
$("p-install").addEventListener("click", async () => {
  try { const view = await post("/webface/plugins/install", packPayload()); $("p-install-out").textContent = view.words; await load(); }
  catch (e) { $("p-install-out").textContent = e.message; }
});
$("p-update").addEventListener("click", async () => {
  if (!selectedId) { $("p-install-out").textContent = "Select a plugin first."; return; }
  try { const view = await post("/webface/plugins/" + encodeURIComponent(selectedId) + "/update", packPayload()); $("p-install-out").textContent = view.words; await load(); }
  catch (e) { $("p-install-out").textContent = e.message; }
});
$("p-settings-save").addEventListener("click", () => saveSettings().catch((e) => { $("p-settings-status").textContent = e.message; }));
$("p-settings-del").addEventListener("click", () => deleteSettings().catch((e) => { $("p-settings-status").textContent = e.message; }));
load().catch((e) => { $("p-status").textContent = e.message; });
