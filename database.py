"""
Simple SQLite-backed credits store.

Note on Railway: Railway's default filesystem is ephemeral (it can reset on
redeploys). For a hobby project this file-based DB is fine to start with,
but if you want credits to survive redeploys forever, mount a Railway
Volume at /data and point DB_PATH there, or swap this module out for
Railway's Postgres plugin later.
"""

import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "bot.db")

STARTING_CREDITS = int(os.getenv("STARTING_CREDITS", "5"))


def init_db():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                credits INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def get_or_create_user(user_id: int, username: str | None) -> int:
    """Returns the user's current credit balance, creating them with
    STARTING_CREDITS if they don't exist yet."""
    with _connect() as conn:
        cur = conn.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if row is not None:
            return row[0]

        conn.execute(
            "INSERT INTO users (user_id, username, credits) VALUES (?, ?, ?)",
            (user_id, username, STARTING_CREDITS),
        )
        conn.commit()
        return STARTING_CREDITS


def get_balance(user_id: int) -> int:
    with _connect() as conn:
        cur = conn.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return row[0] if row else 0


def try_spend_credit(user_id: int, amount: int = 1) -> bool:
    """Atomically deducts `amount` credits if the user has enough.
    Returns True if the deduction succeeded, False if insufficient balance."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE users SET credits = credits - ? WHERE user_id = ? AND credits >= ?",
            (amount, user_id, amount),
        )
        conn.commit()
        return cur.rowcount > 0


def add_credits(user_id: int, amount: int) -> int:
    """Adds credits (used by the admin /grant command) and returns new balance."""
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET credits = credits + ? WHERE user_id = ?",
            (amount, user_id),
        )
        conn.commit()
        cur = conn.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return row[0] if row else 0
