"""SQLite storage: one file in the data folder, created on first use."""
import os
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS people (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    is_owner    INTEGER NOT NULL DEFAULT 0,
    birth_month INTEGER,
    birth_day   INTEGER,
    birth_year  INTEGER,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- One anniversary per couple; person_a < person_b.
CREATE TABLE IF NOT EXISTS anniversaries (
    id       INTEGER PRIMARY KEY,
    person_a INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    person_b INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    month    INTEGER NOT NULL,
    day      INTEGER NOT NULL,
    year     INTEGER,
    UNIQUE (person_a, person_b)
);
-- A phone or tablet that picked "who's using this". Only a hash of its cookie is stored.
CREATE TABLE IF NOT EXISTS devices (
    token_hash    TEXT PRIMARY KEY,
    person_id     INTEGER REFERENCES people(id) ON DELETE SET NULL,
    trusted_owner INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen     TEXT
);
"""


def data_dir() -> Path:
    return Path(os.environ.get("BIRTHDAY_PI_DATA", "data"))


def connect() -> sqlite3.Connection:
    path = data_dir()
    path.mkdir(parents=True, exist_ok=True)
    # Autocommit: every statement is saved straight away. One connection per request, used by
    # one thread at a time, so it may be handed between FastAPI's worker threads.
    conn = sqlite3.connect(path / "birthday-pi.db", isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def is_set_up(conn: sqlite3.Connection) -> bool:
    return get_setting(conn, "setup_complete") == "1"


def owner(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM people WHERE is_owner = 1").fetchone()
