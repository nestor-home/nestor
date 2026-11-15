"""What the parts the agent relies on say of how they run (`Component.notes`) reaches its instructions, in the layer
that changes now and then, from the turn after they say it."""

from collections.abc import Sequence

from nestor.core import Component
from nestor.modules.conversation import RunningNotes
from nestor.testing.cognition.model import ScriptedModel

from .conftest import MakeAgent, message


class Search(Component):
    name = "search"

    def __init__(self) -> None:
        self.said: tuple[str, ...] = ()

    def notes(self) -> Sequence[str]:
        return self.said


async def test_what_a_part_says_of_how_it_runs_is_in_the_instructions_while_it_says_it(make_agent: MakeAgent) -> None:
    search, quiet = Search(), Component()
    model = ScriptedModel("Bonjour.", "Voilà.", "Voilà.")
    agent = make_agent(model=model, context=[RunningNotes(lambda: (search, quiet))])
    for said in ((), ("Your web search goes through free tiers.",), ()):
        search.said = said
        await agent.respond(message("Cherche la marée à Saint-Malo")).collect()
    before, during, after = (r.messages[0] for r in model.requests)
    assert "free tiers" not in before.text and "How you run right now" not in before.text, "nothing said, no section"
    stable, household = during.layers
    assert "- Your web search goes through free tiers." in household and "free tiers" not in stable, "out of the cache"
    assert "free tiers" not in after.text
