"use strict";
/* Rúnmál web face — Characters tab (W-02). Roster from the engine
   library roads; the editor is the desktop's five sections over the
   R-08 compositions served by /webface/characters/{id}/editor. */
const $ = (id) => document.getElementById(id);
const els = { search: $("c-search"), tag: $("c-tag"), fav: $("c-fav"),
  roster: $("c-roster"), census: $("c-census"), status: $("c-status"),
  editor: $("c-editor"), newBtn: $("c-new") };
let current = null; // editor bundle or {create:true}

async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) {
    let detail = "request failed (" + resp.status + ")";
    try { const b = await resp.json(); if (b.error) detail = b.error; } catch (e) {}
    throw new Error(detail);
  }
  const ct = resp.headers.get("content-type") || "";
  return ct.includes("json") ? resp.json() : resp.text();
}
function setStatus(t) { els.status.textContent = t || ""; }
/* Upload with real progress (FIX-AVATAR): fetch cannot report
   upload progress, so uploads go through XMLHttpRequest. The
   status element names the file and shows progress; failures
   surface the server's own words -- never a silent rejection. */
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
      reject(new Error((body && body.error) ||
        ("upload failed (" + xhr.status + ")")));
    });
    xhr.addEventListener("error", () => { if (btn) btn.disabled = false;
      reject(new Error("upload failed -- the connection dropped")); });
    xhr.addEventListener("abort", () => { if (btn) btn.disabled = false;
      reject(new Error("upload cancelled")); });
    xhr.send(fd);
  });
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
    if (card.has_avatar) { const img = el("img"); img.className = "thumb";
      img.alt = ""; img.src = "/webface/characters/" + card.id + "/avatar";
      li.appendChild(img); }
    li.appendChild(el("b", card.name || card.id));
    if (card.is_favourite) li.appendChild(el("span", " ★ favourite", "tag"));
    if (card.tags && card.tags.length)
      li.appendChild(el("span", " tags: " + card.tags.join(", "), "muted"));
    const open = el("button", "Edit", "btn small"); open.type = "button";
    open.addEventListener("click", () => openEditor(card.id));
    li.appendChild(open);
    const fav = el("button", card.is_favourite ? "Unfavourite" : "Favourite", "btn ghost small");
    fav.type = "button";
    fav.addEventListener("click", async () => {
      await api("/webface/library/cards/" + card.id + "/favourite",
        { method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ is_favourite: !card.is_favourite }) });
      loadRoster(); });
    li.appendChild(fav);
    els.roster.appendChild(li);
  }
  if (!items.length) els.roster.appendChild(el("li", "No characters match.", "muted"));
}

const TEXT_FIELDS = [["name", "Name"], ["description", "Description"],
  ["personality", "Personality"], ["scenario", "Scenario"],
  ["first_mes", "First message"], ["mes_example", "Example messages"],
  ["creator_notes", "Creator notes"], ["system_prompt", "System prompt"],
  ["post_history_instructions", "Post-history instructions"],
  ["creator", "Creator"], ["character_version", "Character version"],
  ["nickname", "Nickname"]];

function fieldInput(id, value) { const t = el("textarea"); t.id = id; t.rows = 3;
  t.classList.add("entry-box"); t.value = value || ""; return t; }
function greetingList(id, values) { const wrap = el("div"); wrap.id = id;
  for (const g of values || []) { const t = fieldInput("", g); t.classList.add("greeting"); wrap.appendChild(t); }
  const add = el("button", "Add greeting", "btn ghost small"); add.type = "button";
  add.addEventListener("click", () => { const t = fieldInput("", ""); t.classList.add("greeting");
    wrap.insertBefore(t, add); });
  wrap.appendChild(add); return wrap; }
function greetingsOf(id) { return Array.from(document.querySelectorAll("#" + id + " .greeting"))
  .map((t) => t.value).filter((v) => v.trim() !== ""); }

