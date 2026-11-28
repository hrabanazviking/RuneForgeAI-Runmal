"use strict";
/* Runmal web face - Library search (W-09), a section of
   the Library tab. Desktop R-14 Library Search parity:
   one query fanned out to the search routes that really
   exist - the hub unified search always, one chat's
   workspace unified search when a chat is named. Faces
   has no search road and is never a result. Each hit
   jumps to the tab that owns its kind. */
const $ = (id) => document.getElementById(id);
async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let d = "request failed (" + resp.status + ")"; try { const b = await resp.json(); if (b.error) d = b.error; } catch (e) {} throw new Error(d); }
  return resp.json();
}
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }
async function loadChats() {
  const chats = await api("/webface/chats");
  const pick = $("ls-chat");
  (Array.isArray(chats) ? chats : []).forEach((chat) => {
    const o = el("option", chat.title || chat.id);
    o.value = chat.id;
    pick.appendChild(o);
  });
}
async function search() {
  const q = $("ls-q").value;
  const params = new URLSearchParams({ q: q });
  if ($("ls-kind").value) params.set("kind", $("ls-kind").value);
  if ($("ls-chat").value) params.set("chat_id", $("ls-chat").value);
  const view = await api("/webface/library-search?" + params.toString());
  $("ls-words").textContent = view.words;
  $("ls-faces").textContent = view.notes.faces + " " + view.notes.literal;
  const list = $("ls-results"); list.innerHTML = "";
  Object.keys(view.sources).forEach((source) => {
    view.sources[source].hits.forEach((hit) => {
      const li = el("li", source + ": " + hit.line, "roster-row");
      if (hit.jump) {
        const a = el("a", hit.jump.label);
        a.href = "/" + hit.jump.tab;
        li.appendChild(a);
      }
      list.appendChild(li);
    });
  });
  $("ls-status").textContent = "Searched for \u201C" + view.query + "\u201D.";
}
$("ls-go").addEventListener("click", () => search().catch((e) => { $("ls-status").textContent = e.message; }));
$("ls-q").addEventListener("keydown", (ev) => { if (ev.key === "Enter") search().catch((e) => { $("ls-status").textContent = e.message; }); });
loadChats().catch(() => {});
