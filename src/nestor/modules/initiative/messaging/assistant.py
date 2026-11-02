"""What the central agent sees of messaging: a tool to write or speak to someone of the household, and the
questions still waiting for an answer, on both sides."""

from collections.abc import Mapping, Sequence

from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolProvider
from nestor.modules.conversation import ContextProvider, Layer, Sections, TurnContext
from nestor.modules.household import Household, Person
from nestor.modules.initiative.messaging.book import MessageBook

HOW_TO_MESSAGE = (
    'To tell someone of the household something, now or for someone else ("ask her what she wants for '
    'dinner", "send me the news on Telegram"), call message_person: it reaches them where they are (aloud in '
    "their room, or in writing), unless a channel or writing is asked for. Set expects_reply for a question: their "
    "answer comes back to you, and you pass it on with message_person to whoever asked, with answers set to the "
    "question's id. Confirm briefly once it is sent; you will hear if it could not get through."
)


class MessageTools(ToolProvider, ContextProvider):
    name = "message-tools"

    def __init__(self, book: MessageBook, household: Household) -> None:
        self.book, self.household = book, household

    def tools(self) -> Sequence[Tool]:
        people = [p.id for p in self.household.people]
        send = {
            "type": "object",
            "properties": {
                "person": {"type": "string", "enum": people, "description": "who to tell"},
                "text": {"type": "string", "description": "what to tell them, as you would tell it to them"},
                "expects_reply": {"type": "boolean", "description": "a question whose answer you will pass on"},
                "in_writing": {"type": "boolean", "description": "write it rather than say it"},
                "channel": {"type": "string", "description": "the channel asked for, e.g. telegram"},
                "answers": {"type": "string", "description": "the id of the question this message answers"},
            },
            "required": ["person", "text"],
        }
        return (
            Tool(
                spec=ToolSpec("message_person", "Tell someone of the household something, now.", send),
                run=self._send,
                risk=Risk.WRITE,
            ),
        )

    def guidance(self) -> str:
        names = ", ".join(f"{p.name} ({p.id})" for p in self.household.people)
        return f"{HOW_TO_MESSAGE}\nThe people you can reach: {names}."

    async def context(self, turn: TurnContext) -> Sections:
        if (person := turn.person) is None:
            return {}
        lines = []
        for q in self.book.open_questions():
            asker = self.household.person(q.requested_by).name if q.requested_by else "you"
            if q.to == person.id:
                lines.append(f"- [{q.message_id}] {asker} asked {person.name}: {q.text}")
            elif q.requested_by == person.id:
                lines.append(f"- [{q.message_id}] asked {self.household.person(q.to).name}: {q.text} (no answer yet)")
        return {Layer.TURN: "Questions waiting for an answer:\n" + "\n".join(lines)} if lines else {}

    async def _send(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        if context.person is None:
            raise ToolFailed("you do not know who is asking: only someone of the household can send a message")
        sender = self.household.person(context.person)
        to = self._person(str(arguments["person"]))
        if not sender.may_write_to(to.id):
            raise ToolFailed(f"{sender.name} may not have you write to {to.name}")
        channel = str(arguments["channel"]) if arguments.get("channel") else None
        if channel and to.address_on(channel) is None:
            raise ToolFailed(f"{to.name} has no account on {channel}")
        answers = str(arguments["answers"]) if arguments.get("answers") else None
        if answers and not any(q.message_id == answers for q in self.book.open_questions()):
            raise ToolFailed(f"no open question {answers}")
        message = await self.book.request(
            to.id,
            str(arguments["text"]),
            requested_by=sender.id,
            origin=context.address,
            in_writing=arguments.get("in_writing") is True,
            channel=channel,
            expects_reply=arguments.get("expects_reply") is True,
            answers=answers,
            exchange=context.exchange,
        )
        return {"message_id": message.message_id, "status": "sending"}

    def _person(self, wanted: str) -> Person:
        found = next(
            (p for p in self.household.people if wanted.casefold() in (p.id.casefold(), p.name.casefold())), None
        )
        if found is None:
            raise ToolFailed(f"no one called {wanted} in the household")
        return found
