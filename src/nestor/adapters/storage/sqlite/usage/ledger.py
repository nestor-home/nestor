"""The usage ledger in SQLite: one row per call, with the buckets of time it falls in, in the household's zone."""

import json
import sqlite3
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nestor.adapters.storage.sqlite.common import from_time_key, time_key
from nestor.adapters.storage.sqlite.database import SQLiteDatabase
from nestor.core import ContractError, Money, PersonId, SessionId, Unit
from nestor.modules.channels import Medium
from nestor.modules.usage import (
    CallPurpose,
    ConsumerKind,
    CostBasis,
    Dimension,
    Group,
    Interval,
    Line,
    Outcome,
    Point,
    Totals,
    UsageFilter,
    UsageStore,
)

_COLUMNS = (
    "id, position, at, consumer, kind, provider, served, units, cost_nusd, basis, price, duration_ms, outcome, "
    "purpose, person, channel, medium, session, conversation, turn, origin"
)
_BUCKETS = {Interval.HOUR: "hour", Interval.DAY: "day", Interval.WEEK: "week", Interval.MONTH: "month"}
_FORMATS = {Interval.HOUR: "%Y-%m-%dT%H", Interval.DAY: "%Y-%m-%d", Interval.WEEK: "%Y-%m-%d", Interval.MONTH: "%Y-%m"}
_DIMENSIONS = frozenset(d.value for d in Dimension)  # each is a column of its own name


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
        zone = ZoneInfo(timezone)

        def keep(connection: sqlite3.Connection) -> None:
            row = connection.execute("SELECT timezone FROM usage_zone").fetchone()
            if row is not None and row[0] == timezone:
                return
            connection.execute("DELETE FROM usage")  # its days were another zone's: rebuilt from the journal
            connection.execute("DELETE FROM usage_zone")
            connection.execute("INSERT INTO usage_zone (timezone) VALUES (?)", (timezone,))

        await self.database.write(keep)
        self._zone = zone

    async def position(self) -> int:
        row = await self.database.read(lambda c: c.execute("SELECT MAX(position) FROM usage").fetchone())
        return int(row[0] or 0)

    async def add(self, lines: Sequence[Line]) -> None:
        rows = [self._row(line) for line in lines]
        await self.database.write(
            lambda c: c.executemany(
                "INSERT INTO usage (id, position, at, hour, day, week, month, consumer, kind, provider, served, units, "
                "cost_nusd, basis, price, duration_ms, outcome, purpose, person, channel, medium, session, "
                "conversation, turn, origin) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "?, ?, ?, ?) ON CONFLICT (id) DO NOTHING",
                rows,
            )
        )

    async def totals(self, where: UsageFilter) -> Totals:
        groups = await self._grouped(where, None, None)
        return groups[0].totals if groups else Totals()

    async def groups(self, where: UsageFilter, by: Dimension, *, limit: int | None = None) -> list[Group]:
        return await self._grouped(where, by.value, limit)

    async def series(self, where: UsageFilter, every: Interval, by: Dimension | None = None) -> list[Point]:
        bucket = _BUCKETS[every]
        keys = (bucket, by.value) if by else (bucket,)
        rows = await self.database.read(lambda c: _sums(c, where, keys))
        points: dict[str | None, list[Group]] = defaultdict(list)
        for key, totals in rows:
            points[key[0]].append(Group(key[1] if by else None, totals))
        zone = self._opened()
        return [
            Point(_start(when, every, zone), tuple(sorted(g, key=lambda g: -g.totals.cost.nusd)))
            for when, g in sorted(points.items(), key=lambda p: p[0] or "")
        ]

    async def lines(self, where: UsageFilter, *, before: int | None = None, limit: int = 50) -> list[Line]:
        clause, values = _where(where)
        if before is not None:
            clause, values = f"{clause} AND position < ?", [*values, before]
        sql = f"SELECT {_COLUMNS} FROM usage WHERE {clause} ORDER BY position DESC LIMIT ?"
        rows = await self.database.read(lambda c: c.execute(sql, [*values, limit]).fetchall())
        return [_line(row) for row in rows]

    async def _grouped(self, where: UsageFilter, by: str | None, limit: int | None) -> list[Group]:
        rows = await self.database.read(lambda c: _sums(c, where, (by,) if by else ()))
        groups = sorted(
            (Group(key[0] if by else None, totals) for key, totals in rows), key=lambda g: -g.totals.cost.nusd
        )
        return groups[:limit] if limit is not None else groups

    def _row(self, line: Line) -> tuple[object, ...]:
        local = line.at.astimezone(self._opened())
        monday = local.date() - timedelta(days=local.weekday())
        return (
            line.id,
            line.position,
            time_key(line.at),
            local.strftime(_FORMATS[Interval.HOUR]),
            local.strftime(_FORMATS[Interval.DAY]),
            monday.isoformat(),
            local.strftime(_FORMATS[Interval.MONTH]),
            line.consumer,
            line.kind.value,
            line.provider,
            line.served,
            json.dumps({u.value: q for u, q in line.units.items()}),
            line.cost.nusd if line.cost is not None else None,
            line.basis.value,
            line.price,
            line.duration_ms,
            line.outcome.value,
            line.purpose.value,
            line.person,
            line.channel,
            line.medium.value if line.medium else None,
            line.session,
            line.conversation,
            line.turn,
            line.origin,
        )

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
        column = _column(dimension.value)
        given = sorted(v for v in wanted if v is not None)
        parts = [f"{column} IN ({', '.join('?' * len(given))})"] if given else []
        if None in wanted:
            parts.append(f"{column} IS NULL")
        clauses.append(f"({' OR '.join(parts) or '0 = 1'})")
        values += given
    return " AND ".join(clauses), values


