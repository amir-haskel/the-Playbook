"""SQLite persistence for the Playbook.

The pod is stateless; all configuration and execution history live in a SQLite
database on the PVC-mounted DATA_DIR. Concurrency is low (a config store plus
occasional execution rows), so a single shared connection guarded by a lock is
sufficient and avoids per-request connection churn.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any, Iterable

from .config import settings

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    icon          TEXT NOT NULL DEFAULT 'box',
    color         TEXT NOT NULL DEFAULT 'slate',   -- legacy, unused
    category      TEXT NOT NULL DEFAULT 'General',  -- legacy, unused
    tags          TEXT NOT NULL DEFAULT '[]',       -- JSON array of tag ids
    script_path   TEXT NOT NULL,
    interpreter   TEXT NOT NULL DEFAULT 'auto',
    parameters    TEXT NOT NULL DEFAULT '[]',   -- JSON array
    output_subdir TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    color      TEXT NOT NULL DEFAULT 'slate',
    type       TEXT NOT NULL DEFAULT 'function',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS executions (
    id           TEXT PRIMARY KEY,
    action_id    TEXT NOT NULL,
    action_title TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL,
    exit_code    INTEGER,
    created_at   TEXT NOT NULL,
    finished_at  TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    file_id      TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    path         TEXT NOT NULL,
    filename     TEXT NOT NULL,
    size         INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifacts_exec ON artifacts(execution_id);
CREATE INDEX IF NOT EXISTS idx_exec_action ON executions(action_id);
CREATE INDEX IF NOT EXISTS idx_exec_created ON executions(created_at);
"""


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(
            settings.db_path, check_same_thread=False, isolation_level=None
        )
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL;")
        _conn.execute("PRAGMA foreign_keys=ON;")
    return _conn


def init_db() -> None:
    conn = get_conn()
    with _lock:
        conn.executescript(SCHEMA)
        # Lightweight migration: add the tags column to pre-existing actions
        # tables that were created before tags existed.
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(actions)")}
        if "tags" not in cols:
            conn.execute("ALTER TABLE actions ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")
        tag_cols = {row["name"] for row in conn.execute("PRAGMA table_info(tags)")}
        if "type" not in tag_cols:
            conn.execute("ALTER TABLE tags ADD COLUMN type TEXT NOT NULL DEFAULT 'function'")
        exec_cols = {row["name"] for row in conn.execute("PRAGMA table_info(executions)")}
        if "action_title" not in exec_cols:
            conn.execute(
                "ALTER TABLE executions ADD COLUMN action_title TEXT NOT NULL DEFAULT ''"
            )


def execute(sql: str, params: Iterable[Any] = ()) -> None:
    conn = get_conn()
    with _lock:
        conn.execute(sql, tuple(params))


def query_all(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    conn = get_conn()
    with _lock:
        cur = conn.execute(sql, tuple(params))
        return cur.fetchall()


def query_one(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    conn = get_conn()
    with _lock:
        cur = conn.execute(sql, tuple(params))
        return cur.fetchone()


# --- JSON helpers for the parameters column -------------------------------- #
def dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def loads(value: str | None) -> Any:
    if not value:
        return []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
