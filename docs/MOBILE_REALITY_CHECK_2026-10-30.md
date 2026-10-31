# P-011 — Mobile Reality Check (2026-10-30)

*What "Android/browser client" means for a Python local app —
decided from the tree as it stands, not hoped. This is a decision
record: it builds no client. It gives the P-014 gate (and any
later client slice) a settled shape to plan against, and it
closes the open half of delta rows VX-62/VX-63 (P-004), whose
verdict was HAVE-THIN with "the sovereign client shape is a
decision still to be recorded". That decision is recorded here.*

## Method and evidence

- **Rúnmál side, read this tick:** the web layer
  (`src/runmal/web/` — 8 templates, 13 static JS files, one
  298-line stylesheet), the two server-inline pages (`/voice` in
  `src/runmal/voice/router.py`, `/memories` in
  `src/runmal/memory/router.py`), the serve entrypoint
  (`src/runmal/__main__.py`), ADR-0003 (local auth boundary),
  INV-024 (local-first / offline), and the founding mobile pass's
  own acceptance tests (`tests/test_s310_responsive.py`).
- **Mirror side:** only what P-002/P-003 already attested from
  public sources — Voxta VX-62 (Windows desktop app recommended;
  Linux server + browser; Android companion app for subscribers,
  paired to the PC by QR code; no macOS or iOS app), VX-63 (the
  web UI reworked phone-shaped in 1.11: master-detail drawers,
  cards instead of tables, bottom sheets, step-by-step flows),
  VX-50 (a mobile vision playground that opens the real camera),
  VX-58 (completion notifications integrated with Windows and
  Android). SillyTavern's censused surface names no native
  mobile app of its own; its mobile story is the same
  server-plus-browser shape. No new mirror reading was needed
  and none was invented.
- **Platform facts** relied on below are the web platform's
  public, stable rules (secure contexts for service workers,
  `getUserMedia`, and installable web apps; a LAN address over
  plain HTTP is not a secure context, `localhost` is). They are
  stated as platform facts, not as measurements of this tree.

## §1 What is already true in the tree

1. **The responsive web UI is real and test-pinned.** All 8 main
   templates carry
   `<meta name="viewport" content="width=device-width, initial-scale=1">`.
   The stylesheet's S310 section provides: a 1024px tablet
   breakpoint (slimmer sidebar), a 720px phone breakpoint
   (single column, chat sidebar as an off-canvas drawer capped
   at `min(300px, 85vw)`, bubbles capped at 92%), a
   `pointer: coarse` block giving interactive elements the
   44px touch target (`--touch-target: 44px`), and
   `env(safe-area-inset-bottom)` padding on the composer and
   pages. `tests/test_s310_responsive.py` pins all of it,
   including a no-fixed-width-over-720px sweep and the drawer
   state machine under Node.
2. **There is no PWA layer at all.** No web app manifest, no
   service worker, no `theme-color`, no install icons exist
   anywhere in `src/runmal/web/` (searched this tick: the only
   "manifest" hits in the tree are archive/backup/prompt
   manifests — different objects). Nothing is installable to a
   home screen today; nothing works offline in the browser.
3. **The server is loopback by law, not by accident.**
   `runmal serve` defaults to `127.0.0.1:8098`
   (`DEFAULT_HOST`/`DEFAULT_PORT` in `__main__.py`); ADR-0003
   fixes the loopback bind as the security boundary, with
   `--host` as an explicit user override that "never changes
   silently". Every `/api/v1/*` call is bearer-gated; the
   browser pages are public shells whose token gate stores the
   credential in the browser's local storage and sends it only
   to this server. A phone on the same network therefore
   cannot reach a default Rúnmál at all — by design.
4. **Voice is host audio, not browser audio.** The voice loop
   (Campaign V) enumerates and uses the *server machine's*
   audio devices (S501/PortAudio class); the `/voice` page only
   polls `/api/v1/voice/status` and draws the host microphone's
   waveform. There is no `getUserMedia` call anywhere in the
   tree (searched this tick). A phone browser today gets the
   full text surface and **no voice in or out of its own** —
   the character's ears and mouth stay on the host machine.
5. **Two pages sit outside the responsive pass.** The
   server-inline `/voice` and `/memories` pages carry no
   viewport meta at all (`/voice` has a charset; `/memories`
   neither). On a phone they render at desktop scale. This is
   recorded as a known thin spot, not silently absorbed into
   the "responsive" claim in (1) — the pinned claim covers the
   8 templated pages.

## §2 The decision

**D1 — The client is the browser. No native apps.** Rúnmál's
mobile/desktop client shape is the responsive web UI served by
the user's own server, on every platform: Android phone or
tablet, iPhone/iPad, Windows, macOS, Linux — one codebase, the
one already test-pinned in §1(1). There will be no native
Android companion app, no iOS app, and no Windows desktop app
in this road. Reasons, in the open:

- Voxta's Android companion is a *thin client paired to a PC*
  (VX-62) — the work it does is exactly what a browser tab
  already does against Rúnmál's HTTP API; the pairing dance
  (QR code) buys nothing the bearer-credential token gate does
  not already provide.
- A native app would be a second and third codebase (Kotlin/
  Swift) beside a Python project whose whole fleet is
  Python — the maintenance shape contradicts the project's
  scale (one user, agent-built, Mythic slices).
- App stores are a gate between Volmarr and his own software:
  review, signing, and store policy are precisely the
  dependence the sovereignty campaign (VIII) exists to remove.
  A browser client installs by opening a URL.
- Running the *server* on the phone instead is rejected
  separately in D4.

