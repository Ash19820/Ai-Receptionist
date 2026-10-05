from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "receptionist.sqlite3"


def db_path() -> Path:
    return Path(os.environ.get("RECEPTIONIST_DB", str(DEFAULT_DB))).expanduser().resolve()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS receptionist_requests (
    id INTEGER PRIMARY KEY,
    caller_name TEXT NOT NULL DEFAULT '',
    caller_phone TEXT NOT NULL DEFAULT '',
    request_type TEXT NOT NULL CHECK(request_type IN ('appointment','callback','information','other')),
    service TEXT NOT NULL DEFAULT '',
    preferred_time TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'needs_review' CHECK(status IN ('needs_review','confirmed','closed')),
    source TEXT NOT NULL DEFAULT 'demo',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def initialize() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def audit(action: str, entity_type: str, entity_id: str | int, details: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit_log(action,entity_type,entity_id,details) VALUES(?,?,?,?)",
            (action, entity_type, str(entity_id), json.dumps(details, sort_keys=True)),
        )
