"""Generate the committed S104 card compatibility corpus. Run once; outputs are committed."""

import base64
import json
import struct
import zipfile
import zlib
from pathlib import Path

HERE = Path(__file__).parent

V1 = {
    "name": "Test V1",
    "description": "A v1 test card.",
    "personality": "Curious.",
    "scenario": "A test room.",
    "first_mes": "Hello!",
    "mes_example": "<START>Hi<END>",
}

V2 = {
    "spec": "chara_card_v2",
    "spec_version": "2.0",
    "name": "Test V2",
    "description": "A v2 test card.",
    "personality": "Playful.",
    "scenario": "A test hall.",
    "first_mes": "Hail, traveler!",
    "mes_example": "<START>Yo<END>",
    "creator_notes": "notes",
    "system_prompt": "You are Test.",
    "post_history_instructions": "Stay in character.",
    "alternate_greetings": ["Hi!", "Hey!"],
    "tags": ["test", "fixture"],
    "creator": "forge",
    "character_book": {"name": "Lore", "entries": []},
    "extensions": {"talkativeness": 0.5},
    "x_custom_unknown": "must-survive",
}

V3 = {
    "spec": "chara_card_v3",
    "spec_version": "3.0",
    "data": {
        "name": "Test V3",
        "description": "A v3 test card.",
        "personality": "Wise.",
        "scenario": "A test fjord.",
        "first_mes": "Velkominn!",
        "mes_example": "",
        "alternate_greetings": [],
        "tags": ["v3"],
        "creator": "forge",
        "character_book": {},
        "extensions": {},
        "x_custom_unknown": "must-survive-v3",
    },
}


V3_FULL = {
    "spec": "chara_card_v3",
    "spec_version": "3.0",
    "data": {
        "name": "Test V3 Full",
        "description": "A normative v3 card with assets.",
        "personality": "Thorough.",
        "scenario": "A test archive.",
        "first_mes": "Hail!",
        "mes_example": "",
        "alternate_greetings": ["Ho!"],
        "tags": ["v3", "charx"],
        "creator": "forge",
        "character_book": {
            "name": "Lore",
            "entries": [{"keys": ["fjord"], "content": "Cold water."}],
        },
        "extensions": {"talkativeness": 0.7, "avatar": "embedded://avatar.png"},
        "x_custom_unknown": "must-survive-charx",
    },
}


def png_chunk(ctype: bytes, data: bytes) -> bytes:
    chunk = struct.pack(">I", len(data)) + ctype + data
    return chunk + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)


def make_png(card: dict) -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    text = b"chara\x00" + base64.b64encode(json.dumps(card).encode())
    text_chunk = png_chunk(b"tEXt", text)
    idat = png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
    iend = png_chunk(b"IEND", b"")
    return sig + ihdr + text_chunk + idat + iend


def main() -> None:
    (HERE / "v1.json").write_text(json.dumps(V1, indent=2))
    (HERE / "v2.json").write_text(json.dumps(V2, indent=2))
    (HERE / "v3.json").write_text(json.dumps(V3, indent=2))
    (HERE / "card.png").write_bytes(make_png(V2))
    # PNG with no card chunk
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
    (HERE / "no-card.png").write_bytes(sig + ihdr + idat + png_chunk(b"IEND", b""))
    # CHARX: card.json + one asset
    with zipfile.ZipFile(HERE / "card.charx", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("card.json", json.dumps(V3))
        zf.writestr("avatar.png", b"FAKEPNGDATA")
    # Normative current-v3 CHARX: rich metadata + multiple assets (S113)
    with zipfile.ZipFile(HERE / "card_full.charx", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("card.json", json.dumps(V3_FULL))
        zf.writestr("avatar.png", b"FAKEPNGDATA-FULL")
        zf.writestr("lore/notes.txt", b"fjord notes")
    # CHARX with traversal attack
    with zipfile.ZipFile(HERE / "traversal.charx", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("card.json", json.dumps(V3))
        zf.writestr("../evil.txt", b"evil")
    # malformed JSON
    (HERE / "bad-truncated.json").write_bytes(b'{"name": "Cut off...')
    (HERE / "bad-invalid.json").write_bytes(b"this is not json at all")
    print("fixtures written")


if __name__ == "__main__":
    main()
