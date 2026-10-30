"""Single-use tokens (invitations): handed out once, only their SHA-256 digest is kept."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from nestor.core import ContractError


@dataclass(frozen=True, slots=True)
class Token:
    """`<id>.<secret>`: the id finds the record, the secret proves the bearer received the token."""

    id: str
    secret: str

    @classmethod
    def issue(cls, token_id: str) -> "Token":
        return cls(token_id, secrets.token_urlsafe(32))

    @classmethod
    def parse(cls, text: str) -> "Token":
        token_id, sep, secret = text.strip().partition(".")
        if not (sep and token_id and secret):
            raise ContractError("this is not a token")
        return cls(token_id, secret)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.secret.encode()).hexdigest()

    def matches(self, digest: str) -> bool:
        return hmac.compare_digest(self.digest, digest)

    def __str__(self) -> str:
        return f"{self.id}.{self.secret}"
