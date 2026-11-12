"""Results too large for a turn, the same rule for every tool.

Past a budget, the whole result goes to the `BlobStore`, never to the journal: the model and the history keep its
start, its end, its size and a reference, and two tools read the rest, `read_result` and `search_result`, as a person
would page through a long document. A reference is read back only where it was given: in the same conversation's
session, or by the person it was given to.
"""

import json
import re
from collections.abc import Mapping, Sequence

from nestor.modules.cognition.model import ToolCall, ToolSpec
from nestor.modules.cognition.tools.events import ResultStored
from nestor.modules.cognition.tools.ports import ToolProvider
from nestor.modules.cognition.tools.types import Tool, ToolContext, ToolFailed, ToolOutput
from nestor.modules.journal import BlobStore, Journal

RESULT_CHARS = 8000  # about 2,000 tokens: a page of a mail, a list of a hundred items
MATCHES = 20
AROUND = 120  # characters shown around each match
MEDIA_TYPE = "text/plain; charset=utf-8"

READ = ToolSpec(
    "read_result",
    "Read part of a result that was too long to show in full, by its ref.",
    {
        "type": "object",
        "properties": {
            "ref": {"type": "string"},
            "start": {"type": "integer", "minimum": 0, "description": "the first character to read"},
            "length": {"type": "integer", "minimum": 1},
        },
        "required": ["ref"],
    },
)
SEARCH = ToolSpec(
    "search_result",
    "Find where a text appears in a result that was too long to show in full, by its ref. Gives each match with "
    "what surrounds it and where it starts, to read on from there with read_result.",
    {
        "type": "object",
        "properties": {
            "ref": {"type": "string"},
            "pattern": {"type": "string", "description": "a regular expression, ignoring case"},
        },
        "required": ["ref", "pattern"],
    },
)


READERS = frozenset({READ.name, SEARCH.name})


class Results(ToolProvider):
    name = "results"

    def __init__(self, journal: Journal, blobs: BlobStore, *, budget: int = RESULT_CHARS) -> None:
        self.journal, self.blobs, self.budget = journal, blobs, budget

    def tools(self) -> Sequence[Tool]:
        return (Tool(spec=READ, run=self._read), Tool(spec=SEARCH, run=self._search))

    async def fit(self, call: ToolCall, output: str, context: ToolContext) -> str:
        """`output` as the turn may carry it: itself within the budget (or a part read by these tools, which the budget
        already bounds), otherwise its start and end with a reference to the whole, which is stored."""
        if len(output) <= self.budget or call.name in READERS:
            return output
        ref = await self.store(output, context, call_id=call.id)
        head = self.budget * 3 // 4
        tail = self.budget - head
        # what says how to read on comes first: whatever trims this text later keeps its start
        return json.dumps(
            {
                "ref": ref,
                "size": len(output),
                "shown": f"characters 0-{head} and {len(output) - tail}-{len(output)}",
                "more": "read_result(ref, start, length) reads any part; search_result(ref, pattern) finds where",
                "start": output[:head],
                "end": output[-tail:],
            },
            ensure_ascii=False,
        )

    async def store(self, text: str, context: ToolContext, *, call_id: str | None = None) -> str:
        """Keep `text` for `read_result` and `search_result`, readable where `context` is and by its person; returns
        its reference. `call_id`: the call whose result it is; none for a text that came otherwise (a document)."""
        ref = await self.blobs.put(text.encode(), MEDIA_TYPE)
        await self.journal.publish(
            ResultStored(
                source="toolbox",
                session=context.address.session,
                ref=ref.digest,
                size=len(text),
                call_id=call_id,
                address=context.address,
                person=context.person,
            )
        )
        return ref.digest

    async def _read(self, arguments: Mapping[str, object], context: ToolContext) -> ToolOutput:
        text = await self._text(arguments, context)
        start = _int(arguments.get("start"), 0)
        end = min(len(text), start + min(_int(arguments.get("length"), self.budget), self.budget))
        return {"start": start, "end": end, "size": len(text), "text": text[start:end]}

    async def _search(self, arguments: Mapping[str, object], context: ToolContext) -> ToolOutput:
        text = await self._text(arguments, context)
        pattern = str(arguments["pattern"])
        try:
            found = re.compile(pattern, re.IGNORECASE)
        except re.error:
            found = re.compile(re.escape(pattern), re.IGNORECASE)
        matches = []
        for match in found.finditer(text):
            if len(matches) == MATCHES:
                break
            begin, end = max(0, match.start() - AROUND), min(len(text), match.end() + AROUND)
            matches.append({"at": match.start(), "text": text[begin:end]})
        return {"size": len(text), "matches": matches, "more": len(matches) == MATCHES}

    async def _text(self, arguments: Mapping[str, object], context: ToolContext) -> str:
        ref = str(arguments["ref"])
        stored = await self.journal.history(ResultStored)
        if not any(s.ref == ref and _given_to(s, context) for s in stored):
            raise ToolFailed(f"no result {ref!r} was given here")
        return (await self.blobs.get(ref)).decode()


def _given_to(stored: ResultStored, context: ToolContext) -> bool:
    return stored.address == context.address or (stored.person is not None and stored.person == context.person)


def _int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else default
