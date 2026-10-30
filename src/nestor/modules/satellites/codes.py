"""The two pairing codes of `nestor.satellite/2`, and the pairing URI that carries an enrollment code.

Device code: 6 decimal digits the device shows or says, typed in the admin. Digits read well aloud.

Enrollment code: 8 symbols of Crockford's base32 (40 bits), made in the admin and given to the device,
shown grouped by four (`K7QF-2M9X`). Reading it back forgives case, dashes, spaces, and the letters
Crockford maps to digits (O → 0, I and L → 1). Only its SHA-256 is kept.

Pairing URI: `nestor+http://nestor.local:7860/?code=K7QF2M9X`: the core's base URL, prefixed with
`nestor+` so a scanner or a configuration loader knows what it holds, and the enrollment code.
"""

import hashlib
import re
import secrets
import urllib.parse

from nestor.core import ContractError

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford's base32: no I, L, O, U
ENROLLMENT_LENGTH = 8
DEVICE_CODE = re.compile(r"^\d{6}$")
URI_SCHEMES = {"nestor+http": "http", "nestor+https": "https"}
_ALIASES = str.maketrans({"O": "0", "I": "1", "L": "1"})
_IGNORED = re.compile(r"[\s-]")


def new_device_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def new_enrollment_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(ENROLLMENT_LENGTH))


def normalize_enrollment_code(text: str) -> str | None:
    """The canonical form of a typed or scanned enrollment code (`k7qf-2m9x` → `K7QF2M9X`); `None` when
    it cannot be one."""
    code = _IGNORED.sub("", text).upper().translate(_ALIASES)
    if len(code) != ENROLLMENT_LENGTH or any(c not in ALPHABET for c in code):
        return None
    return code


def group(code: str) -> str:
    """How an enrollment code is shown: `K7QF-2M9X`."""
    return f"{code[:4]}-{code[4:]}"


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def pairing_uri(core_url: str, code: str) -> str:
    """`http://nestor.local:7860` and `K7QF2M9X` → `nestor+http://nestor.local:7860/?code=K7QF2M9X`."""
    parts = urllib.parse.urlsplit(core_url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ContractError(f"the core's address {core_url!r} must be an http(s) URL")
    path = parts.path if parts.path.endswith("/") else parts.path + "/"
    return urllib.parse.urlunsplit((f"nestor+{parts.scheme}", parts.netloc, path, f"code={code}", ""))


def parse_pairing_uri(uri: str) -> tuple[str, str]:
    """The core's base URL and the normalised enrollment code a pairing URI carries."""
    parts = urllib.parse.urlsplit(uri.strip())
    scheme = URI_SCHEMES.get(parts.scheme.lower())
    codes = urllib.parse.parse_qs(parts.query).get("code", [])
    code = normalize_enrollment_code(codes[0]) if len(codes) == 1 else None
    if scheme is None or not parts.netloc or code is None:
        raise ContractError("a pairing URI looks like nestor+http://host:port/?code=K7QF2M9X")
    return urllib.parse.urlunsplit((scheme, parts.netloc, parts.path.rstrip("/"), "", "")), code
