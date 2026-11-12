"""The documents people send most, read without any service: text files as they are, PDFs by their text layer
(pypdf). A scanned PDF has no text layer: it reads as empty, and the model says it cannot read it."""

import asyncio
import codecs
import io
import logging

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from nestor.modules.conversation import DocumentReader

logger = logging.getLogger(__name__)

PDF = "application/pdf"
TEXT_TYPES = frozenset({"application/json", "application/xml", "application/x-yaml", "application/yaml"})
MAX_PAGES = 500  # past a book, the rest is left out: the model is told


def is_text(media_type: str) -> bool:
    return media_type.startswith("text/") or media_type in TEXT_TYPES


def pdf_text(data: bytes) -> str | None:
    """The text of each page of a PDF, page after page; `None` when it cannot be read."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            return None
        pages = [page.extract_text() or "" for page in reader.pages[:MAX_PAGES]]
        left = len(reader.pages) - len(pages)
    except (PyPdfError, ValueError, KeyError, TypeError, OSError) as error:
        logger.info("could not read a PDF: %s", error)
        return None
    text = "\n\n".join(f"[page {i}]\n{p.strip()}" for i, p in enumerate(pages, 1) if p.strip())
    return f"{text}\n\n[{left} more pages not read]" if text and left > 0 else text


class FileReader(DocumentReader):
    def reads(self, media_type: str) -> bool:
        return _base(media_type) == PDF or is_text(_base(media_type))

    async def read(self, data: bytes, media_type: str) -> str | None:
        if _base(media_type) == PDF:
            return await asyncio.to_thread(pdf_text, data)
        return data.decode(_charset(media_type), errors="replace") if self.reads(media_type) else None


def _base(media_type: str) -> str:
    return media_type.split(";")[0].strip().lower()


def _charset(media_type: str) -> str:
    """The charset `media_type` names, if Python knows it; UTF-8 otherwise."""
    pairs = (part.partition("=") for part in media_type.split(";")[1:])
    params = {key.strip().lower(): value.strip().strip('"') for key, _, value in pairs}
    try:
        return codecs.lookup(params.get("charset") or "utf-8").name
    except LookupError:
        return "utf-8"
