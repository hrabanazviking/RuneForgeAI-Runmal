"""Scan depth & context windows for lorebooks (P-037).

Pure-domain module: no DB, no I/O, no network, no randomness,
no wall-clock. It owns the per-book scan-settings vocabulary --
how much context the keyword scanner sees, as stored data --
and the single window builder the scan engine consults.

Before this slice a book had exactly one scan knob, the bare
``scan_depth`` integer (S201): the scanner always looked at the
last ``scan_depth`` chat messages, and nothing else could be
scanned at all. The roadmap line makes the window itself data:

Semantics (normative):
- A book's scan settings are three stored fields:
  ``scan_depth`` (messages-deep, an int >= 1, default 4 -- the
  pre-P-037 knob, meaning unchanged), ``scan_mode`` (which
  window of the chat is scanned), and
  ``scan_external_context`` (whether context that lives
  outside the chat message list joins the window).
- ``scan_mode`` is one of:
  - ``"depth"`` (the default): only the last ``scan_depth``
    chat messages are scanned -- exactly the pre-P-037
    behaviour, so an untouched book scans as it always did.
  - ``"whole_chat"``: every chat message is scanned, however
    long the chat runs; ``scan_depth`` is still stored (the
    author may switch back) but does not bound the window.
- External context is text the caller supplies alongside the
  messages -- character or persona description, scenario text,
  a summary: context that is in the prompt but is not a chat
  message. It is scanned ONLY when the book's
  ``scan_external_context`` is true. It forms its own window
  segment, appended after the chat segment, and is NOT
  counted against ``scan_depth`` (depth counts chat messages;
  the external segment is governed by its own flag). With the
  flag off, supplied external text is ignored entirely --
  never scanned, never reported as scanned.
- The window is a list of texts with honest provenance: every
  position knows whether it came from the chat (and its index
  in the FULL message list, so hit indices stay comparable
  with the pre-P-037 scanner) or from the external segment
  (and its index in the supplied external list). A key may
  match in either segment; primary and secondary keys may be
  satisfied across segments -- the window is one context.
- Strict vs tolerant discipline mirrors P-034/P-036: the
  service/API layer validates strictly via ``check_*`` (a
  real canonical mode, a real bool, a real int >= 1; anything
  else is an error the caller sees); stored/file layers
  normalise tolerantly via ``normalise_*`` (unknown or
  malformed values fall back to the defaults -- an unknown
  mode falls back to ``"depth"``, the behaviour every book
  had before this slice, never to a wider window the author
  did not ask for).
- Settings are PER BOOK: each book's entries are scanned
  against that book's own resolved window (the preview and
  the prompt inspector both loop books and resolve settings
  per book); there is no cross-book window.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

#: Scan modes: which window of the chat is scanned.
SCAN_MODE_DEPTH = "depth"
SCAN_MODE_WHOLE_CHAT = "whole_chat"
SCAN_MODES = frozenset({SCAN_MODE_DEPTH, SCAN_MODE_WHOLE_CHAT})

#: Defaults: an untouched book scans exactly as before P-037.
DEFAULT_SCAN_MODE = SCAN_MODE_DEPTH
DEFAULT_SCAN_DEPTH = 4
DEFAULT_SCAN_EXTERNAL_CONTEXT = False

#: Window-segment provenance labels.
SOURCE_CHAT = "chat"
SOURCE_EXTERNAL = "external"

__all__ = [
    "SCAN_MODE_DEPTH",
    "SCAN_MODE_WHOLE_CHAT",
    "SCAN_MODES",
    "DEFAULT_SCAN_MODE",
    "DEFAULT_SCAN_DEPTH",
    "DEFAULT_SCAN_EXTERNAL_CONTEXT",
    "SOURCE_CHAT",
    "SOURCE_EXTERNAL",
    "ScanSettings",
    "ScanWindow",
    "check_scan_mode",
    "normalise_scan_mode",
    "check_scan_depth",
    "normalise_scan_depth",
    "check_scan_external_context",
    "normalise_scan_external_context",
    "build_scan_window",
]


def check_scan_mode(value) -> str:
    """Strict validation: return ``value`` if it is a scan mode.

    Raises ValueError for anything else (wrong case, unknown
    mode, None, non-strings).
    """
    if isinstance(value, str) and value in SCAN_MODES:
        return value
    raise ValueError(
        f"invalid scan_mode: {value!r} (valid: {sorted(SCAN_MODES)})"
    )


def normalise_scan_mode(value) -> str:
    """Tolerant mode normaliser: canonical name -> itself, else default.

    The fallback is ``"depth"`` -- the narrowest, pre-P-037
    window -- never a wider window the author did not ask for.
    """
    if isinstance(value, str) and value in SCAN_MODES:
        return value
    return DEFAULT_SCAN_MODE


def check_scan_depth(value) -> int:
    """Strict validation: a real int >= 1 (bools are not ints here)."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("scan_depth must be >= 1")
    return value


