"""Pure card logic for the W-02 Characters + Library tabs.

No I/O lives here: tag parsing, the lossless card overlay (the
R-08 composition — fields land at the level the stored shape
keeps them, ``data`` for wrapped cards, top level for flat ones,
and every unknown key is carried verbatim, INV-009), and the
plain-words rendering of the engine's bulk-import report.
"""
from __future__ import annotations

import copy
from typing import Any

CARD_TEXT_FIELDS = (
    "description", "personality", "scenario", "system_prompt",
    "mes_example", "post_history_instructions", "first_mes",
    "creator_notes", "creator", "character_version", "nickname",
)


def parse_tags(text) -> list[str]:
    out: list[str] = []
    for chunk in str(text or "").replace("\n", ",").split(","):
        tag = chunk.strip()
        if tag and tag not in out:
            out.append(tag)
    return out


def card_data_of(card: dict) -> dict:
    data = card.get("data") if isinstance(card, dict) else None
    return data if isinstance(data, dict) else card


def apply_card_edits(raw_card: dict, edits: dict) -> dict:
    result = copy.deepcopy(raw_card)
    level = card_data_of(result)
    for key, value in edits.items():
        level[key] = copy.deepcopy(value)
    return result


def card_fields(card: dict) -> dict:
    """The editor's field bag read from a stored card dict."""
    data = card_data_of(card or {})
    out: dict[str, Any] = {"name": str(data.get("name") or "")}
    for key in CARD_TEXT_FIELDS:
        out[key] = str(data.get(key) or "")
    for key in ("alternate_greetings", "group_only_greetings", "tags"):
        value = data.get(key)
        out[key] = [str(v) for v in value if isinstance(v, str)] if isinstance(value, list) else []
    book = data.get("character_book")
    out["character_book"] = book if isinstance(book, dict) else {}
    return out


def import_report_words(report: dict) -> dict:
    """Collapse the engine bulk-import report (P-022) to verdicts."""
    totals = report.get("totals") if isinstance(report, dict) else None
    totals = totals if isinstance(totals, dict) else {}

    def _n(key):
        value = totals.get(key)
        return value if isinstance(value, int) else 0
    lines, created = [], []
    entries = report.get("entries") if isinstance(report, dict) else None
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("filename") or entry.get("relpath") or "file")
            if entry.get("created_id"):
                created.append(str(entry["created_id"]))
                shown = entry.get("created_name") or entry["created_id"]
                lines.append(f"{name}: imported as \u201c{shown}\u201d")
            elif entry.get("duplicate_of"):
                lines.append(f"{name}: already in the library (exact duplicate)")
            else:
                outcome = str(entry.get("outcome") or entry.get("status") or "")
                reason = str(entry.get("reason") or entry.get("detail") or "")
                if outcome:
                    lines.append(f"{name}: {outcome}" + (f" \u2014 {reason}" if reason else ""))
    accepted, repaired = _n("accepted"), _n("repaired")
    refused, skipped = _n("refused"), _n("skipped") or _n("total_skipped")
    words = f"Import finished: {accepted + repaired} character(s) landed"
    if refused:
        words += f", {refused} refused"
    if skipped:
        words += f", {skipped} skipped"
    return {"total": _n("total_seen") or _n("seen"), "accepted": accepted,
            "repaired": repaired, "refused": refused, "skipped": skipped,
            "lines": lines, "created_ids": created, "words": words + "."}
