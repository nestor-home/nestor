"""What a post brings, kept until taken, and the watch item it becomes."""

import json
from collections.abc import Mapping
from typing import Any

from nestor.adapters.common.text import cap
from nestor.modules.initiative import Incoming

EXCERPT = 4000  # characters of a post's JSON the triage reads
EVENTS = ("x-github-event", "x-gitlab-event", "x-gitea-event", "x-event")  # what a post says it is about
TITLES = ("title", "subject", "summary", "message", "text", "event", "name", "action")


def incoming(source: str, post: Mapping[str, Any]) -> Incoming:
    payload = post.get("payload")
    said = next(
        (str(payload[k]) for k in TITLES if isinstance(payload, dict) and isinstance(payload.get(k), str | int)),
        None,
    )
    title = " · ".join(str(part) for part in (post.get("event"), said) if part) or str(post["hook"])
    return Incoming(
        source=source,
        kind=str(post["kind"]),
        title=cap(" ".join(title.split()), 200),
        body=cap(json.dumps(payload, ensure_ascii=False, indent=1), EXCERPT),
        sender=str(post["hook"]),
        data={"hook": post["hook"], "event": post.get("event")},
        id=str(post["id"]),
    )
