"""A delegated task as the admin shows it: a thread of turns with its executor."""

from datetime import datetime

from pydantic import BaseModel, Field

from nestor.admin.api.v1.shared import OriginOut, People, PersonRef
from nestor.admin.api.v1.tasks.afterwards import Afterwards, Delivery
from nestor.modules.channels import AttachmentKind
from nestor.modules.cognition import TaskState, TurnStatus
from nestor.modules.cognition.delegation import Steer, Task, Turn
from nestor.modules.cognition.tools import TITLE_CHARS
from nestor.modules.journal import FileRef

STEPS = 5  # the latest steps of a turn shown
INSTRUCTION_CHARS = 8000


class DeliveredOut(BaseModel):
    at: datetime
    channel: str
    room: str | None  # when it was said aloud

    @classmethod
    def of(cls, delivery: Delivery) -> "DeliveredOut":
        return cls(at=delivery.at, channel=delivery.channel, room=delivery.room)


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
    steps: list[str]  # the latest the executor said
    steered: list[SteeredOut]  # instructions it took while it worked, the first first
    result: str | None
    question: str | None  # what it asks its owner, when it ended on one
    error: str | None
    files: list[TaskFileOut]
    delivered: DeliveredOut | None  # where and when what it came back with reached the owner

    @classmethod
    def of(cls, turn: Turn, people: People, afterwards: Afterwards) -> "TurnOut":
        outcome = turn.outcome
        delivery = afterwards.delivered.get(turn.id)
        return cls(
            id=turn.id,
            instruction=turn.instruction,
            by=people.ref(turn.by),
            status=turn.status,
            started_at=turn.started_at,
            ended_at=turn.ended_at,
            steps=turn.steps[-STEPS:],
            steered=[SteeredOut.of(s, people) for s in turn.steered],
            result=outcome.result if outcome else None,
            question=outcome.question if outcome else None,
            error=outcome.error if outcome else None,
            files=TaskFileOut.all(turn.given, turn.files),
            delivered=DeliveredOut.of(delivery) if delivery else None,
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

    @classmethod
    def of(cls, task: Task, people: People) -> "TaskOut":
        turn = task.turn
        return cls(
            id=task.id,
            title=task.title,
            executor=task.executor,
            state=task.state,
            owner=people.ref(task.owner),
            origin=OriginOut.of(task.origin),
            created_at=task.created_at,
            last_activity=task.last_activity or task.created_at,
            turns=len(task.turns),
            last_status=turn.status,
            question=task.question,
            now=turn.steps[-1] if task.state is TaskState.WORKING and turn.steps else None,
        )


class TaskThreadOut(TaskOut):
    """A task with its thread, the first turn first, and what its executor kept for it."""

    thread: list[TurnOut]
    notes: list[str]

    @classmethod
    def full(cls, task: Task, people: People, afterwards: Afterwards) -> "TaskThreadOut":
        return cls(
            **TaskOut.of(task, people).model_dump(),
            thread=[TurnOut.of(t, people, afterwards) for t in task.turns],
            notes=task.notes,
        )


class TasksOut(BaseModel):
    tasks: list[TaskOut]  # waiting first, then working, then the latest active


class InstructionIn(BaseModel):
    """An instruction for a task: steers the turn that works, else opens the next (an answer to its question)."""

    text: str = Field(min_length=1, max_length=INSTRUCTION_CHARS)


class TaskEditIn(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_CHARS)


class DirectedOut(BaseModel):
    task: TaskThreadOut
    steered: bool  # True: taken into the turn that works; False: a new turn started


class StopOut(BaseModel):
    task: TaskThreadOut
    confirmed: bool  # False: the executor did not confirm the stop (see the turn's `error`)
