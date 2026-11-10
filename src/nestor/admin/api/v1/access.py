"""Who may see or change what, beyond the scope a route asks for: the people a caller reaches, and the things
that belong to them. Something out of reach is reported as missing, never as forbidden, unless the caller
may see it but not change it: its existence is not disclosed."""

from nestor.admin.api.v1.errors import ApiError, not_found
from nestor.admin.api.v1.security import Caller
from nestor.admin.api.v1.shared import People
from nestor.admin.connecting import Connecting
from nestor.admin.state import AdminState
from nestor.core import PersonId
from nestor.modules.accounts import Principal, Scope
from nestor.modules.cognition import TaskStatus
from nestor.modules.cognition.delegation.service import Task
from nestor.modules.connectors import Connection, Connections
from nestor.modules.initiative import Schedule, Watch
from nestor.modules.memory import Memory


def connections_of(admin: AdminState) -> Connections:
    if admin.nestor.connections is None:
        raise ApiError(404, "no_connectors")
    return admin.nestor.connections


def connecting_of(admin: AdminState) -> Connecting:
    connections_of(admin)
    assert admin.connecting is not None  # built whenever connections are
    return admin.connecting


# -- people ----------------------------------------------------------------------------------------------


def household_person(admin: AdminState, person_id: str) -> PersonId:
    """A person of the household, else 404."""
    if not People(admin.nestor.household).known(person_id):
        raise not_found("person_unknown")
    return PersonId(person_id)


def manages_voice(admin: AdminState, caller: Caller, person: PersonId) -> bool:
    """Their own voice; an owner, the voice of someone without an account."""
    if caller.person == person:
        return True
    return caller.principal.can(Scope.OWNERS_MANAGE) and admin.accounts.of_person(person) is None


def managed_voice(admin: AdminState, caller: Caller, person_id: str) -> PersonId:
    """A person whose voice the caller records, changes or erases; 404 for no one, 403 for someone else's."""
    person = household_person(admin, person_id)
    if not manages_voice(admin, caller, person):
        raise ApiError(403, "voice_not_yours")
    return person


# -- connections -----------------------------------------------------------------------------------------


def reaches_connections_of(principal: Principal, owner: PersonId | None) -> bool:
    return principal.reaches(owner, every=Scope.HOUSEHOLD_CONNECTIONS, own=Scope.OWN_CONNECTIONS)


def reachable_connection(admin: AdminState, caller: Caller, connection_id: str) -> Connection:
    connection = connections_of(admin).connections.get(connection_id)
    if connection is None or not reaches_connections_of(caller.principal, connection.owner):
        raise not_found("connection_unknown")
    return connection


def replaced_connection(admin: AdminState, caller: Caller, kind: str, connection_id: str | None) -> Connection | None:
    """A broken connection being connected again: the caller must reach it."""
    if connection_id is None:
        return None
    reachable_connection(admin, caller, connection_id)
    return connecting_of(admin).replaced(kind, connection_id)


def connection_owner(admin: AdminState, caller: Caller, person: str | None) -> PersonId | None:
    """Whom a new connection is for: `person` when the caller reaches them; without one, the caller's own person
    when that is all they reach, else the whole household."""
    if person is not None and not People(admin.nestor.household).known(person):
        raise ApiError(400, "unknown_person")
    if person is not None:
        chosen = PersonId(person)
    else:
        chosen = None if caller.principal.can(Scope.HOUSEHOLD_CONNECTIONS) else caller.principal.person
    if not reaches_connections_of(caller.principal, chosen):
        raise ApiError(403, "own_connections_only")
    return chosen


# -- memories, tasks, watches ----------------------------------------------------------------------------


def reads_memory(caller: Caller, memory: Memory) -> bool:
    """`memory.manage.own` reads the memories about the account's person and the household-wide ones."""
    return caller.principal.reaches(
        memory.about, every=Scope.MEMORY_MANAGE_ALL, own=Scope.MEMORY_MANAGE_OWN, shared=True
    )


def edits_memory(caller: Caller, memory: Memory) -> bool:
    """`memory.manage.own` corrects or forgets only the memories about the account's person."""
    return caller.principal.reaches(memory.about, every=Scope.MEMORY_MANAGE_ALL, own=Scope.MEMORY_MANAGE_OWN)


async def editable_memory(admin: AdminState, caller: Caller, memory_id: str) -> Memory:
    memory = await admin.nestor.memories.store.get(memory_id)
    if memory is None or not reads_memory(caller, memory):
        raise not_found("memory_unknown")
    if not edits_memory(caller, memory):
        raise ApiError(403, "memory_shared")
    return memory


def reaches_task(caller: Caller, task: Task) -> bool:
    return caller.principal.reaches(task.requested_by, every=Scope.TASKS_MANAGE, own=Scope.TASKS_MANAGE_OWN)


def reachable_task(admin: AdminState, caller: Caller, task_id: str, *, running: bool = False) -> Task:
    """A task the caller reaches (still running, when `running`), else 404."""
    task = admin.nestor.tasks.tasks.get(task_id)
    if task is None or not reaches_task(caller, task) or (running and task.status is not TaskStatus.RUNNING):
        raise not_found("task_unknown")
    return task


def reaches_watch(caller: Caller, watch: Watch) -> bool:
    return caller.principal.reaches(watch.owner, every=Scope.WATCHES_MANAGE_ALL, own=Scope.WATCHES_MANAGE_OWN)


def reachable_watch(admin: AdminState, caller: Caller, watch_id: str) -> Watch:
    watch = admin.nestor.watch_book.watches.get(watch_id)
    if watch is None or not reaches_watch(caller, watch):
        raise not_found("watch_unknown")
    return watch


def reaches_schedule(caller: Caller, schedule: Schedule) -> bool:
    return caller.principal.reaches(schedule.owner, every=Scope.SCHEDULES_MANAGE_ALL, own=Scope.SCHEDULES_MANAGE_OWN)


def reachable_schedule(admin: AdminState, caller: Caller, schedule_id: str) -> Schedule:
    schedule = admin.nestor.schedule_book.schedules.get(schedule_id)
    if schedule is None or not reaches_schedule(caller, schedule):
        raise not_found("schedule_unknown")
    return schedule


def reaches_message_of(caller: Caller, *people: PersonId | None) -> bool:
    """A message between these people, or a confirmation waiting for one of them: every one with
    `messages.read.all`, those concerning the account's person with `messages.read.own`."""
    return any(caller.principal.reaches(p, every=Scope.MESSAGES_READ_ALL, own=Scope.MESSAGES_READ_OWN) for p in people)
