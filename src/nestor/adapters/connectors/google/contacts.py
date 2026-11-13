"""Google Contacts tool: finding someone in the person's contacts."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from nestor.adapters.connectors.common import SHARED
from nestor.adapters.connectors.common.tools import ask
from nestor.adapters.connectors.google.api import GoogleApi
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, bounded

SEARCH_URL = "https://people.googleapis.com/v1/people:searchContacts"
FIELDS = "names,emailAddresses,phoneNumbers,addresses,birthdays,organizations"
MAX_RESULTS = 30

SEARCH = ToolSpec(
    "google_contacts_search",
    "Find people in the person's Google Contacts by name, email, phone or company. Returns name, emails, phones, "
    f"addresses, birthday and company of each. {SHARED}",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "the start of a name, an address, a number"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS, "default": 10},
        },
        "required": ["query"],
    },
)


class ContactTools:
    def __init__(self, account: str, api: Callable[[], GoogleApi], known: dict[str, str]) -> None:
        """`known`: what the connector keeps about the account while it runs (the cache warmed up)."""
        self._account, self._api, self._known = account, api, known

    def tools(self) -> Sequence[Tool]:
        return (Tool(spec=SEARCH, run=self.search, risk=Risk.READ, timeout_s=20.0),)

    async def search(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ToolFailed("give a name, an address or a number to look for")
        api = self._api()
        if "contacts_warmed" not in self._known:  # Google asks for an empty search once, to fill the cache it reads
            await ask("Google Contacts", api.get(SEARCH_URL, [("query", ""), ("readMask", "names")]))
            self._known["contacts_warmed"] = "yes"
        limit = bounded(arguments.get("max_results"), default=10, maximum=MAX_RESULTS)
        found = await ask(
            "Google Contacts",
            api.get(SEARCH_URL, [("query", query), ("readMask", FIELDS), ("pageSize", str(limit))]),
        )
        people = [_person(r["person"]) for r in found.get("results", []) if isinstance(r, dict) and "person" in r]
        return {"account": self._account, "query": query, "contacts": people, "note": SHARED}


def _person(person: Mapping[str, Any]) -> dict[str, object]:
    def values(field: str, key: str) -> list[str]:
        return [str(v[key]) for v in person.get(field) or [] if isinstance(v, dict) and v.get(key)]

    birthday = next((b.get("date") for b in person.get("birthdays") or [] if isinstance(b, dict)), None) or {}
    return {
        "name": next(iter(values("names", "displayName")), ""),
        "emails": values("emailAddresses", "value"),
        "phones": values("phoneNumbers", "value"),
        "addresses": values("addresses", "formattedValue"),
        "birthday": "-".join(f"{birthday[k]:02d}" for k in ("year", "month", "day") if birthday.get(k)),
        "company": next(iter(values("organizations", "name")), ""),
    }