function renderEditor(bundle) {
  current = bundle;
  const f = bundle.fields || {};
  const ed = els.editor; ed.hidden = false; ed.innerHTML = "";
  ed.appendChild(el("h2", bundle.create ? "New character" : "Edit: " + (f.name || bundle.id)));
  const nav = el("div", null, "row");
  for (const name of ["Card", "Greetings", "Avatar & Assets", "Book & Binding", "Versions"]) {
    const a = el("a", name, "tab"); a.href = "#sec-" + name.replace(/[^a-z]/gi, ""); nav.appendChild(a); }
  ed.appendChild(nav);
  const sec = (title) => { const s = el("section"); s.id = "sec-" + title.replace(/[^a-z]/gi, "");
    s.appendChild(el("h3", title)); ed.appendChild(s); return s; };
  const cardSec = sec("Card");
  for (const [key, label] of TEXT_FIELDS) { const lab = el("label", label);
    const inp = fieldInput("f-" + key, f[key]);
    if (!bundle.create && bundle.id) inp.setAttribute("data-draft-key", "character:" + bundle.id + ":" + key);
    lab.appendChild(inp); cardSec.appendChild(lab); }
  const tagLab = el("label", "Tags (comma separated)");
  const tagInp = fieldInput("f-tags", (f.tags || []).join(", "));
  if (!bundle.create && bundle.id) tagInp.setAttribute("data-draft-key", "character:" + bundle.id + ":tags");
  tagLab.appendChild(tagInp);
  cardSec.appendChild(tagLab);
  const grSec = sec("Greetings");
  grSec.appendChild(el("p", "Alternate greetings:", "muted"));
  grSec.appendChild(greetingList("alt-greetings", f.alternate_greetings));
  if ((f.group_only_greetings || []).length) {
    grSec.appendChild(el("p", "Group-only greetings (managed in Groups, W-03) — shown, never dropped:", "muted"));
    for (const g of f.group_only_greetings) grSec.appendChild(el("p", g)); }
  const avSec = sec("Avatar & Assets");
  if (!bundle.create) {
    if (bundle.has_avatar) { const img = el("img"); img.className = "avatar"; img.alt = "avatar";
      img.src = "/webface/characters/" + bundle.id + "/avatar"; avSec.appendChild(img); }
    const avFile = el("input"); avFile.type = "file"; avFile.id = "avatar-file";
    const avBtn = el("button", "Upload avatar", "btn small"); avBtn.type = "button";
    const avStatus = el("span", "", "upload-status"); avStatus.id = "avatar-status";
    avBtn.addEventListener("click", async () => {
      if (!avFile.files.length) { avStatus.textContent = "Pick an avatar file first."; return; }
      const fd = new FormData(); fd.append("file", avFile.files[0]);
      try {
        await uploadWithProgress("/webface/characters/" + bundle.id + "/avatar",
          fd, avStatus, avBtn, avFile.files[0]);
        avStatus.textContent = "Avatar saved."; setStatus("Avatar saved.");
        openEditor(bundle.id);
      } catch (err) { avStatus.textContent = err.message; setStatus(err.message); } });
    avSec.appendChild(avFile); avSec.appendChild(avBtn); avSec.appendChild(avStatus);
    const list = el("ul");
    for (const a of bundle.assets || []) list.appendChild(el("li",
      (a.name || a.id) + " · " + (a.kind || "") + " · " + (a.byte_size || 0) + " bytes"));
    avSec.appendChild(list);
    const asFile = el("input"); asFile.type = "file"; asFile.id = "asset-file";
    const asBtn = el("button", "Upload asset", "btn small"); asBtn.type = "button";
    const asStatus = el("span", "", "upload-status"); asStatus.id = "asset-status";
    asBtn.addEventListener("click", async () => {
      if (!asFile.files.length) { asStatus.textContent = "Pick an asset file first."; return; }
      const fd = new FormData(); fd.append("file", asFile.files[0]);
      try {
        await uploadWithProgress("/webface/characters/" + bundle.id + "/assets",
          fd, asStatus, asBtn, asFile.files[0]);
        asStatus.textContent = "Asset uploaded."; setStatus("Asset uploaded.");
        openEditor(bundle.id);
      } catch (err) { asStatus.textContent = err.message; setStatus(err.message); } });
    avSec.appendChild(asFile); avSec.appendChild(asBtn); avSec.appendChild(asStatus);
  } else avSec.appendChild(el("p", "Save the character first, then add an avatar and assets.", "muted"));
  const bookSec = sec("Book & Binding");
  if (!bundle.create) {
    bookSec.appendChild(el("p", "Character book: " + (bundle.book_entry_count || 0) +
      " entr(ies) travel with this card. Entry editing lives in the Lorebooks tab (W-05)."));
    const b = bundle.binding || {};
    bookSec.appendChild(el("p", b.bound ? "Bound lorebook id: " + (b.lorebook_id || "") : "No lorebook bound."));
    const sel = el("select"); sel.id = "bind-book"; sel.classList.add("entry-box");
    for (const book of bundle.lorebooks || []) { const o = el("option", book.name || book.id); o.value = book.id; sel.appendChild(o); }
    const prec = el("input"); prec.id = "bind-prec"; prec.classList.add("entry-box"); prec.placeholder = "precedence (optional)";
    const bindBtn = el("button", "Bind", "btn small"); bindBtn.type = "button";
    bindBtn.addEventListener("click", async () => {
      await api("/webface/characters/" + bundle.id + "/binding", { method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lorebook_id: sel.value, precedence: prec.value || undefined }) });
      setStatus("Lorebook bound."); openEditor(bundle.id); });
    const unBtn = el("button", "Unbind", "btn ghost small"); unBtn.type = "button";
    unBtn.addEventListener("click", async () => {
      await api("/webface/characters/" + bundle.id + "/binding", { method: "DELETE" });
      setStatus("Lorebook unbound."); openEditor(bundle.id); });
    bookSec.appendChild(sel); bookSec.appendChild(prec); bookSec.appendChild(bindBtn); bookSec.appendChild(unBtn);
  }
  const verSec = sec("Versions");
  if (!bundle.create) {
    const versions = (bundle.versions && bundle.versions.versions) || [];
    const list = el("ul");
    for (const v of versions) { const li = el("li", "v" + v.version_no +
      (v.is_latest ? " · latest" : "") + (v.created_at ? " · " + v.created_at : ""));
      if (!v.is_latest) { const rb = el("button", "Restore", "btn ghost small"); rb.type = "button";
        rb.addEventListener("click", async () => {
          await api("/webface/characters/" + bundle.id + "/versions/" + v.version_no + "/restore", { method: "POST" });
          setStatus("Restored version " + v.version_no + "."); openEditor(bundle.id); });
        li.appendChild(rb); }
      list.appendChild(li); }
    verSec.appendChild(list);
  }
  const save = el("button", bundle.create ? "Create character" : "Save card", "btn");
  save.type = "button"; save.addEventListener("click", saveEditor); ed.appendChild(save);
  if (!bundle.create) {
    const dup = el("button", "Duplicate", "btn ghost"); dup.type = "button";
    dup.addEventListener("click", async () => { const c = await api(
      "/webface/characters/" + bundle.id + "/duplicate", { method: "POST" });
      setStatus("Duplicated as " + (c.name || c.id) + "."); loadTags(); loadRoster(); });
    ed.appendChild(dup);
    const exp = el("a", "Export card JSON", "btn ghost");
    exp.href = "/webface/characters/" + bundle.id + "/export"; ed.appendChild(exp);
    const chat = el("button", "Start chat", "btn"); chat.type = "button";
    chat.addEventListener("click", async () => { await api("/webface/chats",
      { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ character_id: bundle.id }) });
      window.location = "/chat"; });
    ed.appendChild(chat);
    const del = el("button", "Delete", "btn ghost"); del.type = "button";
    del.addEventListener("click", async () => {
      if (!window.confirm("Delete this character? It is hidden, not erased: " +
        "its card and pictures stay stored and Undo brings it straight back.")) return;
      await api("/webface/characters/" + bundle.id, { method: "DELETE" });
      ed.innerHTML = ""; const undo = el("button", "Undo delete", "btn"); undo.type = "button";
      undo.addEventListener("click", async () => { await api(
        "/webface/characters/" + bundle.id + "/restore", { method: "POST" });
        setStatus("Character restored."); loadRoster(); });
      ed.appendChild(el("p", "Deleted (recoverable).")); ed.appendChild(undo); ed.hidden = false;
      loadTags(); loadRoster(); });
    ed.appendChild(del);
  }
}
async function openEditor(id) {
  try { renderEditor(await api("/webface/characters/" + id + "/editor")); }
  catch (err) { setStatus(err.message); }
}
async function saveEditor() {
  const body = {};
  for (const [key] of TEXT_FIELDS) body[key] = $("f-" + key).value;
  body.tags = $("f-tags").value;
  body.alternate_greetings = greetingsOf("alt-greetings");
  if (current && current.fields) body.group_only_greetings = current.fields.group_only_greetings || [];
  try {
    if (current && current.create) {
      const created = await api("/webface/characters", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      setStatus("Created " + (created.name || created.id) + ".");
      loadTags(); loadRoster(); openEditor(created.id);
    } else {
      const savedBundle = await api("/webface/characters/" + current.id, { method: "PATCH",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      // W-11: a successful save retires this character's drafts.
      if (window.RunmalEntryBox) for (const [key] of TEXT_FIELDS.concat([["tags", ""]])) { const inp = $("f-" + key); if (inp) window.RunmalEntryBox.retireDraft(inp); }
      renderEditor(savedBundle);
      setStatus("Saved."); loadTags(); loadRoster();
    }
  } catch (err) { setStatus(err.message); }
}
els.newBtn.addEventListener("click", () => renderEditor({ create: true, fields: {} }));
els.search.addEventListener("input", loadRoster);
els.tag.addEventListener("change", loadRoster);
els.fav.addEventListener("change", loadRoster);
loadTags().then(loadRoster).catch((err) => setStatus(err.message));
