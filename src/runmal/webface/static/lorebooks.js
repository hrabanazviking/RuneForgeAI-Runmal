"use strict";
/* Runmal web face - Lorebooks tab (W-05). Every text-entry
   element carries the shared "entry-box" class (W-11 sweep hook). Book and entry forms
   are GENERATED from the engine's P-042 editor census
   (/webface/lorebooks/schema): field order, kinds and select
   options come from the census. activation_kind is derived -
   shown read-only, never sent. Saves go through the webface's
   lossless composition, so stored fields the form does not
   know survive an edit. Scope assignments (with budget +
   position) are shown separately from card bindings. */
const $ = (id) => document.getElementById(id);
const state = { forms: {}, books: [], characters: [], chats: [], detail: null };

async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let d = "request failed (" + resp.status + ")"; try { const b = await resp.json(); if (b.error) d = b.error; } catch (e) {} throw new Error(d); }
  return resp.json();
}
function jsonOpts(method, body) { return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }; }
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }
function setStatus(t) { $("lb-status").textContent = t || ""; }

function valueToText(f, v) {
  if (v == null) return "";
  if (f.kind === "keys" && Array.isArray(v)) return v.join("\n");
  return String(v);
}
function activationWords(values) {
  if (values && values.constant) return "constant (always on)";
  if (values && values.vectorised) return "vectorised (similarity)";
  return "keyword";
}
/* Build a census form. Returns {wrap, read()} where read()
   yields the raw contract: keys as lists, bools as bools,
   everything else as text. Derived fields render read-only. */
function censusForm(fields, values, draftPrefix) {
  const wrap = el("div");
  const inputs = {};
  const current = {};
  for (const f of fields) {
    const v = (values || {})[f.name];
    current[f.name] = v;
    if (f.derived) {
      const p = el("p", f.label + ": " + activationWords(values || {}), "muted");
      p.dataset.derivedFor = f.name;
      wrap.appendChild(p);
      continue;
    }
    let input;
    if (f.kind === "bool") {
      input = document.createElement("input"); input.type = "checkbox"; input.checked = !!v;
    } else if (f.kind === "select") {
      input = document.createElement("select");
      for (const opt of f.options) { const o = el("option", opt); o.value = opt; input.appendChild(o); }
      if (v != null) input.value = String(v);
    } else if (f.kind === "longtext" || f.kind === "keys") {
      input = document.createElement("textarea"); input.rows = f.kind === "keys" ? 3 : 4; input.value = valueToText(f, v);
    } else {
      input = document.createElement("input");
      if (f.kind === "int" || f.kind === "int_or_null") input.type = "number";
      input.value = valueToText(f, v);
    }
    input.classList.add("entry-box");
    // W-11: prose fields of an EXISTING book/entry carry a draft key
    // (page + book/entry + field); new entities have no stable
    // identity yet, so their fields get parts 1-3 only.
    if (draftPrefix && (f.kind === "longtext" || f.kind === "keys" || !f.kind))
      input.setAttribute("data-draft-key", draftPrefix + ":" + f.name);
    inputs[f.name] = input;
    const label = el("label", f.label);
    label.appendChild(input);
    if (f.help) label.appendChild(el("span", " " + f.help, "muted"));
    wrap.appendChild(label);
  }
  return { wrap, inputs, read() {
    const out = {};
    for (const f of fields) {
      if (f.derived) continue;
      const input = inputs[f.name];
      if (!input) continue;
      if (f.kind === "bool") out[f.name] = input.checked;
      else if (f.kind === "keys") out[f.name] = input.value.split("\n").map((s) => s.trim()).filter(Boolean);
      else out[f.name] = input.value;
    }
    return out;
  } };
}

