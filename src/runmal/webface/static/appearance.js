"use strict";
/* Runmal web face - Appearance tab (W-09). The desktop
   R-15 Appearance prefs (variant / ornament / text
   scale / reduced motion), stored per webface account
   on the server so they follow the account to every
   device, and applied by the shell on every page.
   Applying here saves and reloads, so the whole face
   re-renders under the new prefs at once. */
const $ = (id) => document.getElementById(id);
async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let d = "request failed (" + resp.status + ")"; try { const b = await resp.json(); if (b.error) d = b.error; } catch (e) {} throw new Error(d); }
  return resp.json();
}
function post(path, body) { return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }); }
async function load() {
  const view = await api("/webface/appearance");
  const prefs = view.appearance;
  $("a-variant").value = prefs.variant;
  $("a-ornament").value = prefs.ornament;
  $("a-scale").value = Math.round(prefs.text_scale * 100);
  $("a-motion").checked = !!prefs.reduced_motion;
  $("a-words").textContent = "In force: " + view.words;
  $("a-note").textContent = view.note;
}
async function apply() {
  const scale = Number($("a-scale").value || 100) / 100;
  const view = await post("/webface/appearance", {
    variant: $("a-variant").value, ornament: $("a-ornament").value,
    text_scale: scale, reduced_motion: $("a-motion").checked });
  $("a-status").textContent = "Applied and saved: " + view.words + " Reloading...";
  window.location.reload();
}
async function reset() {
  const view = await post("/webface/appearance/reset", {});
  $("a-status").textContent = "Back to the house theme: " + view.words + " Reloading...";
  window.location.reload();
}
$("a-apply").addEventListener("click", () => apply().catch((e) => { $("a-status").textContent = e.message; }));
$("a-reset").addEventListener("click", () => reset().catch((e) => { $("a-status").textContent = e.message; }));
load().catch((e) => { $("a-status").textContent = e.message; });
