"use strict";
/* Runmal web face - Scenarios tab (W-06). Library + editor over
   the engine's definition store: authored text fields are the
   form's own; structured sections ride as JSON, carried
   unchanged unless replaced wholesale; unknown stored keys
   survive every save (compose-over-stored). Apply = fresh chat
   + the engine's bind (bootstrap lines seed the opening). */
const $ = (id) => document.getElementById(id);
const state = { rows: [], detail: null, checked: null, characters: [] };
async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let d = "request failed (" + resp.status + ")"; try { const b = await resp.json(); if (b.error) d = b.error; } catch (e) {} throw new Error(d); }
  return resp.json();
}
function jsonOpts(method, body) { return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }; }
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }

async function loadList() {
  const q = new URLSearchParams();
  if ($("s-search").value) q.set("q", $("s-search").value);
  if ($("s-fav").checked) q.set("favourites_only", "true");
  const view = await api("/webface/scenarios?" + q.toString());
  state.rows = view.scenarios;
  $("s-count").textContent = view.total + " scenario(s)";
  const list = $("s-list"); list.innerHTML = "";
  view.scenarios.forEach((row, i) => {
    const li = el("li");
    const b = el("button", view.lines[i], "btn ghost small"); b.type = "button";
    b.addEventListener("click", () => openEditor(row.id));
    li.appendChild(b); list.appendChild(li);
  });
  const binds = await api("/webface/scenarios/bindings");
  const bl = $("s-bindings"); bl.innerHTML = "";
  binds.bindings.forEach((b, i) => {
    const li = el("li", binds.lines[i] + " ");
    const u = el("button", "Unbind", "btn ghost small"); u.type = "button";
    u.addEventListener("click", async () => {
      try { const r = await api("/webface/scenarios/bindings/" + b.chat_id, { method: "DELETE" }); $("s-bind-status").textContent = r.words; await loadList(); }
      catch (e) { $("s-bind-status").textContent = e.message; }
    });
    li.appendChild(u); bl.appendChild(li);
  });
  if (!binds.bindings.length) bl.appendChild(el("li", "No bindings yet."));
}

