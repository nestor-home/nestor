"""CardDAV contacts tool: finding someone in the account's address books."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from xml.sax.saxutils import escape

from nestor.adapters.connectors.common import SHARED
from nestor.adapters.connectors.common.tools import ask
from nestor.adapters.connectors.dav import cards
from nestor.adapters.connectors.dav.dav import Dav
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, bounded

MAX_RESULTS = 30
SEARCHED = ("FN", "EMAIL", "TEL", "ORG", "NICKNAME")

SEARCH = ToolSpec(
    "dav_contacts_search",
    "Find people in the person's contacts (CardDAV: iCloud, Fastmail, Nextcloud…) by name, email, phone or company. "
    f"Returns name, emails, phones, addresses, birthday and company of each. {SHARED}",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "part of a name, an address, a number"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS, "default": 10},
        },
        "required": ["query"],
    },
)


class ContactTools:
    def __init__(self, account: str, dav: Callable[[], Awaitable[Dav]]) -> None:
        self._account, self._dav = account, dav

    def tools(self) -> Sequence[Tool]:
        return (Tool(spec=SEARCH, run=self.search, risk=Risk.READ, timeout_s=30.0),)

    async def search(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ToolFailed("give a name, an address or a number to look for")
        limit = bounded(arguments.get("max_results"), default=10, maximum=MAX_RESULTS)
        dav = await ask("the contacts server", self._dav())
        books = await ask("Listing the address books", dav.address_books())
        answers = await ask(
            "Searching the contacts", asyncio.gather(*(dav.report(b.url, _query(query, limit)) for b in books))
        )
        people = [_person(card) for answer in answers for _, data in answer for card in cards.parse(data).find("VCARD")]
        return {"account": self._account, "query": query, "contacts": people[:limit], "note": SHARED}


def _query(words: str, limit: int) -> str:
    """Cards whose name, email, phone, company or nickname contains the words, case left aside."""
    match = f'<a:text-match match-type="contains">{escape(words)}</a:text-match>'
    filters = "".join(f'<a:prop-filter name="{name}">{match}</a:prop-filter>' for name in SEARCHED)
    return (
        '<a:addressbook-query xmlns:d="DAV:" xmlns:a="urn:ietf:params:xml:ns:carddav">'
        f'<d:prop><a:address-data/></d:prop><a:filter test="anyof">{filters}</a:filter>'
        f"<a:limit><a:nresults>{limit}</a:nresults></a:limit></a:addressbook-query>"
    )


def _person(card: cards.Block) -> dict[str, object]:
    def address(line: cards.Line) -> str:  # post box; extended; street; city; region; code; country
        return ", ".join(part.strip() for part in line.parts if part.strip())

    organisation = card.first("ORG")
    birthday = card.text("BDAY").replace("-", "")
    return {
        "name": card.text("FN"),
        "emails": [line.text for line in card.all("EMAIL")],
        "phones": [line.text for line in card.all("TEL")],
        "addresses": [address(line) for line in card.all("ADR")],
        "birthday": f"{birthday[-4:-2]}-{birthday[-2:]}" if len(birthday) == 4 else _day(birthday),
        "company": organisation.parts[0] if organisation else "",
    }


def _day(value: str) -> str:
    """`YYYYMMDD` as `YYYY-MM-DD`; anything else as given."""
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if len(value) == 8 and value.isdigit() else value
