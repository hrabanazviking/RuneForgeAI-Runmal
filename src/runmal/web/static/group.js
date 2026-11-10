/* Rúnmál group chat UI (S305): roster picker, strategy picker, per-author
   styled bubbles, and per-participant typing/stream state over SSE. */
"use strict";

const $ = (id) => document.getElementById(id);
let history = [];       // [{author, content}] — the shared state
let rrCursor = 0;       // round-robin cursor, carried across turns
let colorOf = {};       // author name -> color class index
let openGroupId = null; // P-214: the saved group currently open, null = the stateless room

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

function reasoningPanel(view) {
  // P-212 Group Assistant View: the thinking panel under a
  // group reply, built ONLY from the reasoning events this
  // turn's stateless stream forwarded for that author, read
  // through the shared P-206 view-model (renderer.js
  // reasoningView). Recorded thinking is text in a native
  // <details> disclosure, collapsed by default (the reply
  // stays primary); every other status is one honest status
  // line. Text via textContent ONLY - never as HTML, never
  // through the markdown renderer (the markingBadge rule:
  // thinking is data shown as text, not message content).
  if (!view) return null;
  if (view.kind === "recorded") {
    const details = document.createElement("details");
    details.className = "reasoning";
    const summary = document.createElement("summary");
    summary.textContent = view.label;
    details.appendChild(summary);
    const body = document.createElement("div");
    body.className = "reasoning-text";
    body.textContent = view.text;
    details.appendChild(body);
    return details;
  }
  const line = document.createElement("div");
  line.className = "reasoning-status";
  line.textContent = view.text;
  return line;
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

async function loadSavedGroups() {
  // P-213: populate the Saved groups picker from the banked
  // persistent group list road. The picker holds group ids
  // and names only - never message content.
  const groups = await (await api("/api/v1/groups")).json();
  const select = $("saved-group");
  select.textContent = "";
  for (const g of groups) {
    const option = document.createElement("option");
    option.value = g.id;
    option.textContent = g.name + " (" + g.message_count + ")";
    select.appendChild(option);
  }
}

async function openSavedGroup() {
  // P-213: open the picked group's STORED transcript from
  // the banked transcript road and render it read-only: one
  // bubble per stored message via addBubble (author = the
  // stored speaker_name - user rows carry none and render
  // under the page's own "user" label, as the live path
  // authors them - body = the stored content), with the
  // stored reasoning view rendered under the bubble through
  // the same reasoningView + reasoningPanel pair the P-212
  // stream path uses. DISPLAY-ONLY fence: fetched messages
  // are never copied into the stateless turn state, never
  // sent back, and nothing is written to web storage;
  // opening a saved group puts the composer into that
  // group's persistent mode (P-214). The thread is cleared
  // only after a successful
  // fetch - a failure surfaces via showError and leaves the
  // visible thread untouched.
  const groupId = $("saved-group").value;
  if (!groupId) return;
  try {
    const messages = await (
      await api("/api/v1/groups/" + groupId + "/messages")).json();
    const thread = $("group-thread");
    thread.textContent = "";
    for (const m of messages) {
      const body = addBubble(m.speaker_name || "user", m.content);
      if (m.reasoning) {
        const panel = reasoningPanel(
          window.RunmalRenderer.reasoningView(m.reasoning));
        if (panel) body.parentElement.appendChild(panel);
      }
    }
    openGroupId = groupId;
  } catch (err) {
    showError(String(err));
  }
}

function selectedIds() {
  return Array.from(document.querySelectorAll(".roster-check:checked"))
    .map((b) => b.value);
}

async function sendPersistent(text) {
  // P-214: one persistent turn on the opened group through
  // the banked next-turn road. The group itself chooses
  // the speaker, from its own stored policy and roster;
  // this branch touches none of the stateless turn state
  // and never calls the stateless turn road. The reply
  // renders through the same addBubble + reasoningPanel
  // pair the P-213 stored path uses. A null message (no
  // speaker picked) renders nothing further - the user
  // turn is stored server-side and the page invents no
  // reply. Errors surface via the existing showError.
  try {
    const res = await api("/api/v1/groups/" + openGroupId + "/next", {
      method: "POST",
      body: JSON.stringify({ user_text: text, generate: true }),
    });
    const result = await res.json();
    const m = result.message;
    if (!m) return;
    const body = addBubble(m.speaker_name || "user", m.content);
    if (m.reasoning) {
      const panel = reasoningPanel(
        window.RunmalRenderer.reasoningView(m.reasoning));
      if (panel) body.parentElement.appendChild(panel);
    }
  } catch (err) {
    showError(String(err));
  }
}

$("group-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const text = $("group-input").value.trim();
  if (!text) return;
  $("group-input").value = "";
  addBubble("user", text);
  if (openGroupId) {
    await sendPersistent(text);
    return;
  }
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
    let reasoningByAuthor = {};  // author -> [reasoning text parts] (P-212, this turn only)
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
          } else if (event.type === "reasoning") {
            if (!reasoningByAuthor[event.author]) {
              reasoningByAuthor[event.author] = [];
            }
            reasoningByAuthor[event.author].push(event.text);
          } else if (event.type === "token") {
            if (!bubbles[event.author]) {
              bubbles[event.author] = addBubble(event.author, "");
            }
            bubbles[event.author].textContent += event.text;
          } else if (event.type === "message") {
            if (typing[event.author]) typing[event.author].remove();
            history.push({ author: event.author, content: event.content });
            const view = (reasoningByAuthor[event.author] || []).length
              ? {
                  status: "recorded",
                  text: reasoningByAuthor[event.author].join(""),
                }
              : { status: "not_present" };
            const panel = reasoningPanel(
              window.RunmalRenderer.reasoningView(view));
            if (panel && bubbles[event.author]) {
              bubbles[event.author].parentElement.appendChild(panel);
            }
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

document.addEventListener("DOMContentLoaded", () => {
  loadSavedGroups().catch((err) => showError(String(err)));
  $("open-group").addEventListener("click", () => {
    openSavedGroup();
  });
});
