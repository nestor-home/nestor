"""Episodes: each conversation summarized once it is over, its lasting facts kept, brought back to whoever took
part (and only them), recalled by date, and reread word for word."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from nestor.core import PersonId, new_id
from nestor.modules.channels import Address, Exchange, Medium
from nestor.modules.cognition.tools import ToolContext, ToolFailed
from nestor.modules.conversation import AnswerCut, AssistantTurn, Layer, TurnContext, UserTurn
from nestor.modules.household import Account, Household, Person
from nestor.modules.identity import Speaker
from nestor.modules.journal import Journal
from nestor.modules.memory import Memories, MemoryRecorded
from nestor.modules.memory.assistant import MemoryTools
from nestor.modules.memory.episodes import Consolidator, Episode, Episodes, EpisodeSummarized
from nestor.modules.memory.recall import RecallSettings
from nestor.testing.cognition import ScriptedModel
from nestor.testing.cognition.model import Reply
from nestor.testing.journal import MemoryEventLog
from nestor.testing.memory import EpisodeStoreContract, InMemoryEpisodeStore, InMemoryMemoryStore, episode

LEA = Person(id=PersonId("lea"), name="Léa", accounts=(Account.parse("telegram:7"),))
HUGO = Person(id=PersonId("hugo"), name="Hugo", accounts=(Account.parse("telegram:42"),))
CHAT = Address("telegram", "7")
START = datetime(2026, 11, 2, 18, 0, tzinfo=UTC)
SUMMARY = json.dumps(
    {
        "summary": "Léa a parlé du restaurant Da Marco pour l'anniversaire de mariage.",
        "topics": ["restaurant", "anniversaire"],
        "facts": [{"text": "Léa et Hugo fêtent leur anniversaire de mariage le 14 novembre.", "about": "household"}],
    }
)


class TestInMemoryEpisodeStore(EpisodeStoreContract):
    def store(self) -> InMemoryEpisodeStore:
        return InMemoryEpisodeStore()


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class Home:
    def __init__(self, *replies: Reply) -> None:
        self.journal = Journal(MemoryEventLog())
        self.household = Household([LEA, HUGO])
        self.memories = Memories(self.journal, InMemoryMemoryStore())
        self.episodes = Episodes(self.journal, InMemoryEpisodeStore())
        self.model = ScriptedModel(*replies)
        self.clock = Clock(START)
        self.consolidator = self.build()

    def build(self) -> Consolidator:
        return Consolidator(
            self.journal,
            self.model,
            self.memories,
            self.episodes,
            self.household,
            over_after_s=lambda address: 3600.0,
            assistant="Richie",
            language="French",
            timezone="Europe/Paris",
            tick_s=3600.0,
            clock=self.clock,
        )

    async def exchange(self, conversation: str, said: str, answer: str, *, at: datetime, person: Person = LEA) -> None:
        turn = Exchange(conversation_id=conversation, turn_id=new_id())
        await self.journal.publish(
            UserTurn(
                source="test",
                session=CHAT.session,
                address=CHAT,
                text=said,
                medium=Medium.WRITTEN,
                speaker=Speaker.account(person.id),
                exchange=turn,
                at=at,
            )
        )
        await self.journal.publish(
            AssistantTurn(source="test", session=CHAT.session, address=CHAT, text=answer, exchange=turn, at=at)
        )


async def test_a_conversation_is_summarized_once_its_silence_has_passed_and_its_facts_are_kept() -> None:
    home = Home(SUMMARY)
    async with home.consolidator:
        await home.exchange("c1", "Tu connais Da Marco ?", "Oui, rue Mercière.", at=START)
        await home.exchange("c1", "On y va pour notre anniversaire, le 14.", "Bonne idée.", at=START)
        home.clock.now = START + timedelta(minutes=30)
        assert await home.consolidator.consolidate_due() == 0, "a written conversation lasts an hour here"
        home.clock.now = START + timedelta(hours=2)
        assert await home.consolidator.consolidate_due() == 1
        assert await home.consolidator.consolidate_due() == 0, "once"

    (summarized,) = await home.journal.history(EpisodeSummarized)
    assert (summarized.conversation_id, summarized.participants, summarized.medium) == ("c1", ("lea",), Medium.WRITTEN)
    assert summarized.summary.startswith("Léa a parlé du restaurant Da Marco")
    (fact,) = await home.journal.history(MemoryRecorded)
    assert (fact.episode, fact.about, fact.learnt_in) == ("c1", None, CHAT)
    asked = home.model.requests[0]
    transcript = asked.messages[-1].content
    assert "[19:00] Léa: Tu connais Da Marco ?" in transcript and "[19:00] Richie: Oui, rue Mercière." in transcript
    assert "untrusted data" in asked.messages[0].content and "French" in asked.messages[0].content


async def test_a_restart_summarizes_what_ended_while_stopped_and_never_twice() -> None:
    home = Home(SUMMARY, SUMMARY)
    async with home.consolidator:
        await home.exchange("c1", "Tu connais Da Marco ?", "Oui.", at=START)
    home.clock.now = START + timedelta(hours=2)
    home.consolidator = home.build()
    async with home.consolidator:
        assert await home.consolidator.consolidate_due() == 1, "picked up from the journal"
    home.consolidator = home.build()
    async with home.consolidator:
        assert home.consolidator.pending() == ()
    assert len(await home.journal.history(EpisodeSummarized)) == 1


async def test_a_conversation_with_nothing_to_keep_is_summarized_but_never_brought_back() -> None:
    home = Home(json.dumps({"summary": "", "topics": [], "facts": []}))
    async with home.consolidator:
        await home.exchange("c1", "Allume le salon.", "C'est fait.", at=START)
        home.clock.now = START + timedelta(hours=2)
        await home.consolidator.consolidate_due()
    assert len(await home.journal.history(EpisodeSummarized)) == 1
    assert await home.episodes.recent(LEA.id, limit=5) == []


async def test_a_summary_that_cannot_be_written_is_tried_again_then_waits_for_the_next_start() -> None:
    home = Home("pas du JSON", "toujours pas", "encore raté", SUMMARY)
    async with home.consolidator:
        await home.exchange("c1", "Tu connais Da Marco ?", "Oui.", at=START)
        home.clock.now = START + timedelta(hours=2)
        for _ in range(4):
            await home.consolidator.consolidate_due()
        assert len(home.model.requests) == 3, "three attempts, then it waits"
        assert home.consolidator.pending() == ("c1",)
    assert await home.journal.history(EpisodeSummarized) == []


async def test_an_odd_answer_and_a_broken_memory_never_make_a_conversation_kept_twice() -> None:
    odd = json.dumps({"summary": "Da Marco.", "facts": [{"text": "Léa aime Da Marco.", "about": ["lea"]}]})
    home = Home(odd, odd)

    class Broken(InMemoryMemoryStore):
        async def put(self, memory):  # type: ignore[override]
            raise RuntimeError("disk full")

    home.consolidator.memories = Memories(home.journal, Broken())
    async with home.consolidator:
        await home.exchange("c1", "Tu connais Da Marco ?", "Oui.", at=START)
        home.clock.now = START + timedelta(hours=2)
        for _ in range(3):
            await home.consolidator.consolidate_due()
    assert len(home.model.requests) == 1 and home.consolidator.pending() == ()
    assert len(await home.journal.history(EpisodeSummarized)) == 1


async def test_a_turn_published_after_a_later_one_is_still_read() -> None:
    home = Home(SUMMARY)
    async with home.consolidator:
        await home.exchange("c1", "Tu connais Da Marco ?", "Oui.", at=START)
        home.clock.now = START + timedelta(minutes=50)
        await home.consolidator.consolidate_due()
        await home.exchange("c1", "Et pour le 14 ?", "Je réserve.", at=START + timedelta(minutes=48))
        home.clock.now = START + timedelta(minutes=70)
        assert await home.consolidator.consolidate_due() == 0, "its silence counts from the late turn"


async def test_an_answer_cut_short_is_summarized_as_it_was_heard() -> None:
    home = Home(SUMMARY)
    async with home.consolidator:
        turn = Exchange(conversation_id="c1", turn_id=new_id())
        await home.journal.publish(
            UserTurn(
                source="t",
                session=CHAT.session,
                address=CHAT,
                text="Raconte",
                medium=Medium.SPOKEN,
                exchange=turn,
                at=START,
                speaker=Speaker.unknown(),
            )
        )
        answer = AssistantTurn(
            source="t", session=CHAT.session, address=CHAT, text="Il était une fois un dragon.", exchange=turn, at=START
        )
        await home.journal.publish(answer)
        await home.journal.publish(
            AnswerCut(source="t", session=CHAT.session, answer=answer.id, heard="Il était", exchange=turn)
        )
        home.clock.now = START + timedelta(hours=2)
        assert await home.consolidator.consolidate_due() == 1
    transcript = home.model.requests[0].messages[-1].content
    assert "Richie: Il était" in transcript and "dragon" not in transcript
    assert "Someone: Raconte" in transcript, "an unknown speaker is no one of the household"


def tools(home: Home, recall: RecallSettings | None = None) -> MemoryTools:
    return MemoryTools(
        home.memories,
        home.episodes,
        home.household,
        home.journal,
        assistant="Richie",
        timezone="Europe/Paris",
        recall=recall or RecallSettings(recent_episodes=2, found_episodes=2),
    )


async def keep(home: Home, *episodes: Episode) -> None:
    for kept in episodes:
        await home.episodes.record(kept)


async def test_a_turn_carries_the_latest_conversations_of_whoever_speaks_and_older_ones_its_words_find() -> None:
    home = Home()
    days = {day: datetime(2026, 10, day, 20, tzinfo=UTC) for day in (18, 24, 28, 30)}
    await keep(
        home,
        episode("e18", "Léa a parlé du restaurant Da Marco", "lea", ended=days[18]),
        episode("e24", "Le plombier passera jeudi", "lea", ended=days[24]),
        episode("e28", "La météo du week-end", "lea", ended=days[28]),
        episode("e30", "Hugo voulait voir Dune 3", "hugo", ended=days[30]),
    )

    def turn(person: Person, said: str) -> TurnContext:
        return TurnContext(
            person=person, speaker=Speaker.account(person.id) if person else Speaker.unknown(), address=CHAT, said=said
        )

    asked = (await tools(home).context(turn(LEA, "Tu te souviens du restaurant ?")))[Layer.TURN]
    latest, older = asked.split("Older conversations")
    assert "[e28]" in latest and "[e24]" in latest and "[e18]" not in latest, "the latest two, newest first"
    assert "[e18]" in older and "Da Marco" in older and "Sunday 18 October 2026, 22:00, in writing" in older
    assert "Dune" not in asked, "never someone else's conversation"
    assert "Dune" in (await tools(home).context(turn(HUGO, "Bonjour")))[Layer.TURN]
    assert Layer.TURN not in await tools(home).context(
        TurnContext(person=None, speaker=Speaker.unknown(), address=CHAT, said="Bonjour")
    )


async def test_recall_finds_the_conversations_of_a_time_and_a_participant_can_reread_one() -> None:
    home = Home()
    await home.exchange("e24", "Le plombier vient quand ?", "Jeudi à 9 h.", at=datetime(2026, 10, 24, 18, tzinfo=UTC))
    await keep(
        home,
        episode("e18", "Le restaurant Da Marco", "lea", ended=datetime(2026, 10, 18, 20, tzinfo=UTC)),
        episode(
            "e24", "Le plombier passera jeudi", "lea", ended=datetime(2026, 10, 24, 18, 5, tzinfo=UTC), address=CHAT
        ),
    )
    found = {t.spec.name: t for t in tools(home).tools()}
    lea = ToolContext(address=CHAT, speaker=Speaker.account(LEA.id))

    week = str(await found["recall"].run({"query": "", "since": "2026-10-20", "until": "2026-10-26"}, lea))
    assert "[e24]" in week and "[e18]" not in week
    reread = await found["read_conversation"].run({"conversation_id": "e24"}, lea)
    assert reread == {"conversation": "[20:00] Léa: Le plombier vient quand ?\n[20:00] Richie: Jeudi à 9 h."}
    with pytest.raises(ToolFailed, match="no conversation e24"):
        await found["read_conversation"].run(
            {"conversation_id": "e24"}, ToolContext(address=CHAT, speaker=Speaker.account(HUGO.id))
        )
    with pytest.raises(ToolFailed, match="cannot read the date"):
        await found["recall"].run({"query": "", "since": "mardi dernier"}, lea)
