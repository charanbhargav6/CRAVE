"""
CRAVE — Git Safety Net
Save to: D:\\CRAVE\\src\\core\\git_safety.py

Local-only git operations for safe self-modification.
NO remote, NO GitHub, NO cloud — purely local version control.

Provides: checkpoint, branch, merge, rollback, auto-revert on test failure.
"""

import os
import sys
import subprocess
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("crave.core.git_safety")

CRAVE_ROOT = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")


class GitSafety:
    """Manages local git operations for safe self-modification."""

    def __init__(self, repo_path: str = None):
        self.repo = repo_path or CRAVE_ROOT

    def _run(self, *args, check: bool = True) -> str:
        """Run a git command and return stdout."""
        cmd = ["git", "-C", self.repo] + list(args)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=check,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"[GitSafety] Command failed: git {' '.join(args)}\n{e.stderr}")
            raise
        except subprocess.TimeoutExpired:
            logger.error(f"[GitSafety] Command timed out: git {' '.join(args)}")
            raise

    def is_repo(self) -> bool:
        """Check if the CRAVE directory is a git repo."""
        try:
            self._run("rev-parse", "--is-inside-work-tree")
            return True
        except:
            return False

    def init_repo(self) -> bool:
        """
        One-time git initialization.
        Creates .gitignore and makes first commit.
        """
        if self.is_repo():
            logger.info("[GitSafety] Already a git repo.")
            return True

        try:
            self._run("init")
            self._run("add", "-A")
            self._run("commit", "-m", "CRAVE initial commit — Self-Evolution baseline")
            logger.info("[GitSafety] ✅ Repository initialized with first commit.")
            return True
        except Exception as e:
            logger.error(f"[GitSafety] Init failed: {e}")
            return False

    def checkpoint(self, message: str = None) -> str:
        """
        Create a safety checkpoint before any modification.
        Returns the commit hash.
        """
        if not message:
            message = f"Checkpoint before self-modification at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        try:
            # Stage everything
            self._run("add", "-A")

            # Check if there are changes to commit
            status = self._run("status", "--porcelain")
            if not status:
                # Nothing to commit — return current HEAD
                return self.get_current_hash()

            self._run("commit", "-m", message)
            commit_hash = self.get_current_hash()
            logger.info(f"[GitSafety] ✅ Checkpoint created: {commit_hash[:8]} — {message}")
            return commit_hash
        except Exception as e:
            logger.error(f"[GitSafety] Checkpoint failed: {e}")
            return ""

    def get_current_hash(self) -> str:
        """Get current HEAD commit hash."""
        try:
            return self._run("rev-parse", "HEAD")
        except:
            return ""

    def get_current_branch(self) -> str:
        """Get current branch name."""
        try:
            return self._run("rev-parse", "--abbrev-ref", "HEAD")
        except:
            return "unknown"

    def create_branch(self, name: str) -> bool:
        """Create and switch to a feature branch."""
        try:
            # Ensure we're on main first
            current = self.get_current_branch()
            if current != "main" and current != "master":
                try:
                    self._run("checkout", "main")
                except:
                    try:
                        self._run("checkout", "master")
                    except:
                        pass  # Stay on current branch

            self._run("checkout", "-b", name)
            logger.info(f"[GitSafety] Created branch: {name}")
            return True
        except Exception as e:
            logger.error(f"[GitSafety] Branch creation failed: {e}")
            return False

    def merge_to_main(self, branch: str) -> bool:
        """Merge a feature branch back to main."""
        try:
            # Switch to main
            main_branch = "main"
            try:
                self._run("checkout", main_branch)
            except:
                main_branch = "master"
                self._run("checkout", main_branch)

            # Merge
            self._run("merge", branch, "--no-ff", "-m", f"Merge {branch} — approved self-modification")
            logger.info(f"[GitSafety] ✅ Merged {branch} into {main_branch}")

            # Delete the feature branch
            self._run("branch", "-d", branch)
            return True
        except Exception as e:
            logger.error(f"[GitSafety] Merge failed: {e}")
            return False

    def rollback(self, commit_hash: str) -> bool:
        """Emergency revert to a known good state."""
        try:
            self._run("reset", "--hard", commit_hash)
            logger.warning(f"[GitSafety] ⚠️ ROLLED BACK to {commit_hash[:8]}")
            return True
        except Exception as e:
            logger.error(f"[GitSafety] Rollback failed: {e}")
            return False

    def delete_branch(self, branch: str) -> bool:
        """Delete a rejected feature branch."""
        try:
            current = self.get_current_branch()
            if current == branch:
                # Switch to main first
                try:
                    self._run("checkout", "main")
                except:
                    self._run("checkout", "master")

            self._run("branch", "-D", branch)
            logger.info(f"[GitSafety] Deleted branch: {branch}")
            return True
        except Exception as e:
            logger.error(f"[GitSafety] Branch deletion failed: {e}")
            return False

    def auto_revert_if_broken(self, last_good_hash: str) -> bool:
        """
        Run smoke tests. If they fail, revert to last good commit.
        Returns True if tests pass (no revert needed).
        """
        logger.info("[GitSafety] Running post-merge smoke tests...")
        try:
            result = subprocess.run(
                [sys.executable, os.path.join(CRAVE_ROOT, "tests", "test_smoke.py")],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=CRAVE_ROOT,
            )

            if result.returncode == 0:
                logger.info("[GitSafety] ✅ Smoke tests passed — change is stable.")
                return True
            else:
                logger.error(f"[GitSafety] ❌ Smoke tests FAILED:\n{result.stdout}\n{result.stderr}")
                self.rollback(last_good_hash)
                return False

        except Exception as e:
            logger.error(f"[GitSafety] Test execution error: {e}")
            self.rollback(last_good_hash)
            return False

    def get_diff(self, branch: str = None) -> str:
        """Get diff of changes (for showing to user before approval)."""
        try:
            if branch:
                return self._run("diff", "main..." + branch, "--stat")
            else:
                return self._run("diff", "--stat")
        except:
            return "(unable to generate diff)"

    def get_detailed_diff(self, branch: str = None) -> str:
        """Get full line-by-line diff."""
        try:
            if branch:
                return self._run("diff", "main..." + branch)
            else:
                return self._run("diff")
        except:
            return "(unable to generate diff)"

    def log_recent(self, n: int = 5) -> str:
        """Show recent commit log."""
        try:
            return self._run("log", "--oneline", f"-{n}")
        except:
            return "(no commits)"