def normalise_scan_depth(value) -> int:
    """Tolerant depth normaliser: a real int >= 1, else the default 4."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return DEFAULT_SCAN_DEPTH
    return value


def check_scan_external_context(value) -> bool:
    """Strict validation: the flag must be a real bool."""
    if isinstance(value, bool):
        return value
    raise ValueError(f"scan_external_context must be a bool, got {value!r}")


def normalise_scan_external_context(value) -> bool:
    """Tolerant flag coercion: None -> False, else bool(value) --
    with one guard: a STRING is read as the flag it names, so
    ``"false"`` / ``"0"`` / ``"no"`` / ``"off"`` normalise to
    False, never to True by truthiness. A stringly file value
    must not widen the window past what its author wrote (the
    module's never-widen discipline); only ``"true"`` / ``"1"``
    / ``"yes"`` / ``"on"`` (any case) read as True."""
    if value is None:
        return DEFAULT_SCAN_EXTERNAL_CONTEXT
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


@dataclass(frozen=True)
class ScanSettings:
    """A book's scan settings, as data (see module docstring).

    Construction validates STRICTLY (``check_*``): building a
    ``ScanSettings`` from unvalidated input raises ValueError.
    Use :meth:`normalised` or :meth:`from_book` for stored or
    file-layer values, which coerce tolerantly instead.
    """

    scan_depth: int = DEFAULT_SCAN_DEPTH
    scan_mode: str = DEFAULT_SCAN_MODE
    scan_external_context: bool = DEFAULT_SCAN_EXTERNAL_CONTEXT

    def __post_init__(self) -> None:
        object.__setattr__(self, "scan_depth", check_scan_depth(self.scan_depth))
        object.__setattr__(self, "scan_mode", check_scan_mode(self.scan_mode))
        object.__setattr__(
            self,
            "scan_external_context",
            check_scan_external_context(self.scan_external_context),
        )

    @classmethod
    def normalised(
        cls,
        scan_depth=None,
        scan_mode=None,
        scan_external_context=None,
    ) -> "ScanSettings":
        """Tolerant build: malformed values fall back to defaults."""
        return cls(
            scan_depth=normalise_scan_depth(scan_depth),
            scan_mode=normalise_scan_mode(scan_mode),
            scan_external_context=normalise_scan_external_context(
                scan_external_context
            ),
        )

    @classmethod
    def from_book(cls, book) -> "ScanSettings":
        """Tolerant build from an ORM Lorebook row or a mapping.

        Rows written before P-037 simply lack the new fields;
        they read as the defaults (depth mode, external off),
        which is the behaviour they always had.
        """
        if isinstance(book, Mapping):
            get = book.get
        else:
            def get(name, default=None):
                return getattr(book, name, default)
        return cls.normalised(
            scan_depth=get("scan_depth"),
            scan_mode=get("scan_mode"),
            scan_external_context=get("scan_external_context"),
        )

    def chat_window_size(self, message_count: int) -> int:
        """How many of ``message_count`` chat messages are scanned."""
        if message_count < 0:
            raise ValueError("message_count must be >= 0")
        if self.scan_mode == SCAN_MODE_WHOLE_CHAT:
            return message_count
        return min(self.scan_depth, message_count)

    def to_dict(self) -> dict:
        return {
            "scan_depth": self.scan_depth,
            "scan_mode": self.scan_mode,
            "scan_external_context": self.scan_external_context,
        }


@dataclass(frozen=True)
class ScanWindow:
    """The resolved scan window: texts plus honest provenance.

    ``texts[i]`` was scanned; ``sources[i]`` says where it came
    from (``"chat"`` / ``"external"``); for a chat text,
    ``message_indices[i]`` is its index in the FULL message
    list the caller passed (external positions carry None);
    for an external text, ``external_indices[i]`` is its index
    in the caller's external list (chat positions carry None).
    """

    texts: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    message_indices: tuple[int | None, ...] = ()
    external_indices: tuple[int | None, ...] = ()

    @property
    def chat_count(self) -> int:
        return sum(1 for s in self.sources if s == SOURCE_CHAT)

    @property
    def external_count(self) -> int:
        return sum(1 for s in self.sources if s == SOURCE_EXTERNAL)

    def summary(self) -> dict:
        """Counts only -- what was scanned, never the text itself."""
        return {
            "texts": len(self.texts),
            "chat_messages": self.chat_count,
            "external_texts": self.external_count,
        }


def build_scan_window(
    settings: ScanSettings,
    messages,
    external_context=(),
) -> ScanWindow:
    """Resolve ``settings`` over one tick's context into a window.

    Chat segment first (the last ``settings.scan_depth``
    messages in depth mode, all of them in whole-chat mode),
    then -- only when the book's ``scan_external_context`` is
    true -- the external segment, in caller order, uncounted
    against the depth. With the flag off, ``external_context``
    is ignored entirely.
    """
    msgs = list(messages or ())
    size = settings.chat_window_size(len(msgs))
    start = len(msgs) - size
    texts: list[str] = []
    sources: list[str] = []
    message_indices: list[int | None] = []
    external_indices: list[int | None] = []
    for i in range(start, len(msgs)):
        texts.append(msgs[i])
        sources.append(SOURCE_CHAT)
        message_indices.append(i)
        external_indices.append(None)
    if settings.scan_external_context:
        for j, text in enumerate(external_context or ()):
            texts.append(text)
            sources.append(SOURCE_EXTERNAL)
            message_indices.append(None)
            external_indices.append(j)
    return ScanWindow(
        texts=tuple(texts),
        sources=tuple(sources),
        message_indices=tuple(message_indices),
        external_indices=tuple(external_indices),
    )
