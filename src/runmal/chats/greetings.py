"""Card greeting decks + greeting controls: pure data contract (P-079).

A character card carries one primary greeting (``first_mes``) and a
list of alternates (``alternate_greetings``). The mirrors' public
behaviour, as Rúnmál adopts it: when a chat opens against a card,
the greeting becomes the chat's first message and the alternates
ride along as that message's swipe deck -- the reader swipes the
opening line exactly like any regenerated answer. This module is
the pure deck + choice contract behind that behaviour:

- The deck is ordered: index 0 is the primary greeting when the
  card carries one, and the alternates follow in card order.
  Blank entries (empty, whitespace-only, or not strings at all)
  never join the deck -- a swipe alternate must be a non-empty
  string (the P-065 ``validate_new_alternate`` rule) -- and a card
  with no usable greeting has an EMPTY deck: no greeting text is
  ever manufactured for it.
- A :class:`GreetingChoice` is the control a caller sets when a
  chat is created, or when a greeting is seeded into an empty
  chat. ``first`` (the default) opens on deck index 0. ``index``
  opens on an explicit index, STRICT like ``select_index``: an
  out-of-range index is a caller bug and raises ``ValueError``.
  ``random`` opens on a rolled index, and the roll is honest: a
  ``seed`` makes it reproducible (the P-036 seeded-RNG
  discipline) and the caller records the RESOLVED index, never
  the intention. ``quiet`` is the quiet start: no greeting is
  seeded at all and the chat opens empty.
- Resolving any mode against an empty deck yields ``None`` (no
  greeting), except ``index``, whose strictness raises even
  there: asking for a numbered greeting from a card that has
  none is a caller bug, not a quiet start.

This module is pure data only: no database imports, no I/O. The
one outside dependency is ``select_index`` from
``runmal.chats.swipes`` (the canonical strict swipe selection),
lazy-imported so this module stays importable on its own.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

__all__ = [
    "GREETING_MODES",
    "GreetingChoice",
    "choice_from_data",
    "choice_to_data",
    "greeting_deck",
    "greeting_entries",
]

GREETING_MODES = frozenset({"first", "index", "random", "quiet"})

_CHOICE_KEYS = frozenset({"mode", "index", "seed"})


def greeting_entries(first_mes: object, alternate_greetings: object) -> list[dict]:
    """The card's usable greetings as labelled deck entries.

    Returns one ``{"kind", "source_index", "text"}`` dict per
    usable greeting, in deck order: the primary greeting first
    (``kind == "first"``, ``source_index == 0``), then each
    usable alternate (``kind == "alternate"``, ``source_index``
    = its position in the card's ``alternate_greetings`` list).
    Entries whose text is not a string or is blank never appear.
    A non-list ``alternate_greetings`` reads as no alternates.
    Never raises.
    """
    entries: list[dict] = []
    if isinstance(first_mes, str) and first_mes.strip():
        entries.append({"kind": "first", "source_index": 0, "text": first_mes})
    if isinstance(alternate_greetings, (list, tuple)):
        for position, text in enumerate(alternate_greetings):
            if isinstance(text, str) and text.strip():
                entries.append(
                    {"kind": "alternate", "source_index": position, "text": text}
                )
    return entries


def greeting_deck(first_mes: object, alternate_greetings: object) -> list[str]:
    """The ordered greeting texts for a card (see greeting_entries)."""
    return [entry["text"] for entry in greeting_entries(first_mes, alternate_greetings)]


def _strict_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"greeting choice {field!r} must be an int")
    return value


@dataclass(frozen=True)
class GreetingChoice:
    """How a new chat's greeting is chosen (one control document).

    ``mode``: one of ``first`` / ``index`` / ``random`` /
    ``quiet``. ``index``: the explicit deck index for ``index``
    mode -- required there, refused in every other mode (a
    contradictory control is a caller bug, not a hint). ``seed``:
    the reproducible-roll seed for ``random`` mode -- likewise
    refused elsewhere. Both are real ints; bools are rejected.
    """

    mode: str = "first"
    index: int | None = None
    seed: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, str) or self.mode not in GREETING_MODES:
            raise ValueError(f"unknown greeting mode: {self.mode!r}")
        if self.index is not None:
            _strict_int(self.index, "index")
            if self.index < 0:
                raise ValueError("greeting choice 'index' must be >= 0")
        if self.seed is not None:
            _strict_int(self.seed, "seed")
        if self.mode == "index" and self.index is None:
            raise ValueError("greeting mode 'index' requires an index")
        if self.mode != "index" and self.index is not None:
            raise ValueError("greeting choice 'index' only applies to mode 'index'")
        if self.mode != "random" and self.seed is not None:
            raise ValueError("greeting choice 'seed' only applies to mode 'random'")

    def resolve(self, deck: list[str], rng: random.Random | None = None) -> int | None:
        """Resolve this choice against a deck -> active index or None.

        ``None`` means seed no greeting: quiet mode, or an empty
        deck in ``first`` / ``random`` mode. ``index`` mode is
        strict via ``select_index`` and raises ``ValueError``
        out of range (including an empty deck). ``random`` rolls
        with ``rng`` when given, else ``random.Random(self.seed)``
        -- a seeded choice therefore always lands on the same
        index for the same deck.
        """
        if self.mode == "quiet":
            return None
        if self.mode == "index":
            from runmal.chats.swipes import select_index

            return select_index(deck, self.index)
        if not deck:
            return None
        if self.mode == "first":
            return 0
        roller = rng if rng is not None else random.Random(self.seed)
        return roller.randrange(len(deck))


def choice_from_data(data: object) -> GreetingChoice:
    """Strict decode of a stored/requested greeting-choice document.

    ``None`` yields the default choice (``first``). Anything that
    is not a dict, carries unknown keys, or violates the
    :class:`GreetingChoice` rules raises ``ValueError``.
    """
    if data is None:
        return GreetingChoice()
    if not isinstance(data, dict):
        raise ValueError("greeting choice must be an object")
    unknown = set(data) - _CHOICE_KEYS
    if unknown:
        raise ValueError(f"unknown greeting choice keys: {sorted(unknown)}")
    return GreetingChoice(
        mode=data.get("mode", "first"),
        index=data.get("index"),
        seed=data.get("seed"),
    )


def choice_to_data(choice: GreetingChoice) -> dict:
    """Encode a choice as a plain dict; ALL keys always present."""
    return {"mode": choice.mode, "index": choice.index, "seed": choice.seed}
