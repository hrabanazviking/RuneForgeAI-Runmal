/* Rúnmál lorebook editor (S304 + P-042): book/entry CRUD with key
   editing, import (native + world-info) and export, wired to
   /api/v1/lorebooks. P-042: the editor reaches every field the
   lore engine honours -- book scan settings, the full entry field
   set (selective logic, inclusion groups, probability, placement
   depth/role, entry-state flags), scope assignment (P-040) and
   the full preview control set (incl. recursive scan, P-031).
   The field census lives in runmal.lorebooks.editor and is served
   at /api/v1/lorebooks/editor-schema. */
"use strict";

const $ = (id) => document.getElementById(id);
let books = [];
let entries = [];
let scopes = [];

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
function currentBook() { return books.find((b) => b.id === bookId()); }
function splitKeys(text) {
  return text.split(",").map((k) => k.trim()).filter((k) => k);
}
function numOrNull(id) {
  const v = $(id).value;
  return v === "" ? null : Number(v);
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
  if (books.length) selectBook(books[0].id);
}

function fillBookForm(b) {
  if (!b) return;
  $("b-name").value = b.name;
  $("b-description").value = b.description;
  $("b-scan-depth").value = b.scan_depth;
  $("b-token-budget").value = b.token_budget === null ? "" : b.token_budget;
  $("b-scan-mode").value = b.scan_mode;
  $("b-scan-external").checked = b.scan_external_context;
}

function selectBook(id) {
  fillBookForm(books.find((b) => b.id === id));
  loadEntries(id);
  loadScopes(id);
}

