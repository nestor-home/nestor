"""The admin API token: a random bearer token written at startup into `<data_dir>/admin.token`.

Only the local `nestor` command line reads it (the file is readable by its owner alone). It opens
the JSON API and nothing else: pages keep their session cookie and CSRF tokens.
"""

import os
import secrets
from pathlib import Path

from nestor.core import ContractError

TOKEN_FILE = "admin.token"


def token_path(data_dir: Path) -> Path:
    return data_dir / TOKEN_FILE


def issue_token(path: Path) -> str:
    """A fresh token, written with mode 600 (replacing the previous one atomically)."""
    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.tmp")
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(descriptor, 0o600)  # even if the file existed with looser rights
        os.write(descriptor, token.encode())
    finally:
        os.close(descriptor)
    os.replace(partial, path)
    return token


def read_token(path: Path) -> str:
    try:
        token = path.read_text().strip()
    except OSError:
        raise ContractError(f"no admin token at {path}: is Nestor running with an `admin` section?") from None
    if not token:
        raise ContractError(f"the admin token file {path} is empty: restart Nestor")
    return token
