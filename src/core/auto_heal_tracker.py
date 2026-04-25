"""
CRAVE v10.4 — Auto-Heal Tracker
================================
SQLite-backed error tracking for the self-healing loop.

Tracks which error classes have been seen, how many times self-modification
has been attempted for each, and enforces a 24h cooldown lock after 3
consecutive failures to prevent infinite repair loops.

Used by orchestrator.py (error detection) and self_modifier.py (retry gate).
"""

import os
import sqlite3
import logging
import threading
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("crave.auto_heal")

CRAVE_ROOT = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")
DB_PATH = os.path.join(CRAVE_ROOT, "data", "auto_heal.db")

_lock = threading.Lock()


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=5)
    con.execute("""
        CREATE TABLE IF NOT EXISTS heal_tracker (
            error_class   TEXT PRIMARY KEY,
            attempt_count INTEGER DEFAULT 0,
            last_attempt  TEXT,
            locked_until  TEXT,
            last_traceback TEXT
        )
    """)
    con.commit()
    return con


def record_error(error_class: str, traceback_str: str = "") -> int:
    """
    Record an error occurrence. Returns the current attempt count.
    """
    with _lock:
        con = _connect()
        row = con.execute(
            "SELECT attempt_count FROM heal_tracker WHERE error_class = ?",
            (error_class,),
        ).fetchone()

        now = datetime.now(timezone.utc).isoformat()
        if row:
            new_count = row[0] + 1
            con.execute(
                "UPDATE heal_tracker SET attempt_count = ?, last_attempt = ?, "
                "last_traceback = ? WHERE error_class = ?",
                (new_count, now, traceback_str, error_class),
            )
        else:
            new_count = 1
            con.execute(
                "INSERT INTO heal_tracker (error_class, attempt_count, last_attempt, "
                "last_traceback) VALUES (?, ?, ?, ?)",
                (error_class, 1, now, traceback_str),
            )

        con.commit()
        con.close()
        return new_count


def is_locked(error_class: str) -> bool:
    """Check if this error class is locked (24h cooldown after 3 failures)."""
    with _lock:
        con = _connect()
        row = con.execute(
            "SELECT locked_until FROM heal_tracker WHERE error_class = ?",
            (error_class,),
        ).fetchone()
        con.close()

        if not row or not row[0]:
            return False

        try:
            locked = datetime.fromisoformat(row[0])
            if datetime.now(timezone.utc) < locked:
                return True
            # Lock expired — clear it
            _clear_lock(error_class)
            return False
        except Exception:
            return False


def lock_error(error_class: str, hours: int = 24):
    """Lock an error class for N hours (prevents self-mod attempts)."""
    with _lock:
        con = _connect()
        until = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
        con.execute(
            "UPDATE heal_tracker SET locked_until = ? WHERE error_class = ?",
            (until, error_class),
        )
        con.commit()
        con.close()
        logger.warning(f"[AutoHeal] Locked '{error_class}' for {hours}h")


def _clear_lock(error_class: str):
    """Clear the lock on an error class."""
    con = _connect()
    con.execute(
        "UPDATE heal_tracker SET locked_until = NULL, attempt_count = 0 "
        "WHERE error_class = ?",
        (error_class,),
    )
    con.commit()
    con.close()


def unlock_error(error_class: str):
    """Manual unlock via voice command: 'unlock self-modification for [error]'."""
    with _lock:
        _clear_lock(error_class)
        logger.info(f"[AutoHeal] Manually unlocked '{error_class}'")


def get_attempt_count(error_class: str) -> int:
    """Get current attempt count for an error class."""
    with _lock:
        con = _connect()
        row = con.execute(
            "SELECT attempt_count FROM heal_tracker WHERE error_class = ?",
            (error_class,),
        ).fetchone()
        con.close()
        return row[0] if row else 0


def get_status() -> list:
    """Get full tracker status for diagnostics."""
    with _lock:
        con = _connect()
        rows = con.execute(
            "SELECT error_class, attempt_count, last_attempt, locked_until "
            "FROM heal_tracker ORDER BY last_attempt DESC"
        ).fetchall()
        con.close()
        return [
            {
                "error_class": r[0],
                "attempts": r[1],
                "last_attempt": r[2],
                "locked_until": r[3],
            }
            for r in rows
        ]
