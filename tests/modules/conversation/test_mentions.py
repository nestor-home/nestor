"""`@name` in a message, on any channel: what it names is found in the text, loosely, logged with the turn and told to
the model; what the writer may not use, or nothing answers to, stays words."""

from collections.abc import Iterable

from nestor.core import PersonId
from nestor.modules.conversation import Mentioned, MentionKind, Mentions, MentionSource, UserTurn
from nestor.modules.household import Person
from nestor.modules.journal import Journal
from nestor.testing.cognition.model import ScriptedModel

from .conftest import MATHIS, MakeAgent, message

MATHILDE = Person(id=PersonId("mathilde"), name="Mathilde")


class Board(MentionSource):
    """Things to name, some only for Mathis, as a module offers them."""

    def __init__(self, *things: Mentioned, mine: Iterable[Mentioned] = ()) -> None:
        self.things, self.mine = things, tuple(mine)

    def mentionable(self, person: Person | None) -> Iterable[Mentioned]:
        yield from self.things
        if person is not None and person.id == MATHIS.id:
            yield from self.mine

    def instruction(self, mentioned: Mentioned) -> str:
        return f"do something with {mentioned.label}"


def thing(kind: MentionKind, handle: str, label: str = "", *aliases: str) -> Mentioned:
    return Mentioned(kind=kind, id=handle, handle=handle, label=label or handle, aliases=aliases)


CODEX = thing(MentionKind.EXECUTOR, "codex")
DINING = thing(MentionKind.ROOM, "dining_room", "Salle à manger", "Salle à manger")
GMAIL = thing(MentionKind.CONNECTION, "google", "mathis@gmail.com", "google", "mathis")
SPEAKER = thing(MentionKind.PERSON, "mathis", "Mathis", "Mathis")


def test_names_are_read_loosely_and_once_each_in_the_order_written() -> None:
    mentions = Mentions([Board(CODEX, DINING)])
    named = mentions.named("Avec @Codex, mets la musique en @salle-à-manger puis redis-le à @CODEX.", MATHIS)
    assert [m.handle for m in named] == ["codex", "dining-room"]


def test_an_address_an_unknown_name_and_a_bare_at_stay_words() -> None:
    mentions = Mentions([Board(CODEX)])
    assert mentions.named("écris à mathis@codex.fr, ou à @nobody, @ demain", MATHIS) == ()


def test_a_handle_two_things_share_goes_to_the_first_and_an_alias_never_takes_a_handle() -> None:
    other_codex = thing(MentionKind.ROOM, "codex", "Bureau de Codex")
    mentions = Mentions([Board(SPEAKER, CODEX), Board(other_codex), Board(mine=[GMAIL])])
    offered = {m.handle: m for m in mentions.available(MATHIS)}
    assert offered["codex"].kind is MentionKind.EXECUTOR and offered["codex-2"].kind is MentionKind.ROOM
    (named,) = mentions.named("@mathis", MATHIS)
    assert named.kind is MentionKind.PERSON, "Mathis the person, not the account that answers to his name too"
    assert [m.handle for m in mentions.named("@google", MATHIS)] == ["google"]


def test_what_someone_may_not_use_is_neither_offered_nor_read() -> None:
    mentions = Mentions([Board(CODEX, mine=[GMAIL])])
    assert [m.handle for m in mentions.available(MATHILDE)] == ["codex"]
    assert mentions.named("cherche dans @google", MATHILDE) == ()
    assert mentions.named("cherche dans @google", None) == (), "nobody known: nobody's account"


async def test_a_message_from_any_channel_is_logged_with_what_it_names_and_the_model_told(
    make_agent: MakeAgent, journal: Journal
) -> None:
    model = ScriptedModel("C'est parti.")
    agent = make_agent(model=model, mentions=Mentions([Board(CODEX)]))

    await agent.respond(message("utilise @codex pour mettre à jour le SDK")).collect()

    (turn,) = await journal.history(UserTurn)
    assert [m.handle for m in turn.mentions] == ["codex"]
    instructions = str(model.requests[0].messages[0].content)
    assert "- @codex: do something with codex" in instructions


async def test_a_message_naming_nothing_adds_nothing(make_agent: MakeAgent, journal: Journal) -> None:
    model = ScriptedModel("D'accord.")
    agent = make_agent(model=model, mentions=Mentions([Board(CODEX)]))
    await agent.respond(message("écris à mathis@codex.fr")).collect()
    (turn,) = await journal.history(UserTurn)
    assert turn.mentions == () and "names, with @" not in str(model.requests[0].messages[0].content)
