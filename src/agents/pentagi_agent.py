"""
CRAVE Phase E — Autonomous PentAGI Integration
Bridge between CRAVE and the local PentAGI REST API.
"""

import os
import time
import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger("crave.agents.pentagi")

class PentagiAgent:
    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url.rstrip("/")
        
    def ping(self) -> bool:
        """Check if PentAGI docker container is running."""
        try:
            resp = requests.get(f"{self.api_url}/health", timeout=2.0)
            return resp.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def start_mission(self, target: str, mode: str = "defensive") -> Dict[str, Any]:
        """
        Start an autonomous pentest mission via PentAGI.
        """
        goal = f"Identify and exploit vulnerabilities on {target}."
        if mode == "defensive":
            goal = f"Conduct a defensive counter-reconnaissance port and vulnerability scan on {target}. Do not exploit destructively."
            
        payload = {
            "target": target,
            "goal": goal,
            "mode": "autonomous"
        }
        
        try:
            logger.info(f"Dispatching PentAGI task to {self.api_url}/api/task ...")
            resp = requests.post(f"{self.api_url}/api/task", json=payload, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                task_id = data.get("task_id")
                logger.info(f"Mission started successfully. ID: {task_id}")
                return {"success": True, "task_id": task_id}
            else:
                return {"success": False, "error": f"API HTTP {resp.status_code}: {resp.text}"}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Connection to PentAGI API failed: {e}"}

    def poll_status(self, task_id: str) -> str:
        """Get current status of a running mission."""
        try:
            resp = requests.get(f"{self.api_url}/api/task/{task_id}", timeout=2.0)
            if resp.status_code == 200:
                return resp.json().get("status", "unknown")
            return "error"
        except requests.exceptions.RequestException:
            return "offline"

    def get_report(self, task_id: str) -> Optional[str]:
        """Fetch final markdown report when mission concludes."""
        try:
            resp = requests.get(f"{self.api_url}/api/task/{task_id}/report", timeout=5.0)
            if resp.status_code == 200:
                return resp.json().get("report", "")
            return None
        except requests.exceptions.RequestException:
            return None
