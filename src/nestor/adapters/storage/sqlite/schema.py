"""Schema migrations, applied in order; the database's `user_version` is the number applied.

Never edit a released migration: append a new one.
"""

EVENTS = """
CREATE TABLE events (
    position INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    version INTEGER NOT NULL,
    at TEXT NOT NULL,  -- UTC, fixed width: text order is time order
    source TEXT NOT NULL,
    session TEXT,
    payload TEXT NOT NULL  -- JSON
) STRICT;
CREATE INDEX events_by_type ON events (type, position);
CREATE INDEX events_by_session ON events (session, position);
CREATE INDEX events_by_time ON events (at);
CREATE TRIGGER events_are_never_updated BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
CREATE TRIGGER events_are_never_deleted BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
"""

MIGRATIONS: tuple[str, ...] = (EVENTS,)
