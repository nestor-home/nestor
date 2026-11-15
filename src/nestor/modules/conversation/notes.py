"""What the agent knows of how it runs right now: the notes the parts it relies on leave for it (`Component.notes`)."""

from collections.abc import Callable, Iterable

from nestor.core import Component
from nestor.modules.conversation.ports import ContextProvider, Layer, Sections, TurnContext

NOTES = (
    "How you run right now, as the parts you rely on report it. Tell the person when it bears on what they ask (a "
    "result that may be less reliable, a slower answer), briefly and not in every answer:"
)


class RunningNotes(ContextProvider):
    """The notes of every plugged part, read before each answer: a part that starts or stops writing one changes the
    instructions from the next turn on."""

    def __init__(self, components: Callable[[], Iterable[Component]]) -> None:
        self._components = components

    async def context(self, turn: TurnContext) -> Sections:
        notes = [f"- {note}" for component in self._components() for note in component.notes()]
        return {Layer.HOUSEHOLD: "\n".join((NOTES, *notes))} if notes else {}
