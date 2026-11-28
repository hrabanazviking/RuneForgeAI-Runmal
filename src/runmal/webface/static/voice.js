"use strict";
/* Runmal web face - Voice tab (W-08). Desktop R-13 Voice parity
   over the engine's own roads: status, devices + roles, the
   backend registry with its install truth and defaults, and
   per-chat voice sessions with their live roads. Two honest
   limits are part of the surface, never hidden: no engine road
   returns synthesized audio (speech plays on the engine host)
   and no engine road transcribes an uploaded file (hearing runs
   inside a live session, from the host's microphone). */
const $ = (id) => document.getElementById(id);
async function api(path, options) {
  const resp = await fetch(path, options || {});
  if (!resp.ok) { let d = "request failed (" + resp.status + ")"; try { const b = await resp.json(); if (b.error) d = b.error; } catch (e) {} throw new Error(d); }
  return resp.json();
}
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }
function post(path, body) { return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }); }
function put(path, body) { return api(path, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }); }
let sessionId = null;
let overview = null;

async function loadOverview() {
  overview = await api("/webface/voice/overview");
  $("v-state").textContent = overview.state.words.join("\n");
  $("v-status").textContent = overview.status_words;
  $("v-provider").textContent = overview.provider;
  $("v-provider-note").textContent = overview.provider_note || "";
  $("v-synth-note").textContent = overview.notes.synthesis;
  $("v-transcribe-note").textContent = overview.notes.transcription;
  $("v-char-note").textContent = overview.notes.character_voice;
  const vl = $("v-voices"); if (vl) { vl.innerHTML = ""; (overview.service_voice_lines || []).forEach((line) => vl.appendChild(el("li", line))); }
  const ve = $("v-voices-error"); if (ve) ve.textContent = overview.service_voices_error || "";
  const devs = $("v-devices"); devs.innerHTML = "";
  overview.device_lines.forEach((line) => devs.appendChild(el("li", line)));
  const roles = $("v-roles"); roles.innerHTML = "";
  overview.role_lines.forEach((line) => roles.appendChild(el("li", line)));
  const rolePick = $("v-role-pick"); rolePick.innerHTML = "";
  Object.keys(overview.roles.resolution || {}).forEach((role) => {
    const o = el("option", role); o.value = role; rolePick.appendChild(o);
  });
  const devPick = $("v-device-pick"); devPick.innerHTML = "";
  overview.devices.forEach((d) => {
    const o = el("option", d.name || d.device_id); o.value = d.device_id; devPick.appendChild(o);
  });
  ["tts", "stt"].forEach((kind) => {
    const list = $(kind === "tts" ? "v-tts" : "v-stt"); list.innerHTML = "";
    overview.backend_lines[kind].forEach((line, i) => {
      const row = overview.backends[kind][i];
      const li = el("li", line + " — " + (overview.audit[row.key] || ""));
      if (!row.installed && row.installable) {
        const b = el("button", "Install", "btn ghost small");
        b.type = "button";
        b.addEventListener("click", () => install(kind, row.key));
        li.appendChild(document.createTextNode(" ")); li.appendChild(b);
      }
      list.appendChild(li);
    });
    const sel = $(kind === "tts" ? "v-tts-default" : "v-stt-default");
    sel.innerHTML = "";
    overview.backends[kind].forEach((row) => {
      const o = el("option", row.display_name || row.key); o.value = row.key;
      if (row.selected) o.selected = true; sel.appendChild(o);
    });
  });
}
async function install(kind, key) {
  const view = await post("/webface/voice/backends/" + kind + "/" + key + "/install");
  $("v-backend-status").textContent = view.status === "refused"
    ? ("Refused: " + (view.error || "")) : ("Install " + (view.status || "started"));
  await loadOverview();
}
async function loadChats() {
  const chats = await api("/webface/chats");
  const sel = $("v-chat"); sel.innerHTML = "";
  chats.forEach((c) => { const o = el("option", c.title || c.id); o.value = c.id; sel.appendChild(o); });
  if (chats.length) await loadSessions();
}
async function loadSessions() {
  const chatId = $("v-chat").value;
  const view = await api("/webface/voice/sessions?chat_id=" + encodeURIComponent(chatId));
  const list = $("v-sessions"); list.innerHTML = "";
  view.sessions.forEach((s, i) => {
    const li = el("li", view.lines[i]);
    const b = el("button", "Open", "btn ghost small"); b.type = "button";
    b.addEventListener("click", () => openSession(s.session_id));
    li.appendChild(document.createTextNode(" ")); li.appendChild(b);
    list.appendChild(li);
  });
  if (view.active_session_id) sessionId = view.active_session_id;
}
async function openSession(id) {
  sessionId = id;
  const view = await api("/webface/voice/sessions/" + id);
  $("v-session-words").textContent = view.words;
  const lat = await api("/webface/voice/sessions/" + id + "/latency");
  $("v-latency").textContent = lat.words;
  const live = await api("/webface/voice/sessions/" + id + "/live");
  $("v-live-status").textContent = live.live ? "Live now." : "Not live.";
}
function needSession() { if (!sessionId) throw new Error("start or open a voice session first"); return sessionId; }

