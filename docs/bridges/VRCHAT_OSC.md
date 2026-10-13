# VRChat OSC Reference Bridge (S605)

Third-party starting point: `src/runmal/bridges/vrchat_osc.py` (plus
the dependency-light OSC codec in `src/runmal/bridges/osc.py`).
Everything game-specific lives in that module; Rúnmál core knows
nothing about VRChat.

## The follower pattern

VRChat companionship uses **two accounts**:

1. the user's own account, played normally;
2. a **second account** wearing the companion's avatar, logged in on a
   client the bridge can reach (typically the same PC).

The bridge polls the Rúnmál conversation state (bridge API, S602)
with a scoped bridge token (`chat:read:<chat-id>` is all it needs)
and mirrors each **new companion turn** into the follower client's
chatbox over OSC. An avatar parameter (`CompanionSpeaking`, bool) is
raised while a turn is mirrored, so avatar animators can drive a
speaking gesture/mouth from it. History is never replayed: the first
poll only primes the cursor.

## OSC surface used

VRChat receives OSC on UDP **9000** (sends on 9001):

| Address | Args | Meaning |
| --- | --- | --- |
| `/chatbox/input` | text (string), direct (bool), notify (bool) | show a chatbox message |
| `/chatbox/typing` | bool | chatbox typing indicator |
| `/avatar/parameters/<Name>` | bool / int / float | set an avatar parameter |

The chatbox displays at most **144 characters**; longer turns are
chunked on word boundaries by the bridge (a single over-long word is
hard-split as a last resort).

## What OSC cannot do — stated plainly

**OSC is not room-voice capture.** It carries text and avatar
parameters only; nothing in this bridge hears the user or other
participants. A companion that should *listen* in VRChat needs the
PC-host room-audio ingress of S611 (an explicit audio route into
Rúnmál's voice pipeline, with known self-output excluded or marked;
see `VRCHAT_ROOM_AUDIO.md` for the setup and test procedure).
Standalone-Quest room listening is not supported by this design.

Speaking *aloud* in-world (rather than chatbox text) is likewise a
separate concern: route the S604 TTS hook's audio into the follower
client's microphone input (e.g. a virtual cable on the PC host) —
the bridge API already provides the synthesis and lifecycle; the
audio plumbing belongs to the deployment, not the protocol.

## Running

```
RUNMAL_BRIDGE_TOKEN=<token> python -m runmal.bridges.vrchat_osc \
    --base-url http://127.0.0.1:8000 --chat-id <chat-id>
```

Create the token in the owner UI/API with scope
`chat:read:<chat-id>` (S601). The token is read from the environment,
never from the command line, so it stays out of process listings and
shell history.
