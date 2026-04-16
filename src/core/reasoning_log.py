"""
CRAVE Reasoning Log — In-Memory Ring Buffer
Save to: D:\\CRAVE\\src\\core\\reasoning_log.py

Stores the "why" behind every autonomous decision for transparency.
Used by the "Explain Yourself" command to audit CRAVE's reasoning.

Thread-safe singleton — accessible from any module.
"""

import threading
from datetime import datetime
from collections import deque
from typing import Optional

MAX_ENTRIES = 50


class ReasoningLog:
    """Thread-safe in-memory ring buffer of autonomous decisions."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._entries = deque(maxlen=MAX_ENTRIES)
        return cls._instance

    def log_action(
        self,
        action: str,
        trigger: str,
        reasoning: dict | None = None,
        result: str = "",
    ):
        """
        Log a decision with its full reasoning context.

        Args:
            action:     What was done (e.g. "TRADE_FIRED", "KALI_CMD", "EMAIL_SENT")
            trigger:    What caused it (e.g. "XAUUSD BUY signal", "user voice command")
            reasoning:  Dict of decision factors (scores, approvals, overrides)
            result:     Outcome (e.g. "Order filled at 1852.3", "Scan complete")
        """
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "trigger": trigger,
            "reasoning": reasoning or {},
            "result": result,
        }
        with self._lock:
            self._entries.append(entry)

    def get_last(self, n: int = 5) -> list[dict]:
        """Return the last N entries (most recent first)."""
        with self._lock:
            items = list(self._entries)
        return list(reversed(items[-n:]))

    def get_all(self) -> list[dict]:
        """Return all entries (most recent first)."""
        with self._lock:
            return list(reversed(self._entries))

    def explain_last(self, n: int = 3) -> str:
        """
        Generate a human-readable explanation of the last N actions.
        This is what the "Explain Yourself" command returns.
        """
        entries = self.get_last(n)
        if not entries:
            return "No actions recorded yet. I haven't made any autonomous decisions."

        lines = []
        for i, e in enumerate(entries, 1):
            lines.append(f"─── Action {i} ───")
            lines.append(f"  When:    {e['timestamp']}")
            lines.append(f"  What:    {e['action']}")
            lines.append(f"  Why:     {e['trigger']}")

            if e["reasoning"]:
                lines.append(f"  Factors:")
                for k, v in e["reasoning"].items():
                    lines.append(f"    • {k}: {v}")

            if e["result"]:
                lines.append(f"  Result:  {e['result']}")
            lines.append("")

        return "\n".join(lines)

    def count(self) -> int:
        with self._lock:
            return len(self._entries)


# ── Global accessor ──────────────────────────────────────────────────────────

def get_reasoning_log() -> ReasoningLog:
    """Return the global ReasoningLog singleton."""
    return ReasoningLog()