/* ---- microphone: secure-context honesty -------------------
   Browsers grant microphone access only in secure contexts
   (HTTPS or localhost). This face is plain HTTP on the
   tailnet, so on most browsers the mic is refused before any
   prompt. Feature-detect and say so in plain words - never a
   dead button, never a silent failure. */
const MIC_UNAVAILABLE_WORDS = "Your browser will not grant the microphone over this connection: microphone access needs a secure context (HTTPS or localhost), and this face is served over plain HTTP on the tailnet. Recording a clip elsewhere and uploading it does the same job the browser allows.";
function micAvailability() {
  if (!window.isSecureContext) return { ok: false, reason: MIC_UNAVAILABLE_WORDS };
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return { ok: false, reason: MIC_UNAVAILABLE_WORDS };
  if (typeof MediaRecorder === "undefined") return { ok: false, reason: MIC_UNAVAILABLE_WORDS };
  return { ok: true, reason: "" };
}
let recorder = null;
let recChunks = [];
let recUrl = null;
function setupMic() {
  const mic = micAvailability();
  if (!mic.ok) {
    $("v-mic-note").textContent = mic.reason;
    $("v-mic-record").disabled = true;
    return;
  }
  $("v-mic-note").textContent = "Microphone available on this connection. A recording stays in this page (play it back or download it); the engine transcribes only inside a live session, from its own host microphone.";
  $("v-mic-record").addEventListener("click", async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recChunks = [];
    recorder = new MediaRecorder(stream);
    recorder.addEventListener("dataavailable", (ev) => { if (ev.data.size) recChunks.push(ev.data); });
    recorder.addEventListener("stop", () => {
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(recChunks, { type: recorder.mimeType || "audio/webm" });
      if (recUrl) URL.revokeObjectURL(recUrl);
      recUrl = URL.createObjectURL(blob);
      const player = $("v-mic-player"); player.src = recUrl; player.hidden = false;
      const dl = $("v-mic-download"); dl.href = recUrl; dl.download = "voice-recording.webm"; dl.hidden = false;
      $("v-mic-record").hidden = false; $("v-mic-stop").hidden = true;
    });
    recorder.start();
    $("v-mic-record").hidden = true; $("v-mic-stop").hidden = false;
  });
  $("v-mic-stop").addEventListener("click", () => { if (recorder) recorder.stop(); });
}

