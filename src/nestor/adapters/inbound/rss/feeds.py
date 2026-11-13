"""RSS 2.0, RSS 1.0 (RDF) and Atom read with the standard library's XML parser, element names matched without their
namespace. A feed that declares entities is refused, as defusedxml refuses it (external entities are never resolved
by ElementTree, and expat bounds the expansion of internal ones, but a feed has no use for either). feedparser was
not taken: it reads the same three formats for what watches need (an id, a title, a link, a summary, a date) with
far more code, and its tolerance of broken XML is not needed for the feeds people follow."""

import hashlib
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from nestor.adapters.common.text import html_to_text

ROOTS = frozenset({"rss", "feed", "RDF"})


class NotAFeed(ValueError):
    """The body is not a feed that can be read: malformed, of another format, or declaring entities."""


@dataclass(frozen=True, slots=True)
class Entry:
    id: str  # the feed's own id (guid, Atom id), else the link, else a digest of the title and summary
    title: str
    link: str
    summary: str  # as text, HTML flattened
    published: datetime | None


def parse_feed(body: bytes) -> list[Entry]:
    """The entries of a feed, in the feed's order (newest first, by convention)."""
    if b"<!ENTITY" in body:
        raise NotAFeed("the feed declares entities")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as error:
        raise NotAFeed(f"not well-formed XML ({error})") from None
    if _local(root.tag) not in ROOTS:
        raise NotAFeed(f"not an RSS or Atom feed (its root is <{_local(root.tag)}>)")
    return [_entry(e) for e in root.iter() if _local(e.tag) in ("item", "entry")]


def _entry(element: ET.Element) -> Entry:
    title = " ".join(_text(element, "title").split())
    link = _link(element)
    summary = html_to_text(_text(element, "encoded", "content", "description", "summary"))
    given = _text(element, "guid", "id").strip()
    digest = hashlib.sha256(f"{title}\n{summary}".encode()).hexdigest()[:32]
    return Entry(
        id=given or link or digest,
        title=title,
        link=link,
        summary=summary,
        published=_date(_text(element, "pubDate", "published", "updated", "date")),
    )


def _local(tag: str) -> str:
    return tag.rpartition("}")[2]


def _children(element: ET.Element, names: Iterable[str]) -> list[ET.Element]:
    wanted = tuple(names)
    found = [c for c in element if _local(c.tag) in wanted]
    return sorted(found, key=lambda c: wanted.index(_local(c.tag)))


def _text(element: ET.Element, *names: str) -> str:
    """The text of the first child named one of `names`, in that order of preference."""
    for child in _children(element, names):
        if text := "".join(child.itertext()).strip():
            return text
    return ""


def _link(element: ET.Element) -> str:
    for link in _children(element, ("link",)):
        if link.text and link.text.strip():  # RSS
            return link.text.strip()
        if link.get("href") and link.get("rel", "alternate") == "alternate":  # Atom
            return str(link.get("href"))
    return ""


def _date(text: str) -> datetime | None:
    """An RSS date (RFC 822) or an Atom one (RFC 3339), in UTC; `None` when it cannot be read."""
    if not text:
        return None
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            when = datetime.fromisoformat(text)
        except ValueError:
            return None
    return when.astimezone(UTC) if when.tzinfo else when.replace(tzinfo=UTC)
