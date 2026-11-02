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

MEMORIES = """
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    about TEXT,
    source TEXT,
    told_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;
CREATE INDEX memories_by_update ON memories (updated_at);
-- Accent-insensitive full-text index kept in step with the table.
CREATE VIRTUAL TABLE memories_text USING fts5 (
    text, content = 'memories', content_rowid = 'rowid', tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TRIGGER memories_indexed AFTER INSERT ON memories
BEGIN INSERT INTO memories_text (rowid, text) VALUES (new.rowid, new.text); END;
CREATE TRIGGER memories_unindexed AFTER DELETE ON memories
BEGIN INSERT INTO memories_text (memories_text, rowid, text) VALUES ('delete', old.rowid, old.text); END;
CREATE TRIGGER memories_reindexed AFTER UPDATE ON memories
BEGIN
    INSERT INTO memories_text (memories_text, rowid, text) VALUES ('delete', old.rowid, old.text);
    INSERT INTO memories_text (rowid, text) VALUES (new.rowid, new.text);
END;
"""

EPISODES = """
CREATE TABLE episodes (
    id TEXT PRIMARY KEY,  -- the conversation's
    address TEXT NOT NULL,
    medium TEXT NOT NULL,
    participants TEXT NOT NULL,  -- JSON array of person ids: only they see it again
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    summary TEXT NOT NULL,
    topics TEXT NOT NULL  -- JSON array
) STRICT;
CREATE INDEX episodes_by_end ON episodes (ended_at);
CREATE VIRTUAL TABLE episodes_text USING fts5 (
    summary, topics, content = 'episodes', content_rowid = 'rowid', tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TRIGGER episodes_indexed AFTER INSERT ON episodes
BEGIN INSERT INTO episodes_text (rowid, summary, topics) VALUES (new.rowid, new.summary, new.topics); END;
CREATE TRIGGER episodes_unindexed AFTER DELETE ON episodes
BEGIN
    INSERT INTO episodes_text (episodes_text, rowid, summary, topics)
    VALUES ('delete', old.rowid, old.summary, old.topics);
END;
CREATE TRIGGER episodes_reindexed AFTER UPDATE ON episodes
BEGIN
    INSERT INTO episodes_text (episodes_text, rowid, summary, topics)
    VALUES ('delete', old.rowid, old.summary, old.topics);
    INSERT INTO episodes_text (rowid, summary, topics) VALUES (new.rowid, new.summary, new.topics);
END;
"""

SECRETS = """
CREATE TABLE secrets (
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    sealed BLOB NOT NULL,  -- nonce + AES-GCM ciphertext of the JSON object, bound to (owner, name)
    updated_at TEXT NOT NULL,
    PRIMARY KEY (owner, name)
) STRICT;
"""

VERIFIERS = """
CREATE TABLE verifiers (
    owner TEXT PRIMARY KEY,  -- account:<id>, invitation:<id>
    verifier TEXT NOT NULL,  -- a scrypt hash or a SHA-256 digest, never the secret itself
    updated_at TEXT NOT NULL
) STRICT;
"""

ACTIVITY = """
CREATE TABLE account_activity (
    account_id TEXT PRIMARY KEY,
    seen_at TEXT NOT NULL  -- UTC, fixed width: the last sign-in or authenticated request
) STRICT;
"""

MIGRATIONS: tuple[str, ...] = (EVENTS + MEMORIES + EPISODES + SECRETS + VERIFIERS + ACTIVITY,)
