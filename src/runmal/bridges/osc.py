"""Minimal OSC 1.0 message codec (stdlib only).

Implements the message subset reference bridges need: an address
pattern plus int32 (`i`), float32 (`f`), string (`s`), blob (`b`),
and the no-payload `T`/`F`/`N` tags. Bundles are intentionally out of
scope — every bridge message here is a single message per datagram,
which is what VRChat's OSC endpoints consume.
"""

from __future__ import annotations

import struct


def _pad4(data: bytes) -> bytes:
    remainder = len(data) % 4
    return data if remainder == 0 else data + b"\x00" * (4 - remainder)


def _encode_string(text: str) -> bytes:
    return _pad4(text.encode("utf-8") + b"\x00")


def encode_message(address: str, args: tuple | list = ()) -> bytes:
    """Encode one OSC message. Args map by Python type: bool -> T/F,
    None -> N, int -> i, float -> f, str -> s, bytes -> b."""
    if not address.startswith("/"):
        raise ValueError(f"OSC address must start with '/': {address!r}")
    tags: list[str] = []
    payload = bytearray()
    for arg in args:
        if isinstance(arg, bool):  # before int: bool is an int subclass
            tags.append("T" if arg else "F")
        elif arg is None:
            tags.append("N")
        elif isinstance(arg, int):
            tags.append("i")
            payload += struct.pack(">i", arg)
        elif isinstance(arg, float):
            tags.append("f")
            payload += struct.pack(">f", arg)
        elif isinstance(arg, str):
            tags.append("s")
            payload += _encode_string(arg)
        elif isinstance(arg, (bytes, bytearray)):
            blob = bytes(arg)
            tags.append("b")
            payload += struct.pack(">i", len(blob)) + _pad4(blob)
        else:
            raise TypeError(f"unsupported OSC arg type: {type(arg).__name__}")
    return _encode_string(address) + _encode_string("," + "".join(tags)) + bytes(payload)


def _decode_string(data: bytes, offset: int) -> tuple[str, int]:
    end = data.index(b"\x00", offset)
    text = data[offset:end].decode("utf-8")
    next_offset = offset + ((end - offset) // 4 + 1) * 4
    return text, next_offset


def decode_message(data: bytes) -> tuple[str, list]:
    """Decode one OSC message datagram into (address, args)."""
    if data.startswith(b"#bundle"):
        raise ValueError("OSC bundles are not supported by this codec")
    address, offset = _decode_string(data, 0)
    tag_string, offset = _decode_string(data, offset)
    if not tag_string.startswith(","):
        raise ValueError("OSC message is missing its type tag string")
    args: list = []
    for tag in tag_string[1:]:
        if tag == "i":
            args.append(struct.unpack_from(">i", data, offset)[0])
            offset += 4
        elif tag == "f":
            args.append(struct.unpack_from(">f", data, offset)[0])
            offset += 4
        elif tag == "s":
            value, offset = _decode_string(data, offset)
            args.append(value)
        elif tag == "b":
            length = struct.unpack_from(">i", data, offset)[0]
            offset += 4
            args.append(data[offset : offset + length])
            offset += (length + 3) // 4 * 4
        elif tag == "T":
            args.append(True)
        elif tag == "F":
            args.append(False)
        elif tag == "N":
            args.append(None)
        else:
            raise ValueError(f"unsupported OSC type tag: {tag!r}")
    return address, args
