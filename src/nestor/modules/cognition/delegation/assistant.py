"""What the central agent sees of delegation: its tools to start, direct, stop, read and put away tasks, and a section
of its instructions. A person reaches only their own tasks."""

import posixpath
from collections.abc import Iterable, Mapping, Sequence

from nestor.core import ContractError
from nestor.modules.channels import AttachmentKind, plain_name
from nestor.modules.cognition.delegation.service import Directed, Task, TaskManager
from nestor.modules.cognition.delegation.types import Notify, TaskState, TurnStatus
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import TITLE, Risk, Tool, ToolContext, ToolFailed, ToolProvider, titled
from nestor.modules.conversation import (
    ContextProvider,
    Layer,
    Mentioned,
    MentionKind,
    MentionSource,
    Sections,
    TurnContext,
    UserTurn,
)
from nestor.modules.conversation.history import in_conversation
from nestor.modules.household import Person
from nestor.modules.journal import FileRef

HOW_TO_DELEGATE = """You never do long work yourself: you talk, and you hand over to an executor anything that needs \
acting, searching or computing beyond your own tools. A task is a thread with its executor that lasts: it keeps what \
was done, and the person can come back to it any day.
- start_task opens a task with a precise, verifiable instruction; then say in a very short sentence that it started.
- continue_task gives one of their tasks an instruction: while it works, it reorients it at once; once its turn ended, \
it goes on in the same thread (a follow-up, a correction, a retry). "Continue the website update" continues that task: \
never start a new task for something an existing one is about.
- A task that needs them ends its turn with a question: ask them, and pass their answer with continue_task, with the \
files they sent for it.
- A task receives the files you name in `files` from this conversation (voice messages aside), by default those of \
the message you answer: a file you cannot open yourself, an executor can.
- list_tasks says how their tasks stand, read_task what one did; stop_task stops the turn that works (the task stays); \
rename_task and archive_task put them in order.
- If they want the result in writing (they are leaving, "write me when it's done"), set notify to "message"."""

NO_EXECUTOR = """No executor is plugged in: you cannot carry out long tasks, search or act beyond your own tools. \
If asked, say so simply."""

TASK = {"type": "string", "description": "the task's id (task_id)"}
FILES = {
    "type": "array",
    "items": {"type": "string"},
    "description": "names of files sent in this conversation to give it; by default those of the message you answer",
}
NOTIFY = {
    "type": "string",
    "enum": [n.value for n in Notify],
    "description": "auto: tell what it comes back with in this conversation if possible; message: in writing",
}
INSTRUCTION = {"type": "string", "description": "precise and verifiable: what to do, and what to report"}
READ_TURNS = 10  # the latest turns read_task gives
READ_CHARS = 2000  # of each instruction and report it gives


def _spec(name: str, about: str, properties: Mapping[str, object], *required: str) -> ToolSpec:
    return ToolSpec(name, about, {"type": "object", "properties": dict(properties), "required": list(required)})


