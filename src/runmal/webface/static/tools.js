"use strict";
/* Runmal web face - Tools tab (W-07). Desktop R-12 Compose &
   Macros parity: the macro registry, expansion through the
   engine's own road (never re-implemented here), the variable
   registry + resolver, and the compose preview. The engine
   has no callable-tool registry or tool-call record road, so
   this page wires none and says so in words. */
const $ = (id) => document.getElementById(id);
async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let d = "request failed (" + resp.status + ")"; try { const b = await resp.json(); if (b.error) d = b.error; } catch (e) {} throw new Error(d); }
  return resp.json();
}
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }
function post(path, body) { return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); }

async function load() {
  const view = await api("/webface/tools/macros");
  $("t-scope").textContent = view.note;
  const list = $("t-macros"); list.innerHTML = "";
  view.lines.forEach((line) => list.appendChild(el("li", line)));
  const vars = await api("/webface/tools/variables");
  $("t-var-note").textContent = vars.note;
  const vlist = $("t-vars"); vlist.innerHTML = "";
  vars.lines.forEach((line) => vlist.appendChild(el("li", line)));
}
async function expand() {
  const body = { text: $("t-x-text").value, char: $("t-x-char").value, user: $("t-x-user").value || "User" };
  const seed = $("t-x-seed").value.trim();
  if (seed !== "") { const n = Number(seed); if (Number.isInteger(n)) body.seed = n; }
  const view = await post("/webface/tools/macros/expand", body);
  $("t-x-out").textContent = view.words;
  $("t-x-report").textContent = view.report_lines.join("\n");
}
async function resolve() {
  const view = await post("/webface/tools/resolve", { text: $("t-r-text").value, char: $("t-x-char").value, user: $("t-x-user").value || "User" });
  $("t-r-out").textContent = view.words;
}
async function compose() {
  const history = $("t-c-history").value.split("\n").filter((l) => l.trim());
  const view = await post("/webface/tools/compose", {
    system: $("t-c-system").value, persona: $("t-c-persona").value,
    history: history, authors_note: $("t-c-note").value,
    note_depth: Number($("t-c-depth").value || 0),
    context_limit: Number($("t-c-limit").value || 4096),
    reserve_response: Number($("t-c-reserve").value || 512) });
  $("t-c-out").textContent = view.words;
  $("t-c-manifest").textContent = view.manifest_words;
}
$("t-expand").addEventListener("click", () => expand().catch((e) => { $("t-x-out").textContent = e.message; }));
$("t-resolve").addEventListener("click", () => resolve().catch((e) => { $("t-r-out").textContent = e.message; }));
$("t-compose").addEventListener("click", () => compose().catch((e) => { $("t-c-status").textContent = e.message; }));
load().catch((e) => { $("t-status").textContent = e.message; });
