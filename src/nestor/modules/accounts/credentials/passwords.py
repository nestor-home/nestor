"""Passwords, stored as salted scrypt hashes (`scrypt$n$r$p$salt$hash`, base64 parts)."""

import base64
import functools
import hashlib
import hmac
import os

from nestor.core import ContractError

N, R, P = 2**14, 8, 1  # 16 MiB and ~50 ms per attempt: slow for guessing, fine for one login
MIN_LENGTH = 10
_PREFIX = "scrypt"


def hash_password(password: str) -> str:
    if len(password) < MIN_LENGTH:
        raise ContractError(f"choose a password of at least {MIN_LENGTH} characters")
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P)
    return "$".join([_PREFIX, str(N), str(R), str(P), _b64(salt), _b64(digest)])


def verify_password(password: str, encoded: str) -> bool:
    """Whether `password` is the one `encoded` was made from; a malformed hash matches nothing."""
    parsed = _parse(encoded)
    if parsed is None:
        return False
    n, r, p, salt, expected = parsed
    digest = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=2 * 128 * r * n + 2**20)
    return hmac.compare_digest(digest, expected)


def _parse(encoded: str) -> tuple[int, int, int, bytes, bytes] | None:
    parts = encoded.split("$")
    try:
        if len(parts) != 6 or parts[0] != _PREFIX:
            return None
        n, r, p = (int(x) for x in parts[1:4])
        return n, r, p, base64.b64decode(parts[4], validate=True), base64.b64decode(parts[5], validate=True)
    except ValueError:
        return None


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@functools.cache
def decoy() -> str:
    """A hash checked when the login is unknown, so that a wrong login takes as long as a wrong password."""
    return hash_password(base64.b64encode(os.urandom(12)).decode())
