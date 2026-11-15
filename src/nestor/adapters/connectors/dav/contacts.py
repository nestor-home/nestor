"""CardDAV contacts tool: finding someone in the account's address books."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from xml.sax.saxutils import escape

from nestor.adapters.connectors.common import SHARED
from nestor.adapters.connectors.common.contacts import MAX_CONTACTS, NO_QUERY, Contact, contacts_spec
from nestor.adapters.connectors.common.tools import ask, required
from nestor.adapters.connectors.dav import cards
from nestor.adapters.connectors.dav.dav import Dav
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, bounded

SEARCHED = ("FN", "EMAIL", "TEL", "ORG", "NICKNAME")

SEARCH = contacts_spec("dav_contacts_search", "the person's contacts (CardDAV: iCloud, Fastmail, Nextcloud…)", SHARED)


class ContactTools:
    def __init__(self, account: str, dav: Callable[[], Awaitable[Dav]]) -> None:
        self._account, self._dav = account, dav

    def tools(self) -> Sequence[Tool]:
        return (Tool(spec=SEARCH, run=self.search, risk=Risk.READ, timeout_s=30.0),)

    async def search(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        words = required(arguments, "query", NO_QUERY)
        limit = bounded(arguments.get("max_results"), default=10, maximum=MAX_CONTACTS)
        dav = await ask("the contacts server", self._dav())
        books = await ask("Listing the address books", dav.address_books())
        answers = await ask(
            "Searching the contacts", asyncio.gather(*(dav.report(b.url, _query(words, limit)) for b in books))
        )
        people = [_person(card) for answer in answers for _, data in answer for card in cards.parse(data).find("VCARD")]
        return {
            "account": self._account,
            "query": words,
            "contacts": [p.shown() for p in people[:limit]],
            "note": SHARED,
        }


def _query(words: str, limit: int) -> str:
    """Cards whose name, email, phone, company or nickname contains the words, case left aside."""
    match = f'<a:text-match match-type="contains">{escape(words)}</a:text-match>'
    filters = "".join(f'<a:prop-filter name="{name}">{match}</a:prop-filter>' for name in SEARCHED)
    return (
        '<a:addressbook-query xmlns:d="DAV:" xmlns:a="urn:ietf:params:xml:ns:carddav">'
        f'<d:prop><a:address-data/></d:prop><a:filter test="anyof">{filters}</a:filter>'
        f"<a:limit><a:nresults>{limit}</a:nresults></a:limit></a:addressbook-query>"
    )


def _person(card: cards.Block) -> Contact:
    def address(line: cards.Line) -> str:  # post box; extended; street; city; region; code; country
        return ", ".join(part.strip() for part in line.parts if part.strip())

    organisation = card.first("ORG")
    birthday = card.text("BDAY").replace("-", "")
    return Contact(
        name=card.text("FN"),
        emails=tuple(line.text for line in card.all("EMAIL")),
        phones=tuple(line.text for line in card.all("TEL")),
        addresses=tuple(address(line) for line in card.all("ADR")),
        birthday=f"{birthday[-4:-2]}-{birthday[-2:]}" if len(birthday) == 4 else _day(birthday),
        company=organisation.parts[0] if organisation else "",
    )


def _day(value: str) -> str:
    """`YYYYMMDD` as `YYYY-MM-DD`; anything else as given."""
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if len(value) == 8 and value.isdigit() else value
