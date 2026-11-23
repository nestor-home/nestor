"""The usage ledger in SQLite: one row per call, a column per unit consumed, and the buckets of time it falls in, in
the household's zone, so that every reading is one aggregate over indexed columns."""

import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from nestor.adapters.storage.sqlite.common import from_time_key, time_key
from nestor.adapters.storage.sqlite.database import SQLiteDatabase
from nestor.core import ContractError, ModelType, Money, PersonId, SessionId, Unit
from nestor.modules.channels import Medium
from nestor.modules.usage import (
    Beat,
    CallPurpose,
    CostBasis,
    Dimension,
    Group,
    Interval,
    Line,
    Outcome,
    Point,
    Totals,
    UsageFilter,
    UsageRecorded,
    UsageStore,
)

UNITS = tuple(Unit)
# what a row holds of its call, in the order of `_row`; the dimensions are columns of their own name
FIELDS = (
    "id", "position", "at", "session", "consumer", "kind", "provider", "served", "cost_nusd", "basis", "price",
    "duration_ms", "outcome", "purpose", "person", "channel", "medium", "conversation", "turn", "origin",
)  # fmt: skip
BUCKETS = ("hour", "day", "week", "month")
COLUMNS = (*FIELDS, *(u.value for u in UNITS), *BUCKETS)
INSERT = (
    f"INSERT INTO usage ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))}) ON CONFLICT (id) DO NOTHING"
)
SELECT = f"SELECT {', '.join(FIELDS)}, {', '.join(u.value for u in UNITS)} FROM usage"
TOTALS = (
    "COALESCE(SUM(cost_nusd), 0), COUNT(*), SUM(cost_nusd IS NULL), COALESCE(SUM(duration_ms), 0), "
    "COUNT(DISTINCT conversation), COALESCE(SUM(CASE WHEN conversation IS NOT NULL THEN cost_nusd END), 0), "
    + ", ".join(f"COALESCE(SUM({u.value}), 0)" for u in UNITS)
)
FORMAT = {Interval.HOUR: "%Y-%m-%dT%H", Interval.DAY: "%Y-%m-%d", Interval.MONTH: "%Y-%m"}


class SQLiteUsageStore(UsageStore):
    name = "sqlite-usage"

    def __init__(self, database: SQLiteDatabase, *, owns_database: bool = False) -> None:
        self.database = database
        self._owns_database = owns_database
        self._zone: ZoneInfo | None = None

    async def start(self) -> None:
        if self._owns_database:
            await self.database.start()

    async def close(self) -> None:
        if self._owns_database:
            await self.database.close()

    async def open(self, timezone: str) -> None:
        def keep(connection: sqlite3.Connection) -> None:
            row = connection.execute("SELECT timezone FROM usage_zone").fetchone()
            if row is not None and row[0] == timezone:
                return
            connection.execute("DELETE FROM usage")  # its buckets were another zone's: rebuilt from the journal
            connection.execute("DELETE FROM usage_zone")
            connection.execute("INSERT INTO usage_zone (timezone) VALUES (?)", (timezone,))

        await self.database.write(keep)
        self._zone = ZoneInfo(timezone)

    async def position(self) -> int:
        row = await self.database.read(lambda c: c.execute("SELECT MAX(position) FROM usage").fetchone())
        return int(row[0] or 0)

    async def add(self, lines: Sequence[Line]) -> None:
        rows = [self._row(line) for line in lines]
        await self.database.write(lambda c: c.executemany(INSERT, rows))

    async def totals(self, where: UsageFilter) -> Totals:
        groups = await self._sums(where, ())
        return groups[0][1] if groups else Totals()

    async def groups(self, where: UsageFilter, by: Dimension) -> list[Group]:
        return [Group(key[0], totals) for key, totals in await self._sums(where, (by.value,))]

    async def series(self, where: UsageFilter, every: Interval, by: Dimension | None = None) -> list[Point]:
        grouped = await self._sums(where, (every.value, by.value) if by else (every.value,), order=every.value)
        points: dict[str, list[Group]] = {}
        for key, totals in grouped:
            points.setdefault(str(key[0]), []).append(Group(key[1] if by else None, totals))
        zone = self._opened()
        return [Point(_start(start, every, zone), tuple(groups)) for start, groups in points.items()]

    async def rhythm(self, where: UsageFilter) -> list[Beat]:
        clause, values = _where(where)
        sql = (
            "SELECT CAST(strftime('%w', day) AS INTEGER), CAST(substr(hour, 12, 2) AS INTEGER), "
            f"COALESCE(SUM(cost_nusd), 0), COUNT(*) FROM usage WHERE {clause} GROUP BY 1, 2"
        )
        rows = await self.database.read(lambda c: c.execute(sql, values).fetchall())
        return [Beat((sunday_first + 6) % 7, hour, Money(cost), calls) for sunday_first, hour, cost, calls in rows]

    async def lines(self, where: UsageFilter, *, before: int | None = None, limit: int = 50) -> list[Line]:
        clause, values = _where(where)
        if before is not None:
            clause, values = f"{clause} AND position < ?", [*values, before]
        sql = f"{SELECT} WHERE {clause} ORDER BY position DESC LIMIT ?"
        rows = await self.database.read(lambda c: c.execute(sql, [*values, limit]).fetchall())
        return [_line(row) for row in rows]

    async def _sums(
        self, where: UsageFilter, keys: Sequence[str], *, order: str | None = None
    ) -> list[tuple[tuple[Any, ...], Totals]]:
        """Totals of the calls `where` keeps by the values of the columns `keys`, the costliest first (or in the
        order of `order`), in one aggregate."""
        clause, values = _where(where)
        grouped = f" GROUP BY {', '.join(keys)}" if keys else ""
        cost = len(keys) + 1  # the column of the cost, after the keys
        ordered = f" ORDER BY {order}, {cost} DESC" if order else (f" ORDER BY {cost} DESC" if keys else "")
        selected = "".join(f"{k}, " for k in keys)
        sql = f"SELECT {selected}{TOTALS} FROM usage WHERE {clause}{grouped}{ordered}"
        rows = await self.database.read(lambda c: c.execute(sql, values).fetchall())
        found = []
        for row in rows:
            key, (cost, calls, unknown, duration, conversations, conversed, *units) = row[: len(keys)], row[len(keys) :]
            if calls:
                spent = {u: q for u, q in zip(UNITS, units, strict=True) if q}
                totals = Totals(Money(cost), calls, unknown or 0, spent, duration, conversations, Money(conversed))
                found.append((tuple(key), totals))
        return found

    def _row(self, line: Line) -> tuple[object, ...]:
        call, units = line.call, line.call.units
        local = call.at.astimezone(self._opened())
        monday = local.date() - timedelta(days=local.weekday())
        return (
            call.id, line.position, time_key(call.at), call.session, call.consumer, call.kind.value, call.provider,
            call.served, call.cost_nusd, call.basis.value, call.price, call.duration_ms, call.outcome.value,
            call.purpose.value, call.person, call.channel, call.medium.value if call.medium else None,
            call.conversation, call.turn, call.origin,
            *(units.get(u, 0) for u in UNITS),
            local.strftime(FORMAT[Interval.HOUR]), local.strftime(FORMAT[Interval.DAY]), monday.isoformat(),
            local.strftime(FORMAT[Interval.MONTH]),
        )  # fmt: skip

    def _opened(self) -> ZoneInfo:
        if self._zone is None:
            raise ContractError("open the usage store with the household's time zone first")
        return self._zone


