/* Rúnmál group chat UI (S305): roster picker, strategy picker, per-author
   styled bubbles, and per-participant typing/stream state over SSE. */
"use strict";

const $ = (id) => document.getElementById(id);
let history = [];       // [{author, content}] — the shared state
let rrCursor = 0;       // round-robin cursor, carried across turns
let colorOf = {};       // author name -> color class index

function showError(text) {
  $("error-text").textContent = text;
  $("error-banner").classList.remove("hidden");
}
$("error-dismiss").addEventListener("click", () =>
  $("error-banner").classList.add("hidden"));

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: {
      Authorization: "Bearer " + localStorage.getItem("runmal-token"),
      "Content-Type": "application/json",
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) throw new Error("request failed: " + res.status + " " + path);
  return res;
}

function colorClass(author) {
  if (!(author in colorOf)) colorOf[author] = Object.keys(colorOf).length % 6;
  return "author-c" + colorOf[author];
}

function addBubble(author, content) {
  const div = document.createElement("div");
  div.className = "gmsg " + (author === "user" ? "" : colorClass(author));
  const head = document.createElement("span");
  head.className = "author";
  head.textContent = author;
  div.appendChild(head);
  const body = document.createElement("div");
  body.className = "gmsg-body";
  body.textContent = content;
  div.appendChild(body);
  $("group-thread").appendChild(div);
  return body;
}

async function loadRoster() {
  const chars = await (await api("/api/v1/characters")).json();
  const ul = $("roster");
  ul.textContent = "";
  for (const c of chars) {
    const li = document.createElement("li");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = c.id;
    box.checked = true;
    box.className = "roster-check";
    li.appendChild(box);
    li.appendChild(document.createTextNode(" " + c.name));
    ul.appendChild(li);
  }
}

function selectedIds() {
  return Array.from(document.querySelectorAll(".roster-check:checked"))
    .map((b) => b.value);
}

$("group-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const text = $("group-input").value.trim();
  if (!text) return;
  $("group-input").value = "";
  addBubble("user", text);
  const sentHistory = history.slice();
  history.push({ author: "user", content: text });
  try {
    const res = await api("/api/v1/group/turn", {
      method: "POST",
      body: JSON.stringify({
        participant_ids: selectedIds(),
        history: sentHistory,
        user_text: text,
        strategy: $("strategy").value,
        rr_cursor: rrCursor,
      }),
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let bubbles = {};   // author -> body element (stream state per author)
    let typing = {};    // author -> typing indicator element
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        for (const line of block.split("\n")) {
          if (!line.startsWith("data:")) continue;
          const event = JSON.parse(line.slice(5));
          if (event.type === "typing") {
            const t = document.createElement("div");
            t.className = "typing";
            t.textContent = event.author + " is typing…";
            $("group-thread").appendChild(t);
            typing[event.author] = t;
          } else if (event.type === "token") {
            if (!bubbles[event.author]) {
              bubbles[event.author] = addBubble(event.author, "");
            }
            bubbles[event.author].textContent += event.text;
          } else if (event.type === "message") {
            if (typing[event.author]) typing[event.author].remove();
            history.push({ author: event.author, content: event.content });
          } else if (event.type === "turn_end") {
            rrCursor = event.rr_cursor;
          }
        }
      }
    }
  } catch (err) {
    showError(String(err));
  }
});

loadRoster().catch((err) => showError(String(err)));
