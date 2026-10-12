/* Rúnmál prompt tools UI (S213): compose preview with Author's Note depth
   injection, plus a driver for the S209 generation-session state machine.
   API errors (impossible prompt states, invalid transitions) are shown
   verbatim in the error banner. */
"use strict";

const $ = (id) => document.getElementById(id);
let session = null;  // serialized S209 session, persists across actions

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
    } catch (e) { /* keep status message */ }
    throw new Error(detail);
  }
  return res.json();
}

/* Variable helper (S307): chips insert {{variables}} at the cursor in the
   system field; the resolve preview shows substitutions and flags any
   unknown variables instead of dropping them silently. */
async function loadVariableChips() {
  const vars = await api("/api/v1/tools/variables");
  const row = $("variable-chips");
  for (const v of vars) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "var-chip";
    chip.textContent = "{{" + v.name + "}}";
    chip.title = v.description;
    chip.addEventListener("click", () => {
      const ta = $("c-system");
      const token = "{{" + v.name + "}}";
      const start = ta.selectionStart || ta.value.length;
      ta.value = ta.value.slice(0, start) + token + ta.value.slice(start);
      ta.focus();
      ta.selectionStart = ta.selectionEnd = start + token.length;
    });
    row.appendChild(chip);
  }
}

$("resolve-btn").addEventListener("click", async () => {
  hideError();
  try {
    const out = await api("/api/v1/tools/resolve", {
      method: "POST",
      body: JSON.stringify({
        text: $("c-system").value,
        char: $("v-char").value,
        user: $("v-user").value,
      }),
    });
    $("resolve-result").textContent = out.text;
    const warn = $("unknown-vars");
    if (out.unknown.length) {
      warn.textContent =
        "Unknown variables (left as-is): " +
        out.unknown.map((n) => "{{" + n + "}}").join(", ");
      warn.classList.remove("hidden");
    } else {
      warn.classList.add("hidden");
    }
  } catch (err) {
    showError(String(err));
  }
});

loadVariableChips().catch((err) => showError(String(err)));

function promptMessages() {
  const msgs = [];
  if ($("c-persona").value) msgs.push({ role: "system", content: $("c-persona").value });
  for (const line of $("c-history").value.split("\n")) {
    if (line) msgs.push({ role: "user", content: line });
  }
  return msgs;
}

$("compose-btn").addEventListener("click", async () => {
  hideError();
  try {
    const history = $("c-history").value.split("\n").filter((l) => l);
    const out = await api("/api/v1/tools/compose", {
      method: "POST",
      body: JSON.stringify({
        system: $("c-system").value,
        persona: $("c-persona").value,
        history,
        authors_note: $("c-note").value,
        note_depth: Number($("c-depth").value),
        context_limit: Number($("c-context").value),
        reserve_response: Number($("c-reserve").value),
      }),
    });
    $("compose-result").textContent = JSON.stringify(out, null, 2);
  } catch (err) {
    showError(String(err));
  }
});

document.querySelectorAll("#session-buttons button").forEach((btn) => {
  btn.addEventListener("click", async () => {
    hideError();
    let action = btn.dataset.action;
    let delta = 0;
    if (action === "swipe-back") { action = "swipe"; delta = -1; }
    if (action === "swipe-fwd") { action = "swipe"; delta = 1; }
    try {
      const out = await api("/api/v1/tools/session", {
        method: "POST",
        body: JSON.stringify({
          action,
          session,
          mode: $("s-mode").value,
          messages: promptMessages(),
          content: $("s-content").value,
          delta,
        }),
      });
      session = out.session;
      $("session-result").textContent = JSON.stringify(out.result, null, 2);
    } catch (err) {
      showError(String(err));
    }
  });
});
