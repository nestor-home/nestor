"""A fake feed server for the feed source's tests."""

import hashlib
from xml.sax.saxutils import escape

import httpx


class FakeFeed:
    """A feed server: its entries newest first, a validator of its content (an ETag, or a Last-Modified date as
    kernel.org sends), `304` when the client already has it."""

    def __init__(self, atom: bool = False, *, dated: bool = False) -> None:
        self.atom, self.dated = atom, dated
        self.entries: list[tuple[str, str]] = []  # (id, title), newest first
        self.broken: bytes | None = None  # served instead of the feed
        self.answers: list[int] = []
        self.conditional: list[str | None] = []

    def add(self, title: str, summary: str = "<p>Les <b>nouveautés</b></p>") -> None:
        self.entries.insert(0, (f"tag:kernel.example,{len(self.entries)}", title))
        self.summary = summary

    def body(self) -> bytes:
        if self.broken is not None:
            return self.broken
        if self.atom:
            entries = "".join(
                f'<entry><id>{id}</id><title>{escape(t)}</title><link rel="alternate" href="https://kernel.example/{i}"/>'
                f'<updated>2026-11-13T08:00:00Z</updated><summary type="html">{escape(self.summary)}</summary></entry>'
                for i, (id, t) in enumerate(self.entries)
            )
            return f'<feed xmlns="http://www.w3.org/2005/Atom"><title>Kernel</title>{entries}</feed>'.encode()
        items = "".join(
            f"<item><guid>{id}</guid><title>{escape(t)}</title><link>https://kernel.example/{i}</link>"
            f"<pubDate>Fri, 13 Nov 2026 08:00:00 +0000</pubDate>"
            f"<description>{escape(self.summary)}</description></item>"
            for i, (id, t) in enumerate(self.entries)
        )
        return f'<?xml version="1.0"?><rss version="2.0"><channel><title>Kernel</title>{items}</channel></rss>'.encode()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = self.body()
        digest = hashlib.sha256(body).hexdigest()
        if self.dated:  # a date per version of the content
            header, asked = "Last-Modified", "if-modified-since"
            validator = f"Fri, 13 Nov 2026 {int(digest[:4], 16) % 24:02d}:00:00 GMT"
        else:
            header, asked, validator = "ETag", "if-none-match", f'"{digest[:12]}"'
        self.conditional.append(request.headers.get(asked))
        status = 304 if request.headers.get(asked) == validator else 200
        self.answers.append(status)
        return httpx.Response(status, content=b"" if status == 304 else body, headers={header: validator})
