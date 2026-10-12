/* Rúnmál connections UI (S211). Lists profiles, sets the active one, and
   probes health (latency + capabilities) via the API. Vanilla JS, offline. */
"use strict";

const $ = (id) => document.getElementById(id);

function showError(text) {
  $("error-text").textContent = text;
  $("error-banner").classList.remove("hidden");
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: {
      Authorization: <redacted>
      "Content-Type": "application/json",
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) throw new Error("request failed: " + res.status + " " + path);
  return res.json();
}

async function refresh() {
  const profiles = await api("/api/v1/connections");
  const ul = $("connection-list");
  ul.textContent = "";
  for (const p of profiles) {
    const li = document.createElement("li");
    li.className = "connection-item";
    const label = document.createElement("span");
    label.textContent =
      p.name + " — " + p.backend + (p.model ? " / " + p.model : "") +
      (p.is_active ? " (active)" : "");
    li.appendChild(label);
    const activate = document.createElement("button");
    activate.type = "button";
    activate.textContent = "Set active";
    activate.disabled = p.is_active;
    activate.addEventListener("click", async () => {
      await api("/api/v1/connections/" + p.id + "/activate", { method: "POST" });
      refresh();
    });
    li.appendChild(activate);
    const health = document.createElement("button");
    health.type = "button";
    health.textContent = "Probe health";
    health.addEventListener("click", async () => {
      const result = await api("/api/v1/connections/" + p.id + "/health");
      $("health-panel").classList.remove("hidden");
      $("health-result").textContent = JSON.stringify(result, null, 2);
    });
    li.appendChild(health);
    ul.appendChild(li);
  }
}

$("create-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  try {
    await api("/api/v1/connections", {
      method: "POST",
      body: JSON.stringify({
        name: $("f-name").value,
        backend: $("f-backend").value,
        base_url: $("f-url").value,
        model: $("f-model").value,
      }),
    });
    refresh();
  } catch (err) {
    showError(String(err));
  }
});

$("error-dismiss").addEventListener("click", () =>
  $("error-banner").classList.add("hidden")
);

refresh().catch((err) => showError(String(err)));
