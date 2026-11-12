"""Who speaks: the account a channel authenticated, or, on a shared device, the voice that was recognised, the name
someone said, or someone of the household nobody knows.

A satellite is a place: anyone at home may talk to it. When nothing tells who speaks and the answer depends on it,
the agent asks, then records the answer (`speaker_is`); it holds for the conversation, unless a recognised voice
says otherwise. A recognised voice is learned a little more with each clear turn, and a correction takes back
what the conversation taught. None of this authorises anything: sensitive actions are confirmed in writing.
"""

import asyncio
import logging
import re
from collections.abc import Callable, Mapping, Sequence

from nestor.core import PersonId
from nestor.core.i18n import Message
from nestor.modules.channels import Address, InboundMessage
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolProvider
from nestor.modules.conversation.events import SpeakerDeclared, UserTurn
from nestor.modules.conversation.history import in_conversation
from nestor.modules.conversation.ports import ContextProvider, Sections, TurnContext
from nestor.modules.household import Household, Person
from nestor.modules.identity import Heard, Identified, Speaker, Voices
from nestor.modules.journal import Journal

logger = logging.getLogger(__name__)

HOW_TO_TELL = (
    "Anyone at home may talk to a satellite. The instructions say who is speaking when it is known. When it is not "
    'and your answer depends on who it is (their agenda, "remind me", "as usual", something about them), first ask '
    "who it is in a few words, then call speaker_is with the answer. Never ask for what anyone at home may do: "
    "lights, heating, a timer, a shared list, a question. Knowing who speaks personalises your answer; it never "
    "authorises a sensitive action."
)

RECORD_VOICE = (
    "Start recording the voice of whoever speaks, once they said who they are, so that you recognise it on every "
    "satellite. They agree to keep a voiceprint of it (never the recording), which improves as they talk, and they "
    "can erase it at any time from the admin. They then repeat five sentences aloud. Only on a satellite."
)
_LOOKBACK = 200  # turns of a session read to settle who speaks: far more than a spoken conversation holds
_WORD = re.compile(r"\w+")


