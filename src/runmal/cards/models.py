"""Normalized character card (S104).

`raw` always holds the complete original mapping so unknown-but-valid
fields survive supported round trips (INV-009).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CharacterCard:
    name: str
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_mes: str = ""
    mes_example: str = ""
    creator_notes: str = ""
    system_prompt: str = ""
    post_history_instructions: str = ""
    alternate_greetings: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    creator: str = ""
    character_book: dict = field(default_factory=dict)
    extensions: dict = field(default_factory=dict)
    assets: dict[str, bytes] = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    spec_version: str = "2"
    source_format: str = "json"

    def resolve_asset(self, uri: str) -> bytes | None:
        """Resolve `embeded://` / `embedded://` asset URIs (both spellings
        accepted per the v3 spec's misspelling and real-world usage)."""
        for scheme in ("embeded://", "embedded://"):
            if uri.startswith(scheme):
                return self.assets.get(uri[len(scheme) :])
        return self.assets.get(uri)