**D2 — PWA is the install shape, as a named future slice, with
its limits stated.** The sovereign equivalent of "install the
app" is an installable PWA: web app manifest + icons +
`theme-color` + a service worker that caches the static shell
(HTML/CSS/JS) so the UI opens instantly and survives a server
restart's refresh, **never caching `/api/v1/*` responses or the
credential**. Two honest limits ride with the decision:

- Installability, service workers, and `getUserMedia` all
  require a **secure context**. `localhost` qualifies; a LAN
  address over plain HTTP does not. So on the user's own
  machine the PWA installs fully; on a phone reaching the
  server over the home LAN by plain HTTP it does not install
  and gets no mic/camera — until the deployment gains HTTPS
  (a local CA, a self-signed cert the user trusts, or a private
  tunnel the user already runs). This record does not choose
  that HTTPS mechanism; it names the gate so no later slice
  promises phone install/mic over plain-HTTP LAN and fails.
- A PWA is not an offline *app*: with the server down it can
  show the shell, never the chats (the data lives server-side
  by INV-024's local-first shape). "Works offline" claims are
  limited to the shell, in writing, wherever they are made.

Parts II–VI contain no PWA slice, so D2 is flagged **NO HOME**
for the P-014 gate (recommendation §4.1) — kin to P-008's
generic adapter and P-010's generic speech adapter.

**D3 — Reaching the server from a phone is an explicit user
act, unchanged from ADR-0003.** The default bind stays
`127.0.0.1`. A user who wants Rúnmál on their phone at home
runs `runmal serve --host <LAN address>` (or `0.0.0.0`) on a
network they trust, opens the page, and pastes the local
credential into the token gate — the same flow as desktop,
already built. Recorded risks, plainly: the credential then
lives in the phone browser's local storage, and over plain
HTTP on the LAN it travels readable to anyone who can sniff
that network. That is accepted for a trusted home network by
the user's own choice of `--host`; it is never the default,
never silent, and no slice may widen the bind on the user's
behalf. Remote reach from outside the home (tunnels, port
forwarding) is **out of scope for this record and this road** —
if Volmarr wants it, it gets its own decision with its own
threat model, because ADR-0003's boundary is the thing being
crossed.

**D4 — No on-phone server.** Rúnmál's server (Python + SQLite +
the voice extras' native dependency tree) does not target
Android/iOS as a host platform: no Termux/Chaquopy-class
packaging, no phone platform-matrix leg. The phone is a
client (D1); the server runs where it already runs —
laptop, desktop, Pi (the S805 Linux leg is the proven shape).
This also keeps the platform matrix honest: its legs are
server hosts, and phone browsers are client evidence, gathered
through the responsive tests rather than a fake "Android leg".

**D5 — Mobile voice and camera are Part VII territory, and
this record says what they require.** Phone mic in / speaker
out and camera-for-vision (the VX-50 shape) need a browser
audio/vision capture slice: `getUserMedia` capture in the web
client, streamed to the server's existing voice seams. Its
preconditions are D2's secure-context gate (HTTPS or
localhost) — on a phone that means the HTTPS question in D2
must be answered first. Until that slice lands, the honest
mobile claim is: **full text chat, library, lorebooks, groups,
inspector and tools in the phone browser; voice remains a
host-machine surface.** VX-58's OS notifications get the same
treatment: the web platform's answer is the Notifications /
Push surface behind the PWA slice (D2), not a native app —
no separate notification build is wanted.

## §3 What this closes and what it does not

- **VX-62** (clients): the decision its delta row was waiting
  for is D1+D4 — browser client everywhere, no native apps,
  no on-phone server. The row's HAVE-THIN stands as measured
  (Linux + browser proven); it is a *shape* gap that is now
  closed by decision, and a *depth* gap (PWA) carried by D2.
- **VX-63** (phone-shaped UI depth: bottom sheets, cards
  instead of tables, step-by-step flows): the responsive
  foundation is proven (§1(1)); the 1.11-depth patterns are
  **not** claimed. They are ordinary web-UI slices whenever a
  later part wants them — no decision here pretends the drawer
  layout is a bottom-sheet UI.
- **Not decided here:** the HTTPS mechanism for LAN phone use
  (D2/D3 name the gate, not the road), any remote-access shape,
  and the PWA slice's exact contents. Each is named so the
  P-014 gate can home them or drop them explicitly.
- **No device was tested by this record.** Every tree claim
  rests on the tree and its pinned tests, re-read this tick;
  no phone, emulator, or browser was run. A PWA or capture
  slice must bring its own device evidence when it lands.

## §4 Recommendations to the P-014 gate

1. **PWA shell slice** (manifest, icons, theme-color,
   shell-only service worker, credential/API never cached):
   **NO HOME** in Parts II–VI — home it (a small Part I
   follow-on or the Part VII voice run-up, since D5 depends
   on it) or drop it explicitly.
2. **Browser capture slice** (phone mic/camera via
   `getUserMedia` into the existing voice/vision seams):
   belongs with Part VII (title only in the filed roadmap);
   record its secure-context precondition (D5) in that part's
   validation.
3. **Viewport repair for `/voice` and `/memories`** (§1(5)):
   two-meta-tag smallness — fold into the PWA slice or any
   next web slice; until then the responsive claim reads
   "8 templated pages", never "every page".
4. **HTTPS-for-LAN decision** stays Volmarr's, surfaced once
   by this record: without it, phone use is text-over-HTTP on
   a trusted network by explicit `--host` (D3); with it, D2
   install and D5 capture unlock on phones.
