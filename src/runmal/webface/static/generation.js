"use strict";
/* Runmal web face - Generation tab (W-04). ONE uniform sampler
   form (built from /webface/sampler-form, the engine's canonical
   29 keys) drives preset bags, bundle sampler sections and
   per-chat override deltas. Unknown keys are carried verbatim
   and named. */
const $ = (id) => document.getElementById(id);
const state = { fields: [], presets: [], bundles: [], chats: [] };

async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let d = "request failed (" + resp.status + ")"; try { const b = await resp.json(); if (b.error) d = b.error; } catch (e) {} throw new Error(d); }
  return resp.json();
}
function jsonOpts(method, body) { return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }; }
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }
function setStatus(t) { $("g-status").textContent = t || ""; }

function valueToText(f, v) {
  if (v == null) return "";
  if (f.kind === "strings" && Array.isArray(v)) return v.join("\n");
  if (f.kind === "bias" && typeof v === "object") return Object.keys(v).sort((a, b) => a - b).map((k) => k + " = " + v[k]).join("\n");
  return String(v);
}
function samplerForm(known) {
  const wrap = el("div");
  const inputs = {};
  let group = null, box = null;
  for (const f of state.fields) {
    if (f.group !== group) { group = f.group; box = el("fieldset"); box.appendChild(el("legend", group)); wrap.appendChild(box); }
    let input;
    if (f.kind === "strings" || f.kind === "bias") { input = document.createElement("textarea"); input.rows = 2; }
    else { input = document.createElement("input"); input.type = "number"; input.step = f.kind === "int" ? "1" : "any"; }
    input.value = valueToText(f, (known || {})[f.key]);
    inputs[f.key] = input;
    const l = el("label", f.label + " (" + f.key + ")"); l.appendChild(input); box.appendChild(l);
  }
  return { wrap, read() {
    const out = {};
    for (const f of state.fields) {
      const raw = inputs[f.key].value.trim();
      if (!raw) continue;
      if (f.kind === "strings") out[f.key] = raw.split("\n").map((s) => s.trim()).filter(Boolean);
      else if (f.kind === "bias") { const b = {}; for (const line of raw.split("\n")) { const [k, v] = line.split("=").map((s) => s.trim()); if (k) b[k] = Number(v); } out[f.key] = b; }
      else out[f.key] = raw;
    }
    return out;
  } };
}
function extraNote(extra) {
  const keys = Object.keys(extra || {});
  return keys.length ? "Also carried, exactly as stored (keys this form does not know): " + keys.join(", ") : "No extra keys.";
}

async function loadAll() {
  state.fields = await api("/webface/sampler-form");
  state.presets = await api("/webface/presets");
  state.bundles = await api("/webface/bundles");
  state.chats = await api("/webface/chats");
  renderPresets(); renderBundles(); fillChatSelects();
}
function renderPresets() {
  const list = $("g-presets"); list.innerHTML = "";
  for (const p of state.presets) {
    const li = el("li", null, "roster-row");
    li.appendChild(el("span", p.name + " - " + Object.keys(p.params || {}).length + " value(s)" + (p.extra_names && p.extra_names.length ? " - extra keys carried: " + p.extra_names.join(", ") : "")));
    const edit = el("button", "Edit", "btn small ghost"); edit.type = "button"; edit.addEventListener("click", () => presetEditor(p));
    const del = el("button", "Delete", "btn small ghost"); del.type = "button"; del.addEventListener("click", async () => { if (window.confirm("Delete preset '" + p.name + "'?")) { await api("/webface/presets/" + p.id, { method: "DELETE" }); setStatus("Deleted '" + p.name + "'."); loadAll(); } });
    li.appendChild(edit); li.appendChild(del); list.appendChild(li);
  }
  const add = el("button", "New preset", "btn"); add.type = "button"; add.addEventListener("click", () => presetEditor(null));
  list.appendChild(add);
}
function presetEditor(p) {
  const box = $("g-editor"); box.hidden = false; box.innerHTML = "";
  box.appendChild(el("h2", p ? "Edit preset" : "New preset"));
  const name = document.createElement("input"); name.value = p ? p.name : "";
  const nameL = el("label", "Name"); nameL.appendChild(name); box.appendChild(nameL);
  const form = samplerForm(p ? p.known : {}); box.appendChild(form.wrap);
  box.appendChild(el("p", extraNote(p ? p.extra : {}), "muted"));
  const ref = document.createElement("input"); ref.value = p ? (p.template_ref || "") : "";
  const refL = el("label", "Prompt template reference"); refL.appendChild(ref); box.appendChild(refL);
  const save = el("button", "Save preset", "btn"); save.type = "button";
  save.addEventListener("click", async () => {
    try {
      const body = { name: name.value, sampler: form.read(), extra: p ? p.extra : {}, template_ref: ref.value };
      const saved = p ? await api("/webface/presets/" + p.id, jsonOpts("PATCH", body)) : await api("/webface/presets", jsonOpts("POST", body));
      setStatus("Saved preset '" + saved.name + "'."); box.hidden = true; loadAll();
    } catch (e) { setStatus("Preset not saved: " + e.message); }
  });
  box.appendChild(save);
}
function renderBundles() {
  const list = $("g-bundles"); list.innerHTML = "";
  for (const row of state.bundles) {
    const b = row.bundle || {};
    const li = el("li", null, "roster-row");
    li.appendChild(el("span", (b.name || row.name) + " - sampler: " + Object.keys(b.sampler || {}).length + " value(s)" + (row.carried && row.carried.length ? " - also carries: " + row.carried.join(", ") : "") + (row.extra_names && row.extra_names.length ? " - extra sampler keys: " + row.extra_names.join(", ") : "")));
    const edit = el("button", "Edit", "btn small ghost"); edit.type = "button"; edit.addEventListener("click", () => bundleEditor(row));
    const del = el("button", "Delete", "btn small ghost"); del.type = "button"; del.addEventListener("click", async () => { if (window.confirm("Delete this bundle?")) { await api("/webface/bundles/" + row.id, { method: "DELETE" }); setStatus("Bundle deleted."); loadAll(); } });
    li.appendChild(edit); li.appendChild(del); list.appendChild(li);
  }
  const add = el("button", "New bundle", "btn"); add.type = "button"; add.addEventListener("click", () => bundleEditor(null));
  list.appendChild(add);
  const sel = $("ov-bundle"); sel.innerHTML = "";
  for (const row of state.bundles) { const o = el("option", (row.bundle || {}).name || row.name); o.value = row.id; sel.appendChild(o); }
}
function bundleEditor(row) {
  const box = $("g-bundle-editor"); box.hidden = false; box.innerHTML = "";
  const b = row ? (row.bundle || {}) : {};
  box.appendChild(el("h2", row ? "Edit bundle" : "New bundle"));
  if (row && row.carried.length) box.appendChild(el("p", "This bundle also carries, untouched: " + row.carried.join(", ") + ".", "muted"));
  const name = document.createElement("input"); name.value = b.name || "";
  const nameL = el("label", "Name"); nameL.appendChild(name); box.appendChild(nameL);
  const form = samplerForm(row ? row.known : {}); box.appendChild(form.wrap);
  box.appendChild(el("p", extraNote(row ? row.extra : {}), "muted"));
  const ref = document.createElement("input"); ref.value = b.template_ref || "";
  const refL = el("label", "Prompt template reference"); refL.appendChild(ref); box.appendChild(refL);
  const save = el("button", "Save bundle", "btn"); save.type = "button";
  save.addEventListener("click", async () => {
    try {
      const body = { name: name.value, sampler: form.read(), extra: row ? row.extra : {}, template_ref: ref.value };
      const saved = row ? await api("/webface/bundles/" + row.id, jsonOpts("PATCH", body)) : await api("/webface/bundles", jsonOpts("POST", body));
      setStatus("Saved bundle '" + (saved.bundle ? saved.bundle.name : saved.name) + "'."); box.hidden = true; loadAll();
    } catch (e) { setStatus("Bundle not saved: " + e.message); }
  });
  box.appendChild(save);
}
function fillChatSelects() {
  for (const id of ["ov-chat", "rv-chat"]) {
    const sel = $(id); sel.innerHTML = "";
    for (const c of state.chats) { const o = el("option", c.title || ("Chat " + c.id.slice(0, 8))); o.value = c.id; sel.appendChild(o); }
  }
  buildOverrideForm();
}
let ovForm = null;
async function buildOverrideForm() {
  const wrap = $("ov-form"); wrap.innerHTML = "";
  ovForm = samplerForm({});
  wrap.appendChild(el("p", "The delta: only the values you set here override the bundle for the chosen chat.", "muted"));
  wrap.appendChild(ovForm.wrap);
  try {
    const rows = await api("/webface/overrides");
    const mine = rows.find((r) => r.scope_kind === "chat" && r.owner_id === $("ov-chat").value);
    $("ov-status").textContent = mine ? "This chat already has an override naming a bundle; saving replaces it." : "This chat has no override yet.";
  } catch (e) { /* words stay neutral */ }
}
$("ov-chat").addEventListener("change", buildOverrideForm);
$("ov-save").addEventListener("click", async () => {
  try {
    const saved = await api("/webface/overrides/chat/" + $("ov-chat").value, jsonOpts("PUT", { bundle_id: $("ov-bundle").value, sampler: ovForm.read(), extra: {} }));
    $("ov-status").textContent = "Override saved for this chat (bundle " + saved.bundle_id + ").";
  } catch (e) { $("ov-status").textContent = "Override not saved: " + e.message; }
});
$("ov-delete").addEventListener("click", async () => {
  try { await api("/webface/overrides/chat/" + $("ov-chat").value, { method: "DELETE" }); $("ov-status").textContent = "Override deleted."; }
  catch (e) { $("ov-status").textContent = "No override to delete: " + e.message; }
});
$("rv-show").addEventListener("click", async () => {
  const out = $("rv-out"); out.innerHTML = "";
  try {
    const view = await api("/webface/resolve?chat_id=" + encodeURIComponent($("rv-chat").value));
    const table = el("table");
    for (const r of view.rows) { const tr = el("tr"); tr.appendChild(el("td", r.label)); tr.appendChild(el("td", String(r.value))); tr.appendChild(el("td", "from " + r.source)); table.appendChild(tr); }
    out.appendChild(table);
    for (const n of view.notes) out.appendChild(el("p", n, "muted"));
    if (!view.rows.length) out.appendChild(el("p", "Nothing is set for this chat beyond the engine defaults.", "muted"));
  } catch (e) { out.appendChild(el("p", "Preview failed: " + e.message)); }
});
loadAll().catch((e) => setStatus("Could not load: " + e.message));