def _sums(
    connection: sqlite3.Connection, where: UsageFilter, keys: Sequence[str]
) -> list[tuple[tuple[str | None, ...], Totals]]:
    """Totals of the calls `where` keeps, by the values of the columns `keys`: costs and counts, then units."""
    columns = [_column(k) for k in keys]
    clause, values = _where(where)
    selected = "".join(f"{c}, " for c in columns)
    grouped = f" GROUP BY {', '.join(columns)}" if columns else ""
    sql = (
        f"SELECT {selected}COALESCE(SUM(cost_nusd), 0), COUNT(*), SUM(cost_nusd IS NULL), "
        "COALESCE(SUM(duration_ms), 0) "
        f"FROM usage WHERE {clause}{grouped}"
    )
    counts = {tuple(row[: len(columns)]): row[len(columns) :] for row in connection.execute(sql, values)}
    sql = (
        f"SELECT {selected}j.key, SUM(j.value) FROM usage, json_each(usage.units) AS j "
        f"WHERE {clause} GROUP BY {''.join(f'{c}, ' for c in columns)}j.key"
    )
    units: dict[tuple[str | None, ...], dict[Unit, float]] = defaultdict(dict)
    for row in connection.execute(sql, values):
        units[tuple(row[: len(columns)])][Unit(row[-2])] = row[-1]
    return [
        (key, Totals(Money(cost), calls, unknown or 0, units.get(key, {}), duration))
        for key, (cost, calls, unknown, duration) in counts.items()
        if calls
    ]


def _column(name: str) -> str:
    if name not in _DIMENSIONS and name not in _BUCKETS.values():
        raise ContractError(f"no usage column {name!r}")
    return name


def _start(bucket: str | None, every: Interval, zone: ZoneInfo) -> datetime:
    if bucket is None:
        raise ContractError("a call without its bucket of time")
    if every is Interval.MONTH:
        bucket = f"{bucket}-01"
    fmt = "%Y-%m-%dT%H" if every is Interval.HOUR else "%Y-%m-%d"
    return datetime.strptime(bucket, fmt).replace(tzinfo=zone)


def _line(row: Sequence[object]) -> Line:
    (id_, position, at, consumer, kind, provider, served, units, cost, basis, price, duration, outcome, purpose,
     person, channel, medium, session, conversation, turn, origin) = row  # fmt: skip
    decoded: Mapping[str, float] = json.loads(str(units))
    return Line(
        id=str(id_),
        position=int(str(position)),
        at=from_time_key(str(at)),
        consumer=str(consumer),
        kind=ConsumerKind(kind),
        provider=str(provider),
        served=_text(served),
        units={Unit(u): q for u, q in decoded.items()},
        cost=Money(int(str(cost))) if cost is not None else None,
        basis=CostBasis(basis),
        price=_text(price),
        duration_ms=int(str(duration)),
        outcome=Outcome(outcome),
        purpose=CallPurpose(purpose),
        person=PersonId(str(person)) if person is not None else None,
        channel=_text(channel),
        medium=Medium(medium) if medium is not None else None,
        session=SessionId(str(session)) if session is not None else None,
        conversation=_text(conversation),
        turn=_text(turn),
        origin=_text(origin),
    )


def _text(value: object) -> str | None:
    return None if value is None else str(value)
