/* Rúnmál persona/scenario/greeting editor (S212). Wired to the Campaign I
   character service via /api/v1/characters/{id}/editor. Validation errors
   from the API are shown verbatim in the error banner. */
"use strict";

const $ = (id) => document.getElementById(id);

function showError(text) {
  $("error-text").textContent = text;
  $("error-banner").classList.remove("hidden");
}
function hideError() { $("error-banner").classList.add("hidden"); }

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: {
      Authorization: <redacted>
      "Content-Type": "application/json",
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = "request failed: " + res.status;
    try {
      const body = await res.json();
      if (body.detail) detail = JSON.stringify(body.detail);
    } catch (e) { /* keep the status-line message */ }
    throw new Error(detail);
  }
  return res.json();
}

function currentId() { return $("character-select").value; }

function renderGreetings(greetings) {
  const list = $("greetings-list");
  list.textContent = "";
  for (const g of greetings) addGreetingField(g);
}

function addGreetingField(value) {
  const ta = document.createElement("textarea");
  ta.className = "greeting-field";
  ta.rows = 2;
  ta.value = value || "";
  $("greetings-list").appendChild(ta);
}

async function loadCharacters() {
  const chars = await api("/api/v1/characters");
  const sel = $("character-select");
  sel.textContent = "";
  for (const c of chars) {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = c.name;
    sel.appendChild(opt);
  }
  if (chars.length) await loadEditor(chars[0].id);
}

async function loadEditor(id) {
  const view = await api("/api/v1/characters/" + id + "/editor");
  $("f-description").value = view.description;
  $("f-personality").value = view.personality;
  $("f-scenario").value = view.scenario;
  $("f-first-mes").value = view.first_mes;
  renderGreetings(view.alternate_greetings);
}

$("character-select").addEventListener("change", () =>
  loadEditor(currentId()).catch((e) => showError(String(e)))
);
$("add-greeting").addEventListener("click", () => addGreetingField(""));
$("error-dismiss").addEventListener("click", hideError);

$("editor-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  hideError();
  const greetings = Array.from(
    document.querySelectorAll(".greeting-field")
  ).map((ta) => ta.value);
  try {
    await api("/api/v1/characters/" + currentId() + "/editor", {
      method: "PATCH",
      body: JSON.stringify({
        description: $("f-description").value,
        personality: $("f-personality").value,
        scenario: $("f-scenario").value,
        first_mes: $("f-first-mes").value,
        alternate_greetings: greetings,
      }),
    });
    $("save-notice").classList.remove("hidden");
  } catch (err) {
    showError(String(err));  // validation errors stay visible until fixed
  }
});

loadCharacters().catch((err) => showError(String(err)));
