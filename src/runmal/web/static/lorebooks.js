/* Rúnmál lorebook editor (S304): book/entry CRUD with key editing,
   import (native + world-info) and export, wired to /api/v1/lorebooks. */
"use strict";

const $ = (id) => document.getElementById(id);
let books = [];
let entries = [];

function showError(text) {
  $("error-text").textContent = text;
  $("error-banner").classList.remove("hidden");
}
function hideError() { $("error-banner").classList.add("hidden"); }
$("error-dismiss").addEventListener("click", hideError);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: {
      Authorization: "Bearer " + localStorage.getItem("runmal-token"),
      "Content-Type": "application/json",
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = "request failed: " + res.status;
    try {
      const body = await res.json();
      if (body.detail) detail = JSON.stringify(body.detail);
    } catch (e) { /* keep status message */ }
    throw new Error(detail);
  }
  return res.json();
}

function bookId() { return $("book-select").value; }
function splitKeys(text) {
  return text.split(",").map((k) => k.trim()).filter((k) => k);
}

function renderBooks() {
  const sel = $("book-select");
  sel.textContent = "";
  for (const b of books) {
    const opt = document.createElement("option");
    opt.value = b.id;
    opt.textContent = b.name + " (" + b.entry_count + ")";
    sel.appendChild(opt);
  }
  if (books.length) loadEntries(books[0].id);
}

function renderEntries() {
  const rows = $("entry-rows");
  rows.textContent = "";
  for (const e of entries) {
    const tr = document.createElement("tr");
    for (const cell of [e.name, e.keys.join(", "), String(e.priority),
                        e.position, e.constant ? "yes" : ""]) {
      const td = document.createElement("td");
      td.textContent = cell;
      tr.appendChild(td);
    }
    const actions = document.createElement("td");
    const edit = document.createElement("button");
    edit.type = "button";
    edit.textContent = "Edit";
    edit.addEventListener("click", () => fillForm(e));
    actions.appendChild(edit);
    const del = document.createElement("button");
    del.type = "button";
    del.className = "danger";
    del.textContent = "Delete";
    del.addEventListener("click", async () => {
      await api("/api/v1/lorebooks/" + bookId() + "/entries/" + e.id,
                { method: "DELETE" });
      loadEntries(bookId());
    });
    actions.appendChild(del);
    tr.appendChild(actions);
    rows.appendChild(tr);
  }
}

function fillForm(e) {
  $("e-id").value = e.id;
  $("e-name").value = e.name;
  $("e-content").value = e.content;
  $("e-keys").value = e.keys.join(", ");
  $("e-secondary").value = e.secondary_keys.join(", ");
  $("e-priority").value = e.priority;
  $("e-position").value = e.position;
  $("e-constant").checked = e.constant;
  $("e-sticky").value = e.sticky_prompts;
  $("e-cooldown").value = e.cooldown_prompts;
  $("e-delay").value = e.delay_prompts;
}

function clearForm() {
  $("entry-form").reset();
  $("e-id").value = "";
  $("e-priority").value = 100;
}

async function loadBooks() {
  books = await api("/api/v1/lorebooks");
  renderBooks();
}

async function loadEntries(id) {
  entries = await api("/api/v1/lorebooks/" + id + "/entries");
  renderEntries();
  $("export-link").href = "/api/v1/lorebooks/" + id + "/export";
}

$("book-select").addEventListener("change", () =>
  loadEntries(bookId()).catch((e) => showError(String(e)))
);
$("new-book").addEventListener("click", async () => {
  const name = prompt("Book name:");
  if (!name) return;
  await api("/api/v1/lorebooks", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  loadBooks();
});
$("delete-book").addEventListener("click", async () => {
  await api("/api/v1/lorebooks/" + bookId(), { method: "DELETE" });
  loadBooks();
});
$("e-clear").addEventListener("click", clearForm);

$("entry-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  hideError();
  const payload = {
    name: $("e-name").value,
    content: $("e-content").value,
    keys: splitKeys($("e-keys").value),
    secondary_keys: splitKeys($("e-secondary").value),
    priority: Number($("e-priority").value),
    position: $("e-position").value,
    constant: $("e-constant").checked,
    sticky_prompts: Number($("e-sticky").value),
    cooldown_prompts: Number($("e-cooldown").value),
    delay_prompts: Number($("e-delay").value),
  };
  try {
    const id = $("e-id").value;
    if (id) {
      await api("/api/v1/lorebooks/" + bookId() + "/entries/" + id, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
    } else {
      await api("/api/v1/lorebooks/" + bookId() + "/entries", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }
    clearForm();
    loadEntries(bookId());
  } catch (err) {
    showError(String(err));
  }
});

$("import-file").addEventListener("change", async (e) => {
  if (!e.target.files.length) return;
  try {
    const data = JSON.parse(await e.target.files[0].text());
    await api("/api/v1/lorebooks/import", {
      method: "POST",
      body: JSON.stringify(data),
    });
    loadBooks();
  } catch (err) {
    showError("Import failed: " + err.message);
  }
});

function renderPreview(result) {
  const list = $("p-results");
  list.textContent = "";
  $("p-summary").textContent =
    "Tokens used: " + result.tokens_used +
    " / budget " + (result.token_budget === null ? "∞" : result.token_budget) +
    " · scan depth " + result.scan_depth;
  for (const row of result.entries) {
    const li = document.createElement("li");
    let text = row.name + " — " + row.status;
    if (row.via) text += " (via " + row.via + ")";
    if (row.matched_primary.length)
      text += " · keys: " + row.matched_primary.join(", ");
    if (row.matched_secondary.length)
      text += " · secondary: " + row.matched_secondary.join(", ");
    if (row.tokens !== null) text += " · " + row.tokens + " tokens";
    if (row.discard_reason) text += " · discarded: " + row.discard_reason;
    li.textContent = text;
    list.appendChild(li);
  }
}

$("p-run").addEventListener("click", async () => {
  hideError();
  const payload = {
    messages: $("p-messages").value.split("\n").filter((m) => m.trim()),
  };
  const depth = $("p-depth").value;
  if (depth) payload.scan_depth = Number(depth);
  const budget = $("p-budget").value;
  if (budget) payload.token_budget = Number(budget);
  try {
    const result = await api(
      "/api/v1/lorebooks/" + bookId() + "/preview",
      { method: "POST", body: JSON.stringify(payload) }
    );
    renderPreview(result);
  } catch (err) {
    showError(String(err));
  }
});

loadBooks().catch((err) => showError(String(err)));
