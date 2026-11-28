"""W-02 compositions over the engine API (the R-08 roads).

Full card = summary + current version's stored card; save =
PATCH the overlaid card losslessly, tag sync only when tags
changed; version restore = GET version card -> PATCH back;
export = the stored card serialised. No new engine routes.
"""
from __future__ import annotations

import json
from email import policy
from email.parser import BytesParser
from typing import Any

from .cards import CARD_TEXT_FIELDS, apply_card_edits, card_fields, parse_tags
from .engine import EngineError


def parse_multipart(body: bytes, content_type: str):
    """Split a multipart/form-data body into (fields, files).

    files: list of (field_name, filename, bytes). Uses the stdlib
    email parser — the webface server stays stdlib-only.
    """
    raw = (f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n"
           .encode() + body)
    message = BytesParser(policy=policy.default).parsebytes(raw)
    fields: dict[str, str] = {}
    files: list[tuple[str, str, bytes]] = []
    if not message.is_multipart():
        return fields, files
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            files.append((str(name or "file"), str(filename), payload))
        elif name:
            fields[str(name)] = payload.decode("utf-8", "replace")
    return fields, files


def _summary(engine, cid):
    payload = engine.request("GET", f"/api/v1/characters/{cid}")
    return payload if isinstance(payload, dict) else {}


def _version_card(engine, cid, version_no):
    payload = engine.request(
        "GET", f"/api/v1/characters/{cid}/versions/{version_no}")
    if isinstance(payload, dict):
        card = payload.get("card")
        if isinstance(card, dict):
            return card
    return {}


def stored_card(engine, cid):
    summary = _summary(engine, cid)
    version_no = summary.get("version_no")
    card = _version_card(engine, cid,
                         version_no if isinstance(version_no, int) else 1)
    return summary, card


def editor_bundle(engine, cid) -> dict:
    summary, card = stored_card(engine, cid)
    fields = card_fields(card)
    if not fields["name"]:
        fields["name"] = str(summary.get("name") or "")
    org = engine.request(
        "GET", f"/api/v1/library/cards/{cid}/organisation")
    org = org if isinstance(org, dict) else {}
    if isinstance(org.get("tags"), list):
        fields["tags"] = [str(t) for t in org["tags"]]
    book = engine.request("GET", f"/api/v1/characters/{cid}/character-book")
    book = book if isinstance(book, dict) else {}
    entries = book.get("entries")
    binding = engine.request(
        "GET", f"/api/v1/characters/{cid}/lorebook-binding")
    assets = engine.request("GET", f"/api/v1/characters/{cid}/assets")
    versions = engine.request("GET", f"/api/v1/characters/{cid}/versions")
    lorebooks = engine.request("GET", "/api/v1/lorebooks")
    editor = engine.request("GET", f"/api/v1/characters/{cid}/editor")
    # Amendment 1: the character's voice - S512 profile + the
    # speech service's registered voices for the picker. A voice
    # road failure degrades to an empty picker, never a dead editor.
    try:
        from . import w08 as _w08
        voice_profile = _w08.character_voice(engine, cid)
        voice_names = _w08.list_service_voices(engine)["names"]
    except Exception:
        voice_profile, voice_names = {}, []
    return {
        "id": cid, "summary": summary, "fields": fields,
        "raw_card": card, "organisation": org,
        "is_favourite": bool(org.get("is_favourite", False)),
        "book_entry_count": len(entries) if isinstance(entries, list) else 0,
        "binding": binding if isinstance(binding, dict) else {},
        "assets": assets if isinstance(assets, list) else [],
        "versions": versions if isinstance(versions, dict) else {},
        "lorebooks": lorebooks if isinstance(lorebooks, list) else [],
        "editor_view": editor if isinstance(editor, dict) else {},
        "voice_profile": voice_profile,
        "voice_names": voice_names,
        "has_avatar": bool(summary.get("has_avatar", False)),
    }


def save_character(engine, cid, body: dict) -> dict:
    _summary_row, card = stored_card(engine, cid)
    if not card:
        raise EngineError("that character has no stored card", status=404)
    edits: dict[str, Any] = {}
    for key in CARD_TEXT_FIELDS:
        if key in body:
            edits[key] = str(body.get(key) or "")
    if "name" in body:
        name = str(body.get("name") or "").strip()
        if not name:
            raise EngineError("the character needs a name", status=422)
        edits["name"] = name
    for key in ("alternate_greetings", "group_only_greetings"):
        if key in body and isinstance(body.get(key), list):
            edits[key] = [str(g) for g in body[key]]
    new_card = apply_card_edits(card, edits)
    name = edits.get("name") or card_fields(card)["name"]
    payload: dict[str, Any] = {"card": new_card}
    if name:
        payload["name"] = name
    engine.request("PATCH", f"/api/v1/characters/{cid}", json_body=payload)
    if "tags" in body:
        raw_tags = body["tags"]
        new_tags = (parse_tags(raw_tags) if isinstance(raw_tags, str)
                    else [str(t) for t in raw_tags])
        org = engine.request("GET", f"/api/v1/library/cards/{cid}/organisation")
        old_tags = org.get("tags") if isinstance(org, dict) else None
        if old_tags != new_tags:
            engine.request("PUT", f"/api/v1/library/cards/{cid}/tags",
                           json_body={"tags": new_tags})
    return editor_bundle(engine, cid)


def create_character(engine, body: dict) -> dict:
    name = str(body.get("name") or "").strip()
    if not name:
        raise EngineError("the character needs a name", status=422)
    card: dict[str, Any] = {"name": name}
    for key in CARD_TEXT_FIELDS:
        card[key] = str(body.get(key) or "")
    for key in ("alternate_greetings", "group_only_greetings"):
        value = body.get(key)
        card[key] = [str(g) for g in value] if isinstance(value, list) else []
    raw_tags = body.get("tags")
    tags = (parse_tags(raw_tags) if isinstance(raw_tags, str)
            else [str(t) for t in raw_tags or []])
    card["tags"] = tags
    created = engine.request("POST", "/api/v1/characters",
                             json_body={"card": card, "name": name})
    created = created if isinstance(created, dict) else {}
    if tags and created.get("id"):
        engine.request("PUT", f"/api/v1/library/cards/{created['id']}/tags",
                       json_body={"tags": tags})
    return created


def restore_version(engine, cid, version_no: int) -> dict:
    card = _version_card(engine, cid, version_no)
    if not card:
        raise EngineError(f"version {version_no} has no stored card", status=404)
    fields = card_fields(card)
    payload: dict[str, Any] = {"card": card}
    if fields["name"]:
        payload["name"] = fields["name"]
    engine.request("PATCH", f"/api/v1/characters/{cid}", json_body=payload)
    return editor_bundle(engine, cid)


def export_text(engine, cid) -> str:
    _row, card = stored_card(engine, cid)
    if not card:
        raise EngineError("that character has no stored card to export", status=404)
    return json.dumps(card, indent=2, ensure_ascii=False)
