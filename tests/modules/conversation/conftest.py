"""A household, a journal and an agent wired with doubles: the conversation without any provider."""

from collections.abc import Callable, Iterable

import pytest

from nestor.adapters.i18n import FluentLocalizer, catalogue_dirs
from nestor.core import PersonId
from nestor.modules.channels import Address, InboundMessage, Medium, Sender
from nestor.modules.cognition.tools import Tool, Toolbox
from nestor.modules.conversation import (
    Agent,
    AgentSettings,
    ChannelProfile,
    ContextProvider,
    Conversations,
    Persona,
)
from nestor.modules.household import Account, Household, Person
from nestor.modules.journal import Journal
from nestor.testing.cognition.model import Reply, ScriptedModel
from nestor.testing.journal import MemoryEventLog

MATHIS = Person(id=PersonId("mathis"), name="Mathis", accounts=(Account.parse("telegram:42"), Account.parse("voice:*")))
TELEGRAM = Address("telegram", "42")
VOICE = Address("voice", "salon")


def message(text: str, address: Address = TELEGRAM, sender: str = "42") -> InboundMessage:
    return InboundMessage(address=address, sender=Sender(sender), text=text)


type MakeAgent = Callable[..., Agent]


@pytest.fixture
def journal() -> Journal:
    return Journal(MemoryEventLog())


@pytest.fixture
def make_agent(journal: Journal) -> MakeAgent:
    def make(
        *replies: Reply,
        model: ScriptedModel | None = None,
        tools: Iterable[Tool] = (),
        context: Iterable[ContextProvider] = (),
        settings: AgentSettings | None = None,
        conversations: Conversations | None = None,
    ) -> Agent:
        return Agent(
            model=model or ScriptedModel(*replies),
            persona=Persona(name="Richie", character="Tu es Richie, le robot de la maison."),
            journal=journal,
            household=Household([MATHIS]),
            toolbox=Toolbox(journal, tools),
            localizer=FluentLocalizer(catalogue_dirs(["nestor"])),
            channels={"voice": ChannelProfile(Medium.SPOKEN, style="Use [laughs] sparingly.")},
            context=context,
            settings=settings,
            conversations=conversations,
        )

    return make