async function loadBooks() {
  state.books = await api("/webface/lorebooks");
  const list = $("lb-list"); list.innerHTML = "";
  for (const b of state.books) {
    const li = el("li", null, "roster-row");
    li.appendChild(el("span", b.name + " - " + (b.entry_count || 0) + " entries"));
    const open = el("button", "Open", "btn small ghost"); open.type = "button";
    open.addEventListener("click", () => openBook(b.id));
    const del = el("button", "Delete", "btn small ghost"); del.type = "button";
    del.addEventListener("click", async () => {
      if (!window.confirm("Delete lorebook '" + b.name + "' and all its entries?")) return;
      await api("/webface/lorebooks/" + b.id, { method: "DELETE" });
      setStatus("Deleted '" + b.name + "'.");
      hideDetail(); loadBooks();
    });
    const exp = el("a", "Export", "btn small ghost"); exp.href = "/webface/lorebooks/" + b.id + "/export";
    const pack = el("a", "Pack", "btn small ghost"); pack.href = "/webface/lorebooks/" + b.id + "/pack";
    li.appendChild(open); li.appendChild(exp); li.appendChild(pack); li.appendChild(del);
    list.appendChild(li);
  }
  const add = el("button", "New lorebook", "btn"); add.type = "button";
  add.addEventListener("click", () => bookEditor(null));
  list.appendChild(add);
}
function hideDetail() {
  state.detail = null;
  for (const id of ["lb-editor", "lb-entries", "lb-entry-editor", "lb-scopes", "lb-previews"]) $(id).hidden = true;
}
function bookEditor(book) {
  const box = $("lb-editor"); box.hidden = false; box.innerHTML = "";
  box.appendChild(el("h2", book ? "Edit lorebook" : "New lorebook"));
  const form = censusForm(state.forms.book || [], book || {}, book ? "lorebook:" + book.id : null);
  box.appendChild(form.wrap);
  const save = el("button", book ? "Save book" : "Create book", "btn"); save.type = "button";
  save.addEventListener("click", async () => {
    try {
      const saved = book
        ? await api("/webface/lorebooks/" + book.id, jsonOpts("PATCH", { values: form.read() }))
        : await api("/webface/lorebooks", jsonOpts("POST", { values: form.read() }));
      if (window.RunmalEntryBox) for (const n of Object.values(form.inputs)) window.RunmalEntryBox.retireDraft(n);
      setStatus("Saved '" + saved.name + "'.");
      await loadBooks();
      openBook(saved.id);
    } catch (e) { setStatus(e.message); }
  });
  box.appendChild(save);
}
async function openBook(bookId) {
  state.detail = await api("/webface/lorebooks/" + bookId);
  bookEditor(state.detail.book);
  renderEntries(); renderScopes(); renderPreviews();
}
function renderEntries() {
  const box = $("lb-entries"); box.hidden = false; box.innerHTML = "";
  box.appendChild(el("h2", "Entries in '" + state.detail.book.name + "'"));
  const list = el("ul", null, "roster");
  for (const entry of state.detail.entries) {
    const li = el("li", null, "roster-row");
    const keys = (entry.keys || []).join(", ");
    li.appendChild(el("span", (entry.name || "(unnamed)") + " - " + activationWords(entry) + (keys ? " - keys: " + keys : "")));
    const edit = el("button", "Edit", "btn small ghost"); edit.type = "button";
    edit.addEventListener("click", () => entryEditor(entry));
    const del = el("button", "Delete", "btn small ghost"); del.type = "button";
    del.addEventListener("click", async () => {
      if (!window.confirm("Delete entry '" + (entry.name || entry.id) + "'?")) return;
      await api("/webface/lorebooks/" + state.detail.book.id + "/entries/" + entry.id, { method: "DELETE" });
      openBook(state.detail.book.id);
    });
    li.appendChild(edit); li.appendChild(del); list.appendChild(li);
  }
  box.appendChild(list);
  const add = el("button", "New entry", "btn"); add.type = "button";
  add.addEventListener("click", () => entryEditor(null));
  box.appendChild(add);
}
function entryEditor(entry) {
  const box = $("lb-entry-editor"); box.hidden = false; box.innerHTML = "";
  box.appendChild(el("h2", entry ? "Edit entry" : "New entry"));
  const form = censusForm(state.forms.entry || [], entry || {}, entry ? "lorebook:" + state.detail.book.id + ":entry:" + entry.id : null);
  box.appendChild(form.wrap);
  const save = el("button", entry ? "Save entry" : "Create entry", "btn"); save.type = "button";
  save.addEventListener("click", async () => {
    try {
      const bookId = state.detail.book.id;
      const saved = entry
        ? await api("/webface/lorebooks/" + bookId + "/entries/" + entry.id, jsonOpts("PATCH", { values: form.read() }))
        : await api("/webface/lorebooks/" + bookId + "/entries", jsonOpts("POST", { values: form.read() }));
      if (window.RunmalEntryBox) for (const n of Object.values(form.inputs)) window.RunmalEntryBox.retireDraft(n);
      setStatus("Saved entry '" + (saved.name || saved.id) + "'.");
      openBook(bookId);
    } catch (e) { setStatus(e.message); }
  });
  box.appendChild(save);
}
function ownerOptions(kind) {
  if (kind === "character" || kind === "persona") return state.characters.map((c) => [c.id, c.name || c.id]);
  if (kind === "chat") return state.chats.map((c) => [c.id, c.title || c.id]);
  return [];
}
function renderScopes() {
  const box = $("lb-scopes"); box.hidden = false; box.innerHTML = "";
  box.appendChild(el("h2", "Scope assignments"));
  box.appendChild(el("p", state.detail.scope_note, "muted"));
  const list = el("ul", null, "roster");
  for (const s of state.detail.scopes) {
    const li = el("li", null, "roster-row");
    li.appendChild(el("span", s.words));
    const del = el("button", "Remove", "btn small ghost"); del.type = "button";
    del.addEventListener("click", async () => {
      const q = new URLSearchParams({ scope_kind: s.scope_kind });
      if (s.owner_id) q.set("owner_id", s.owner_id);
      await api("/webface/lorebooks/" + state.detail.book.id + "/scope?" + q.toString(), { method: "DELETE" });
      openBook(state.detail.book.id);
    });
    li.appendChild(del); list.appendChild(li);
  }
  box.appendChild(list);
  if (state.detail.bindings && state.detail.bindings.length) {
    box.appendChild(el("h3", "Also: card bindings naming this book"));
    const bl = el("ul", null, "roster");
    for (const b of state.detail.bindings) bl.appendChild(el("li", b.words));
    box.appendChild(bl);
  }
  const kind = document.createElement("select"); kind.classList.add("entry-box");
  for (const k of ["global", "character", "persona", "chat"]) { const o = el("option", k); o.value = k; kind.appendChild(o); }
  const owner = document.createElement("select"); owner.classList.add("entry-box");
  const budget = document.createElement("input"); budget.type = "number"; budget.classList.add("entry-box"); budget.placeholder = "budget (blank = none)";
  const position = document.createElement("input"); position.type = "number"; position.classList.add("entry-box"); position.value = "0";
  function fillOwners() {
    owner.innerHTML = "";
    for (const [id, name] of ownerOptions(kind.value)) { const o = el("option", name); o.value = id; owner.appendChild(o); }
    owner.disabled = kind.value === "global";
  }
  kind.addEventListener("change", fillOwners); fillOwners();
  const row = el("div", null, "row");
  const kL = el("label", "Kind"); kL.appendChild(kind); row.appendChild(kL);
  const oL = el("label", "Owner"); oL.appendChild(owner); row.appendChild(oL);
  const bL = el("label", "Budget"); bL.appendChild(budget); row.appendChild(bL);
  const pL = el("label", "Position"); pL.appendChild(position); row.appendChild(pL);
  const assign = el("button", "Assign / update scope", "btn"); assign.type = "button";
  assign.addEventListener("click", async () => {
    try {
      const body = { scope_kind: kind.value, owner_id: owner.disabled ? null : owner.value, position: position.value };
      if (budget.value !== "") body.token_budget = Number(budget.value);
      const saved = await api("/webface/lorebooks/" + state.detail.book.id + "/scope", jsonOpts("PUT", body));
      setStatus("Scope saved: " + saved.words);
      openBook(state.detail.book.id);
    } catch (e) { setStatus(e.message); }
  });
  row.appendChild(assign);
  box.appendChild(row);
  box.appendChild(el("p", "Assigning the same kind + owner again updates its budget and position.", "muted"));
}
function renderPreviews() {
  const box = $("lb-previews"); box.hidden = false; box.innerHTML = "";
  box.appendChild(el("h2", "Previews"));
  box.appendChild(el("h3", "This book's activation preview"));
  const bookMsgs = document.createElement("textarea"); bookMsgs.classList.add("entry-box"); bookMsgs.rows = 3;
  bookMsgs.placeholder = "Sample messages, one per line";
  box.appendChild(bookMsgs);
  const bookBtn = el("button", "Preview this book", "btn"); bookBtn.type = "button";
  const bookOut = el("div");
  bookBtn.addEventListener("click", async () => {
    try {
      const r = await api("/webface/lorebooks/" + state.detail.book.id + "/preview", jsonOpts("POST", { messages: bookMsgs.value.split("\n") }));
      bookOut.innerHTML = "";
      for (const w of r.words) bookOut.appendChild(el("p", w));
      if (!r.words.length) bookOut.appendChild(el("p", "No entries to judge.", "muted"));
    } catch (e) { setStatus(e.message); }
  });
  box.appendChild(bookBtn); box.appendChild(bookOut);
  box.appendChild(el("h3", "Layered preview for a chat"));
  const chatSel = document.createElement("select"); chatSel.classList.add("entry-box");
  for (const c of state.chats) { const o = el("option", c.title || c.id); o.value = c.id; chatSel.appendChild(o); }
  box.appendChild(chatSel);
  const chatMsgs = document.createElement("textarea"); chatMsgs.classList.add("entry-box"); chatMsgs.rows = 3;
  chatMsgs.placeholder = "Sample messages, one per line";
  box.appendChild(chatMsgs);
  const chatBtn = el("button", "Preview the chat's lore", "btn"); chatBtn.type = "button";
  const chatOut = el("div");
  chatBtn.addEventListener("click", async () => {
    try {
      const r = await api("/webface/chats/" + chatSel.value + "/lore-preview", jsonOpts("POST", { messages: chatMsgs.value.split("\n") }));
      chatOut.innerHTML = "";
      for (const layer of r.layers) chatOut.appendChild(el("p", layer.words));
      for (const w of r.words) chatOut.appendChild(el("p", w));
      if (r.shadowed && r.shadowed.length) chatOut.appendChild(el("p", "Shadowed by a more specific layer: " + r.shadowed.join(", "), "muted"));
      if (!r.words.length) chatOut.appendChild(el("p", "No scoped lore applies to this chat.", "muted"));
    } catch (e) { setStatus(e.message); }
  });
  box.appendChild(chatBtn); box.appendChild(chatOut);
}
async function readFileJson() {
  const file = $("lb-file").files[0];
  if (!file) throw new Error("pick a lorebook or pack file first");
  return JSON.parse(await file.text());
}
function transferStatus(t) { $("lb-transfer-status").textContent = t || ""; }
async function transfer(action) {
  try {
    const doc = await readFileJson();
    const out = $("lb-transfer-out"); out.innerHTML = "";
    if (action === "import") {
      const r = await api("/webface/lorebooks/import", jsonOpts("POST", { document: doc }));
      transferStatus(r.words); await loadBooks();
    } else if (action === "pack-inspect") {
      const r = await api("/webface/lorebooks/pack/inspect", jsonOpts("POST", { document: doc }));
      transferStatus(r.words);
    } else if (action === "pack-import") {
      const r = await api("/webface/lorebooks/import-pack", jsonOpts("POST", { document: doc }));
      transferStatus(r.words); await loadBooks();
    } else if (action === "upgrade-inspect") {
      const r = await api("/webface/lorebooks/upgrade/inspect", jsonOpts("POST", { document: doc }));
      transferStatus(r.words);
    } else if (action === "upgrade") {
      const r = await api("/webface/lorebooks/upgrade", jsonOpts("POST", { document: doc }));
      transferStatus(r.words);
      const blob = new Blob([JSON.stringify(r.lorebook, null, 2)], { type: "application/json" });
      const a = el("a", "Download the upgraded lorebook file", "btn ghost");
      a.href = URL.createObjectURL(blob); a.download = "upgraded-lorebook.json";
      out.appendChild(a);
      const imp = el("button", "Import the upgraded file", "btn"); imp.type = "button";
      imp.addEventListener("click", async () => {
        const rr = await api("/webface/lorebooks/import", jsonOpts("POST", { document: r.lorebook }));
        transferStatus(rr.words); await loadBooks();
      });
      out.appendChild(imp);
    }
  } catch (e) { transferStatus(e.message); }
}
$("lb-import").addEventListener("click", () => transfer("import"));
$("lb-pack-inspect").addEventListener("click", () => transfer("pack-inspect"));
$("lb-pack-import").addEventListener("click", () => transfer("pack-import"));
$("lb-upgrade-inspect").addEventListener("click", () => transfer("upgrade-inspect"));
$("lb-upgrade").addEventListener("click", () => transfer("upgrade"));
async function loadAll() {
  const census = await api("/webface/lorebooks/schema");
  state.forms = census.forms;
  state.characters = await api("/webface/characters");
  state.chats = await api("/webface/chats");
  await loadBooks();
}
loadAll().catch((e) => setStatus(e.message));
