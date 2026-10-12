/* Rúnmál character gallery (S303): grid + search, duplicate, soft delete
   with undo, and a card import dropzone. Wired to the character API. */
"use strict";

const $ = (id) => document.getElementById(id);
let characters = [];
let lastDeletedId = null;

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
  if (!res.ok) throw new Error("request failed: " + res.status + " " + path);
  return res.json();
}

function render() {
  const q = $("search").value.trim().toLowerCase();
  const grid = $("gallery-grid");
  grid.textContent = "";
  for (const c of characters) {
    if (q && !c.name.toLowerCase().includes(q)) continue;
    const card = document.createElement("article");
    card.className = "gallery-card";
    const title = document.createElement("h3");
    title.textContent = c.name;
    card.appendChild(title);
    if (c.has_avatar) {
      const img = document.createElement("img");
      img.src = "/api/v1/characters/" + c.id + "/avatar";
      img.alt = c.name;
      card.appendChild(img);
    }
    const dup = document.createElement("button");
    dup.type = "button";
    dup.textContent = "Duplicate";
    dup.addEventListener("click", async () => {
      await api("/api/v1/characters/" + c.id + "/duplicate", { method: "POST" });
      refresh();
    });
    card.appendChild(dup);
    const edit = document.createElement("a");
    edit.href = "/editor";
    edit.textContent = "Edit persona";
    card.appendChild(edit);
    const del = document.createElement("button");
    del.type = "button";
    del.className = "danger";
    del.textContent = "Delete";
    del.addEventListener("click", async () => {
      await api("/api/v1/characters/" + c.id, { method: "DELETE" });
      lastDeletedId = c.id;
      $("undo-text").textContent = "Deleted " + c.name + " (recoverable).";
      $("undo-banner").classList.remove("hidden");
      refresh();
    });
    card.appendChild(del);
    grid.appendChild(card);
  }
}

async function refresh() {
  characters = await api("/api/v1/characters");
  render();
}

$("search").addEventListener("input", render);
$("undo-btn").addEventListener("click", async () => {
  if (!lastDeletedId) return;
  await api("/api/v1/characters/" + lastDeletedId + "/restore", { method: "POST" });
  $("undo-banner").classList.add("hidden");
  lastDeletedId = null;
  refresh();
});

async function importCardFile(file) {
  try {
    const card = JSON.parse(await file.text());
    await api("/api/v1/characters", {
      method: "POST",
      body: JSON.stringify({ card }),
    });
    refresh();
  } catch (err) {
    showError("Import failed: " + err.message);
  }
}

const dz = $("dropzone");
dz.addEventListener("dragover", (e) => {
  e.preventDefault();
  dz.classList.add("dragover");
});
dz.addEventListener("dragleave", () => dz.classList.remove("dragover"));
dz.addEventListener("drop", (e) => {
  e.preventDefault();
  dz.classList.remove("dragover");
  if (e.dataTransfer.files.length) importCardFile(e.dataTransfer.files[0]);
});
$("import-file").addEventListener("change", (e) => {
  if (e.target.files.length) importCardFile(e.target.files[0]);
});

refresh().catch((err) => showError(String(err)));
