"""A hook: its name, the kind of its posts, its secret, and how a post proves it holds that secret."""

import hmac

from fastapi import Request
from pydantic import Field

from nestor.adapters.common.http import signature
from nestor.runtime.plugins import AdapterSettings, RequiredSecret


class Hook(AdapterSettings):
    name: str = Field(pattern=r"^[A-Za-z0-9_-]+$")  # its address: /hooks/<name>
    kind: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")  # what its posts are, for watches: "github", "washing-machine"
    secret: RequiredSecret


SIGNATURES = ("x-hub-signature-256", "x-nestor-signature")


def proven(secret: str, request: Request, body: bytes) -> bool:
    """Whether the post holds the hook's secret: its body signed with it, else the secret as a bearer token."""
    signed = next((request.headers[h] for h in SIGNATURES if h in request.headers), None)
    if signed is not None:
        return hmac.compare_digest(signed.encode(), signature(secret, body).encode())
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return scheme.lower() == "bearer" and hmac.compare_digest(token.strip().encode(), secret.encode())
