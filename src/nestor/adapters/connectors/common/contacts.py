"""What every contacts connector shares: its search tool as the model sees it, and a contact as it reads one."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass

from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import ToolFailed

MAX_CONTACTS = 30


def contacts_spec(name: str, contacts: str, shared: str) -> ToolSpec:
    """The search tool `name` over `contacts` ("the person's Google Contacts")."""
    return ToolSpec(
        name,
        f"Find people in {contacts} by name, email, phone or company. Returns name, emails, phones, addresses, "
        f"birthday and company of each. {shared}",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "part of a name, an address, a number"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_CONTACTS, "default": 10},
            },
            "required": ["query"],
        },
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class Contact:
    name: str
    emails: tuple[str, ...] = ()
    phones: tuple[str, ...] = ()
    addresses: tuple[str, ...] = ()
    birthday: str = ""  # YYYY-MM-DD, or MM-DD when the year is not known
    company: str = ""

    def shown(self) -> dict[str, object]:
        return {k: list(v) if isinstance(v, tuple) else v for k, v in asdict(self).items()}


def query(arguments: Mapping[str, object]) -> str:
    found = str(arguments.get("query") or "").strip()
    if not found:
        raise ToolFailed("give a name, an address or a number to look for")
    return found
