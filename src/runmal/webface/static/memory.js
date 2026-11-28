"use strict";
/* Runmal web face - Memory tab (W-06). Read-only by the
   engine's own shape: list/search/filter + full detail with
   sources and provenance. There are deliberately no create,
   edit or delete controls - no engine road serves them. */
const $ = (id) => document.getElementById(id);
const state = { memories: [] };
async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let d = "request failed (" + resp.status + ")"; try { const b = await resp.json(); if (b.error) d = b.error; } catch (e) {} throw new Error(d); }
  return resp.json();
}
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }

function fillFilters(view) {
  for (const [id, values] of [["m-state", view.states], ["m-kind", view.kinds]]) {
    const sel = $(id);
    if (sel.options.length > 1) continue;
    for (const v of values || []) { const o = el("option", v); o.value = v; sel.appendChild(o); }
  }
}
async function load() {
  const q = new URLSearchParams();
  if ($("m-search").value) q.set("q", $("m-search").value);
  if ($("m-state").value) q.set("state", $("m-state").value);
  if ($("m-kind").value) q.set("kind", $("m-kind").value);
  const view = await api("/webface/memories?" + q.toString());
  fillFilters(view);
  $("m-embed-note").textContent = view.embedding_note + " " + view.note;
  state.memories = view.memories;
  $("m-count").textContent = view.total + " memor" + (view.total === 1 ? "y" : "ies");
  const list = $("m-list"); list.innerHTML = "";
  view.memories.forEach((m, i) => {
    const li = el("li");
    const b = el("button", view.lines[i], "btn ghost small"); b.type = "button";
    b.addEventListener("click", () => showDetail(m.id));
    li.appendChild(b); list.appendChild(li);
  });
  if (!view.memories.length) $("m-status").textContent = "No memories match.";
}
async function showDetail(id) {
  const view = await api("/webface/memories/" + id);
  const box = $("m-detail"); box.hidden = false; box.innerHTML = "";
  box.appendChild(el("h2", "Memory"));
  const pre = el("pre", view.words); pre.className = "words"; box.appendChild(pre);
  const m = view.memory;
  const row = el("div"); row.className = "row";
  if (m.chat_id) { const a = el("a", "Open the chat this memory came from"); a.href = "/chat"; row.appendChild(a); }
  if (m.character_id) { const a = el("a", "See the character in Characters"); a.href = "/characters"; row.appendChild(a); }
  box.appendChild(row);
  box.scrollIntoView({ block: "nearest" });
}
$("m-go").addEventListener("click", () => load().catch((e) => { $("m-status").textContent = e.message; }));
$("m-search").addEventListener("keydown", (ev) => { if (ev.key === "Enter") load().catch((e) => { $("m-status").textContent = e.message; }); });
load().catch((e) => { $("m-status").textContent = e.message; });
