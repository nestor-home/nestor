"""The admin password, stored as a salted scrypt hash (`scrypt$n$r$p$salt$hash`, base64 parts)."""

import base64
import hashlib
import hmac
import os

from nestor.core import ContractError

N, R, P = 2**14, 8, 1  # 16 MiB and ~50 ms per attempt: slow for guessing, fine for one login
_PREFIX = "scrypt"


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ContractError("choose an admin password of at least 10 characters")
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P)
    return "$".join([_PREFIX, str(N), str(R), str(P), _b64(salt), _b64(digest)])


def verify_password(password: str, encoded: str) -> bool:
    n, r, p, salt, expected = _parse(encoded)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=2 * 128 * r * n + 2**20)
    return hmac.compare_digest(digest, expected)


def check_hash(encoded: str) -> None:
    """Raise `ContractError` when `encoded` is not a hash made by `hash_password`."""
    _parse(encoded)


def _parse(encoded: str) -> tuple[int, int, int, bytes, bytes]:
    parts = encoded.split("$")
    try:
        if len(parts) != 6 or parts[0] != _PREFIX:
            raise ValueError
        n, r, p = (int(x) for x in parts[1:4])
        return n, r, p, base64.b64decode(parts[4], validate=True), base64.b64decode(parts[5], validate=True)
    except ValueError:
        raise ContractError("the admin password_hash is not a hash: generate it with `nestor admin-password`") from None


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()
