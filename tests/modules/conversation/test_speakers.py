"""Who speaks: a satellite is a place anyone at home talks to. The account a channel authenticated, a recognised
voice, a name said, or someone of the household nobody knows; the agent asks when it matters."""

from nestor.adapters.i18n import FluentLocalizer, catalogue_dirs
from nestor.core import PersonId
from nestor.core.i18n import Locale, Message
from nestor.modules.channels import Address, Medium
from nestor.modules.cognition.model import ModelRequest, ToolCall
from nestor.modules.cognition.tools import ToolContext, ToolFailed
from nestor.modules.conversation import Conversations, SpeakerDeclared, Speakers, UserTurn
from nestor.modules.household import Account, Household, Person
from nestor.modules.identity import Identified, Speaker, Voices
from nestor.modules.journal import Journal
from nestor.testing.cognition.model import ScriptedModel
from nestor.testing.identity import MemoryVoiceprintStore, TaggedVoices, tagged

from .conftest import MATHIS, VOICE, MakeAgent, message

LEA = Person(id=PersonId("lea"), name="Léa", accounts=(Account.parse("telegram:7"),))
HOME = Household([MATHIS, LEA])
FR = Locale("fr-FR")


def speakers(journal: Journal, voices: Voices | None = None) -> Speakers:
    localizer = FluentLocalizer(catalogue_dirs(["nestor"]))
    return Speakers(journal, HOME, voices, say=lambda m: localizer.format(m, FR))


async def voices_of(journal: Journal, *people: str) -> Voices:
    found = Voices(TaggedVoices(), MemoryVoiceprintStore(), journal)
    await found.start()
    for person in people:
        enrollment = found.begin(PersonId(person), by=None, where="admin")
        for phrase in range(len(enrollment.phrases)):
            await found.take(enrollment.id, phrase, tagged(person, take=100 + phrase))
        await found.finish(enrollment.id)
    return found


async def turns(journal: Journal) -> list[Speaker]:
    return [t.speaker for t in await journal.history(UserTurn)]


async def test_on_a_satellite_whoever_speaks_is_answered_as_someone_at_home(make_agent: MakeAgent, journal) -> None:
    model = ScriptedModel("Bien sûr.")
    agent = make_agent(model=model, household=HOME, speakers=speakers(journal))
    assert await agent.respond(message("Allume la lumière", VOICE)).collect() == ("Bien sûr.",)
    assert await turns(journal) == [Speaker.unknown()]
    instructions = model.requests[0].messages[0].text
    assert "satellite of the room salon: you do not know who" in instructions
    assert "first ask who it is" in instructions, "the agent asks when the answer depends on who it is"


async def test_an_account_says_who_writes(make_agent: MakeAgent, journal) -> None:
    agent = make_agent("Salut.", household=HOME, speakers=speakers(journal))
    await agent.respond(message("Salut", sender="7")).collect()
    assert await turns(journal) == [Speaker.account(LEA.id)]


async def test_a_recognised_voice_says_who_speaks_and_is_learned_a_little_more(make_agent: MakeAgent, journal) -> None:
    voices = await voices_of(journal, "lea")
    found = speakers(journal, voices)
    agent = make_agent("Oui Léa.", household=HOME, speakers=found)
    heard = await agent.hear(tagged("lea", take=1))
    await agent.respond(message("C'est quoi mon programme ?", VOICE, heard=heard)).collect()
    await found.close()  # the learning runs in the background
    [speaker] = await turns(journal)
    assert (speaker.person, speaker.by) == (LEA.id, Identified.VOICE) and speaker.private
    assert voices.status(LEA.id).learned == 1
    assert agent.voice_wait_s is not None, "with voices, the turn waits for the voice to be heard"


async def test_a_name_said_holds_for_the_conversation_until_another_voice_speaks(
    make_agent: MakeAgent, journal
) -> None:
    voices = await voices_of(journal, "mathis")
    found = speakers(journal, voices)
    agent = make_agent(
        "C'est qui ?", ToolCall("c1", "speaker_is", {"person": "lea"}), "Merci Léa.", "D'accord.", "Oui Mathis.",
        household=HOME, speakers=found,
    )  # fmt: skip
    await agent.respond(message("Rappelle-moi le dentiste", VOICE)).collect()
    await agent.respond(message("C'est Léa", VOICE)).collect()
    await agent.respond(message("Et demain ?", VOICE)).collect()
    mathis = await voices.hear(tagged("mathis", take=3))
    await agent.respond(message("Et moi ?", VOICE, heard=mathis)).collect()
    await agent.respond(message("Et après ?", VOICE)).collect()
    said = [(s.person, s.by) for s in await turns(journal)]
    assert said == [
        (None, Identified.UNKNOWN),
        (None, Identified.UNKNOWN),
        (LEA.id, Identified.SAID),
        (MATHIS.id, Identified.VOICE),
        (None, Identified.UNKNOWN),  # Mathis's voice spoke after Léa said her name: it no longer holds
    ]
    assert [d.person for d in await journal.history(SpeakerDeclared)] == [LEA.id]


