# P-109 - Voice Affects as Carried Data (Part VII, VX-12 first step)

## Derivation statement (binding honesty)
The governing roadmap gives Part VII only its part line -
VII | Voice, the Voxta Way | P-101..P-116 - and no per-slice
entries. This scope is DERIVED, not roadmap verbatim, from
in-tree sources only: census row VX-12 (voices carry emotion
- anger, whispering, laughing - with proper prosody and
affects), the P-105 slice doc (VX-12 not taken there: no
affect seam exists in any TTS backend; VoiceInfo carries no
affect field), and the P-101/P-104 scouts (VX-12 needs its
own truth model). The keeper reviews this derived scope at
banking. Base dfdd07c (P-106 banking record). Migration: NONE.

## 1. The gap, exactly
VX-12's full form needs an engine: a backend that accepts an
affect and renders prosody. No such seam exists and this slice
does not invent one. The DATA half was missing entirely: no
vocabulary (a profile could not name an affect in any
validated way), no carrying surface (the session snapshot
recorded voice but no affect), no surface stating the truth
that nothing consumes one. A character's intended affect
evaporated at the profile door.

## 2. What lands
- src/runmal/voice/affects.py: the closed vocabulary as data
  (neutral + anger, whispering, laughing - exactly the census
  row's named affects); strict normalize_affect for write
  doors; tolerant affect_from_params (missing = neutral via
  default; out-of-vocabulary stored = neutral via fallback,
  NAMED); with_affect (neutral removes the params key -
  absence is neutral's one representation); consumption_view
  / affect_view / vocabulary_view, every one stating
  consumed: False with the reason as data.
- profiles.py: set_character_voice validates params[affect]
  strictly when present - the vocabulary's first real
  consumer. Unknown affect = ValueError at the write door.
- session.py: SessionSettings gains affect + affect_source,
  resolved once at session start from the character voice
  params (P-101 snapshot law); to_dict carries affect,
  affect_source, affect_consumed: False; from_dict resolves
  a stored value through the same fallback law (a corrupt
  stored affect never bricks a stored session; pre-P-109
  snapshots construct unchanged).
- router.py (founding road, additive): GET /voice/affects
  (vocabulary + truth) and GET /voice/sessions/{id}/affect
  (the session's carried affect view; 404 unknown session).
- voice/__init__.py: one module-map entry (additive).
- Battery tests/test_p109_voice_affects.py (13 tests).

## 3. Laws held
No fake prosody (nothing claims an affect is rendered, heard
or consumed; every surface shows consumed: False). One
vocabulary, imported never copied. Write strict, read
tolerant with the fallback named. No migration, no new store.

## 4. Honest limitations
- No backend consumes an affect: synthesis is byte-identical
  with or without one. The engine half of VX-12 (a backend
  seam accepting affect, prosody rendering, the census
  playground/benchmark) stays open for its own slice.
- Per-turn affect changes are not modelled: the affect is the
  profile's standing intention, snapshotted at session start
  like the voice itself. Mid-session change = profile edit +
  new session.
- The vocabulary is the census row's three named affects +
  neutral; widening it is a design act for a later slice.
- VX-13 narrator, the character-asks repeat half (P-102
  responder seam), and P-108's recorded limitations stay
  open exactly as the scout records.
