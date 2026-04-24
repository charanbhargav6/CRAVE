"""
CRAVE Phase 12 - Hardened File Agent
Zero-latency vault denial + directory traversal protection.
Security-enhanced per benchmark results.
"""

import os
from pathlib import Path
from src.security.rbac import get_rbac

# Frozen set of blocked paths — checked BEFORE any filesystem operation
# This provides microsecond denial without touching the disk
_BLOCKED_PATHS = frozenset([
    os.path.normpath(os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "data", "vault")),
    os.path.normpath(os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "data", "vault", "")),
])

def _is_vault_path(target: str) -> bool:
    """Microsecond check: is target inside any blocked path?"""
    norm = os.path.normpath(os.path.abspath(target))
    for blocked in _BLOCKED_PATHS:
        if norm == blocked or norm.startswith(blocked + os.sep):
            return True
    return False


class FileAgent:
    def __init__(self):
        self.root = Path(os.environ.get("CRAVE_ROOT", r"D:\CRAVE").resolve()
        
    def _is_safe_path(self, target_path: str) -> bool:
        """Prevent directory traversal attacks + vault access."""
        # Stage 1: Instant vault denial (microseconds)
        if _is_vault_path(target_path):
            return False
        # Stage 2: Standard traversal check
        resolved = Path(target_path).resolve()
        return resolved.is_relative_to(self.root)

    def read_file(self, filepath: str) -> str:
        """Read text from a local file."""
        if not self._is_safe_path(filepath):
            return "ERROR: Access Denied. Path blocked by security policy."
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"ERROR reading file: {e}"

    def write_file(self, filepath: str, content: str) -> str:
        """Write text to a file, protected by RBAC."""
        if not self._is_safe_path(filepath):
            return "ERROR: Access Denied. Cannot write to protected paths."
            
        rbac = get_rbac()
        # Require Level 2 (App access) to write files
        if rbac.auth_level < 2:
            return "ERROR: Unauthorized. L2 PIN required to modify files."
            
        try:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return "SUCCESS: File written safely."
        except Exception as e:
            return f"ERROR writing file: {e}"

    def list_dir(self, directory: str = ".") -> str:
        """List contents of a directory."""
        target = self.root / directory
        if not self._is_safe_path(str(target)):
            return "ERROR: Access Denied. Path blocked by security policy."
            
        try:
            items = os.listdir(target)
            return "\n".join(items) if items else "Directory is empty."
        except Exception as e:
            return f"ERROR reading directory: {e}"

