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
-- A person's anniversaries; kind is a key of dates.ANNIVERSARY_TYPES.
CREATE TABLE IF NOT EXISTS anniversaries (
    id        INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    kind      TEXT NOT NULL,
    month     INTEGER NOT NULL,
    day       INTEGER NOT NULL,
    year      INTEGER
);
-- "Got it" on a reminder; key is "<p|a><id>:<stage>:<celebration date>".
CREATE TABLE IF NOT EXISTS reminder_acks (
    key       TEXT PRIMARY KEY,
    person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
    acked_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- Family photos. Files live in <data>/photos as <id>.jpg and <id>-thumb.jpg.
CREATE TABLE IF NOT EXISTS photos (
    id          TEXT PRIMARY KEY,
    sha256      TEXT NOT NULL UNIQUE,
    uploader_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
    status      TEXT NOT NULL,  -- 'pending' (waiting for Grandma) or 'approved'
    hidden      INTEGER NOT NULL DEFAULT 0,
    width       INTEGER,
    height      INTEGER,
    taken_at    TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    faces_scanned INTEGER NOT NULL DEFAULT 0  -- set by the faces worker
);
-- Who's in each photo, tagged by hand.
CREATE TABLE IF NOT EXISTS photo_people (
    photo_id  TEXT NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    PRIMARY KEY (photo_id, person_id)
);
-- Faces the faces worker groups together as probably the same person.
CREATE TABLE IF NOT EXISTS face_groups (
    id        INTEGER PRIMARY KEY,
    person_id INTEGER REFERENCES people(id) ON DELETE SET NULL
);
-- Faces found in photos. Crops live in <data>/faces/<id>.jpg; embedding is 128 float32s from SFace.
CREATE TABLE IF NOT EXISTS faces (
    id        INTEGER PRIMARY KEY,
    photo_id  TEXT NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    group_id  INTEGER REFERENCES face_groups(id) ON DELETE SET NULL,
    x INTEGER NOT NULL, y INTEGER NOT NULL, w INTEGER NOT NULL, h INTEGER NOT NULL,
    score     REAL NOT NULL,
    embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS faces_group ON faces(group_id);
CREATE INDEX IF NOT EXISTS faces_photo ON faces(photo_id);
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
    conn.execute("PRAGMA busy_timeout = 5000")  # the faces worker writes to the same file
    _migrate(conn)
    conn.executescript(SCHEMA)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring databases from earlier builds up to date. Runs before SCHEMA creates any missing tables."""
    photo_cols = [r["name"] for r in conn.execute("PRAGMA table_info(photos)")]
    if photo_cols and "faces_scanned" not in photo_cols:  # v0.1
        conn.execute("ALTER TABLE photos ADD COLUMN faces_scanned INTEGER NOT NULL DEFAULT 0")
    # Early M1 builds stored one anniversary per couple; keep it as person_a's wedding anniversary.
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(anniversaries)")]
    if "person_a" in cols:
        conn.executescript("""
            BEGIN;
            ALTER TABLE anniversaries RENAME TO anniversaries_old;
            CREATE TABLE anniversaries (
                id        INTEGER PRIMARY KEY,
                person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
                kind      TEXT NOT NULL,
                month     INTEGER NOT NULL,
                day       INTEGER NOT NULL,
                year      INTEGER
            );
            INSERT INTO anniversaries (person_id, kind, month, day, year)
                SELECT person_a, 'wedding', month, day, year FROM anniversaries_old;
            DROP TABLE anniversaries_old;
            COMMIT;
        """)


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
