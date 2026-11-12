"""A household, a journal and an agent wired with doubles: the conversation without any provider."""

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime

import pytest

from nestor.adapters.i18n import FluentLocalizer, catalogue_dirs
from nestor.core import PersonId, utc_now
from nestor.core.i18n import Locale
from nestor.modules.channels import Address, InboundMessage, Medium, Sender
from nestor.modules.cognition.tools import Tool, Toolbox
from nestor.modules.conversation import (
    Agent,
    AgentSettings,
    Attachments,
    ChannelProfile,
    ContextProvider,
    ModelChoice,
    Persona,
    Speakers,
)
from nestor.modules.household import Account, Household, Person
from nestor.modules.identity import Heard
from nestor.modules.journal import Journal
from nestor.testing.cognition.model import Reply, ScriptedModel
from nestor.testing.journal import MemoryBlobStore, MemoryEventLog

MATHIS = Person(id=PersonId("mathis"), name="Mathis", accounts=(Account.parse("telegram:42"),))
TELEGRAM = Address("telegram", "42")
VOICE = Address("voice", "salon")


def message(
    text: str, address: Address = TELEGRAM, sender: str = "42", medium: Medium | None = None, heard: Heard | None = None
) -> InboundMessage:
    """A turn, said on the voice channel (a shared device: whoever is in the room) unless `medium` says otherwise,
    typed elsewhere from an account."""
    shared = address.channel == "voice"
    said = Medium.SPOKEN if shared else Medium.WRITTEN
    return InboundMessage(
        address=address, sender=None if shared else Sender(sender), text=text, medium=medium or said, heard=heard
    )


type MakeAgent = Callable[..., Agent]


@pytest.fixture
def journal() -> Journal:
    return Journal(MemoryEventLog())


@pytest.fixture
def make_agent(journal: Journal) -> MakeAgent:
    def make(
        *replies: Reply,
        model: ScriptedModel | None = None,
        models: ModelChoice | None = None,
        tools: Iterable[Tool] = (),
        context: Iterable[ContextProvider] = (),
        settings: AgentSettings | None = None,
        clock: Callable[[], datetime] = utc_now,
        channels: Mapping[str, ChannelProfile] | None = None,
        speakers: Speakers | None = None,
        household: Household | None = None,
        attachments: Attachments | None = None,
    ) -> Agent:
        return Agent(
            models=models or ModelChoice.single(model or ScriptedModel(*replies)),
            persona=Persona(
                name="Richie",
                character="Tu es Richie, le robot de la maison.",
                locale=Locale("fr-FR"),
                language="French",
                timezone="Europe/Paris",
            ),
            journal=journal,
            household=household or Household([MATHIS]),
            toolbox=Toolbox(journal, tools, [speakers] if speakers else ()),
            localizer=FluentLocalizer(catalogue_dirs(["nestor"])),
            channels=channels or {"voice": ChannelProfile(style="Use [laughs] sparingly.")},
            context=context,
            settings=settings,
            clock=clock,
            speakers=speakers,
            attachments=attachments or Attachments(MemoryBlobStore()),
        )

    return make
