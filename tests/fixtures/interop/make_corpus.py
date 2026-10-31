"""Generate the binary P-005 corpus fixture + refresh manifest hashes.

Run once (and whenever a fixture changes); outputs are committed.
The dual-chunk PNG carries BOTH a v2 ``chara`` chunk and a v3
``ccv3`` chunk — the shape real dual-published cards take — so the
corpus pins which payload wins on import (the v3 one, per the
parser's documented preference).

Manifest hashes: this script recomputes the sha256 of every file
listed in ``manifest.json`` and rewrites the manifest with them, so
the manifest can never silently drift from the bytes on disk.
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).parent

V2_PAYLOAD = {
    "spec": "chara_card_v2",
    "spec_version": "2.0",
    "name": "Dual Card (v2 payload)",
    "description": "The older payload in a dual-published PNG.",
    "first_mes": "Old greeting.",
}

V3_PAYLOAD = {
    "spec": "chara_card_v3",
    "spec_version": "3.0",
    "data": {
        "name": "Dual Card (v3 payload)",
        "description": "The newer payload in a dual-published PNG.",
        "first_mes": "New greeting.",
    },
}


def png_chunk(ctype: bytes, data: bytes) -> bytes:
    chunk = struct.pack(">I", len(data)) + ctype + data
    return chunk + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)


def make_dual_png() -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    chara = png_chunk(
        b"tEXt", b"chara\x00" + base64.b64encode(json.dumps(V2_PAYLOAD).encode())
    )
    ccv3 = png_chunk(
        b"tEXt", b"ccv3\x00" + base64.b64encode(json.dumps(V3_PAYLOAD).encode())
    )
    idat = png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
    iend = png_chunk(b"IEND", b"")
    return sig + ihdr + chara + ccv3 + idat + iend


def main() -> None:
    (HERE / "card_dual_ccv3.png").write_bytes(make_dual_png())
    manifest_path = HERE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["fixtures"]:
        data = (HERE / entry["file"]).read_bytes()
        entry["sha256"] = hashlib.sha256(data).hexdigest()
        entry["bytes"] = len(data)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"corpus refreshed: {len(manifest['fixtures'])} fixtures")


if __name__ == "__main__":
    main()
