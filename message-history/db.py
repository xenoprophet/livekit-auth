import json
import os
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent.parent / "messages.db"))
MAX_PAGE_SIZE = int(os.environ.get("MAX_PAGE_SIZE", 500))

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        _migrate(conn)
        _local.conn = conn
    return _local.conn


def _migrate(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ts            INTEGER NOT NULL,
            server_id     INTEGER NOT NULL DEFAULT 1,
            actor_name    TEXT    NOT NULL,
            actor_user_id INTEGER,
            msg_type      TEXT    NOT NULL CHECK(msg_type IN ('channel','dm','broadcast')),
            channel_id    INTEGER,
            recipients    TEXT,
            text          TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_msg_channel ON messages(channel_id, ts);
        CREATE INDEX IF NOT EXISTS idx_msg_ts      ON messages(ts);
        CREATE INDEX IF NOT EXISTS idx_msg_actor   ON messages(actor_name, ts);
    """)
    conn.commit()


def save_message(
    *,
    server_id: int = 1,
    actor_name: str,
    actor_user_id: int | None,
    msg_type: str,
    channel_id: int | None,
    recipients: list | None,
    text: str,
) -> None:
    ts = int(time.time() * 1000)
    conn = _get_conn()
    conn.execute(
        """INSERT INTO messages
               (ts, server_id, actor_name, actor_user_id, msg_type, channel_id, recipients, text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ts,
            server_id,
            actor_name or "unknown",
            actor_user_id,
            msg_type,
            channel_id,
            json.dumps(recipients) if recipients else None,
            text,
        ),
    )
    conn.commit()


def get_channel_history(
    *, server_id: int = 1, channel_id: int, before: int | None = None, limit: int = 100
) -> list[dict]:
    page = min(int(limit or 100), MAX_PAGE_SIZE)
    conn = _get_conn()
    if before:
        rows = conn.execute(
            """SELECT * FROM messages
               WHERE server_id=? AND channel_id=? AND ts<?
               ORDER BY ts DESC LIMIT ?""",
            (server_id, channel_id, int(before), page),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM messages
               WHERE server_id=? AND channel_id=?
               ORDER BY ts DESC LIMIT ?""",
            (server_id, channel_id, page),
        ).fetchall()
    return [dict(r) for r in rows]


def get_dm_history(
    *,
    server_id: int = 1,
    user_a: str,
    user_b: str,
    before: int | None = None,
    limit: int = 100,
) -> list[dict]:
    page = min(int(limit or 100), MAX_PAGE_SIZE)
    conn = _get_conn()
    like_a = f'%"{user_a}"%'
    like_b = f'%"{user_b}"%'
    base = """SELECT * FROM messages
              WHERE server_id=? AND msg_type='dm'
                AND ((actor_name=? AND recipients LIKE ?)
                     OR (actor_name=? AND recipients LIKE ?))"""
    if before:
        rows = conn.execute(
            f"{base} AND ts<? ORDER BY ts DESC LIMIT ?",
            (server_id, user_a, like_b, user_b, like_a, int(before), page),
        ).fetchall()
    else:
        rows = conn.execute(
            f"{base} ORDER BY ts DESC LIMIT ?",
            (server_id, user_a, like_b, user_b, like_a, page),
        ).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    conn = _get_conn()
    row = conn.execute("SELECT COUNT(*) AS count FROM messages").fetchone()
    return {"count": row["count"]}
