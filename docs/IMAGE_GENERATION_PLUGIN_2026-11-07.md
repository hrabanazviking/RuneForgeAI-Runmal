# P-087 — Image Generation plugin (Part VI, Extensions Row)

Roadmap line: *Image Generation plugin: prompt-from-scene +
manual, local diffusion endpoints first (Part X consumes for
avatars).*

Clean-room: built from the roadmap line and Rúnmál's own
contracts only — the P-081 Plugin API v1, the P-082 sandbox
policy, the P-023 asset machinery and the P-073 extractive
honesty pattern. Base d17b12d3 (P-085 banking record),
migration head 0041. **No migration taken.**

## What landed

`src/runmal/plugins/image_generation.py` — a first-class
P-081 citizen, id `runmal.image-generation`:

- capabilities `chat.events`, `prompt.hooks`, `ui.slots`;
  permissions `chat.read`, `prompt.inject`, `ui.contribute`
  (`chat.write` NOT declared — reserved in v1, and this
  citizen never writes chat messages);
- events `chat.created` only, a deliberate no-op (see
  "Never automatic" below);
- one slots-stage prompt hook `image-scene` (priority 80);
  one UI contribution `image-panel` in `chat.sidebar`;
- settings defaults `{default_width: 512, default_height:
  512, endpoint: "", model: ""}` read by `ImageGenConfig`
  (strict validation; lenient manifest fallback, the P-084
  pattern). An explicit config/provider outranks the
  manifest defaults, which outrank the module constants.

## Prompt-from-scene + manual

`derive_scene_prompt` is pure, deterministic and extractive
(generator `extractive-scene-1`): the subject is the chat's
character name (else its title), and the segments are the
first sentence of each of the last six non-empty messages,
capped per segment, the whole prompt capped at the configured
maximum. Every word comes from the chat itself or its names;
nothing is invented and no model is called. The derivation
is inspectable end to end — `preview_scene_prompt` returns
`{prompt, subject, segments, sources, message_count,
generator, enabled}` for an owned chat and generates
nothing, so the owner can read and edit the prompt before
any generation spends anything. `generate_image` uses the
scene derivation only when no manual prompt is supplied;
a manual prompt (whitespace-collapsed, non-empty, capped)
always wins, and an empty scene with no manual prompt
refuses plainly instead of inventing one.

## Per-chat enablement — never automatic

Generation is opt-in **per chat**: the plugin instance holds
the enabled chat ids (process-local, like the P-081 registry
itself), `generate_image` raises `ChatNotEnabledError` for a
chat that is not enabled, and `image_status` reports the
flag. The citizen subscribes to no message events and its
one declared event is a no-op: creating a chat or appending
a message never generates an image. Sovereignty is the
default state; a picture exists only because someone asked
for one in that chat.

## Providers — local first, honest always

The seam is `ImageRequest` → `GeneratedImage` behind any
provider object with `provider_id` / `model` / `endpoint` /
`road` and an async `generate`. `build_provider` selects:

- **`LocalDiffusionProvider`** (road `local_diffusion`) when
  an endpoint is configured. The constructor **refuses any
  non-loopback endpoint** (hostname must be `localhost`,
  `127.0.0.0/8` or `::1`), so no configuration can point this
  citizen at the external network. It POSTs the common local
  txt2img JSON shape `{prompt, negative_prompt, width,
  height, seed}` through an injected transport (production:
  urllib in a worker thread with the configured timeout;
  tests inject a fake and never touch a socket) and accepts
  `{images: [base64]}`, `{image: base64}` or raw image bytes
  back. Transport failures, non-200 replies and imageless
  replies raise `ImageProviderError`.
- **`DeterministicImageProvider`** (provider
  `deterministic-local`, model `hash-canvas-1`, road
  `deterministic_local`) when no endpoint is configured: a
  deterministic local test road rendering a real PNG (RGB,
  bit depth 8 — the subset the founding imaging code
  decodes, so P-023 thumbnails come out `ready`) whose
  gradient and block pattern derive from the request hash.
  The same request yields identical bytes.

Every generation record names the road, provider, model and
endpoint that truly produced it; the deterministic fallback
is labelled `deterministic_local` in the record, the status
and the prompt slot — never disguised as diffusion.
Provider bytes are sniffed before they count: bytes that
are not a recognisable image raise `ImageProviderError`
and record nothing.

## Asset landing — and where the stack cannot land

Landed images ride the founding P-023 machinery:
`assets.service.add_asset` with kind `background`, a filename
derived from the image digest, and `add_asset`'s own commit
contract. **P-023 assets are character-scoped, so landing
requires the chat to be bound to a character.** A chat with
no bound character still generates; its record states
`landed=False`, `landing_reason="no_character_bound"`,
`asset_id=None` — plainly, in the record itself. A landing
failure degrades the same way (`landing_reason=
"landing_failed"`, `landing_error` naming the exception
type) without un-generating the image.

The generation ledger is process-local: records
(`gen-NNNN`, chat, prompt + source, seed, size, provenance,
format, dimensions, byte size, sha256, landing outcome) are
exposed through `image_status` and `plugin.history`; the
image bytes themselves are NOT retained in the ledger —
they live in the P-023 asset store when landed. Part X
(avatars) and P-095 (gallery) build on these records.

The `image-scene` hook offers one system slot naming the
chat's latest generation — id, prompt excerpt, road,
provider/model, and the asset id or the unlanded reason —
and abstains unless the chat is enabled and a generation
exists, so composition is otherwise unchanged.

## Sandbox stance (P-082)

Only v1 surface permissions are declared, so the derived
resource grant set is empty (`sandbox_grants()` returns it;
the battery pins it). Providers and the session factory are
host-supplied wiring handed to trusted in-tree registration
code, not plugin resource grants; the local provider's
loopback refusal is defence in depth on top of that.

## Wiring

`register_plugin(registry, session_factory, *, provider,
config, enable=False)` is the one-call trusted registration
road. `build_registry` and `create_app` are deliberately
unchanged (P-081 pins the empty boot registry). P-086 banks
before this slice; the keeper reconciles liveness at
banking. This slice imports no unbanked code.

## Storage stance

No migration: enablement and the ledger are process-local
(the P-081 registry's own stance), and landed images ride
the founding P-023 `character_assets` table. The battery
pins migration head 0041 and `0042` absent.

## Verification

Battery `tests/test_p087_image_generation.py` plus
neighbours (P-081, P-082, P-083, P-084, P-085, P-023) and
the full suite — counts in `hidden_files/P087_EVIDENCE.md`.
