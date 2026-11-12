"""Results too long for a turn: the model keeps the start and the end, and reads the rest when it needs it."""

import json
from collections.abc import Mapping

import pytest

from nestor.core import PersonId
from nestor.modules.channels import Address
from nestor.modules.cognition.model import ToolCall, ToolSpec
from nestor.modules.cognition.tools import Results, ResultStored, Tool, Toolbox, ToolCompleted, ToolContext
from nestor.modules.identity import Speaker
from nestor.modules.journal import Journal
from nestor.testing.journal import MemoryBlobStore, MemoryEventLog

TELEGRAM = Address("telegram", "42")
MAIL = "\n".join(f"Ligne {n} du mail." for n in range(2000)) + "\nCode de suivi : XK-4471.\nFin du mail."
MATHIS = ToolContext(address=TELEGRAM, speaker=Speaker.account(PersonId("mathis")))


async def read_mail(arguments: Mapping[str, object], context: ToolContext) -> str:
    return MAIL


@pytest.fixture
def journal() -> Journal:
    return Journal(MemoryEventLog())


@pytest.fixture
def toolbox(journal: Journal) -> Toolbox:
    tool = Tool(spec=ToolSpec("read_mail", "Read a mail"), run=read_mail)
    return Toolbox(journal, [tool], results=Results(journal, MemoryBlobStore(), budget=2000))


async def test_a_long_result_keeps_its_start_and_end_and_never_enters_the_journal_whole(
    toolbox: Toolbox, journal: Journal
) -> None:
    shown = json.loads((await toolbox.call(ToolCall("c1", "read_mail"), MATHIS)).output)

    assert shown["size"] == len(MAIL)
    assert MAIL.startswith(shown["start"]) and MAIL.endswith(shown["end"])
    assert len(shown["start"]) + len(shown["end"]) == 2000
    [completed] = await journal.history(ToolCompleted)
    assert len(completed.output) < 3000 and "XK-4471" in completed.output  # the end is kept


async def test_the_model_finds_and_reads_the_rest(toolbox: Toolbox) -> None:
    ref = json.loads((await toolbox.call(ToolCall("c1", "read_mail"), MATHIS)).output)["ref"]

    search = ToolCall("c2", "search_result", {"ref": ref, "pattern": "ligne 1000 "})
    found = json.loads((await toolbox.call(search, MATHIS)).output)
    [match] = found["matches"]
    part = ToolCall("c3", "read_result", {"ref": ref, "start": match["at"], "length": 40})
    read = json.loads((await toolbox.call(part, MATHIS)).output)

    assert read["text"] == MAIL[match["at"] : match["at"] + 40]
    assert read["text"].startswith("Ligne 1000 du mail.")


async def test_a_search_with_a_broken_pattern_looks_for_the_text_itself(toolbox: Toolbox) -> None:
    ref = json.loads((await toolbox.call(ToolCall("c1", "read_mail"), MATHIS)).output)["ref"]
    broken = ToolCall("c2", "search_result", {"ref": ref, "pattern": "("})
    found = json.loads((await toolbox.call(broken, MATHIS)).output)
    assert found["matches"] == []


async def test_a_read_is_never_longer_than_the_budget(toolbox: Toolbox) -> None:
    ref = json.loads((await toolbox.call(ToolCall("c1", "read_mail"), MATHIS)).output)["ref"]
    read = json.loads((await toolbox.call(ToolCall("c2", "read_result", {"ref": ref, "length": 10**6}), MATHIS)).output)
    assert (read["start"], read["end"]) == (0, 2000)


async def test_a_result_is_read_back_only_where_it_was_given(toolbox: Toolbox, journal: Journal) -> None:
    ref = json.loads((await toolbox.call(ToolCall("c1", "read_mail"), MATHIS)).output)["ref"]
    elsewhere = ToolContext(address=Address("voice", "salon"))  # someone nobody recognised, in another room
    same_person = ToolContext(address=Address("voice", "salon"), speaker=Speaker.account(PersonId("mathis")))

    refused = json.loads((await toolbox.call(ToolCall("c2", "read_result", {"ref": ref}), elsewhere)).output)
    allowed = json.loads((await toolbox.call(ToolCall("c3", "read_result", {"ref": ref}), same_person)).output)

    assert "no result" in refused["error"]
    assert allowed["text"] == MAIL[:2000]
    [stored] = await journal.history(ResultStored)
    assert (stored.ref, stored.person, stored.address) == (ref, "mathis", TELEGRAM)


async def test_a_short_result_is_left_as_it_is(journal: Journal) -> None:
    async def short(arguments: Mapping[str, object], context: ToolContext) -> str:
        return "Rien de neuf."

    toolbox = Toolbox(
        journal, [Tool(spec=ToolSpec("news", "News"), run=short)], results=Results(journal, MemoryBlobStore())
    )
    assert (await toolbox.call(ToolCall("c1", "news"), MATHIS)).output == "Rien de neuf."
    assert await journal.history(ResultStored) == []
