# Rúnmál Voice License Matrix

Rúnmál's project policy is a permissive-only distributed voice stack. The exact license of **every shipped artifact** matters: application code, Python/native dependencies, model weights, voices, phonemizer data and bundled binaries.

This file is a release/build gate, not legal advice. Re-verify exact versions upstream before adoption/distribution.

## Status vocabulary

- ✅ **cleared** — exact chosen version/artifact reviewed against project policy.
- 🟡 **candidate** — promising but complete runtime tree not cleared.
- ❌ **rejected by project policy** — known selected artifact/license conflicts with the permissive-only distribution policy.
- 🔄 **reverify** — previously checked but must be checked again for release/version change.

## Candidate stack ledger

| Layer | Candidate | Current Rúnmál state | Required evidence before acceptance |
|---|---|---|---|
| VAD | Silero VAD | 🟡 candidate | exact code/model license/version + transitive runtime tree |
| STT | faster-whisper + chosen Whisper weights | 🟡 candidate | package dependencies + model-weight license/version |
| TTS model | Kokoro-82M family | 🟡 candidate | exact model/weights license + voice asset terms |
| TTS runtime | kokoro-onnx or independent ONNX path | 🟡 candidate | wrapper + ONNX runtime + phonemizer dependencies |
| Phonemization | Misaki/native G2P or other permissive path | 🟡 candidate | exact install extras/dependencies; prove no incompatible fallback is bundled |
| Audio I/O | sounddevice/PortAudio or final choice | 🟡 candidate | exact package/native library licenses |
| AEC | not selected | 🟡 research | exact runtime/binary license + quality on target route |

## Known caution categories

### eSpeak/eSpeak-NG paths

Do not assume a phonemizer is cleared because the high-level TTS package is permissive. If the selected runtime depends on or bundles eSpeak/eSpeak-NG, inspect the exact upstream licensing and decide against Rúnmál's project policy before S504 acceptance.

### Piper ecosystem

Do not use the name "Piper" as a license conclusion. Different repositories/packages/voices/history may carry different licensing. Review the **exact artifact/version** if reconsidered.

### XTTS / cloning models

Model-weight licenses can impose restrictions independent of inference code. Check exact weight license and commercial/distribution rights before considering a cloning model.

## S504 gate

S504 cannot pass with only "Kokoro is Apache/MIT" or an equivalent top-level statement.

Acceptance evidence should record:

```text
TTS model:
  artifact/version/hash:
  license:
  source:

TTS runtime:
  package/version:
  license:
  dependency lock reviewed:

Phonemizer:
  package/version:
  license:
  optional/fallback dependencies:

Voice assets:
  IDs/files:
  license/source:

Native binaries:
  artifacts:
  licenses:

Verdict: cleared / rejected
Reviewed date:
Commit:
```

## Automated gate

Campaign VIII should generate an SBOM/license report from the release environment, but automation supplements manual review for model/voice assets that ordinary Python license scanners may not understand.

A package scanner saying "green" is not proof that separately downloaded weights/assets are cleared.

## Change rule

When any voice dependency/model/voice version changes, return its row to 🔄/🟡 until the release artifact is rechecked.