"""Penyimpanan SQLite: pengaturan, server, permintaan perintah, dan sesi login."""

from __future__ import annotations

import sqlite3
import time

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS servers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL UNIQUE,
    host           TEXT NOT NULL,
    port           INTEGER NOT NULL DEFAULT 22,
    username       TEXT NOT NULL,
    mode           TEXT NOT NULL DEFAULT 'setuju' CHECK (mode IN ('baca', 'setuju', 'bebas')),
    allow_patterns TEXT NOT NULL DEFAULT '',
    note           TEXT NOT NULL DEFAULT '',
    host_key       TEXT NOT NULL DEFAULT '',
    created_at     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id   INTEGER NOT NULL,
    server_name TEXT NOT NULL,
    command     TEXT NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',
    policy      TEXT NOT NULL,
    status      TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    decided_at  REAL,
    finished_at REAL,
    exit_code   INTEGER,
    output      TEXT
);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests (status, created_at);
CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    csrf       TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS login_failures (at REAL NOT NULL);
"""

# Status permintaan:
#   refused  ditolak aturan          pending  menunggu persetujuan
#   denied   ditolak pemilik         expired  tidak diputuskan tepat waktu
#   running  sedang berjalan         done     selesai (kode keluar 0)
#   failed   selesai dengan galat atau tidak tersambung
STATUS_TEXT = {
    "refused": "ditolak aturan",
    "pending": "menunggu persetujuan",
    "denied": "ditolak pemilik",
    "expired": "kedaluwarsa",
    "running": "sedang berjalan",
    "done": "selesai",
    "failed": "gagal",
}


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(_SCHEMA)
    return conn


# -- pengaturan ---------------------------------------------------------------


def get_setting(conn, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


# -- server ----------------------------------------------------------------------


def list_servers(conn):
    return conn.execute("SELECT * FROM servers ORDER BY name").fetchall()


def get_server(conn, server_id: int):
    return conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()


def get_server_by_name(conn, name: str):
    return conn.execute("SELECT * FROM servers WHERE name = ?", (name,)).fetchone()


def add_server(conn, *, name, host, port, username, mode, allow_patterns="", note="") -> int:
    cur = conn.execute(
        "INSERT INTO servers (name, host, port, username, mode, allow_patterns, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, host, port, username, mode, allow_patterns, note, time.time()),
    )
    conn.commit()
    return cur.lastrowid


def update_server(conn, server_id: int, *, name, host, port, username, mode, allow_patterns, note):
    conn.execute(
        "UPDATE servers SET name = ?, host = ?, port = ?, username = ?, mode = ?, "
        "allow_patterns = ?, note = ? WHERE id = ?",
        (name, host, port, username, mode, allow_patterns, note, server_id),
    )
    conn.commit()


def set_host_key(conn, server_id: int, text: str) -> None:
    conn.execute("UPDATE servers SET host_key = ? WHERE id = ?", (text, server_id))
    conn.commit()


def delete_server(conn, server_id: int) -> None:
    conn.execute("DELETE FROM servers WHERE id = ?", (server_id,))
    conn.commit()


# -- permintaan perintah ---------------------------------------------------------------


def create_request(conn, server, command: str, reason: str, policy: str, status: str,
                   note: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO requests (server_id, server_name, command, reason, policy, status, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (server["id"], server["name"], command, reason, policy, status, note, time.time()),
    )
    conn.commit()
    return cur.lastrowid


def get_request(conn, request_id: int):
    return conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()


def list_requests(conn, *, status: str | None = None, limit: int = 100):
    if status:
        return conn.execute(
            "SELECT * FROM requests WHERE status = ? ORDER BY id DESC LIMIT ?", (status, limit)
        ).fetchall()
    return conn.execute("SELECT * FROM requests ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def expire_pending(conn, now: float | None = None) -> int:
    cutoff = (now or time.time()) - config.PENDING_MINUTES * 60
    cur = conn.execute(
        "UPDATE requests SET status = 'expired', decided_at = ? "
        "WHERE status = 'pending' AND created_at < ?",
        (now or time.time(), cutoff),
    )
    conn.commit()
    return cur.rowcount


def decide(conn, request_id: int, approve: bool) -> bool:
    """Ubah permintaan pending menjadi running (disetujui) atau denied. False jika bukan pending."""
    expire_pending(conn)
    cur = conn.execute(
        "UPDATE requests SET status = ?, decided_at = ? WHERE id = ? AND status = 'pending'",
        ("running" if approve else "denied", time.time(), request_id),
    )
    conn.commit()
    return cur.rowcount == 1


def finish_request(conn, request_id: int, exit_code: int, output: str) -> None:
    conn.execute(
        "UPDATE requests SET status = ?, exit_code = ?, output = ?, finished_at = ? WHERE id = ?",
        ("done" if exit_code == 0 else "failed", exit_code, output, time.time(), request_id),
    )
    conn.commit()


# -- sesi login -----------------------------------------------------------------


def create_session(conn, token: str, csrf: str) -> None:
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
    conn.execute(
        "INSERT INTO sessions (token, csrf, expires_at) VALUES (?, ?, ?)",
        (token, csrf, time.time() + config.SESSION_DAYS * 86400),
    )
    conn.commit()


def get_session(conn, token: str):
    return conn.execute(
        "SELECT * FROM sessions WHERE token = ? AND expires_at > ?", (token, time.time())
    ).fetchone()


def delete_session(conn, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()


def delete_all_sessions(conn) -> None:
    conn.execute("DELETE FROM sessions")
    conn.commit()


def record_login_failure(conn) -> None:
    conn.execute("INSERT INTO login_failures (at) VALUES (?)", (time.time(),))
    conn.execute("DELETE FROM login_failures WHERE at < ?", (time.time() - 3600,))
    conn.commit()


def recent_login_failures(conn, minutes: int = 10) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM login_failures WHERE at > ?", (time.time() - minutes * 60,)
    ).fetchone()
    return row["n"]
