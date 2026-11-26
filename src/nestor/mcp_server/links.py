"""Short-lived links to a task's files, for an executor that shares no folder with Nestor: one to download a file sent
with the task (`read_file`), one to upload a file made for it (`attach_file`).

A link is signed with a key of this run of Nestor and names its task and the turn it was given for: it works for
`LINK_S`, only while that turn works, and an upload link once. A restart ends every link: the executor asks for another.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

LINK_S = 600


@dataclass(frozen=True, slots=True)
class Link:
    """What a link allows, while the turn `turn` of `task` works: `GET` downloads the file sent with the task whose
    digest is `target`; `PUT` uploads a file named `target`, of `media_type`, to go with what the turn brings."""

    method: str
    task: str  # its id
    turn: str  # its id
    target: str
    media_type: str = ""


class Links:
    def __init__(self, base: str) -> None:
        """`base`: the URL the links start with (`<public_url>/mcp/files`)."""
        self._base = base.rstrip("/")
        self._key = secrets.token_bytes(32)
        self._used: dict[str, float] = {}  # upload links already used, until they expire

    def download(self, task: str, turn: str, digest: str) -> str:
        return self._url(Link("GET", task, turn, digest))

    def upload(self, task: str, turn: str, name: str, media_type: str) -> str:
        return self._url(Link("PUT", task, turn, name, media_type))

    def read(self, token: str) -> Link | None:
        """The link a token is, while it is valid; `None` for anything else."""
        payload, _, signature = token.partition(".")
        if not hmac.compare_digest(self._sign(payload), signature):
            return None
        method, task, turn, target, media_type, until = json.loads(_decode(payload))
        now = time.time()
        self._used = {t: end for t, end in self._used.items() if end >= now}
        if now > until or token in self._used:
            return None
        return Link(method, task, turn, target, media_type)

    def used(self, token: str) -> None:
        """An upload link that did its work: never again."""
        self._used[token] = time.time() + LINK_S

    def _url(self, link: Link) -> str:
        until = int(time.time()) + LINK_S
        payload = _encode(json.dumps([link.method, link.task, link.turn, link.target, link.media_type, until]).encode())
        return f"{self._base}/{payload}.{self._sign(payload)}"

    def _sign(self, payload: str) -> str:
        return _encode(hmac.new(self._key, payload.encode(), hashlib.sha256).digest())


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
