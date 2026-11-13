"""The feed source: each feed checked with its validators, new entries as items."""

from nestor.adapters.common.text import cap
from nestor.adapters.common.web import WebError
from nestor.adapters.inbound.polled import (
    Check,
    Polled,
    State,
    Watched,
)
from nestor.adapters.inbound.rss.feeds import Entry, NotAFeed, parse_feed
from nestor.modules.initiative import Incoming

KIND = "feed"
DROPPED = 500  # ids no longer listed kept per feed, should a feed list them again
EXCERPT = 1500  # characters of an entry's summary the triage reads


class FeedSource(Polled):
    brand = "rss"
    kind = KIND

    async def check(self, watched: Watched, known: State | None) -> Check:
        asked = {}
        if known and known.get("etag"):
            asked["If-None-Match"] = str(known["etag"])
        if known and known.get("modified"):
            asked["If-Modified-Since"] = str(known["modified"])
        fetched = await self._web.get(watched.url, headers=asked)
        if fetched.status == 304 and known is not None:
            return Check(state=known)
        try:
            entries = parse_feed(fetched.body)
        except NotAFeed as error:
            raise WebError(f"{fetched.url} is not a feed that can be read: {error}", transient=True) from None
        listed = [e.id for e in entries]
        seen: list[str] = list(known["seen"]) if known and isinstance(known.get("seen"), list) else []
        validators = {"etag": fetched.headers.get("etag"), "modified": fetched.headers.get("last-modified")}
        state = {**validators, "seen": _kept(seen, listed)}
        if known is None:
            return Check(state=state)
        known_ids = set(seen)
        found = []
        for entry in reversed(entries):  # oldest first
            if entry.id not in known_ids:
                known_ids.add(entry.id)
                seen = [*seen, entry.id]
                found.append((self._incoming(watched, entry), {**known, "seen": seen}))
        return Check(found=found, state=state)

    def _incoming(self, watched: Watched, entry: Entry) -> Incoming:
        published = entry.published.isoformat() if entry.published else None
        body = "\n\n".join(filter(None, (cap(entry.summary, EXCERPT), entry.link)))
        return Incoming(
            source=self.name,
            kind=KIND,
            title=entry.title or cap(entry.summary, 80) or entry.link,
            body=body,
            sender=watched.name,
            data={"feed": watched.name, "link": entry.link, "published": published},
        )


def _kept(seen: list[str], listed: list[str]) -> list[str]:
    """What the feed lists, and the last ids it no longer lists."""
    current = set(listed)
    dropped = [i for i in dict.fromkeys(seen) if i not in current][-DROPPED:]
    return [*dropped, *dict.fromkeys(listed)]
