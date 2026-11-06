"""A delegated task as the admin shows it."""

from datetime import datetime

from pydantic import BaseModel

from nestor.admin.api.v1.shared import OriginOut, People, PersonRef
from nestor.admin.api.v1.tasks.afterwards import Afterwards, Delivery
from nestor.modules.cognition import TaskStatus
from nestor.modules.cognition.delegation.service import Task

STEPS = 5  # the latest progress reports shown


class DeliveredOut(BaseModel):
    at: datetime
    channel: str
    room: str | None  # when it was said aloud

    @classmethod
    def of(cls, delivery: Delivery) -> "DeliveredOut":
        return cls(at=delivery.at, channel=delivery.channel, room=delivery.room)


class TaskOut(BaseModel):
    id: str
    objective: str
    executor: str
    status: TaskStatus
    requested_by: PersonRef | None
    origin: OriginOut
    delivered: DeliveredOut | None  # where and when its result reached the person
    started_at: datetime
    ended_at: datetime | None  # None while it runs
    steps: list[str]  # the latest progress reports
    result: str | None
    error: str | None

    @classmethod
    def of(cls, task: Task, people: People, afterwards: Afterwards) -> "TaskOut":
        outcome = task.outcome
        delivery = afterwards.delivered.get(task.id)
        return cls(
            id=task.id,
            objective=task.objective,
            executor=task.executor,
            status=task.status,
            requested_by=people.ref(task.requested_by),
            origin=OriginOut(session=str(task.origin), channel=task.origin.channel),
            delivered=DeliveredOut.of(delivery) if delivery else None,
            started_at=task.started_at,
            ended_at=afterwards.ended.get(task.id) if outcome else None,
            steps=task.steps[-STEPS:],
            result=outcome.result if outcome else None,
            error=outcome.error if outcome else None,
        )


class TasksOut(BaseModel):
    running: list[TaskOut]
    recent: list[TaskOut]  # ended, newest first


class CancelOut(BaseModel):
    task: TaskOut
    confirmed: bool  # False: the executor did not confirm the stop (see `task.error`)
