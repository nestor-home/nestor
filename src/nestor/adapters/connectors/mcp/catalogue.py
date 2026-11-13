"""Well-known remote MCP servers, published by the services themselves, and how an account on any server is named.

Every address here leads, from the 401 it answers, to its authorization server. GitHub and Asana register no client
on the spot: the person brings their own OAuth app, or a token (GitHub). Hugging Face answers without one.
"""

import re
import urllib.parse
from collections.abc import Iterable

from nestor.modules.connectors import Preset

PRESETS = (
    Preset(name="GitHub", brand="github", values={"url": "https://api.githubcopilot.com/mcp/"}),
    Preset(name="Linear", brand="linear", values={"url": "https://mcp.linear.app/mcp"}),
    Preset(name="Notion", brand="notion", values={"url": "https://mcp.notion.com/mcp"}),
    Preset(name="Todoist", brand="todoist", values={"url": "https://ai.todoist.net/mcp"}),
    Preset(name="Atlassian", brand="atlassian", values={"url": "https://mcp.atlassian.com/v1/mcp"}),
    Preset(name="Asana", brand="asana", values={"url": "https://mcp.asana.com/v2/mcp"}),
    Preset(name="Sentry", brand="sentry", values={"url": "https://mcp.sentry.dev/mcp"}),
    Preset(name="Cloudflare", brand="cloudflare", values={"url": "https://bindings.mcp.cloudflare.com/mcp"}),
    Preset(name="Stripe", brand="stripe", values={"url": "https://mcp.stripe.com"}),
    Preset(name="Vercel", brand="vercel", values={"url": "https://mcp.vercel.com"}),
    Preset(name="Canva", brand="canva", values={"url": "https://mcp.canva.com/mcp"}),
    Preset(name="Hugging Face", brand="huggingface", values={"url": "https://huggingface.co/mcp"}),
)

_GENERIC_LABELS = frozenset({"mcp", "api", "www", "ai", "app"})
_NOT_A_NAME = re.compile(r"[^a-z0-9]+")


def host(url: str) -> str:
    """The server's host, with its port when one is given."""
    parts = urllib.parse.urlsplit(url)
    name = (parts.hostname or "").lower()
    return f"{name}:{parts.port}" if parts.port else name


def account(who: str, url: str, taken: Iterable[str] = ()) -> str:
    """What the person recognises of an account on a server: whose it is and where (`mathis@mcp.linear.app`). Another
    account of theirs on the same server is numbered (`mathis-2@mcp.linear.app`) so that each is told apart."""
    label, n = f"{who}@{host(url)}", 1
    while label in taken:
        n += 1
        label = f"{who}-{n}@{host(url)}"
    return label


def known(account_label: str) -> Preset | None:
    """The well-known service of an account's server, if it is one."""
    where = account_label.rpartition("@")[2]
    return next((p for p in PRESETS if host(p.values["url"]) == where), None)


def service_name(account_label: str) -> str:
    """How a message names the server with `@`: the service's own name when it is well known (`linear`), else the
    telling part of its host (`tickets` for `mcp.tickets.example`)."""
    preset = known(account_label)
    if preset is not None:
        return _NOT_A_NAME.sub("-", preset.name.lower()).strip("-")
    labels = account_label.rpartition("@")[2].partition(":")[0].split(".")
    telling = [label for label in labels[:-1] if label not in _GENERIC_LABELS] or labels
    return _NOT_A_NAME.sub("-", telling[0].lower()).strip("-") or "mcp"
