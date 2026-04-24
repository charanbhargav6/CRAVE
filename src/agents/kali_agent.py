"""
CRAVE Phase 7 - Kali Agent
Provides headless control over WSL2 Kali Linux. 
Includes explicit Vmmem RAM protection and emergency kill-switches.
"""

import subprocess
import threading
import logging
import queue
import shlex
from src.security.rbac import get_rbac

logger = logging.getLogger("crave.agents.kali")

class KaliAgent:
    def __init__(self):
        self._active_processes = []
        self._lock = threading.Lock()
        self._output_queue = queue.Queue()

    def run_command(self, cmd: str) -> str:
        """
        Executes a Kali command synchronously.
        Requires L4 permissions.
        """
        rbac = get_rbac()
        # Security Gate: Hacking operations require L4
        if rbac.auth_level < 4:
            return "ERROR: Unauthorized. L4 Passphrase required for offensive operations."

        logger.warning(f"Executing offensive command: {cmd}")
        
        # Build the WSL command string safely
        try:
            wsl_cmd = ["wsl", "-d", "kali-linux", "--"] + shlex.split(cmd)
        except ValueError as e:
            return f"ERROR: Malformed shell command - {e}"
        
        try:
            with self._lock:
                proc = subprocess.Popen(
                    wsl_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                self._active_processes.append(proc)
            
            # Wait for completion
            stdout, stderr = proc.communicate()
            
            with self._lock:
                if proc in self._active_processes:
                    self._active_processes.remove(proc)

            # Important: Immediately release Kali RAM if no more offensive tasks running
            self._cleanup_vmmem()
            
            if proc.returncode == 0:
                return stdout
            else:
                return f"ERROR (Code {proc.returncode}):\n{stderr}\n{stdout}"
                
        except Exception as e:
            self._cleanup_vmmem()
            return f"CRITICAL FAILURE in Kali connection: {e}"

    def kill_switch(self):
        """
        EMERGENCY KILL SWITCH
        Instantly terminates all active Kali processes and forcefully shuts down the WSL instance.
        """
        logger.critical("🚨 KALI KILL SWITCH ENGAGED 🚨")
        
        with self._lock:
            killed = 0
            for proc in self._active_processes:
                try:
                    proc.terminate()
                    proc.kill()
                    killed += 1
                except:
                    pass
            self._active_processes.clear()
            
        print(f"[Kali] Force-killed {killed} background hacking processes.")
        
        # Hard shutdown WSL immediately
        try:
            subprocess.run(["wsl", "--shutdown"], check=False)
            print("[Kali] WSL Virtual Machine successfully shut down.")
            logger.info("WSL Vmmem purged. Kill switch complete.")
        except Exception as e:
            logger.error(f"Failed to shutdown WSL: {e}")

    def _cleanup_vmmem(self):
        """
        Hygienic shutdown: kills Vmmem ghost process if no tasks are running.
        Prevents Kali from holding 4GB+ RAM captive and breaking Ollama/Gemma 3.
        """
        with self._lock:
            if len(self._active_processes) > 0:
                return # Still running other scans
                
        logger.info("No active offensive tasks. Shutting down WSL to release VMMEM RAM...")
        try:
            subprocess.run(["wsl", "--shutdown"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
