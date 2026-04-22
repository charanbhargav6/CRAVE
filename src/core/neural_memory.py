"""
CRAVE v10.3 — Neural Memory (Persistent Session State)
=======================================================
SQLite-backed persistent memory that survives restarts.

What it stores:
  - Session state (what we were working on, what tabs were open)
  - Project context (key decisions, file paths, milestones)
  - Conversation summaries (compressed context across sessions)
  - Cross-AI export format (JSON endpoint for other AIs/CLIs)

When the user asks "where did we stop?", CRAVE queries this module
and responds with 2-3 crisp bullet points + reopens recent context.

Storage: D:\\CRAVE\\data\\neural_memory.db (SQLite, survives restarts)
"""

import os
import json
import sqlite3
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, List, Dict

logger = logging.getLogger("crave.neural_memory")

CRAVE_ROOT = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")
DB_PATH = os.path.join(CRAVE_ROOT, "data", "neural_memory.db")


class NeuralMemory:
    """
    Persistent brain that survives laptop restarts.
    Thread-safe SQLite with WAL mode for concurrent reads.
    """

    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._create_tables()
        logger.info(f"[NeuralMemory] Initialized at {DB_PATH}")

    def _create_tables(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at  TEXT NOT NULL,
                    ended_at    TEXT,
                    summary     TEXT,
                    key_points  TEXT,     -- JSON array of bullet points
                    open_tabs   TEXT,     -- JSON array of URLs/file paths
                    project     TEXT,     -- current project name
                    status      TEXT DEFAULT 'active'
                );

                CREATE TABLE IF NOT EXISTS context_items (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  INTEGER,
                    timestamp   TEXT NOT NULL,
                    category    TEXT NOT NULL,  -- 'decision', 'milestone', 'file', 'note', 'error'
                    content     TEXT NOT NULL,
                    metadata    TEXT,           -- JSON extras
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS shared_context (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    key         TEXT UNIQUE NOT NULL,
                    value       TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_ctx_session ON context_items(session_id);
                CREATE INDEX IF NOT EXISTS idx_ctx_category ON context_items(category);
                CREATE INDEX IF NOT EXISTS idx_shared_key ON shared_context(key);
            """)
            self._conn.commit()

    # ── Session Management ───────────────────────────────────────────────────

    def start_session(self, project: str = "general") -> int:
        """Begin a new session. Returns session ID."""
        with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            cur = self._conn.execute(
                "INSERT INTO sessions (started_at, project, status) VALUES (?, ?, 'active')",
                (now, project)
            )
            self._conn.commit()
            sid = cur.lastrowid
            logger.info(f"[NeuralMemory] Session #{sid} started (project: {project})")
            return sid

    def end_session(self, session_id: int, summary: str = "", key_points: list = None, open_tabs: list = None):
        """End a session with a summary and bullet points."""
        with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                """UPDATE sessions SET ended_at=?, summary=?, key_points=?, 
                   open_tabs=?, status='closed' WHERE id=?""",
                (now, summary, json.dumps(key_points or []),
                 json.dumps(open_tabs or []), session_id)
            )
            self._conn.commit()

    def get_active_session(self) -> Optional[Dict]:
        """Get the current active session, or None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE status='active' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row:
                return self._session_to_dict(row)
            return None

    def get_last_session(self) -> Optional[Dict]:
        """Get the most recent closed session (for 'where did we stop?')."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE status='closed' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row:
                return self._session_to_dict(row)
            return None

    def _session_to_dict(self, row) -> Dict:
        return {
            "id": row[0],
            "started_at": row[1],
            "ended_at": row[2],
            "summary": row[3],
            "key_points": json.loads(row[4]) if row[4] else [],
            "open_tabs": json.loads(row[5]) if row[5] else [],
            "project": row[6],
            "status": row[7],
        }

    # ── Context Items (decisions, milestones, notes) ─────────────────────────

    def log(self, category: str, content: str, metadata: dict = None, session_id: int = None):
        """
        Log a context item. Auto-attaches to active session if session_id not given.
        Categories: 'decision', 'milestone', 'file', 'note', 'error', 'tab'
        """
        with self._lock:
            if session_id is None:
                active = self.get_active_session()
                session_id = active["id"] if active else None

            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                "INSERT INTO context_items (session_id, timestamp, category, content, metadata) VALUES (?, ?, ?, ?, ?)",
                (session_id, now, category, content, json.dumps(metadata or {}))
            )
            self._conn.commit()

    def get_recent_context(self, limit: int = 20, category: str = None) -> List[Dict]:
        """Get recent context items, optionally filtered by category."""
        with self._lock:
            if category:
                rows = self._conn.execute(
                    "SELECT * FROM context_items WHERE category=? ORDER BY id DESC LIMIT ?",
                    (category, limit)
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM context_items ORDER BY id DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [self._ctx_to_dict(r) for r in rows]

    def _ctx_to_dict(self, row) -> Dict:
        return {
            "id": row[0],
            "session_id": row[1],
            "timestamp": row[2],
            "category": row[3],
            "content": row[4],
            "metadata": json.loads(row[5]) if row[5] else {},
        }

    # ── Shared Key-Value Store (for cross-AI context) ────────────────────────

    def set(self, key: str, value: str):
        """Set a shared key-value pair. Other AIs/CLIs can read this."""
        with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                "INSERT OR REPLACE INTO shared_context (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, now)
            )
            self._conn.commit()

    def get(self, key: str) -> Optional[str]:
        """Get a shared value by key."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM shared_context WHERE key=?", (key,)
            ).fetchone()
            return row[0] if row else None

    def get_all_shared(self) -> Dict[str, str]:
        """Export all shared context as a dict (for cross-AI consumption)."""
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM shared_context").fetchall()
            return {r[0]: r[1] for r in rows}

    # ── Resume Command ("where did we stop?") ────────────────────────────────

    def generate_resume_brief(self) -> str:
        """
        Generate a crisp 2-3 bullet point summary of what was last worked on.
        Returns a human-readable string ready for TTS.
        """
        last = self.get_last_session()
        if not last:
            return "No previous sessions found. This is a fresh start."

        points = last.get("key_points", [])
        project = last.get("project", "general")
        summary = last.get("summary", "")

        # Build response
        lines = [f"Last session was on project: {project}"]
        if summary:
            lines.append(f"Summary: {summary}")
        if points:
            for i, p in enumerate(points[:3], 1):
                lines.append(f"  {i}. {p}")
        else:
            # No explicit points — pull latest context items
            recent = self.get_recent_context(limit=3)
            for i, ctx in enumerate(recent, 1):
                lines.append(f"  {i}. [{ctx['category']}] {ctx['content'][:100]}")

        return "\n".join(lines)

    def get_recent_tabs(self) -> List[str]:
        """Get the list of tabs/files that were open in the last session."""
        last = self.get_last_session()
        if last:
            return last.get("open_tabs", [])
        return []

    # ── Auto Session Save (called by orchestrator on shutdown) ───────────────

    def auto_save_session(self, context: list, summary: str = ""):
        """
        Automatically end the current session with a summary.
        Called during graceful shutdown.
        """
        active = self.get_active_session()
        if not active:
            return

        # Extract key points from recent conversation context
        key_points = []
        for msg in context[-6:]:
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if len(content) > 20:
                    key_points.append(content[:120] + "..." if len(content) > 120 else content)

        # Get open tabs/files from context items
        tab_items = self.get_recent_context(limit=10, category="tab")
        open_tabs = [t["content"] for t in tab_items]

        if not summary:
            summary = f"Session with {len(context)} messages"

        self.end_session(
            session_id=active["id"],
            summary=summary,
            key_points=key_points[:3],
            open_tabs=open_tabs
        )
        logger.info(f"[NeuralMemory] Session #{active['id']} auto-saved")

    # ── Export for External AIs / CLIs ────────────────────────────────────────

    def export_context_json(self) -> str:
        """
        Export full context as JSON for other AIs to consume.
        Includes: last session summary, recent decisions, shared KV store.
        """
        data = {
            "last_session": self.get_last_session(),
            "active_session": self.get_active_session(),
            "recent_context": self.get_recent_context(limit=10),
            "shared": self.get_all_shared(),
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
        return json.dumps(data, indent=2)


# ── Singleton ────────────────────────────────────────────────────────────────

_instance: Optional[NeuralMemory] = None

def get_neural_memory() -> NeuralMemory:
    global _instance
    if _instance is None:
        _instance = NeuralMemory()
    return _instance
