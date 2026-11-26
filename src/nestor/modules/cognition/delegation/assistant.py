"""What the central agent sees of delegation: its tools to start, direct, stop, read and put away tasks, and a section
of its instructions. A person reaches only their own tasks."""

from collections.abc import Iterable, Mapping, Sequence

from nestor.core import ContractError, shorten
from nestor.modules.channels import AttachmentKind, plain_name, unique_name
from nestor.modules.cognition.delegation.service import Directed, Task, TaskManager
from nestor.modules.cognition.delegation.types import READ_TURNS, TURN_CHARS, Notify, TaskState, TurnStatus
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
acting, searching or computing beyond your own tools. What your own tools do (a web search, a page, the weather), you \
do yourself, at once. To hand over, call start_task with a precise, verifiable instruction, then say in a very short \
sentence that it is started. It works in the background: keep talking meanwhile; what it comes back with will be told \
when it arrives. If the person wants it in writing (they are leaving, "write me when it's done"), set notify to \
"message".
A task lasts: its executor keeps what it did. To go on with one of their tasks (the answer to its question, a \
follow-up, a correction, "continue the website update"), call continue_task on it rather than start a new one: while \
it works, the instruction reorients it at once. When asked how their tasks are going, call list_tasks; read_task says \
what one did. stop_task stops the turn that works, and only say it stopped if the stop is confirmed. A task receives \
the files you name in `files` from this conversation, voice messages aside, by default those of the message you \
answer: a file you cannot open yourself, an executor can."""

NO_EXECUTOR = """No executor is plugged in: you cannot carry out long tasks, search or act beyond your own tools. \
If asked, say so simply, with what could be added (about_nestor)."""

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
RECENT = 5  # the latest ready tasks each turn names, besides those working or waiting
DIRECTED = {
    Directed.STEERED: "Taken into the turn it works on: tell the person in a few words.",
    Directed.STARTED: "A new turn started in the same thread: tell the person in a few words.",
    Directed.BUSY: "Not given: the turn it works on could not be stopped for it. Tell the person; they can try again "
    "in a moment.",
}


def _spec(name: str, about: str, properties: Mapping[str, object], *required: str) -> ToolSpec:
    return ToolSpec(name, about, {"type": "object", "properties": dict(properties), "required": list(required)})


class Delegation(ToolProvider, ContextProvider, MentionSource):
    name = "delegation"

    def __init__(self, tasks: TaskManager) -> None:
        self.tasks = tasks

    def tools(self) -> Sequence[Tool]:
        if not self.tasks.executors:
            return ()
        # always named, even when there is one: a request no executor covers is refused, never sent to the first
        executor = {
            "type": "string",
            "enum": list(self.tasks.executors),
            "description": "the one whose skills cover it",
        }
        start = {"executor": executor, "title": TITLE, "instruction": INSTRUCTION, "files": FILES, "notify": NOTIFY}
        directed = {"task": TASK, "instruction": INSTRUCTION, "files": FILES, "notify": NOTIFY}
        return (
            Tool(
                spec=_spec(
                    "start_task",
                    "Hand a long task over to an executor; it works on it in the background.",
                    start,
                    "executor",
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
            "Nothing else: hand a request over only to an executor whose description covers it; for any other, start "
            "no task and say you cannot, with what could be added (about_nestor)."
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
        return (
            f"the executor {mentioned.id}: hand that part of the work to it with start_task(executor={mentioned.id!r})"
        )

    async def context(self, turn: TurnContext) -> Sections:
        """Their tasks that work or wait on them, and the latest they could take up again: what a follow-up may be
        about, without looking them up first."""
        person = turn.person
        theirs = self.tasks.of(person.id) if person else []
        current = [t for t in theirs if t.state is not TaskState.READY]
        current += [t for t in theirs if t.state is TaskState.READY][:RECENT]
        if not current:
            return {}
        lines = []
        for task in current:
            waits = f", waiting for their answer to: {task.question}" if task.question else ""
            lines.append(f"- {task.id} ({task.title}, {task.executor}): {task.state.value}{waits}")
        return {Layer.TURN: "Their tasks now:\n" + "\n".join(lines)}

    async def _start(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        try:
            task = await self.tasks.start_task(
                str(arguments["instruction"]),
                title=titled(arguments),
                origin=context.address,
                owner=context.person,
                executor=str(arguments.get("executor", "")),
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
                origin=context.address,
                given=await self._given(arguments, context),
                notify=_notify(arguments),
                exchange=context.exchange,
                asked=context.asked,
            )
        except ContractError as error:
            raise ToolFailed(str(error)) from None
        return {"task_id": task.id, "directed": directed.value, "note": DIRECTED[directed]}

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
            read: dict[str, object] = {"asked": shorten(turn.instruction, TURN_CHARS), "status": turn.status.value}
            if outcome and outcome.result:
                read["came_back"] = shorten(outcome.result, TURN_CHARS)
            if outcome and outcome.question:
                read["question"] = outcome.question
            if outcome and outcome.error:
                read["error"] = outcome.error
            if turn.files:
                read["files"] = [f.name for f in turn.files]
            turns.append(read)
        notes = [{"note": number, "text": text} for number, text in enumerate(task.notes, start=1)]
        return {**task.summary(), "turns": turns, "notes": notes}

    async def _rename(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        task = await self.tasks.rename(self._theirs(arguments, context).id, titled(arguments), by=context.person)
        return {"task_id": task.id, "title": task.title}

    async def _archive(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        task = await self.tasks.archive(self._theirs(arguments, context).id, by=context.person)
        return {"task_id": task.id, "state": task.state.value}

    def _theirs(self, arguments: Mapping[str, object], context: ToolContext) -> Task:
        """The task named, when it is the asking person's: nobody reaches another's, even in a shared conversation."""
        task = self.tasks.theirs(str(arguments.get("task", "")), context.person)
        if task is None:
            raise ToolFailed(f"no task {arguments.get('task')!r} of theirs: list_tasks names them")
        return task

    def _executor_of(self, task_id: object) -> object:
        task = self.tasks.tasks.get(str(task_id))
        return task.executor if task else None

    def _risk(self, executor: object) -> Risk:
        """Sensitive when the executor acts with real power: confirmed when asked from a shared device."""
        chosen = self.tasks.executors.get(str(executor))
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
                name = unique_name(plain_name(attached.name, attached.blob.media_type), taken)
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
