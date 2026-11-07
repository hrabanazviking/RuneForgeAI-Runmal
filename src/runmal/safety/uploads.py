"""Capped streaming reads for uploaded files (P-027).

An upload is untrusted input: reading it with an unbounded
``await upload.read()`` lets a single request allocate as much
memory as the client cares to send, long before any downstream
size check on the finished ``bytes`` runs. This helper reads in
fixed-size chunks instead and refuses the upload the moment the
running total passes the caller's limit, so at most roughly
``limit + chunk_size`` bytes are ever held.
"""

from __future__ import annotations

from runmal.safety.guards import SafetyError, SafetyErrorKind

__all__ = ["read_upload_capped"]


async def read_upload_capped(upload, limit, *, chunk_size=65536) -> bytes:
    """Read *upload* fully, refusing as soon as it exceeds *limit*.

    ``upload`` is any object with an async ``read(size)`` method
    returning ``bytes`` (an empty result ends the upload), such as a
    FastAPI/Starlette ``UploadFile``. Chunks of *chunk_size* bytes
    are accumulated until the upload is exhausted; if the running
    total ever exceeds *limit*, :class:`SafetyError` with kind
    ``INPUT_TOO_LARGE`` is raised immediately, without reading the
    rest of the upload. Pure: no I/O beyond the upload's own reads
    and no state beyond the bytes returned.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise SafetyError(
                SafetyErrorKind.INPUT_TOO_LARGE,
                f"upload exceeds limit of {limit} bytes",
            )
        chunks.append(chunk)
    return b"".join(chunks)
