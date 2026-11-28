"use strict";
/* Runmal web face - Bridge tab (W-09). Desktop R-14
   Bridge parity over the engine's admin roads: list,
   create (the token is shown exactly once, in the
   one-time field - it is never stored by this page
   beyond that field, never rendered into the list or
   the status words), and revoke behind its
   confirmation. Agent access to this web face itself
   is W-10 scope and lives on the Account tab; the page
   carries that line in the engine surface's own words. */
const $ = (id) => document.getElementById(id);
async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let d = "request failed (" + resp.status + ")"; try { const b = await resp.json(); if (b.error) d = b.error; } catch (e) {} throw new Error(d); }
  return resp.json();
}
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }
function post(path, body) { return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }); }
let credentials = [];
let selectedId = null;
async function load() {
  const view = await api("/webface/bridge/credentials");
  credentials = view.credentials;
  $("br-words").textContent = view.words;
  $("br-w10").textContent = view.notes.w10;
  $("br-token-note").textContent = view.notes.token;
  const list = $("br-list"); list.innerHTML = "";
  credentials.forEach((row) => {
    const li = el("li", row.line, "roster-row");
    const btn = el("button", "Select", "btn small ghost");
    btn.type = "button";
    btn.addEventListener("click", () => { selectedId = row.id; $("br-status").textContent = "Selected: " + row.line; });
    li.appendChild(btn); list.appendChild(li);
  });
}
async function create() {
  const result = await post("/webface/bridge/credentials", {
    name: $("br-name").value, scopes: $("br-scopes").value });
  /* Reload first: the one-time field is filled afterwards,
     so nothing in the reload can clear or copy it (the
     desktop window's own discipline). */
  await load();
  const token = result.token || "";
  $("br-token").value = token;
  $("br-status").textContent = token
    ? "Credential created. Its token is in the one-time field above - copy it now; it will not be shown again and is not stored by this page."
    : "Credential created; the engine returned no token to show.";
}
async function revoke() {
  if (!selectedId) { $("br-status").textContent = "Select a credential first."; return; }
  const view = await post("/webface/bridge/credentials/" + encodeURIComponent(selectedId) + "/revoke",
    { confirm: $("br-revoke-confirm").checked });
  $("br-token").value = "";
  $("br-revoke-out").textContent = view.line;
  selectedId = null;
  await load();
}
$("br-create").addEventListener("click", () => create().catch((e) => { $("br-status").textContent = e.message; }));
$("br-revoke").addEventListener("click", () => revoke().catch((e) => { $("br-revoke-out").textContent = e.message; }));
load().catch((e) => { $("br-status").textContent = e.message; });
