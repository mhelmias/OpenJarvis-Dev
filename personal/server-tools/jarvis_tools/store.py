"""Penyimpanan tugas di SQLite."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

DEFAULT_DB = "/var/lib/jarvis-tools/tasks.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    due_at      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done')),
    source_when TEXT,
    created_at  TEXT NOT NULL,
    sent_at     TEXT,
    done_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_pending ON tasks (status, sent_at, due_at);
"""


def utc_text(dt: datetime) -> str:
    """Simpan waktu sebagai teks UTC dengan format tetap, supaya bisa dibandingkan."""
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_utc(text: str) -> datetime:
    return datetime.fromisoformat(text)


def connect(path: str | None = None) -> sqlite3.Connection:
    path = path or os.environ.get("JARVIS_TOOLS_DB") or DEFAULT_DB
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(_SCHEMA)
    return conn


def add_task(conn: sqlite3.Connection, title: str, due: datetime, source_when: str,
             now: datetime) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO tasks (title, due_at, source_when, created_at) VALUES (?, ?, ?, ?)",
            (title, utc_text(due), source_when, utc_text(now)),
        )
    return int(cur.lastrowid)


def get_task(conn: sqlite3.Connection, task_id: int):
    return conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


def list_tasks(conn: sqlite3.Connection, status: str) -> list:
    if status == "all":
        sql = "SELECT * FROM tasks ORDER BY status = 'done', due_at LIMIT 100"
        return conn.execute(sql).fetchall()
    order = "due_at" if status == "open" else "done_at DESC"
    sql = f"SELECT * FROM tasks WHERE status = ? ORDER BY {order} LIMIT 50"
    return conn.execute(sql, (status,)).fetchall()


def complete_task(conn: sqlite3.Connection, task_id: int, now: datetime) -> bool:
    with conn:
        cur = conn.execute(
            "UPDATE tasks SET status = 'done', done_at = ? WHERE id = ? AND status = 'open'",
            (utc_text(now), task_id),
        )
    return cur.rowcount == 1


def reschedule_task(conn: sqlite3.Connection, task_id: int, due: datetime,
                    source_when: str) -> bool:
    with conn:
        cur = conn.execute(
            "UPDATE tasks SET due_at = ?, source_when = ?, sent_at = NULL, status = 'open', "
            "done_at = NULL WHERE id = ?",
            (utc_text(due), source_when, task_id),
        )
    return cur.rowcount == 1


def due_unsent(conn: sqlite3.Connection, now: datetime) -> list:
    return conn.execute(
        "SELECT * FROM tasks WHERE status = 'open' AND sent_at IS NULL AND due_at <= ? "
        "ORDER BY due_at",
        (utc_text(now),),
    ).fetchall()


def mark_sent(conn: sqlite3.Connection, task_id: int, now: datetime) -> None:
    with conn:
        conn.execute("UPDATE tasks SET sent_at = ? WHERE id = ?", (utc_text(now), task_id))