function fieldRow(labelText, input) {
  const lab = el("label", labelText); lab.appendChild(input); return lab;
}
function textInput(value, long) {
  const n = document.createElement(long ? "textarea" : "input");
  n.className = "entry-box"; n.value = value || ""; return n;
}
async function openEditor(id) {
  const box = $("s-editor"); box.hidden = false; box.innerHTML = "";
  let detail = null;
  if (id) { detail = await api("/webface/scenarios/" + id); state.detail = detail; }
  else state.detail = null;
  const def = detail ? detail.definition : {};
  box.appendChild(el("h2", id ? ("Scenario: " + (detail.record.name || "")) : "New scenario"));
  if (detail) {
    box.appendChild(el("p", "Revision " + detail.record.revision + " · source format " + (detail.record.source_format || "") + " · " + detail.carried, "muted"));
    const rep = detail.record.report || {};
    const un = rep.unmappable || [];
    if (un.length) box.appendChild(el("p", un.length + " unmappable element(s) recorded on import - kept as data, never run.", "muted"));
  }
  const inputs = {};
  const fields = detail ? detail.fields : null;
  const fieldDefs = fields || [];
  for (const f of fieldDefs) { const inp = textInput(def[f.name], f.long); if (id && f.long) inp.setAttribute("data-draft-key", "scenario:" + id + ":" + f.name); inputs[f.name] = inp; box.appendChild(fieldRow(f.label, inp)); }
  const sectionInputs = {};
  const sections = detail ? detail.sections : [];
  for (const s of sections) {
    const ta = textInput(s.json, true); ta.rows = 6; sectionInputs[s.name] = ta;
    box.appendChild(fieldRow(s.label + " (JSON - carried unchanged unless you replace it)", ta));
  }
  const row = el("div"); row.className = "row";
  const save = el("button", id ? "Save scenario" : "Create scenario", "btn"); save.type = "button";
  save.addEventListener("click", async () => {
    try {
      const values = {}; for (const k in inputs) values[k] = inputs[k].value;
      const secs = {}; for (const k in sectionInputs) secs[k] = sectionInputs[k].value;
      const r = await api(id ? "/webface/scenarios/" + id : "/webface/scenarios", jsonOpts(id ? "PUT" : "POST", { values, sections: secs }));
      if (window.RunmalEntryBox) for (const k in inputs) window.RunmalEntryBox.retireDraft(inputs[k]);
      $("s-status").textContent = r.words; await loadList(); if (r.id) await openEditor(r.id);
    } catch (e) { $("s-status").textContent = e.message; }
  });
  row.appendChild(save);
  if (id) {
    const dup = el("button", "Duplicate", "btn ghost"); dup.type = "button";
    dup.addEventListener("click", async () => { try { const r = await api("/webface/scenarios/" + id + "/duplicate", jsonOpts("POST", {})); $("s-status").textContent = r.words; await loadList(); } catch (e) { $("s-status").textContent = e.message; } });
    row.appendChild(dup);
    const fav = el("button", detail.organisation && detail.organisation.is_favourite ? "Clear favourite" : "Make favourite", "btn ghost"); fav.type = "button";
    fav.addEventListener("click", async () => { try { const cur = !!(detail.organisation && detail.organisation.is_favourite); const r = await api("/webface/scenarios/" + id + "/favourite", jsonOpts("PUT", { is_favourite: !cur })); $("s-status").textContent = r.words; await loadList(); await openEditor(id); } catch (e) { $("s-status").textContent = e.message; } });
    row.appendChild(fav);
    const del = el("button", "Delete scenario", "btn ghost"); del.type = "button";
    del.addEventListener("click", async () => {
      if (!window.confirm("Delete this scenario definition? Chats it seeded keep their opening lines; bindings left behind will be named stale.")) return;
      try { const r = await api("/webface/scenarios/" + id, { method: "DELETE" }); $("s-status").textContent = r.words; box.hidden = true; await loadList(); } catch (e) { $("s-status").textContent = e.message; }
    });
    row.appendChild(del);
    const exp = el("a", "Download (native file)"); exp.href = "/webface/scenarios/" + id + "/export-file?format=native"; row.appendChild(exp);
    const expV = el("a", "Download (Voxta file)"); expV.href = "/webface/scenarios/" + id + "/export-file?format=voxta"; row.appendChild(expV);
  }
  box.appendChild(row);
  if (id) {
    const tagsInp = textInput(((detail.organisation || {}).tags || []).join(", "), false);
    box.appendChild(fieldRow("Tags (comma separated)", tagsInp));
    const tagBtn = el("button", "Save tags", "btn ghost small"); tagBtn.type = "button";
    tagBtn.addEventListener("click", async () => { try { const r = await api("/webface/scenarios/" + id + "/tags", jsonOpts("PUT", { tags: tagsInp.value })); $("s-status").textContent = r.words; await loadList(); } catch (e) { $("s-status").textContent = e.message; } });
    box.appendChild(tagBtn);
    box.appendChild(el("h3", "Start a chat from this scenario"));
    box.appendChild(el("p", "A fresh chat is made with the character you pick, then the scenario is bound to it: its opening (bootstrap) lines become the chat's first messages and its initial flags and variables are seeded. The chat is a normal chat afterwards - pin a mind in Connections before sending.", "muted"));
    const charSel = document.createElement("select"); charSel.classList.add("entry-box");
    for (const c of state.characters) { const o = el("option", c.name || c.id); o.value = c.id; charSel.appendChild(o); }
    box.appendChild(fieldRow("Character", charSel));
    const apply = el("button", "Start chat from scenario", "btn"); apply.type = "button";
    const applyOut = el("p", "", "muted");
    apply.addEventListener("click", async () => {
      try {
        const r = await api("/webface/scenarios/" + id + "/apply", jsonOpts("POST", { character_id: charSel.value }));
        applyOut.textContent = r.words + " " + r.note + " ";
        const a = el("a", "Open the chat"); a.href = "/chat"; applyOut.appendChild(a);
        await loadList();
      } catch (e) { applyOut.textContent = e.message; }
    });
    box.appendChild(apply); box.appendChild(applyOut);
    if (detail.bindings && detail.bindings.length) box.appendChild(el("p", "Bound to: " + detail.binding_lines.join(" · "), "muted"));
  }
  box.scrollIntoView({ block: "nearest" });
}
async function newEditor() {
  const model = await api("/webface/scenarios/editor-model");
  const box = $("s-editor");
  box.hidden = false; box.innerHTML = "";
  box.appendChild(el("h2", "New scenario"));
  const inputs = {}; const sectionInputs = {};
  for (const f of model.fields) { const inp = textInput("", f.long); inputs[f.name] = inp; box.appendChild(fieldRow(f.label, inp)); }
  for (const s of model.sections) { const ta = textInput(s.json, true); ta.rows = 6; sectionInputs[s.name] = ta; box.appendChild(fieldRow(s.label + " (JSON)", ta)); }
  const save = el("button", "Create scenario", "btn"); save.type = "button";
  save.addEventListener("click", async () => {
    try {
      const values = {}; for (const k in inputs) values[k] = inputs[k].value;
      const secs = {}; for (const k in sectionInputs) secs[k] = sectionInputs[k].value;
      const r = await api("/webface/scenarios", jsonOpts("POST", { values, sections: secs }));
      $("s-status").textContent = r.words; await loadList(); if (r.id) await openEditor(r.id);
    } catch (e) { $("s-status").textContent = e.message; }
  });
  box.appendChild(save);
  box.scrollIntoView({ block: "nearest" });
}
$("s-new").addEventListener("click", () => newEditor().catch((e) => { $("s-status").textContent = e.message; }));
$("s-search").addEventListener("keydown", (ev) => { if (ev.key === "Enter") loadList().catch((e) => { $("s-status").textContent = e.message; }); });
$("s-fav").addEventListener("change", () => loadList().catch((e) => { $("s-status").textContent = e.message; }));
async function readFile() {
  const f = $("s-file").files[0]; if (!f) throw new Error("pick a scenario file first");
  return JSON.parse(await f.text());
}
$("s-check").addEventListener("click", async () => {
  try { const doc = await readFile(); const r = await api("/webface/scenarios/import-check", jsonOpts("POST", { document: doc })); state.checked = r.scenario; $("s-import-status").textContent = r.words; const out = $("s-import-out"); out.innerHTML = ""; out.appendChild(el("pre", JSON.stringify(r.report, null, 2), "words")); }
  catch (e) { $("s-import-status").textContent = e.message; }
});
$("s-store").addEventListener("click", async () => {
  try { const doc = state.checked || (await readFile()); const r = await api("/webface/scenarios", jsonOpts("POST", { values: {}, sections: {}, document: doc })); $("s-import-status").textContent = r.words; await loadList(); }
  catch (e) { $("s-import-status").textContent = e.message; }
});
(async () => { state.characters = await api("/webface/characters"); await loadList(); })().catch((e) => { $("s-status").textContent = e.message; });
