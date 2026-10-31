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
    character_version: str = ""
    # Character Card v3 additions (P-016), mapped by field name in
    # docs/CARD_V3_IMPORT_2026-10-31.md. `asset_refs` holds the v3
    # spec's declared `assets` descriptors ({type, uri, name, ext});
    # it is distinct from `assets` below, which holds embedded file
    # bytes (CHARX). Timestamps are Unix seconds, None when the card
    # does not carry them — never fabricated.
    nickname: str = ""
    group_only_greetings: list[str] = field(default_factory=list)
    creator_notes_multilingual: dict = field(default_factory=dict)
    source: list[str] = field(default_factory=list)
    creation_date: int | None = None
    modification_date: int | None = None
    asset_refs: list[dict] = field(default_factory=list)
    character_book: dict = field(default_factory=dict)
    extensions: dict = field(default_factory=dict)
    assets: dict[str, bytes] = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    spec_version: str = "2"
    source_format: str = "json"

    def find_asset_ref(
        self, asset_type: str | None = None, name: str | None = None
    ) -> dict | None:
        """First declared v3 asset descriptor matching type and/or name."""
        for ref in self.asset_refs:
            if asset_type is not None and ref.get("type") != asset_type:
                continue
            if name is not None and ref.get("name") != name:
                continue
            return ref
        return None

    def resolve_asset(self, uri: str) -> bytes | None:
        """Resolve `embeded://` / `embedded://` asset URIs (both spellings
        accepted per the v3 spec's misspelling and real-world usage)."""
        for scheme in ("embeded://", "embedded://"):
            if uri.startswith(scheme):
                return self.assets.get(uri[len(scheme) :])
        return self.assets.get(uri)