class Speakers(ContextProvider, ToolProvider):
    name = "speakers"

    def __init__(
        self,
        journal: Journal,
        household: Household,
        voices: Voices | None = None,
        *,
        say: Callable[[Message], str] = str,
        wait_s: float = 0.5,
    ) -> None:
        """`say` renders what is said in the household's language (the phrases to repeat); `wait_s` is how long a
        turn waits for its voice to be recognised (computed while the speech is transcribed, usually ready before)."""
        self.journal, self.household, self.voices, self.wait_s = journal, household, voices, wait_s
        self._say = say
        self._learning: set[asyncio.Task[None]] = set()

    async def of(self, message: InboundMessage, conversation: str | None) -> Speaker:
        """Who said `message`: its account; on a shared device their voice, then what they said in the open
        `conversation`, then nobody in particular."""
        if message.sender is not None:
            person = self.household.identify(message.address.channel, message.sender)
            return Speaker.account(person.id) if person else Speaker.unknown()
        heard = message.heard
        if heard is not None and heard.person is not None and self._known(heard.person):
            return Speaker(heard.person, Identified.VOICE, round(heard.score, 3))
        declared = await self._declared(message.address, conversation)
        return Speaker(declared, Identified.SAID) if declared else Speaker.unknown()

    def learn(self, heard: Heard | None, turn: UserTurn) -> None:
        """Learn the voice of a turn it recognised, in the background: the answer does not wait for it."""
        if self.voices is None or heard is None or turn.speaker.by is not Identified.VOICE:
            return
        task = asyncio.create_task(self._learn(self.voices, heard, turn), name=f"learn voice {turn.id}")
        self._learning.add(task)
        task.add_done_callback(self._learning.discard)

    async def close(self) -> None:
        await asyncio.gather(*self._learning, return_exceptions=True)

    async def enrolling(self, message: InboundMessage) -> str | None:
        """When the room is recording someone's voice and this turn repeats the phrase asked, what to say next;
        `None` for any other turn, which also ends a recording the person walked away from."""
        voices = self.voices
        enrollment = voices.enrolling(message.address.conversation) if voices and message.sender is None else None
        if voices is None or enrollment is None or (phrase := enrollment.next) is None:
            return None
        if not _alike(message.text, self._say(Message.of(enrollment.phrases[phrase]))):
            voices.abandon(enrollment.id)
            return None
        check = voices.take_heard(enrollment.id, phrase, message.heard)
        following = enrollment.next
        if following is None:
            await voices.finish(enrollment.id)
            return self._say(Message.of("voice-enroll-done"))
        said = "voice-enroll-next" if check.problem is None else f"voice-again-{check.problem.value.replace('_', '-')}"
        return self._say(Message.of(said, phrase=self._say(Message.of(enrollment.phrases[following]))))

    def name_of(self, speaker: Speaker) -> str | None:
        return self.household.name_of(speaker.person, "") or None

    # --- what the agent sees ---------------------------------------------------------------------

    def guidance(self) -> str:
        return HOW_TO_TELL

    async def context(self, turn: TurnContext) -> Sections:
        return {}

    def tools(self) -> Sequence[Tool]:
        people = [p.id for p in self.household.people]
        said = {
            "type": "object",
            "properties": {"person": {"type": "string", "enum": people, "description": "who said they are speaking"}},
            "required": ["person"],
        }
        declare = Tool(
            spec=ToolSpec("speaker_is", "Record who is speaking on a shared device, once they said it.", said),
            run=self._declare,
            risk=Risk.READ,
        )
        if self.voices is None:
            return (declare,)
        nothing = {"type": "object", "properties": {}}
        record = Tool(spec=ToolSpec("record_voice", RECORD_VOICE, nothing), run=self._record, risk=Risk.SENSITIVE)
        return (declare, record)

    async def _declare(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        if context.speaker.by is Identified.ACCOUNT:
            raise ToolFailed("this conversation is on someone's own account: it already says who is writing")
        person = self._person(str(arguments["person"]))
        await self.journal.publish(
            SpeakerDeclared(
                source=self.name,
                session=context.address.session,
                address=context.address,
                person=person.id,
                exchange=context.exchange,
            )
        )
        if self.voices is not None and context.exchange is not None:
            turns = await self._turns(context.address, context.exchange.conversation_id)
            mistaken = {t.id for t in turns if t.speaker.by is Identified.VOICE and t.person != person.id}
            await self.voices.unlearn(mistaken)
        return {"speaker": person.name}

    async def _record(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        """Runs once the person confirmed it in writing: the room starts asking for the phrases."""
        assert self.voices is not None  # offered only with voices
        if context.person is None:
            raise ToolFailed("ask who is speaking first, then call speaker_is")
        enrollment = self.voices.begin(context.person, by=context.person, where=context.address.conversation)
        first = self._say(Message.of(enrollment.phrases[0]))
        return {"status": "recording", "say_exactly": self._say(Message.of("voice-enroll-start", phrase=first))}

    # --- helpers ---------------------------------------------------------------------------------

    async def _declared(self, address: Address, conversation: str | None) -> PersonId | None:
        """Who said they speak in this conversation, unless a voice recognised since says someone else."""
        if conversation is None:
            return None
        events = await self.journal.history(
            SpeakerDeclared, UserTurn, session=address.session, newest_first=True, limit=_LOOKBACK
        )
        recognised: set[PersonId | None] = set()  # voices recognised since, newest first
        for event in in_conversation(events, conversation):
            if isinstance(event, SpeakerDeclared):
                contradicted = recognised - {event.person}  # someone else's voice spoke since: it no longer holds
                return event.person if self._known(event.person) and not contradicted else None
            if event.speaker.by is Identified.VOICE:
                recognised.add(event.person)
        return None

    async def _turns(self, address: Address, conversation: str) -> list[UserTurn]:
        events = await self.journal.history(UserTurn, session=address.session, newest_first=True, limit=_LOOKBACK)
        return in_conversation(events, conversation)

    async def _learn(self, voices: Voices, heard: Heard, turn: UserTurn) -> None:
        try:
            await voices.learn(heard, turn=turn.id, room=turn.address.conversation)
        except Exception:  # learning is a bonus: a failure must not reach the conversation
            logger.exception("voices: could not learn from turn %s", turn.id)

    def _known(self, person: PersonId) -> bool:
        return any(p.id == person for p in self.household.people)

    def _person(self, said: str) -> Person:
        found = next((p for p in self.household.people if said in (p.id, p.name)), None)
        if found is None:
            raise ToolFailed(f"nobody named {said!r} in the household")
        return found


def _alike(said: str, phrase: str) -> bool:
    """Whether a transcript is an attempt at the phrase: it shares at least a third of its words."""
    words = {w.casefold() for w in _WORD.findall(phrase)}
    return bool(words) and len(words & {w.casefold() for w in _WORD.findall(said)}) * 3 >= len(words)