$("v-assign").addEventListener("click", () => api("/webface/voice/roles", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role: $("v-role-pick").value, device_id: $("v-device-pick").value }) }).then(() => { $("v-role-status").textContent = "Role assigned."; return loadOverview(); }).catch((e) => { $("v-role-status").textContent = e.message; }));
$("v-save-defaults").addEventListener("click", () => put("/webface/voice/defaults", { tts_backend: $("v-tts-default").value, stt_backend: $("v-stt-default").value }).then(() => { $("v-backend-status").textContent = "Defaults saved."; return loadOverview(); }).catch((e) => { $("v-backend-status").textContent = e.message; }));
$("v-chat").addEventListener("change", () => loadSessions().catch((e) => { $("v-status-line").textContent = e.message; }));
$("v-start").addEventListener("click", () => post("/webface/voice/sessions", { chat_id: $("v-chat").value }).then(async (view) => { sessionId = view.session.session_id; $("v-session-words").textContent = view.words; await loadSessions(); }).catch((e) => { $("v-session-words").textContent = e.message; }));
$("v-stop").addEventListener("click", () => post("/webface/voice/sessions/" + needSession() + "/stop", { note: "stopped from the web face" }).then((view) => { $("v-session-words").textContent = view.words; }).catch((e) => { $("v-session-words").textContent = e.message; }));
$("v-live-start").addEventListener("click", () => post("/webface/voice/sessions/" + needSession() + "/live/start").then(() => { $("v-live-status").textContent = "Live now."; }).catch((e) => { $("v-live-status").textContent = e.message; }));
$("v-live-stop").addEventListener("click", () => post("/webface/voice/sessions/" + needSession() + "/live/stop").then(() => { $("v-live-status").textContent = "Not live."; }).catch((e) => { $("v-live-status").textContent = e.message; }));
$("v-speak").addEventListener("click", () => post("/webface/voice/sessions/" + needSession() + "/live/speak", { text: $("v-speak-text").value }).then((turn) => { $("v-speak-out").textContent = "Spoken on the engine host: " + ($("v-speak-text").value); if (turn && turn.error) $("v-speak-out").textContent = turn.error; }).catch((e) => { $("v-speak-out").textContent = e.message; }));
$("v-interrupt").addEventListener("click", () => post("/webface/voice/sessions/" + needSession() + "/live/interrupt").then(() => { $("v-speak-out").textContent = "Interrupted."; }).catch((e) => { $("v-speak-out").textContent = e.message; }));
$("v-record-turn").addEventListener("click", () => post("/webface/voice/sessions/" + needSession() + "/turns", { transcript_text: $("v-turn-transcript").value, response_text: $("v-turn-response").value }).then(() => openSession(sessionId)).catch((e) => { $("v-turn-out").textContent = e.message; }));
$("v-project").addEventListener("click", () => post("/webface/voice/sessions/" + needSession() + "/project").then((view) => { $("v-turn-out").textContent = "Projected into the chat: " + JSON.stringify(view); }).catch((e) => { $("v-turn-out").textContent = e.message; }));
$("v-transcribe").addEventListener("click", () => {
  const file = $("v-clip").files[0];
  post("/webface/voice/transcribe", { filename: file ? file.name : "microphone-recording" })
    .then(() => { $("v-transcribe-out").textContent = ""; })
    .catch((e) => { $("v-transcribe-out").textContent = e.message; });
});
setupMic();
loadOverview().then(loadChats).catch((e) => { $("v-status-line").textContent = e.message; });

const regBtn = $("v-reg-btn");
if (regBtn) regBtn.addEventListener("click", async () => {
  const file = $("v-reg-file").files[0];
  if (!file) { $("v-reg-status").textContent = "Pick a reference audio file first."; return; }
  const fd = new FormData();
  fd.append("name", $("v-reg-name").value); fd.append("transcript", $("v-reg-transcript").value); fd.append("file", file);
  try { const r = await fetch("/webface/voice/service-voices", { method: "POST", body: fd }); const b = await r.json(); if (!r.ok) throw new Error(b.error || ("request failed (" + r.status + ")")); $("v-reg-status").textContent = "Saved voice: " + (b.name || $("v-reg-name").value); await loadOverview(); } catch (e) { $("v-reg-status").textContent = e.message; }
});
