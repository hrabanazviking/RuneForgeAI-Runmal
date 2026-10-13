# VRChat room-audio ingress (S611)

OSC (see `VRCHAT_OSC.md`) carries control and text. It does not —
and cannot — carry the room's voices. Room audio is sound, and on a
PC it already exists as an ordinary audio mix. This document is the
supported way to feed that mix to Rúnmál's ears, and an honest
statement of the path that does not exist.

## The shape (PCVR only)

```
VRChat (PC) ──audio──▶ virtual cable A ──▶ Rúnmál "room_ingress" route ──▶ STT
Rúnmál companion output route ──▶ virtual cable B ──▶ VRChat microphone input
```

- **Cable A** carries the room: other participants and game audio,
  exactly as the PC mixes them. Bind its output device to the
  `room_ingress` logical route (S513 routing) in Rúnmál's settings.
- **Cable B** carries the companion *into* the room (S605's follower
  pattern made audible). Because her voice also reaches the room mix,
  cable A hears her too — which is why self-output separation exists.

## Self-output separation

Rúnmál knows precisely when the companion spoke: the S508 playback
ledger records every played chunk's time span. The ingress
(`runmal.voice.room_ingress.RoomIngress`) marks any captured frame
overlapping a playback span (plus a 50 ms guard band for cable
latency) as `contains_self_output`, and the **default policy
excludes marked frames from STT** — she never transcribes, and so
never answers, her own voice. A `mark_only` policy keeps flagged
frames for diagnostics. A window made entirely of self-output
transcribes as silence.

If the route is unassigned or its device is unplugged, opening the
ingress fails loudly with the route's status. It never falls back to
"some microphone" (INV-022).

## PCVR test procedure (manual evidence)

1. Install a virtual audio cable (e.g. VB-CABLE) — two cables, or
   one cable plus a headset for her output.
2. In VRChat (PC, via SteamVR or Quest Link/Air Link to the PC):
   set the output device to cable A's input; set the microphone to
   cable B's output.
3. In Rúnmál: bind `room_ingress` to cable A's output device and
   `companion_output` to cable B's input device.
4. Join a world with a second participant (the S605 second-account
   pattern works well). Have the participant speak: their words
   should arrive as room speech for transcription.
5. Have the companion speak into the room. While she speaks, have
   the participant stay silent, then speak immediately after. The
   transcript of the window must contain the participant's words and
   **not** the companion's sentence.
6. Unplug/reassign cable A and confirm Rúnmál reports the route as
   `device_missing` instead of quietly listening elsewhere.

Automated evidence for the separation logic lives in
`tests/test_s611_room_ingress.py` (fake devices, scripted playback
spans): clean room audio reaches STT untouched; overlapping frames
are marked and excluded; `mark_only` keeps them flagged; a pure
self-output window yields no transcript.

## What is NOT supported

**Standalone Quest room listening is unsupported.** A Quest running
VRChat natively offers no supported way to hand its room-audio mix
to another process; Rúnmál cannot hear a standalone Quest room, and
no setting changes that. Use PCVR — Quest Link or Air Link to the
PC running Rúnmál counts, because the mix then exists on the PC.
