"""Write Nestor's release feed (`releases.json`) from CHANGELOG.md, for the release workflow.

    uv run python scripts/release_feed.py > releases.json

Every release of the changelog, newest first, with its changes as plain text (breaking ones first),
and the satellite protocol versions this checkout speaks: the release being published is the newest.
The admin of a running Nestor reads it (`nestor.modules.system.Releases`); nothing in it is ever run.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

from nestor.modules.satellites import PROTOCOL

CHANGELOG = Path(__file__).parent.parent / "CHANGELOG.md"
NOTES = "https://github.com/nestor-home/nestor/releases/tag/v{version}"
KINDS = {"⚠ BREAKING CHANGES": "breaking", "Features": "feature", "Bug Fixes": "fix"}

_RELEASE = re.compile(r"^## \[?(?P<version>\d+\.\d+\.\d+)\]?(?:\([^)]*\))? \((?P<date>\d{4}-\d{2}-\d{2})\)")
_LINKS = re.compile(r"(?:\s*\(\[[^\]]*\]\([^)]*\)\))+\s*$")  # the trailing ([#41](…)) ([9fcd42f](…))
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_SCOPE = re.compile(r"^\*\*([^*]+):\*\* ")


def feed(changelog: str) -> dict[str, Any]:
    releases: list[dict[str, Any]] = []
    kind = "other"
    for line in changelog.splitlines():
        if match := _RELEASE.match(line):
            releases.append({**match.groupdict(), "url": NOTES.format(**match.groupdict()), "changes": []})
            kind = "other"  # until this release's first section says otherwise
        elif line.startswith("### ") and releases:
            kind = KINDS.get(line[4:].strip(), "other")
        elif line.startswith("* ") and releases:
            text = _SCOPE.sub(r"\1: ", _LINK.sub(r"\1", _LINKS.sub("", line[2:]))).strip()
            changes = releases[-1]["changes"]
            if not any(
                c["kind"] == "breaking" and c["text"] == text for c in changes
            ):  # listed twice by release-please
                changes.append({"kind": kind, "text": text})
    return {"protocols": [PROTOCOL], "releases": releases}


if __name__ == "__main__":
    json.dump(feed(CHANGELOG.read_text()), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
