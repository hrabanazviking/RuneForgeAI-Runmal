# Rúnmál Compatibility Targets

This file states intended compatibility promises. Implementation status is tracked separately in `STATUS.md`.

## 1. Character cards

Target support:

| Format | Import | Export | Notes |
|---|---:|---:|---|
| Tavern/Character Card v1 JSON/PNG | Target | Target | Normalize into internal model while preserving source data where possible. |
| Character Card v2 JSON/PNG | Target | Target | Preserve opaque `extensions`; respect prompt-vs-metadata field roles. |
| Character Card v3 JSON/PNG | Target | Target | Use current normative v3 specification, not outdated conceptual docs. |
| CHARX archive | Target | Target | Preserve supported assets and unknown compatible metadata safely. |

The current Character Card v3 archive name is **CHARX**. Research/implementation should use the normative current `SPEC_V3.md` as source of truth and treat older `concepts.md` material as non-normative when they disagree.

## 2. Round-trip promise

For supported formats:

- opaque extension data survives;
- unknown valid fields are not intentionally dropped;
- supported assets survive;
- creator metadata is preserved without becoming prompt text;
- import → export → import yields equivalent semantic card data.

Binary PNG files are not required to be byte-identical if legal metadata encoding/chunk ordering differs; the card data and supported assets are the compatibility contract.

## 3. Inference providers

Initial targets:

- Ollama native API;
- OpenRouter OpenAI-compatible chat API;
- Project Aesir when its server contract is ready.

Other OpenAI-compatible providers may be added through adapters, but "OpenAI-compatible" is not assumed to mean perfectly identical behavior.

## 4. Embeddings

Embedding backends are independently selectable from chat backends. Current Ollama native embeddings should be implemented against the current official native endpoint (`POST /api/embed`) when Campaign III is built; re-verify official docs at implementation time.

Stored vectors are compatible only with the exact embedding space described by their model/provider/dimension/version provenance.

## 5. Operating systems

Primary development target: modern Linux/Kubuntu-class desktop.

Release goal: Linux + Windows for core chat/storage/provider functionality. Audio/virtual-device behavior is OS-specific and requires separate hardware-in-loop validation.

Systemd is a Linux deployment convenience, not a cross-platform architecture dependency.

## 6. Browsers

The web UI should target current evergreen desktop browsers. Voice browser capabilities may differ and are not assumed equivalent to native/host audio routing.

## 7. Database compatibility

SQLite is the canonical phase-one store. Released schema changes use versioned migrations. Old supported database fixtures must upgrade through CI migration tests.

## 8. API compatibility

External bridge API begins at `/api/v1/...` and follows `BRIDGE_PROTOCOL.md`. Internal implementation details are not compatibility promises.

## 9. Portable archives

The future `.runmal` archive has its own format version independent from application semver. Unknown future fields should be preserved/ignored safely where the format permits rather than causing silent loss.

## 10. License compatibility

Core distributed dependencies must satisfy Rúnmál's permissive-license policy. License review applies to the **runtime dependency tree, model weights, voices/assets and bundled binaries**, not merely the top-level Python package.

Current voice caution: Kokoro model/wrapper licensing may be permissive while phonemization/runtime dependencies can introduce different obligations. The final selected stack must pass the license audit before acceptance.