"""Text the model can read, from mail or the web: HTML flattened, whitespace tidied, size capped, headers decoded."""

import re
from dataclasses import dataclass
from email.errors import HeaderParseError
from email.header import decode_header, make_header
from html.parser import HTMLParser

_BLOCKS = frozenset(
    {"p", "div", "br", "li", "tr", "table", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "hr"}
)
_HIDDEN = frozenset({"script", "style", "head", "title", "template"})
# what frames a web page's content: menus, banners, forms, embeds
_CHROME = _HIDDEN | {"nav", "header", "footer", "aside", "form", "button", "svg", "noscript", "iframe", "dialog"}


class _TextExtractor(HTMLParser):
    def __init__(self, hidden: frozenset[str]) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.title: list[str] = []
        self._hidden_tags = hidden
        self._hidden = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._in_title = self._in_title or tag == "title"
        if tag in self._hidden_tags:
            self._hidden += 1
        elif tag in _BLOCKS:
            self.chunks.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCKS:
            self.chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        self._in_title = self._in_title and tag != "title"
        if tag in self._hidden_tags:
            self._hidden = max(0, self._hidden - 1)
        elif tag in _BLOCKS:
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title.append(data)
        if not self._hidden:
            self.chunks.append(data)


def html_to_text(html: str) -> str:
    """The visible text of an HTML mail, one line per block; scripts, styles and the head dropped."""
    return _extract(html, _HIDDEN).text


@dataclass(frozen=True, slots=True)
class Page:
    title: str
    text: str


def page_text(html: str) -> Page:
    """A web page's title and the text of its content, one line per block: menus, banners, forms and scripts
    dropped."""
    return _extract(html, _CHROME)


def _extract(html: str, hidden: frozenset[str]) -> Page:
    extractor = _TextExtractor(hidden)
    extractor.feed(html)
    extractor.close()
    return Page(title=" ".join("".join(extractor.title).split()), text=tidy("".join(extractor.chunks)))


def tidy(text: str) -> str:
    """Spaces collapsed inside lines, at most one blank line in a row, no leading or trailing blank."""
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines()]  # NBSP included
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def cap(text: str, limit: int) -> str:
    """`text` cut to `limit` characters, saying how much was left out."""
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}\n[truncated: {len(text) - limit} more characters]"


def decode_header_value(value: str) -> str:
    """A header as people read it: RFC 2047 encoded words (`=?utf-8?q?…?=`) decoded, folding removed."""
    unfolded = " ".join(value.split())
    if "=?" not in unfolded:
        return unfolded
    try:
        return str(make_header(decode_header(unfolded)))
    except (HeaderParseError, LookupError, UnicodeDecodeError):
        return unfolded
