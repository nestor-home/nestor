"""Releases of Nestor, as its release feed lists them: what changed in each, and which satellite
protocol versions the latest one speaks."""

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from nestor.core import ContractError

_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def version_key(version: str) -> tuple[int, int, int]:
    """What orders released versions (`major.minor.patch`, never a pre-release)."""
    match = _VERSION.match(version)
    if match is None:
        raise ContractError(f"version {version!r} is not major.minor.patch")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


class ChangeKind(StrEnum):
    BREAKING = "breaking"  # the data or the configuration must be redone, or a contract changed
    FEATURE = "feature"
    FIX = "fix"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Change:
    kind: ChangeKind
    text: str  # one line of the changelog, in English, plain text


@dataclass(frozen=True, slots=True)
class Release:
    version: str
    date: date
    url: str  # its notes, for people
    changes: tuple[Change, ...]

    @property
    def breaking(self) -> bool:
        return any(c.kind is ChangeKind.BREAKING for c in self.changes)


@dataclass(frozen=True, slots=True)
class Releases:
    """The feed: every release, newest first, and the satellite protocols the newest one speaks."""

    releases: tuple[Release, ...]
    protocols: frozenset[str]

    @property
    def latest(self) -> Release | None:
        return self.releases[0] if self.releases else None

    def newer_than(self, version: str) -> tuple[Release, ...]:
        """The releases after `version`, newest first."""
        running = version_key(version)
        return tuple(r for r in self.releases if version_key(r.version) > running)

    @classmethod
    def from_json(cls, data: object) -> "Releases":
        """Validate a feed (`{"protocols": [...], "releases": [{"version", "date", "url", "changes"}]}`)."""
        if not isinstance(data, dict) or not isinstance(data.get("releases"), list):
            raise ContractError("a release feed is an object with protocols and releases")
        protocols = data.get("protocols")
        if not isinstance(protocols, list) or not all(isinstance(p, str) for p in protocols):
            raise ContractError("a release feed lists the satellite protocols of its latest release")
        releases = sorted((_release(entry) for entry in data["releases"]), key=lambda r: version_key(r.version))
        return cls(tuple(reversed(releases)), frozenset(protocols))


def _release(entry: object) -> Release:
    if not isinstance(entry, dict) or {"version", "date", "url", "changes"} - entry.keys():
        raise ContractError("a release has a version, a date, a url and changes")
    version, url, changes = entry["version"], entry["url"], entry["changes"]
    if not isinstance(version, str) or not isinstance(url, str) or not isinstance(changes, list):
        raise ContractError(f"release {version!r}: version and url are text, changes a list")
    version_key(version)
    try:
        released = date.fromisoformat(entry["date"])
        listed = tuple(Change(ChangeKind(c["kind"]), c["text"]) for c in changes if isinstance(c["text"], str))
    except (KeyError, TypeError, ValueError) as error:
        raise ContractError(f"release {version}: {error}") from None
    if len(listed) != len(changes):
        raise ContractError(f"release {version}: a change's text is not text")
    return Release(version, released, url, listed)
