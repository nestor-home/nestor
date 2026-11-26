"""A delegated task as the admin shows it: a thread of turns with its executor."""

from collections.abc import Collection
from datetime import datetime
from typing import Annotated, Any, Self

from pydantic import BaseModel, Field, StringConstraints

from nestor.admin.api.v1.shared import Input, OriginOut, People, PersonRef
from nestor.modules.channels import AttachmentKind
from nestor.modules.cognition import TaskState, TurnStatus
from nestor.modules.cognition.delegation import STEER, Executor, Steer, Task, Turn
from nestor.modules.cognition.tools import TITLE_CHARS
from nestor.modules.journal import FileRef

INSTRUCTION_CHARS = 8000


class DeliveredOut(BaseModel):
    at: datetime
    channel: str
    room: str | None  # when it was said aloud


class TaskFileOut(BaseModel):
    """A file of a turn: sent with its instruction (`given`) or handed back; its bytes at
    `/tasks/{id}/turns/{turn}/files/{index}`."""

    index: int
    name: str
    kind: AttachmentKind
    media_type: str
    size: int  # in bytes
    given: bool

    @classmethod
    def all(cls, given: tuple[FileRef, ...], made: list[FileRef]) -> list["TaskFileOut"]:
        return [
            cls(
                index=i,
                name=f.name,
                kind=AttachmentKind.of(f.blob.media_type),
                media_type=f.blob.media_type,
                size=f.blob.size,
                given=i < len(given),
            )
            for i, f in enumerate((*given, *made))
        ]


class SteeredOut(BaseModel):
    """An instruction the turn took while it worked."""

    instruction: str
    by: PersonRef | None
    at: datetime

    @classmethod
    def of(cls, steer: Steer, people: People) -> "SteeredOut":
        return cls(instruction=steer.instruction, by=people.ref(steer.by), at=steer.at)


class TurnOut(BaseModel):
    id: str
    instruction: str
    by: PersonRef | None
    status: TurnStatus
    started_at: datetime
    ended_at: datetime | None  # None while it works
    steps: list[str]  # the latest the executor said, while it worked
    steered: list[SteeredOut]  # instructions it took while it worked, the first first
    result: str | None
    question: str | None  # what it asks its owner, when it ended on one
    error: str | None
    files: list[TaskFileOut]
    delivered: DeliveredOut | None  # where and when what it came back with reached the owner

    @classmethod
    def of(cls, turn: Turn, people: People, spoken: Collection[str]) -> "TurnOut":
        """`spoken`: the channels that speak aloud, where a delivery is said in a room."""
        outcome, delivery = turn.outcome, turn.delivered
        return cls(
            id=turn.id,
            instruction=turn.instruction,
            by=people.ref(turn.by),
            status=turn.status,
            started_at=turn.started_at,
            ended_at=turn.ended_at,
            steps=list(turn.steps),
            steered=[SteeredOut.of(s, people) for s in turn.steered],
            result=outcome.result if outcome else None,
            question=outcome.question if outcome else None,
            error=outcome.error if outcome else None,
            files=TaskFileOut.all(turn.given, turn.files),
            delivered=DeliveredOut(
                at=delivery.at,
                channel=delivery.address.channel,
                room=delivery.address.conversation if delivery.address.channel in spoken else None,
            )
            if delivery
            else None,
        )


class TaskOut(BaseModel):
    """A task in a list: how it stands, not its thread."""

    id: str
    title: str  # the short name the household knows it by
    executor: str
    state: TaskState
    owner: PersonRef | None
    origin: OriginOut
    created_at: datetime
    last_activity: datetime
    turns: int
    last_status: TurnStatus  # how its latest turn stands: whether a ready task came back, failed or was stopped
    question: str | None  # what it waits on its owner for
    now: str | None  # the latest step, while it works
    steers: bool  # an instruction given while it works reorients it, rather than stopping it and starting anew

    @classmethod
    def of(cls, task: Task, people: People, executor: Executor | None, **more: Any) -> Self:
        """`executor`: the task's, `None` when it is no longer plugged in; `more`, the fields of a subclass."""
        return cls(
            id=task.id,
            title=task.title,
            executor=task.executor,
            state=task.state,
            owner=people.ref(task.owner),
            origin=OriginOut.of(task.origin),
            created_at=task.created_at,
            last_activity=task.last_activity,
            turns=len(task.turns),
            last_status=task.turn.status,
            question=task.question,
            now=task.now,
            steers=executor is not None and STEER in executor.capabilities,
            **more,
        )


class TaskThreadOut(TaskOut):
    """A task with its thread, the first turn first, and what its executor kept for it."""

    thread: list[TurnOut]
    notes: list[str]

    @classmethod
    def full(cls, task: Task, people: People, executor: Executor | None, spoken: Collection[str]) -> "TaskThreadOut":
        return cls.of(
            task, people, executor, thread=[TurnOut.of(t, people, spoken) for t in task.turns], notes=list(task.notes)
        )


class TasksOut(BaseModel):
    tasks: list[TaskOut]  # waiting first, then working, then the latest active


class InstructionIn(Input):
    """An instruction for a task: steers the turn that works, else opens the next (an answer to its question)."""

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=INSTRUCTION_CHARS)]


class TaskEditIn(Input):
    title: str = Field(min_length=1, max_length=TITLE_CHARS)


class TaskChangedOut(BaseModel):
    """A task as a change left it (renamed, archived)."""

    task: TaskThreadOut


class DirectedOut(TaskChangedOut):
    steered: bool  # True: taken into the turn that works; False: a new turn started


class StopOut(TaskChangedOut):
    confirmed: bool  # False: the executor did not confirm the stop (see the turn's `error`)
