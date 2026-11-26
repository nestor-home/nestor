"""What Nestor is made of, as the agent reads it: each part's card (what it enables, what it needs, its page of the
documentation), and whether it is plugged in here, installed but not configured, or missing."""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from nestor.core import Component, ContractError, Health, ModelType

DOCS = "https://nestorhome.dev/docs"
_SLUG = re.compile(r"^[a-z0-9-]+(/[a-z0-9-]+)*(#[a-z0-9-]+)?$")


class Capability(StrEnum):
    """What a part gives the household."""

    CHANNEL = "channel"  # a way people reach Nestor, or Nestor reaches them
    LANGUAGE_MODEL = "language-model"
    EMBEDDING_MODEL = "embedding-model"
    IMAGE_MODEL = "image-model"
    SPEAKER_MODEL = "speaker-model"
    TRANSCRIPTION_MODEL = "transcription-model"
    SPEECH_MODEL = "speech-model"
    EXECUTOR = "executor"  # an agent long tasks are handed to
    TOOLS = "tools"  # tools the agent calls in a turn
    INBOUND = "inbound"  # a source the watches follow
    HOME = "home"  # the home system: presence, rooms, devices
    CONNECTOR = "connector"  # a service people connect their accounts to from the admin
    SATELLITE = "satellite"  # a device in a room people talk with: a package of its own, run on that device

    @classmethod
    def model(cls, model_type: ModelType) -> "Capability":
        return cls(f"{model_type.value}-model")


class Need(StrEnum):
    """What a part asks of the household before it works."""

    KEY = "key"  # an API key or a token from the service
    ACCOUNT = "account"  # an account at the service
    SERVER = "server"  # a server to run or reach (Home Assistant, a SearXNG instance, Hermes)
    PROGRAM = "program"  # a program installed next to Nestor (the `claude` or `codex` command)
    HARDWARE = "hardware"  # a device: a microphone and a speaker, a robot, a phone number
    PUBLIC_ADDRESS = "public-address"  # Nestor reachable from the internet, for the service to post to it


@dataclass(frozen=True, slots=True, kw_only=True)
class Card:
    """How a part describes itself. `summary`: one line in English, for the model, saying what it lets Nestor do;
    `docs`: its page on nestorhome.dev by slug, with the section when there is one (`tools#search`); `needs`: what the
    household provides for it to work (the optional dependencies it imports are the plugin's `requires`)."""

    summary: str
    docs: str
    needs: tuple[Need, ...] = ()

    def __post_init__(self) -> None:
        if not self.summary.strip() or "\n" in self.summary:
            raise ContractError(f"a card's summary is one line: {self.summary!r}")
        if not _SLUG.match(self.docs):
            raise ContractError(f"a card's docs is a page slug, with a section maybe (`tools#search`): {self.docs!r}")

    @property
    def page(self) -> str:
        """The page's slug, without its section."""
        return self.docs.partition("#")[0]

    @property
    def section(self) -> str | None:
        return self.docs.partition("#")[2] or None

    @property
    def url(self) -> str:
        """Its page for people, at its section."""
        page = "" if self.page == "index" else f"{self.page}/"
        return f"{DOCS}/{page}" + (f"#{self.section}" if self.section else "")


class Standing(StrEnum):
    PLUGGED = "plugged"  # in the configuration, running
    INSTALLED = "installed"  # installed, not in the configuration
    MISSING = "missing"  # what it imports is not installed, or it is a package of its own


@dataclass(frozen=True, slots=True, kw_only=True)
class Part:
    """One entry of the map: a plugin (`id` as the configuration names it) or a package of the ecosystem."""

    id: str
    capability: Capability
    card: Card
    standing: Standing
    install: str | None = None  # what installs it, when it is missing
    names: tuple[str, ...] = ()  # the configured instances, when plugged
    built: Sequence[Component] = field(default=(), compare=False, repr=False)  # those that can tell their health

    def health(self) -> Health | None:
        """The worst health of its instances now; None when none can tell."""
        known = [c.health() for c in self.built]
        order = (Health.UNAVAILABLE, Health.DEGRADED, Health.STARTED)
        return next((h for h in order if h in known), None)
