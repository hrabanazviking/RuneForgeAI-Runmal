"""Image sniffing + pure-Python PNG thumbnails (P-023).

Stdlib only (struct, zlib) — no Pillow. ``sniff_image`` reads just
the headers of PNG/JPEG/GIF/WebP byte strings; anything it cannot
identify is ``unknown`` (with ``error`` set only when the bytes claim
a format but are malformed). ``make_png_thumbnail`` fully decodes a
PNG (bit depth 8, colour types 0/2/3/4/6, non-interlaced),
box-averages it down to ``max_dim`` and re-encodes it as RGBA PNG;
anything outside that supported set returns None.
"""

from __future__ import annotations

import struct
import zlib

from runmal.assets.models import ImageInfo

__all__ = ["is_probable_archive", "make_png_thumbnail", "sniff_image"]

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MAX_PIXELS = 25_000_000
_MAX_DECOMPRESSED = 200 * 1024 * 1024


def is_probable_archive(data: bytes) -> bool:
    """True when the bytes start with a ZIP signature (pack assets)."""
    return data.startswith(b"PK\x03\x04")


def sniff_image(data: bytes) -> ImageInfo:
    if not data:
        return ImageInfo(format="unknown", error="empty")
    if data[:8] == _PNG_SIGNATURE:
        return _sniff_png(data)
    if data[:2] == b"\xff\xd8":
        return _sniff_jpeg(data)
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return _sniff_gif(data)
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _sniff_webp(data)
    return ImageInfo(format="unknown")


def _sniff_png(data: bytes) -> ImageInfo:
    # Signature (8) + chunk length (4) + chunk type (4) + IHDR dims (8).
    if len(data) < 24:
        return ImageInfo(format="png", error="corrupt")
    (ihdr_len,) = struct.unpack(">I", data[8:12])
    if ihdr_len != 13 or data[12:16] != b"IHDR":
        return ImageInfo(format="png", error="corrupt")
    width, height = struct.unpack(">II", data[16:24])
    if width == 0 or height == 0:
        return ImageInfo(format="png", error="corrupt")
    return ImageInfo(format="png", width=width, height=height)


def _sniff_jpeg(data: bytes) -> ImageInfo:
    pos = 2  # past SOI (FF D8)
    size = len(data)
    while pos < size:
        if data[pos] != 0xFF:
            return ImageInfo(format="jpeg", error="corrupt")
        # Skip the marker prefix plus any 0xFF padding fill bytes.
        pos += 1
        while pos < size and data[pos] == 0xFF:
            pos += 1
        if pos >= size:
            return ImageInfo(format="jpeg", error="corrupt")
        marker = data[pos]
        pos += 1
        if marker == 0x00:
            # Stuffed 0xFF inside entropy data; no SOF seen yet.
            return ImageInfo(format="jpeg", error="corrupt")
        if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
            continue  # standalone markers carry no length field
        if pos + 2 > size:
            return ImageInfo(format="jpeg", error="corrupt")
        (seg_len,) = struct.unpack(">H", data[pos : pos + 2])
        if seg_len < 2:
            return ImageInfo(format="jpeg", error="corrupt")
        if marker in (0xC0, 0xC1, 0xC2):
            # SOF: length(2) precision(1) height(2) width(2).
            if pos + 7 > size:
                return ImageInfo(format="jpeg", error="corrupt")
            height, width = struct.unpack(">HH", data[pos + 3 : pos + 7])
            if width == 0 or height == 0:
                return ImageInfo(format="jpeg", error="corrupt")
            return ImageInfo(format="jpeg", width=width, height=height)
        if marker == 0xDA:
            # Start of scan with no SOF before it: no dimensions exist.
            return ImageInfo(format="jpeg", error="corrupt")
        pos += seg_len
    return ImageInfo(format="jpeg", error="corrupt")


def _sniff_gif(data: bytes) -> ImageInfo:
    if len(data) < 10:
        return ImageInfo(format="gif", error="corrupt")
    width, height = struct.unpack("<HH", data[6:10])
    if width == 0 or height == 0:
        return ImageInfo(format="gif", error="corrupt")
    return ImageInfo(format="gif", width=width, height=height)


def _sniff_webp(data: bytes) -> ImageInfo:
    if len(data) < 20:
        return ImageInfo(format="webp", error="corrupt")
    fourcc = data[12:16]
    if fourcc == b"VP8X":
        if len(data) < 30:
            return ImageInfo(format="webp", error="corrupt")
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return ImageInfo(format="webp", width=width, height=height)
    if fourcc == b"VP8 ":
        # Frame tag (3) then the 9d 01 2a start code, then 14-bit dims.
        if len(data) < 30:
            return ImageInfo(format="webp", error="corrupt")
        if data[23:26] != b"\x9d\x01\x2a":
            return ImageInfo(format="webp", error="corrupt")
        width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        if width == 0 or height == 0:
            return ImageInfo(format="webp", error="corrupt")
        return ImageInfo(format="webp", width=width, height=height)
    if fourcc == b"VP8L":
        if len(data) < 25:
            return ImageInfo(format="webp", error="corrupt")
        if data[20] != 0x2F:
            return ImageInfo(format="webp", error="corrupt")
        packed = int.from_bytes(data[21:25], "little")
        width = (packed & 0x3FFF) + 1
        height = ((packed >> 14) & 0x3FFF) + 1
        return ImageInfo(format="webp", width=width, height=height)
    return ImageInfo(format="webp", error="corrupt")


def _png_chunk(ctype: bytes, data: bytes) -> bytes:
    chunk = struct.pack(">I", len(data)) + ctype + data
    return chunk + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)


