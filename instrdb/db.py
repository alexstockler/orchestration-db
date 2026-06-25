"""SQLite schema and connection management.

For production (Postgres), swap sqlite3 for psycopg2 and change:
  - AUTOINCREMENT  ->  SERIAL
  - INTEGER (booleans) ->  BOOLEAN
  - PRAGMA foreign_keys  ->  not needed (Postgres enforces by default)
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("orchestration.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS composers (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL UNIQUE,
    slug TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS works (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    slug                TEXT    NOT NULL UNIQUE,
    composer_id         INTEGER NOT NULL REFERENCES composers(id),
    title               TEXT    NOT NULL,
    catalog             TEXT,
    year_start          INTEGER,
    year_end            INTEGER,
    duration_minutes    INTEGER,
    formula             TEXT,
    has_strings         INTEGER NOT NULL DEFAULT 0,
    strings_description TEXT,
    has_continuo        INTEGER NOT NULL DEFAULT 0,
    timpani             INTEGER NOT NULL DEFAULT 0,
    perc_players        INTEGER NOT NULL DEFAULT 0,
    harp                INTEGER NOT NULL DEFAULT 0,
    publisher           TEXT,
    publisher_label     TEXT,
    additional_raw      TEXT,
    chorus_raw          TEXT,
    offstage            TEXT
);

CREATE TABLE IF NOT EXISTS work_external_ids (
    work_id     INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    source      TEXT    NOT NULL,
    external_id TEXT    NOT NULL,
    PRIMARY KEY (work_id, source)
);

-- One row per instrument that appears in a work.
-- Primary chairs: is_doubling=0, player_count = number of seats.
-- Doublings:      is_doubling=1, player_count = NULL (no extra chair).
CREATE TABLE IF NOT EXISTS work_instruments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id      INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    instrument   TEXT    NOT NULL,
    family       TEXT,
    player_count INTEGER,
    is_doubling  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS work_provenance (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id    INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    source     TEXT    NOT NULL,
    source_url TEXT,
    confidence TEXT,
    notes      TEXT
);

CREATE INDEX IF NOT EXISTS idx_work_instruments_instrument ON work_instruments(instrument);
CREATE INDEX IF NOT EXISTS idx_work_instruments_work       ON work_instruments(work_id);
CREATE INDEX IF NOT EXISTS idx_works_composer              ON works(composer_id);
CREATE INDEX IF NOT EXISTS idx_works_year                  ON works(year_start);
"""


def get_connection(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = get_connection(path)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn
