"""Typed card-parse errors (S104)."""

from __future__ import annotations

from enum import StrEnum


class CardErrorKind(StrEnum):
    INPUT_TOO_LARGE = "input_too_large"
    INVALID_JSON = "invalid_json"
    TRUNCATED = "truncated"
    NOT_A_CARD = "not_a_card"
    UNSUPPORTED_VERSION = "unsupported_version"
    BAD_ARCHIVE = "bad_archive"
    PATH_TRAVERSAL = "path_traversal"
    ASSET_TOO_LARGE = "asset_too_large"
    NO_CARD_DATA = "no_card_data"
    INVALID_PNG = "invalid_png"


class CardParseError(ValueError):
    """A card import failed for a typed, testable reason."""

    def __init__(self, kind: CardErrorKind, message: str) -> None:
        self.kind = kind
        super().__init__(message)
