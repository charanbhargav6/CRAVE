"""
CRAVE — Sandbox Runner (Self-Evolution Engine)
Save to: D:\\CRAVE\\src\\core\\sandbox_runner.py

Isolated execution environment for testing self-modifications.
Creates a temporary virtual environment, installs dependencies,
applies code changes, and runs smoke tests BEFORE touching production.
"""

import os
import sys
import shutil
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("crave.core.sandbox_runner")

CRAVE_ROOT = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")


class SandboxRunner:
    """Manages isolated test environments for code changes."""

    def __init__(self, sandbox_dir: str = None):
        self.sandbox_base = Path(sandbox_dir or os.path.join(CRAVE_ROOT, ".sandbox"))
        # Use D drive if unspecified or if the target drive is missing
        if str(self.sandbox_base).startswith("C:"):
            self.sandbox_base = Path(os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), ".sandbox"))
            
        os.makedirs(self.sandbox_base, exist_ok=True)

    def _get_feature_dir(self, feature_name: str) -> Path:
        """Sanitize feature name and return directory path."""
        safe_name = "".join([c if c.isalnum() else "_" for c in feature_name])
        return self.sandbox_base / safe_name

    def setup_sandbox(self, feature_name: str) -> bool:
        """
        Create a fresh sandbox:
        1. Create directory
        2. Copy src/, tests/, config/
        3. Create python venv
        """
        sandbox_dir = self._get_feature_dir(feature_name)
        logger.info(f"[Sandbox] Setting up sandbox: {sandbox_dir}")

        try:
            # 1. Clean existing
            if sandbox_dir.exists():
                shutil.rmtree(sandbox_dir, ignore_errors=True)
            os.makedirs(sandbox_dir)

            # 2. Copy source files (excluding .venv, __pycache__, etc)
            def ignore_func(dir_path, contents):
                ignore = []
                for c in contents:
                    if c in [".venv", "venv", ".git", "__pycache__", "Ollama", ".sandbox"]:
                        ignore.append(c)
                    elif c.endswith(".pyc") or c.endswith(".enc"):
                        ignore.append(c)
                return ignore

            shutil.copytree(os.path.join(CRAVE_ROOT, "src"), sandbox_dir / "src", ignore=ignore_func)
            shutil.copytree(os.path.join(CRAVE_ROOT, "tests"), sandbox_dir / "tests", ignore=ignore_func)
            shutil.copytree(os.path.join(CRAVE_ROOT, "config"), sandbox_dir / "config", ignore=ignore_func)
            
            # Copy root files (DO NOT COPY .env)
            for file in ["requirements.txt", "main.py"]:
                src_file = os.path.join(CRAVE_ROOT, file)
                if os.path.exists(src_file):
                    shutil.copy2(src_file, sandbox_dir / file)

            # 3. Create venv
            venv_dir = sandbox_dir / ".venv"
            logger.info("[Sandbox] Creating virtual environment...")
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

            return True

        except Exception as e:
            logger.error(f"[Sandbox] Setup failed: {e}")
            return False

    def install_dependencies(self, feature_name: str, new_packages: list[str] = None) -> bool:
        """Install requirements.txt + any new packages in the sandbox venv."""
        sandbox_dir = self._get_feature_dir(feature_name)
        pip_exe = sandbox_dir / ".venv" / "Scripts" / "pip.exe" if os.name == "nt" else sandbox_dir / ".venv" / "bin" / "pip"

        if not pip_exe.exists():
            logger.error("[Sandbox] Cannot install deps — venv pip not found.")
            return False

        try:
            # Install existing requirements
            req_path = sandbox_dir / "requirements.txt"
            if req_path.exists():
                logger.info("[Sandbox] Installing base requirements...")
                subprocess.run([str(pip_exe), "install", "-r", str(req_path)], capture_output=True, check=True)

            # Install new packages
            if new_packages:
                logger.info(f"[Sandbox] Installing new packages: {new_packages}")
                subprocess.run([str(pip_exe), "install"] + new_packages, capture_output=True, check=True)

            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"[Sandbox] Dep installation failed: {e.stderr.decode('utf-8', errors='ignore')}")
            return False

    def apply_code_changes(self, feature_name: str, modifications: list[dict]) -> bool:
        """
        Apply generated code changes TO THE SANDBOX ONLY.
        modifications format: [{"file": "src/x.py", "content": "..."}]
        """
        sandbox_dir = self._get_feature_dir(feature_name)

        try:
            for mod in modifications:
                file_path = mod.get("file", "")
                content = mod.get("content", "")

                if not file_path or not content:
                    continue

                # Ensure path is within sandbox (security)
                full_path = sandbox_dir / file_path
                # Prevent directory traversal
                if not os.path.commonpath([sandbox_dir, full_path.resolve()]) == str(sandbox_dir.resolve()):
                    logger.error(f"[Sandbox] Path traversal attempt blocked: {file_path}")
                    return False

                os.makedirs(full_path.parent, exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                
                logger.info(f"[Sandbox] Wrote modified file: {file_path}")

            return True

        except Exception as e:
            logger.error(f"[Sandbox] Failed to apply code changes: {e}")
            return False

    def run_smoke_tests(self, feature_name: str) -> tuple[bool, str]:
        """Run the test_smoke.py suite inside the sandbox venv."""
        sandbox_dir = self._get_feature_dir(feature_name)
        python_exe = sandbox_dir / ".venv" / "Scripts" / "python.exe" if os.name == "nt" else sandbox_dir / ".venv" / "bin" / "python"

        if not python_exe.exists():
            return False, "Sandbox Python executable not found."

        test_script = sandbox_dir / "tests" / "test_smoke.py"
        if not test_script.exists():
            return False, "Smoke test script not found in sandbox."

        logger.info("[Sandbox] Running smoke tests in isolation...")
        try:
            # Need to pass CRAVE_ROOT as the sandbox dir so tests run logically there
            env = os.environ.copy()
            env["CRAVE_ROOT"] = str(sandbox_dir)
            
            result = subprocess.run(
                [str(python_exe), str(test_script)],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
                cwd=str(sandbox_dir)
            )

            success = result.returncode == 0
            output = result.stdout + "\n" + result.stderr

            if success:
                logger.info("[Sandbox] ✅ Smoke tests passed.")
            else:
                logger.error("[Sandbox] ❌ Smoke tests failed.")

            return success, output

        except subprocess.TimeoutExpired:
            return False, "Tests timed out after 120 seconds."
        except Exception as e:
            return False, f"Test execution error: {e}"

    def cleanup(self, feature_name: str):
        """Delete the sandbox environment."""
        sandbox_dir = self._get_feature_dir(feature_name)
        if sandbox_dir.exists():
            try:
                # On Windows, deleting venvs can be tricky due to locked files
                # Using cmd /c rmdir to force
                if os.name == "nt":
                    subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(sandbox_dir)], shell=True)
                else:
                    shutil.rmtree(sandbox_dir, ignore_errors=True)
                logger.info(f"[Sandbox] Cleaned up {sandbox_dir}")
            except:
                pass
