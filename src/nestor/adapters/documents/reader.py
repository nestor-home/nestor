"""The documents people send most, read without any service: text files as they are, PDFs by their text layer
(pypdf). A scanned PDF has no text layer: it reads as empty, and the model says it cannot read it."""

import asyncio
import codecs
import functools
import io
import logging
import re

from nestor.modules.conversation import DocumentReader

logger = logging.getLogger(__name__)

PDF = "application/pdf"
TEXT_TYPES = frozenset(
    {"application/json", "application/xml", "application/xhtml+xml", "application/x-yaml", "application/yaml"}
)
HTML = frozenset({"text/html", "application/xhtml+xml"})
_META_CHARSET = re.compile(rb"<meta[^>]+charset=[\"']?([A-Za-z0-9_.:-]+)", re.IGNORECASE)
MAX_PAGES = 500  # past a book, the rest is left out: the model is told


def is_text(media_type: str) -> bool:
    return media_type.startswith("text/") or media_type in TEXT_TYPES


def pdf_text(data: bytes) -> str | None:
    """The text of each page of a PDF, page after page; `None` when it cannot be read."""
    return _pdf(data)[0]


def pdf_pages(data: bytes) -> int | None:
    """How many pages a PDF has; `None` when it cannot be read."""
    return _pdf(data)[1]


@functools.lru_cache(maxsize=4)  # its text, then its pages, are asked of the same document: parsed once
def _pdf(data: bytes) -> tuple[str | None, int | None]:
    from pypdf import PdfReader  # slow to import: only once a PDF is read, not when Nestor starts

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            return None, None
        pages = [page.extract_text() or "" for page in reader.pages[:MAX_PAGES]]
        count = len(reader.pages)
    except Exception as error:  # a damaged file fails pypdf in many ways: none may fail the turn
        logger.info("could not read a PDF: %s", error)
        return None, None
    left = count - len(pages)
    text = "\n\n".join(f"[page {i}]\n{p.strip()}" for i, p in enumerate(pages, 1) if p.strip())
    return (f"{text}\n\n[{left} more pages not read]" if text and left > 0 else text), count


class FileReader(DocumentReader):
    def reads(self, media_type: str) -> bool:
        return _base(media_type) == PDF or is_text(_base(media_type))

    async def read(self, data: bytes, media_type: str) -> str | None:
        if _base(media_type) == PDF:
            return await asyncio.to_thread(pdf_text, data)
        return data.decode(_charset(media_type, data), errors="replace") if self.reads(media_type) else None

    async def pages(self, data: bytes, media_type: str) -> int | None:
        return await asyncio.to_thread(pdf_pages, data) if _base(media_type) == PDF else None


def _base(media_type: str) -> str:
    return media_type.split(";")[0].strip().lower()


def _charset(media_type: str, data: bytes) -> str:
    """The charset `media_type` names, else the one an HTML page declares in its head (`<meta charset>`), if Python
    knows it; UTF-8 otherwise."""
    pairs = (part.partition("=") for part in media_type.split(";")[1:])
    named = {key.strip().lower(): value.strip().strip('"') for key, _, value in pairs}.get("charset")
    if not named and _base(media_type) in HTML and (meta := _META_CHARSET.search(data[:4096])):
        named = meta.group(1).decode("ascii")
    try:
        return codecs.lookup(named or "utf-8").name
    except LookupError:
        return "utf-8"