function renderEntries() {
  const rows = $("entry-rows");
  rows.textContent = "";
  for (const e of entries) {
    const tr = document.createElement("tr");
    for (const cell of [e.name, e.keys.join(", "), String(e.priority),
                        e.position, e.constant ? "yes" : "",
                        e.activation_kind, e.enabled ? "yes" : "no"]) {
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

function derivedKind() {
  if ($("e-constant").checked) return "constant";
  if ($("e-vectorised").checked) return "vectorised";
  return "selective";
}

function fillForm(e) {
  $("e-id").value = e.id;
  $("e-name").value = e.name;
  $("e-content").value = e.content;
  $("e-keys").value = e.keys.join(", ");
  $("e-secondary").value = e.secondary_keys.join(", ");
  $("e-selective-logic").value = e.selective_logic;
  $("e-inclusion-group").value = e.inclusion_group;
  $("e-group-weight").value = e.group_weight;
  $("e-probability").value = e.probability;
  $("e-priority").value = e.priority;
  $("e-position").value = e.position;
  $("e-depth").value = e.depth === null ? "" : e.depth;
  $("e-role").value = e.role;
  $("e-enabled").checked = e.enabled;
  $("e-constant").checked = e.constant;
  $("e-vectorised").checked = e.vectorised;
  $("e-activation-kind").value = e.activation_kind;
  $("e-case-sensitive").checked = e.case_sensitive;
  $("e-whole-word").checked = e.whole_word;
  $("e-sticky").value = e.sticky_prompts;
  $("e-cooldown").value = e.cooldown_prompts;
  $("e-delay").value = e.delay_prompts;
}

function clearForm() {
  $("entry-form").reset();
  $("e-id").value = "";
  $("e-priority").value = 100;
  $("e-group-weight").value = 100;
  $("e-probability").value = 100;
  $("e-activation-kind").value = "selective";
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

function renderScopes() {
  const list = $("s-list");
  list.textContent = "";
  for (const s of scopes) {
    const li = document.createElement("li");
    let text = s.scope_kind;
    if (s.owner_id) text += " @ " + s.owner_id;
    text += " · budget " + (s.token_budget === null ? "∞" : s.token_budget);
    text += " · position " + s.position;
    li.textContent = text + " ";
    const del = document.createElement("button");
    del.type = "button";
    del.className = "danger";
    del.textContent = "Remove";
    del.addEventListener("click", async () => {
      const q = "scope_kind=" + encodeURIComponent(s.scope_kind) +
        (s.owner_id ? "&owner_id=" + encodeURIComponent(s.owner_id) : "");
      await api("/api/v1/lorebooks/" + bookId() + "/scope?" + q,
                { method: "DELETE" });
      loadScopes(bookId());
    });
    li.appendChild(del);
    list.appendChild(li);
  }
}

async function loadScopes(id) {
  const data = await api("/api/v1/lorebooks/" + id + "/scopes");
  scopes = data.scopes;
  renderScopes();
}

$("book-select").addEventListener("change", () =>
  selectBook(bookId())
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
$("e-constant").addEventListener("change", () => {
  $("e-activation-kind").value = derivedKind();
});
$("e-vectorised").addEventListener("change", () => {
  $("e-activation-kind").value = derivedKind();
});

$("book-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  hideError();
  const payload = {
    name: $("b-name").value,
    description: $("b-description").value,
    scan_depth: Number($("b-scan-depth").value),
    token_budget: numOrNull("b-token-budget"),
    scan_mode: $("b-scan-mode").value,
    scan_external_context: $("b-scan-external").checked,
  };
  try {
    await api("/api/v1/lorebooks/" + bookId(), {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    loadBooks();
  } catch (err) {
    showError(String(err));
  }
});

$("s-assign").addEventListener("click", async () => {
  hideError();
  const payload = {
    scope_kind: $("s-kind").value,
    owner_id: $("s-owner").value || null,
    token_budget: numOrNull("s-budget"),
    position: Number($("s-position").value),
  };
  try {
    await api("/api/v1/lorebooks/" + bookId() + "/scope", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    loadScopes(bookId());
  } catch (err) {
    showError(String(err));
  }
});

$("entry-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  hideError();
  const payload = {
    name: $("e-name").value,
    content: $("e-content").value,
    keys: splitKeys($("e-keys").value),
    secondary_keys: splitKeys($("e-secondary").value),
    selective_logic: $("e-selective-logic").value,
    inclusion_group: $("e-inclusion-group").value,
    group_weight: Number($("e-group-weight").value),
    probability: Number($("e-probability").value),
    priority: Number($("e-priority").value),
    position: $("e-position").value,
    depth: numOrNull("e-depth"),
    role: $("e-role").value,
    enabled: $("e-enabled").checked,
    constant: $("e-constant").checked,
    vectorised: $("e-vectorised").checked,
    case_sensitive: $("e-case-sensitive").checked,
    whole_word: $("e-whole-word").checked,
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
    if (row.tokens !== null && row.tokens !== undefined)
      text += " · " + row.tokens + " tokens";
    if (row.discard_reason) text += " · discarded: " + row.discard_reason;
    li.textContent = text;
    list.appendChild(li);
  }
}

$("p-run").addEventListener("click", async () => {
  hideError();
  const payload = {
    messages: $("p-messages").value.split("\n").filter((m) => m.trim()),
    recursive_scan: $("p-recursive").checked,
  };
  const depth = $("p-depth").value;
  if (depth) payload.scan_depth = Number(depth);
  const budget = $("p-budget").value;
  if (budget) payload.token_budget = Number(budget);
  const seed = $("p-seed").value;
  if (seed) payload.seed = Number(seed);
  const rollContext = $("p-roll-context").value;
  if (rollContext) payload.roll_context = rollContext;
  const scanMode = $("p-scan-mode").value;
  if (scanMode) payload.scan_mode = scanMode;
  if ($("p-scan-external").checked) payload.scan_external_context = true;
  const external = $("p-external").value.split("\n").filter((m) => m.trim());
  if (external.length) payload.external_context = external;
  const maxRecursion = $("p-max-recursion").value;
  if (maxRecursion) payload.max_recursion_depth = Number(maxRecursion);
  const hits = splitKeys($("p-vector-hits").value);
  if (hits.length) payload.vector_hit_ids = hits;
  const threshold = $("p-vector-threshold").value;
  if (threshold) payload.vector_threshold = Number(threshold);
  const vectorMax = $("p-vector-max").value;
  if (vectorMax) payload.vector_max_entries = Number(vectorMax);
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
