"""Lorebook import/export (S304).

Export is Rúnmál's native shape. Import accepts two shapes:

1. **Native** -- ``{"name": ..., "entries": [{...entry fields...}]}`` (what
   export produces; round-trips exactly).
2. **World-info** -- the common SillyTavern-style lorebook shape:
   ``{"entries": {"<uid>": {"key": [...], "keysecondary": [...],
   "content": ..., "comment": <name>, "constant": bool, "disable": bool,
   "order": int, "position": int}}}`` (``entries`` may also be a list).
   Field mapping: key->keys, keysecondary->secondary_keys,
   comment->name, order->priority, disable->not enabled,
   position 0->before_char / 1->after_char (anything else -> before_char).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import Lorebook
from runmal.lorebooks import service


def export_book(book: dict, entries: list[dict]) -> dict:
    """Serialize a book + its entries (API dicts) to the native shape."""
    return {
        "format": "runmal-lorebook",
        "version": 1,
        "name": book["name"],
        "description": book.get("description", ""),
        "scan_depth": book.get("scan_depth", 4),
        "token_budget": book.get("token_budget"),
        "entries": [
            {
                "name": e["name"],
                "content": e["content"],
                "keys": e["keys"],
                "secondary_keys": e["secondary_keys"],
                "priority": e["priority"],
                "position": e["position"],
                "enabled": e["enabled"],
                "constant": e["constant"],
                "case_sensitive": e["case_sensitive"],
                "whole_word": e["whole_word"],
                "sticky_prompts": e["sticky_prompts"],
                "cooldown_prompts": e["cooldown_prompts"],
                "delay_prompts": e["delay_prompts"],
            }
            for e in entries
        ],
    }


def _native_entry(raw: dict) -> dict:
    return {
        "name": str(raw.get("name", "")),
        "content": str(raw.get("content", "")),
        "keys": list(raw.get("keys") or []),
        "secondary_keys": list(raw.get("secondary_keys") or []),
        "priority": int(raw.get("priority", 100)),
        "position": str(raw.get("position", "before_char")),
        "enabled": bool(raw.get("enabled", True)),
        "constant": bool(raw.get("constant", False)),
        "case_sensitive": bool(raw.get("case_sensitive", False)),
        "whole_word": bool(raw.get("whole_word", True)),
        "sticky_prompts": int(raw.get("sticky_prompts", 0)),
        "cooldown_prompts": int(raw.get("cooldown_prompts", 0)),
        "delay_prompts": int(raw.get("delay_prompts", 0)),
    }


def _worldinfo_entry(raw: dict) -> dict:
    position = {0: "before_char", 1: "after_char"}.get(
        raw.get("position"), "before_char"
    )
    keys = raw.get("key") or []
    if isinstance(keys, str):
        keys = [keys]
    secondary = raw.get("keysecondary") or []
    if isinstance(secondary, str):
        secondary = [secondary]
    return {
        "name": str(raw.get("comment") or raw.get("name") or ""),
        "content": str(raw.get("content", "")),
        "keys": [str(k) for k in keys],
        "secondary_keys": [str(k) for k in secondary],
        "priority": int(raw.get("order", 100)),
        "position": position,
        "enabled": not bool(raw.get("disable", False)),
        "constant": bool(raw.get("constant", False)),
        "case_sensitive": bool(raw.get("caseSensitive", False)),
        "whole_word": True,
        "sticky_prompts": 0,
        "cooldown_prompts": 0,
        "delay_prompts": 0,
    }


def parse_import(data: dict) -> tuple[dict, list[dict]]:
    """Parse either import shape into (book fields, entry field dicts)."""
    if not isinstance(data, dict):
        raise ValueError("lorebook import must be a JSON object")
    raw_entries = data.get("entries")
    if raw_entries is None:
        raise ValueError("lorebook import has no 'entries'")
    if isinstance(raw_entries, dict):
        # world-info: uid-keyed mapping; order by numeric uid for stability
        ordered = [
            raw_entries[k]
            for k in sorted(raw_entries, key=lambda k: (len(str(k)), str(k)))
        ]
        entries = [_worldinfo_entry(e) for e in ordered]
        book = {"name": str(data.get("name") or "Imported lorebook")}
    elif isinstance(raw_entries, list):
        if raw_entries and isinstance(raw_entries[0], dict) and (
            "key" in raw_entries[0] or "keysecondary" in raw_entries[0]
        ):
            entries = [_worldinfo_entry(e) for e in raw_entries]
            book = {"name": str(data.get("name") or "Imported lorebook")}
        else:
            entries = [_native_entry(e) for e in raw_entries]
            book = {
                "name": str(data.get("name") or ""),
                "description": str(data.get("description") or ""),
                "scan_depth": int(data.get("scan_depth") or 4),
                "token_budget": data.get("token_budget"),
            }
    else:
        raise ValueError("'entries' must be an object or a list")
    if not book.get("name"):
        raise ValueError("lorebook import needs a name")
    return book, entries


async def import_book(
    session: AsyncSession, user_id: str, data: dict
) -> Lorebook:
    """Create a lorebook + entries from either import shape."""
    book_fields, entry_fields = parse_import(data)
    book = await service.create_lorebook(
        session,
        user_id,
        name=book_fields["name"],
        description=book_fields.get("description", ""),
        scan_depth=book_fields.get("scan_depth", 4),
        token_budget=book_fields.get("token_budget"),
    )
    for fields in entry_fields:
        await service.create_entry(session, user_id, book.id, **fields)
    return book