def _where(where: UsageFilter) -> tuple[str, list[object]]:
    clauses, values = ["1 = 1"], list[object]()
    if where.since is not None:
        clauses.append("at >= ?")
        values.append(time_key(where.since))
    if where.until is not None:
        clauses.append("at < ?")
        values.append(time_key(where.until))
    for dimension, wanted in where.only.items():
        given = sorted(v for v in wanted if v is not None)
        parts = [f"{dimension.value} IN ({', '.join('?' * len(given))})"] if given else []
        if None in wanted:
            parts.append(f"{dimension.value} IS NULL")
        clauses.append(f"({' OR '.join(parts) or '0 = 1'})")
        values += given
    return " AND ".join(clauses), values


def _start(bucket: str, every: Interval, zone: ZoneInfo) -> datetime:
    """When a bucket starts, in the household's zone: a week is its Monday, a month its first."""
    text, fmt = (f"{bucket}-01", "%Y-%m-%d") if every is Interval.MONTH else (bucket, FORMAT.get(every, "%Y-%m-%d"))
    return datetime.strptime(text, fmt).replace(tzinfo=zone)


def _line(row: Sequence[Any]) -> Line:
    fields: Mapping[str, Any] = dict(zip(FIELDS, row[: len(FIELDS)], strict=True))
    units = {u: q for u, q in zip(UNITS, row[len(FIELDS) :], strict=True) if q}
    call = UsageRecorded(
        source="usage",
        id=fields["id"],
        at=from_time_key(fields["at"]),
        session=SessionId(fields["session"]) if fields["session"] is not None else None,
        consumer=fields["consumer"],
        kind=ModelType(fields["kind"]),
        provider=fields["provider"],
        served=fields["served"],
        units=units,
        cost_nusd=fields["cost_nusd"],
        basis=CostBasis(fields["basis"]),
        price=fields["price"],
        duration_ms=fields["duration_ms"],
        outcome=Outcome(fields["outcome"]),
        purpose=CallPurpose(fields["purpose"]),
        person=PersonId(fields["person"]) if fields["person"] is not None else None,
        channel=fields["channel"],
        medium=Medium(fields["medium"]) if fields["medium"] is not None else None,
        conversation=fields["conversation"],
        turn=fields["turn"],
        origin=fields["origin"],
    )
    return Line(fields["position"], call)