class Delegation(ToolProvider, ContextProvider, MentionSource):
    name = "delegation"

    def __init__(self, tasks: TaskManager) -> None:
        self.tasks = tasks

    def tools(self) -> Sequence[Tool]:
        if not self.tasks.executors:
            return ()
        start: dict[str, object] = {"title": TITLE, "instruction": INSTRUCTION, "files": FILES, "notify": NOTIFY}
        if len(self.tasks.executors) > 1:
            start["executor"] = {"type": "string", "enum": list(self.tasks.executors)}
        directed = {"task": TASK, "instruction": INSTRUCTION, "files": FILES, "notify": NOTIFY}
        return (
            Tool(
                spec=_spec(
                    "start_task",
                    "Open a task with an executor: it works in the background.",
                    start,
                    "title",
                    "instruction",
                ),
                run=self._start,
                risk=Risk.WRITE,
                assess=lambda arguments: self._risk(arguments.get("executor")),
                account_vouches=True,
            ),
            Tool(
                spec=_spec(
                    "continue_task",
                    "Give one of their tasks an instruction: steers it while it works, else goes on in its thread.",
                    directed,
                    "task",
                    "instruction",
                ),
                run=self._continue,
                risk=Risk.WRITE,
                assess=lambda arguments: self._risk(self._executor_of(arguments.get("task"))),
                account_vouches=True,
                timeout_s=60.0,
            ),
            Tool(
                spec=_spec(
                    "stop_task",
                    "Stop the turn a task is working on; the task stays, ready to go on. Says whether the stop is "
                    "confirmed; effects already produced remain.",
                    {"task": TASK},
                    "task",
                ),
                run=self._stop,
                risk=Risk.WRITE,
                timeout_s=30.0,
            ),
            Tool(
                spec=_spec("list_tasks", "How their tasks stand: working, waiting for them, ready.", {}), run=self._list
            ),
            Tool(
                spec=_spec(
                    "read_task",
                    "What a task was asked and came back with, turn by turn, and its notes.",
                    {"task": TASK},
                    "task",
                ),
                run=self._read,
            ),
            Tool(
                spec=_spec(
                    "rename_task",
                    "Give one of their tasks another title.",
                    {"task": TASK, "title": TITLE},
                    "task",
                    "title",
                ),
                run=self._rename,
                risk=Risk.WRITE,
            ),
            Tool(
                spec=_spec(
                    "archive_task",
                    "Put away a task they are done with; continuing it opens it again.",
                    {"task": TASK},
                    "task",
                ),
                run=self._archive,
                risk=Risk.WRITE,
            ),
        )

    def guidance(self) -> str:
        if not self.tasks.executors:
            return NO_EXECUTOR
        executors = "\n".join(f"- {e.name}: {e.description}" for e in self.tasks.executors.values())
        return (
            f"{HOW_TO_DELEGATE}\n\nYour executors and what they can really do:\n{executors}\n"
            "Nothing else: for any other request, say right away that you cannot, without starting a task."
        )

    def mentionable(self, person: Person | None) -> Iterable[Mentioned]:
        for executor in self.tasks.executors.values():
            yield Mentioned(
                kind=MentionKind.EXECUTOR,
                id=executor.name,
                handle=executor.name,
                label=executor.name,
                detail=executor.description,
                brand=executor.brand,
            )
        for task in self.tasks.of(person.id) if person else ():
            executor = self.tasks.executors.get(task.executor)
            yield Mentioned(
                kind=MentionKind.TASK,
                id=task.id,
                handle=task.title,
                label=task.title,
                aliases=(task.title,),
                detail=task.state.value,
                brand=executor.brand if executor else None,
            )

    def instruction(self, mentioned: Mentioned) -> str:
        if mentioned.kind is MentionKind.TASK:
            return f"their task {mentioned.id} ({mentioned.label}): direct it with continue_task(task={mentioned.id!r})"
        which = f" (executor: {mentioned.id})" if len(self.tasks.executors) > 1 else ""
        return f"the executor {mentioned.id}: hand that part of the work to it with start_task{which}"

    async def context(self, turn: TurnContext) -> Sections:
        """Their tasks that work or wait on them: what a follow-up may be about."""
        person = turn.person
        current = [t for t in self.tasks.of(person.id) if t.state is not TaskState.READY] if person else []
        if not current:
            return {}
        lines = []
        for task in current:
            waits = f", waiting for their answer to: {task.question}" if task.question else ""
            lines.append(f"- {task.id} ({task.title}, {task.executor}): {task.state.value}{waits}")
        return {Layer.TURN: "Their tasks now:\n" + "\n".join(lines)}

    async def _start(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        executor = arguments.get("executor")
        try:
            task = await self.tasks.start_task(
                str(arguments["instruction"]),
                title=titled(arguments),
                origin=context.address,
                owner=context.person,
                executor=str(executor) if executor else None,
                exchange=context.exchange,
                thread=context.thread,
                given=await self._given(arguments, context),
                notify=_notify(arguments),
                asked=context.asked,
            )
        except ContractError as error:
            raise ToolFailed(str(error)) from None
        return {"task_id": task.id, "state": task.state.value, "note": "Started: tell the person in a few words."}

    async def _continue(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        task = self._theirs(arguments, context)
        try:
            directed = await self.tasks.direct(
                task.id,
                str(arguments["instruction"]),
                by=context.person,
                given=await self._given(arguments, context),
                notify=_notify(arguments),
                exchange=context.exchange,
                asked=context.asked,
            )
        except ContractError as error:
            raise ToolFailed(str(error)) from None
        note = (
            "Taken into the turn it works on: tell the person in a few words."
            if directed is Directed.STEERED
            else "A new turn started in the same thread: tell the person in a few words."
        )
        return {"task_id": task.id, "directed": directed.value, "note": note}

    async def _stop(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        task = self._theirs(arguments, context)
        outcome = await self.tasks.stop(task.id, by=context.person)
        stopped = outcome.status is TurnStatus.STOPPED
        return {"stopped": stopped, "state": task.state.value, **({"error": outcome.error} if outcome.error else {})}

    async def _list(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        return {"tasks": [t.summary() for t in self.tasks.of(context.person)] if context.person else []}

    async def _read(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        task = self._theirs(arguments, context)
        turns = []
        for turn in task.turns[-READ_TURNS:]:
            outcome = turn.outcome
            read: dict[str, object] = {"asked": turn.instruction[:READ_CHARS], "status": turn.status.value}
            if outcome and outcome.result:
                read["came_back"] = outcome.result[:READ_CHARS]
            if outcome and outcome.question:
                read["question"] = outcome.question
            if outcome and outcome.error:
                read["error"] = outcome.error
            if turn.files:
                read["files"] = [f.name for f in turn.files]
            turns.append(read)
        return {**task.summary(), "turns": turns, "notes": task.notes}

    async def _rename(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        task = await self.tasks.rename(self._theirs(arguments, context).id, titled(arguments), by=context.person)
        return {"task_id": task.id, "title": task.title}

    async def _archive(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        task = await self.tasks.archive(self._theirs(arguments, context).id, by=context.person)
        return {"task_id": task.id, "state": task.state.value}

    def _theirs(self, arguments: Mapping[str, object], context: ToolContext) -> Task:
        """The task named, when it is the asking person's: nobody reaches another's, even in a shared conversation."""
        task = self.tasks.tasks.get(str(arguments.get("task", "")))
        if task is None or context.person is None or task.owner != context.person:
            raise ToolFailed(f"no task {arguments.get('task')!r} of theirs: list_tasks names them")
        return task

    def _executor_of(self, task_id: object) -> object:
        task = self.tasks.tasks.get(str(task_id))
        return task.executor if task else None

    def _risk(self, executor: object) -> Risk:
        """Sensitive when the executor acts with real power: confirmed when asked from a shared device."""
        chosen = self.tasks.executors.get(str(executor)) if executor else self.tasks.default_executor
        return Risk.SENSITIVE if chosen is not None and chosen.sensitive else Risk.WRITE

    async def _given(self, arguments: Mapping[str, object], context: ToolContext) -> tuple[FileRef, ...]:
        """The files sent in the conversation that go with an instruction, but recordings of what was said: those
        named in `files`, else those of the message being answered; by names none of which is another's."""
        if context.exchange is None:
            return ()
        exchange = context.exchange
        history = await self.tasks.journal.history(UserTurn, session=context.address.session)
        sent: list[tuple[str, FileRef]] = []
        seen: set[str] = set()
        taken: set[str] = set()
        for turn in in_conversation(history, exchange.conversation_id):
            for attached in turn.attachments:
                if attached.kind is AttachmentKind.VOICE or attached.blob.digest in seen:
                    continue
                seen.add(attached.blob.digest)
                name = _unique(plain_name(attached.name, attached.blob.media_type), taken)
                taken.add(name)
                sent.append((turn.exchange.turn_id if turn.exchange else "", FileRef(attached.blob, name)))
        wanted = arguments.get("files")
        if isinstance(wanted, list) and wanted:
            named = {str(w) for w in wanted}
            if unknown := named - {f.name for _, f in sent}:
                raise ToolFailed(f"no file named {', '.join(sorted(unknown))} in this conversation")
            return tuple(f for _, f in sent if f.name in named)
        return tuple(f for turn_id, f in sent if turn_id == exchange.turn_id)


def _notify(arguments: Mapping[str, object]) -> Notify:
    try:
        return Notify(str(arguments.get("notify", Notify.AUTO)))
    except ValueError:
        raise ToolFailed(f"notify must be one of: {', '.join(Notify)}") from None


def _unique(name: str, taken: set[str]) -> str:
    """`name`, or `name (2)`, `name (3)`… when it is taken."""
    stem, extension = posixpath.splitext(name)
    found, n = name, 2
    while found in taken:
        found, n = f"{stem} ({n}){extension}", n + 1
    return found
