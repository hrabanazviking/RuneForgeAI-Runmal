"""Webface security primitives (stdlib-first; Web Hall pattern).

Passwords: argon2id when the argon2 package is importable, otherwise
hashlib.scrypt. Hashes are stored self-describing so the KDF can
migrate without invalidating logins. Session tokens are stored only
as SHA-256 digests; the plaintext is shown exactly once (the cookie).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

try:
    from argon2 import PasswordHasher as _Argon2Hasher
    from argon2.exceptions import VerifyMismatchError as _Argon2Mismatch
    _HAS_ARGON2 = True
except Exception:  # pragma: no cover - argon2 may be absent
    _HAS_ARGON2 = False

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 15, 8, 1
# scrypt at these params needs ~32 MiB; OpenSSL's default maxmem is
# at/below that on some builds, so the limit is stated explicitly.
_SCRYPT_MAXMEM = 256 * 1024 * 1024


def hash_password(password: str) -> str:
    if _HAS_ARGON2:
        return "argon2id:" + _Argon2Hasher().hash(password)
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt,
                        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32,
                        maxmem=_SCRYPT_MAXMEM)
    return f"scrypt:{_SCRYPT_N}:{_SCRYPT_R}:{_SCRYPT_P}:{salt.hex()}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        if stored.startswith("argon2id:"):
            if not _HAS_ARGON2:
                return False
            try:
                return _Argon2Hasher().verify(stored[len("argon2id:"):], password)
            except _Argon2Mismatch:
                return False
        if stored.startswith("scrypt:"):
            _, n, r, p, salt_hex, dk_hex = stored.split(":")
            dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                                n=int(n), r=int(r), p=int(p), dklen=32,
                                maxmem=_SCRYPT_MAXMEM)
            return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False
    return False


def new_secret(nbytes: int = 32) -> str:
    """A fresh CSPRNG secret (session tokens)."""
    return secrets.token_urlsafe(nbytes)


def digest(secret_value: str) -> str:
    return hashlib.sha256(secret_value.encode()).hexdigest()
