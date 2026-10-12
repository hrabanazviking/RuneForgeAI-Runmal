"use strict";
// Prompt inspector (S215): renders an S214 Prompt Trace so the user can
// answer "why was this injected / discarded?" from trace data alone.

const $ = (id) => document.getElementById(id);

function headers() {
  return {
    "Content-Type": "application/json",
    Authorization: "Bearer " + localStorage.getItem("runmal-token"),
  };
}

function showError(message) {
  $("error-text").textContent = message;
  $("error-banner").classList.remove("hidden");
}

async function loadOptions() {
  try {
    const [chars, books] = await Promise.all([
      fetch("/api/v1/characters", { headers: headers() }).then((r) => r.json()),
      fetch("/api/v1/lorebooks", { headers: headers() }).then((r) => r.json()),
    ]);
    const charSel = $("inspect-character");
    charSel.innerHTML = '<option value="">(none)</option>';
    for (const c of chars.characters || chars) {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.name;
      charSel.appendChild(opt);
    }
    const bookSel = $("inspect-lorebook");
    bookSel.innerHTML = '<option value="">(none)</option>';
    for (const b of books.lorebooks || books) {
      const opt = document.createElement("option");
      opt.value = b.id;
      opt.textContent = b.name;
      bookSel.appendChild(opt);
    }
  } catch (err) {
    showError("Could not load characters/lorebooks: " + err.message);
  }
}

function whyText(slot) {
  if (slot.status === "included") {
    if (slot.trigger) return "triggered by " + JSON.stringify(slot.trigger);
    return slot.provenance || "always included";
  }
  return slot.reason || "discarded";
}

function renderTrace(trace) {
  const ledger = trace.ledger;
  $("ledger-summary").textContent =
    "context " + ledger.context_limit +
    " · reserved response " + ledger.reserved_response +
    " · overhead " + ledger.overhead +
    " · input budget " + ledger.input_budget +
    " · used " + ledger.total_input_tokens +
    " · remaining " + ledger.remaining_input_tokens +
    " · count quality " + ledger.count_quality;
  $("ledger-section").classList.remove("hidden");

  const rows = $("trace-rows");
  rows.innerHTML = "";
  for (const slot of trace.slots) {
    const tr = document.createElement("tr");
    const cells = [
      slot.slot_id,
      slot.kind,
      slot.status,
      String(slot.tokens),
      slot.trigger || "—",
      whyText(slot),
    ];
    for (const text of cells) {
      const td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    }
    rows.appendChild(tr);
  }
  $("trace-section").classList.remove("hidden");
}

$("inspect-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const messages = $("inspect-messages").value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  const body = {
    character_id: $("inspect-character").value || null,
    lorebook_ids: $("inspect-lorebook").value ? [$("inspect-lorebook").value] : [],
    messages,
    context_limit: Number($("inspect-context").value),
    reserve_response: Number($("inspect-reserve").value),
  };
  try {
    const response = await fetch("/api/v1/debug/prompt-inspect", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error("inspect failed: " + response.status);
    renderTrace(await response.json());
  } catch (err) {
    showError(err.message);
  }
});

$("error-dismiss").addEventListener("click", () => {
  $("error-banner").classList.add("hidden");
});

loadOptions();