async def test_saying_who_speaks_takes_back_what_a_mistaken_voice_taught(journal) -> None:
    voices = await voices_of(journal, "mathis")
    found = speakers(journal, voices)
    heard = await voices.hear(tagged("mathis", take=4))
    turn = await Conversations(journal, ends_after_s=lambda a, m: 300).turn(VOICE, Medium.SPOKEN)
    said = await turn.said("Coucou", Medium.SPOKEN, Speaker(MATHIS.id, Identified.VOICE, heard.score))
    found.learn(heard, said)
    await found.close()
    assert voices.status(MATHIS.id).learned == 1
    [tool] = [t for t in found.tools() if t.name == "speaker_is"]
    unknown = ToolContext(address=VOICE, speaker=Speaker.unknown(), exchange=turn.exchange)
    await tool.run({"person": "lea"}, unknown)
    assert voices.status(MATHIS.id).learned == 0


async def test_an_account_needs_no_declaration(journal) -> None:
    from nestor.modules.cognition.tools import ToolContext

    [tool] = [t for t in speakers(journal).tools() if t.name == "speaker_is"]
    try:
        await tool.run(
            {"person": "lea"}, ToolContext(address=Address("telegram", "7"), speaker=Speaker.account(LEA.id))
        )
    except ToolFailed as refused:
        assert "already says who" in str(refused)
    else:
        raise AssertionError("an account cannot be overridden by a name")


async def test_a_voice_is_recorded_aloud_on_a_satellite_phrase_by_phrase(journal) -> None:
    voices = await voices_of(journal)
    found = speakers(journal, voices)
    record = {t.name: t for t in found.tools()}["record_voice"]
    started = await record.run({}, ToolContext(address=VOICE, speaker=Speaker.account(LEA.id)))
    assert isinstance(started, dict) and str(started["say_exactly"]).startswith(
        "Je t'écoute. Répète après moi : Nestor, allume"
    )

    localizer = FluentLocalizer(catalogue_dirs(["nestor"]))
    phrases = [localizer.format(Message.of(f"voice-phrase-{n}"), FR) for n in range(1, 6)]

    async def say(text: str, take: int) -> str | None:
        heard = await voices.hear(tagged("lea", take=take))
        return await found.enrolling(message(text, VOICE, heard=heard))

    answers = [await say(phrases[0], 0), await say("euh", 1)]
    assert answers[0] is not None and phrases[1] in answers[0]
    assert answers[1] is None and voices.enrolling("salon") is None, "talking about something else ends it"

    await record.run({}, ToolContext(address=VOICE, speaker=Speaker.account(LEA.id)))
    short = await found.enrolling(message(phrases[0], VOICE, heard=await voices.hear(tagged("lea", 0.5))))
    assert short is not None and short.startswith("C'était un peu court")
    said = [await say(phrase, n) for n, phrase in enumerate(phrases)]
    assert said[-1] == "C'est fait : je reconnaîtrai ta voix."
    assert (await voices.hear(tagged("lea", take=9))).person == LEA.id


async def test_without_voices_there_is_nothing_to_record_or_hear(make_agent: MakeAgent, journal) -> None:
    agent = make_agent(household=HOME, speakers=speakers(journal))
    assert [t.name for t in agent.speakers.tools()] == ["speaker_is"]
    assert await agent.hear(tagged("lea")) is None and agent.voice_wait_s is None
    assert await agent.speakers.enrolling(message("Nestor", VOICE)) is None


async def test_the_history_of_a_shared_room_says_who_said_what(make_agent: MakeAgent, journal) -> None:
    model = ScriptedModel("Ok.", "Ok.")
    voices = await voices_of(journal, "lea")
    agent = make_agent(model=model, household=HOME, speakers=speakers(journal, voices))
    await agent.respond(message("Bonjour", VOICE, heard=await voices.hear(tagged("lea", take=2)))).collect()
    await agent.respond(message("Et toi ?", VOICE)).collect()
    second: ModelRequest = model.requests[1]
    assert [m.content for m in second.messages if m.role.value == "user"] == ["[Léa] Bonjour", "Et toi ?"]