_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def _decode_png_rgba(data: bytes) -> tuple[int, int, list[bytearray]] | None:
    """Decode a supported PNG to RGBA scanlines, or None."""
    if len(data) < 8 or data[:8] != _PNG_SIGNATURE:
        return None
    pos = 8
    ihdr: bytes | None = None
    palette: bytes | None = None
    idat = bytearray()
    seen_iend = False
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        ctype = data[pos + 4 : pos + 8]
        end = pos + 8 + length
        if end > len(data):
            return None
        payload = data[pos + 8 : end]
        if ctype == b"IHDR":
            if ihdr is not None or length != 13:
                return None
            ihdr = payload
        elif ctype == b"PLTE":
            palette = payload
        elif ctype == b"IDAT":
            idat.extend(payload)
        elif ctype == b"IEND":
            seen_iend = True
            break
        pos = end + 4  # skip CRC (CRC issues are ignored)
    if ihdr is None or not seen_iend:
        return None
    width, height, bit_depth, color_type, comp, filt, interlace = struct.unpack(
        ">IIBBBBB", ihdr
    )
    if bit_depth != 8 or interlace != 0 or comp != 0 or filt != 0:
        return None
    channels = _CHANNELS.get(color_type)
    if channels is None:
        return None
    if width == 0 or height == 0 or width * height > _MAX_PIXELS:
        return None
    if color_type == 3 and not palette:
        return None
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error:
        return None
    if len(raw) > _MAX_DECOMPRESSED:
        return None
    stride = width * channels
    if len(raw) != height * (stride + 1):
        return None
    # Unfilter every scanline (bpp = channel count at bit depth 8).
    rows: list[bytearray] = []
    prev = bytearray(stride)
    offset = 0
    for _y in range(height):
        ftype = raw[offset]
        line = bytearray(raw[offset + 1 : offset + 1 + stride])
        offset += stride + 1
        if ftype == 0:
            pass
        elif ftype == 1:
            for x in range(channels, stride):
                line[x] = (line[x] + line[x - channels]) & 0xFF
        elif ftype == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 0xFF
        elif ftype == 3:
            for x in range(stride):
                left = line[x - channels] if x >= channels else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 0xFF
        elif ftype == 4:
            for x in range(stride):
                a = line[x - channels] if x >= channels else 0
                b = prev[x]
                c = prev[x - channels] if x >= channels else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pred) & 0xFF
        else:
            return None
        rows.append(line)
        prev = line
    # Expand every pixel to RGBA.
    rgba_rows: list[bytearray] = []
    for line in rows:
        out = bytearray(width * 4)
        if color_type == 6:
            out[:] = line
        elif color_type == 2:
            for x in range(width):
                s, d = x * 3, x * 4
                out[d : d + 3] = line[s : s + 3]
                out[d + 3] = 255
        elif color_type == 0:
            for x in range(width):
                v = line[x]
                d = x * 4
                out[d] = out[d + 1] = out[d + 2] = v
                out[d + 3] = 255
        elif color_type == 4:
            for x in range(width):
                s, d = x * 2, x * 4
                v = line[s]
                out[d] = out[d + 1] = out[d + 2] = v
                out[d + 3] = line[s + 1]
        elif color_type == 3:
            assert palette is not None
            for x in range(width):
                idx = line[x] * 3
                if idx + 2 >= len(palette):
                    return None
                d = x * 4
                out[d : d + 3] = palette[idx : idx + 3]
                out[d + 3] = 255
        rgba_rows.append(out)
    return width, height, rgba_rows


def make_png_thumbnail(data: bytes, max_dim: int = 256) -> bytes | None:
    """Decode *data* (PNG only), downscale to fit ``max_dim`` and
    re-encode as an RGBA PNG. Returns None for anything undecodable
    or outside the supported PNG subset. A source already inside
    ``max_dim`` keeps its native size but is still re-encoded from
    the decoded pixels, so the thumbnail is a real derived file."""
    if max_dim < 1:
        return None
    decoded = _decode_png_rgba(data)
    if decoded is None:
        return None
    width, height, rgba_rows = decoded
    scale = max_dim / max(width, height)
    if scale >= 1:
        new_w, new_h = width, height
        out_rows = rgba_rows
    else:
        new_w = max(1, round(width * scale))
        new_h = max(1, round(height * scale))
        out_rows = []
        for oy in range(new_h):
            y0 = oy * height // new_h
            y1 = max(y0 + 1, (oy + 1) * height // new_h)
            out = bytearray(new_w * 4)
            for ox in range(new_w):
                x0 = ox * width // new_w
                x1 = max(x0 + 1, (ox + 1) * width // new_w)
                count = (x1 - x0) * (y1 - y0)
                sums = [0, 0, 0, 0]
                for sy in range(y0, y1):
                    row = rgba_rows[sy]
                    for sx in range(x0, x1):
                        s = sx * 4
                        sums[0] += row[s]
                        sums[1] += row[s + 1]
                        sums[2] += row[s + 2]
                        sums[3] += row[s + 3]
                d = ox * 4
                for ch in range(4):
                    out[d + ch] = sums[ch] // count
            out_rows.append(out)
    raw = b"".join(b"\x00" + bytes(row) for row in out_rows)
    ihdr = _png_chunk(
        b"IHDR", struct.pack(">IIBBBBB", new_w, new_h, 8, 6, 0, 0, 0)
    )
    idat = _png_chunk(b"IDAT", zlib.compress(raw))
    iend = _png_chunk(b"IEND", b"")
    return _PNG_SIGNATURE + ihdr + idat + iend
