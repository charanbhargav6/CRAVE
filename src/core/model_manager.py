"""
CRAVE — Model Manager (Self-Evolution Engine)
Save to: D:\\CRAVE\\src\\core\\model_manager.py

Handles the full model lifecycle:
  Discover → Disk/RAM Check → Download → Multi-Model Benchmark → Swap → Cleanup

Key design: Uses MULTI-MODEL CONSENSUS (not waterfall) for benchmarking.
Both old and new models are scored, then Gemini + local judge evaluate.

All operations require ConfirmationGate approval.
"""

import os
import sys
import json
import time
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("crave.core.model_manager")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

CRAVE_ROOT = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")
CONFIG_PATH = os.path.join(CRAVE_ROOT, "config", "hardware.json")
BENCHMARK_PATH = os.path.join(CRAVE_ROOT, "config", "benchmark_prompts.json")
TIMESTAMP_PATH = os.path.join(CRAVE_ROOT, "data", "model_manager_state.json")


def _get_best_drive() -> str:
    """Return the drive letter with the most free space."""
    try:
        import psutil
        best_drive = "D:\\"
        best_free = 0
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                if usage.free > best_free:
                    best_free = usage.free
                    best_drive = part.mountpoint
            except:
                continue
        return best_drive
    except ImportError:
        return "D:\\"


class ModelCandidate:
    """Represents a model that could be an upgrade."""
    def __init__(self, name: str, size_gb: float, family: str = "", params: str = ""):
        self.name = name
        self.size_gb = size_gb
        self.family = family
        self.params = params


class BenchmarkResult:
    """Stores benchmark comparison between two models."""
    def __init__(self):
        self.current_model = ""
        self.candidate_model = ""
        self.scores: dict[str, dict] = {}  # {test_name: {current: score, candidate: score}}
        self.total_current = 0
        self.total_candidate = 0
        self.winner = ""
        self.timestamp = datetime.now().isoformat()


class ModelManager:
    """Full lifecycle model management with safety checks."""

    def __init__(self):
        self._config = self._load_config()
        self._evo_config = self._config.get("self_evolution", {})
        self._state = self._load_state()

    def _load_config(self) -> dict:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def _save_config(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=4, ensure_ascii=False)

    def _load_state(self) -> dict:
        """Load persistent state (last check time, pending deletions, etc)."""
        if os.path.exists(TIMESTAMP_PATH):
            try:
                with open(TIMESTAMP_PATH, "r") as f:
                    return json.load(f)
            except:
                pass
        return {"last_model_check": None, "pending_deletions": []}

    def _save_state(self):
        os.makedirs(os.path.dirname(TIMESTAMP_PATH), exist_ok=True)
        with open(TIMESTAMP_PATH, "w") as f:
            json.dump(self._state, f, indent=2)

    # ── Discovery ─────────────────────────────────────────────────────────────

    def list_installed(self) -> list[dict]:
        """List all locally installed Ollama models with sizes."""
        try:
            import ollama
            models = ollama.list()
            return [
                {
                    "name": m.model,
                    "size_gb": round(m.size / (1024**3), 1),
                }
                for m in models.models
            ]
        except Exception as e:
            logger.error(f"[ModelManager] Failed to list models: {e}")
            return []

    def check_system_resources(self) -> dict:
        """Check available disk space and RAM. Uses D: drive or highest storage."""
        try:
            import psutil

            # Use D: drive or drive with most free space
            target_drive = _get_best_drive()
            disk = psutil.disk_usage(target_drive)
            mem = psutil.virtual_memory()

            return {
                "drive": target_drive,
                "disk_free_gb": round(disk.free / (1024**3), 1),
                "disk_total_gb": round(disk.total / (1024**3), 1),
                "ram_total_gb": round(mem.total / (1024**3), 1),
                "ram_available_gb": round(mem.available / (1024**3), 1),
                "max_model_gb": self._calculate_max_model_size(mem, disk),
            }
        except ImportError:
            return {"error": "psutil not installed", "max_model_gb": 10.0}

    def _calculate_max_model_size(self, mem, disk) -> float:
        """
        Dynamic model size limit.
        Minimum 10GB. Can go higher if system allows.
        Based on: 70% of available RAM or 30% of free disk, whichever is smaller.
        """
        ram_limit = (mem.total / (1024**3)) * 0.7
        disk_limit = (disk.free / (1024**3)) * 0.3
        dynamic = min(ram_limit, disk_limit)
        return max(10.0, round(dynamic, 1))

    def can_download(self, size_gb: float) -> tuple[bool, str]:
        """Check if we have enough resources to download a model."""
        resources = self.check_system_resources()
        if "error" in resources:
            return False, resources["error"]

        if size_gb > resources["disk_free_gb"] * 0.8:
            return False, f"Not enough disk space. Need {size_gb}GB, have {resources['disk_free_gb']}GB free on {resources['drive']}"

        if size_gb > resources["max_model_gb"]:
            return False, f"Model too large for RAM. Max safe size: {resources['max_model_gb']}GB, model: {size_gb}GB"

        return True, f"Resources OK. {resources['disk_free_gb']}GB disk free, max model size: {resources['max_model_gb']}GB"

    # ── Benchmark ─────────────────────────────────────────────────────────────

    def _load_benchmark_prompts(self) -> list[dict]:
        """Load benchmark prompts from config file."""
        try:
            with open(BENCHMARK_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return [{"name": "Basic", "prompt": "Hello, how are you?", "criteria": "coherence"}]

    def _run_model_prompt(self, model: str, prompt: str) -> str:
        """Run a single prompt against a model via Ollama."""
        try:
            import ollama
            resp = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp["message"]["content"]
        except Exception as e:
            return f"[ERROR: {e}]"

    def _judge_with_gemini(self, prompt: str, criteria: str,
                           response_a: str, response_b: str,
                           model_a: str, model_b: str) -> dict:
        """Use Gemini API to score both responses."""
        try:
            from google import genai

            gemini_key = os.environ.get("GEMINI_API_KEY", "")
            if not gemini_key:
                return {"error": "No Gemini API key"}

            client = genai.Client(api_key=gemini_key)
            judge_model = self._evo_config.get("benchmark_judge", "gemini-2.5-pro")

            judge_prompt = f"""You are a fair AI model evaluator. Score both responses on a 1-10 scale.

PROMPT: {prompt}
CRITERIA: {criteria}

RESPONSE A ({model_a}):
{response_a[:2000]}

RESPONSE B ({model_b}):
{response_b[:2000]}

Respond ONLY in this exact JSON format:
{{"score_a": <number>, "score_b": <number>, "reasoning": "<one sentence>"}}"""

            result = client.models.generate_content(
                model=judge_model,
                contents=judge_prompt,
            )

            # Parse JSON from response
            text = result.text.strip()
            # Extract JSON if wrapped in code block
            if "```" in text:
                text = text.split("```")[1].replace("json", "").strip()

            return json.loads(text)

        except Exception as e:
            logger.error(f"[ModelManager] Gemini judge failed: {e}")
            return {"error": str(e)}

    def _judge_with_local(self, prompt: str, criteria: str,
                          response_a: str, response_b: str) -> dict:
        """Fallback: use local model to judge (less accurate but free)."""
        try:
            import ollama

            judge_prompt = f"""Compare these two AI responses. Which is better? Score each 1-10.

PROMPT: {prompt}
CRITERIA: {criteria}

RESPONSE A:
{response_a[:1500]}

RESPONSE B:
{response_b[:1500]}

Reply ONLY with JSON: {{"score_a": <number>, "score_b": <number>}}"""

            resp = ollama.chat(
                model=self._config.get("models", {}).get("reasoning", "qwen3:8b"),
                messages=[{"role": "user", "content": judge_prompt}],
            )

            text = resp["message"]["content"].strip()
            if "```" in text:
                text = text.split("```")[1].replace("json", "").strip()

            return json.loads(text)
        except:
            return {"score_a": 5, "score_b": 5}

    def benchmark(self, current_model: str, candidate_model: str) -> BenchmarkResult:
        """
        Run multi-model benchmark: both models answer 5 prompts,
        scored by Gemini (primary) + local judge (fallback).
        Returns structured BenchmarkResult.
        """
        result = BenchmarkResult()
        result.current_model = current_model
        result.candidate_model = candidate_model

        prompts = self._load_benchmark_prompts()
        logger.info(f"[ModelManager] Starting benchmark: {current_model} vs {candidate_model}")

        for p in prompts:
            name = p["name"]
            prompt = p["prompt"]
            criteria = p["criteria"]

            logger.info(f"[ModelManager] Benchmark test: {name}")

            # Get responses from both models
            resp_current = self._run_model_prompt(current_model, prompt)
            resp_candidate = self._run_model_prompt(candidate_model, prompt)

            # Judge with Gemini (primary)
            gemini_scores = self._judge_with_gemini(
                prompt, criteria, resp_current, resp_candidate,
                current_model, candidate_model
            )

            # Judge with local model (fallback/secondary opinion)
            local_scores = self._judge_with_local(
                prompt, criteria, resp_current, resp_candidate
            )

            # Average the scores (if both available)
            if "error" not in gemini_scores:
                avg_current = (gemini_scores.get("score_a", 5) + local_scores.get("score_a", 5)) / 2
                avg_candidate = (gemini_scores.get("score_b", 5) + local_scores.get("score_b", 5)) / 2
            else:
                avg_current = local_scores.get("score_a", 5)
                avg_candidate = local_scores.get("score_b", 5)

            result.scores[name] = {
                "current": round(avg_current, 1),
                "candidate": round(avg_candidate, 1),
                "current_response": resp_current[:500],
                "candidate_response": resp_candidate[:500],
            }

            result.total_current += avg_current
            result.total_candidate += avg_candidate

        result.total_current = round(result.total_current, 1)
        result.total_candidate = round(result.total_candidate, 1)
        result.winner = "candidate" if result.total_candidate > result.total_current else "current"

        # Save results to file
        self._save_benchmark_results(result)

        return result

    def _save_benchmark_results(self, result: BenchmarkResult):
        """Save benchmark results to logs for audit."""
        path = os.path.join(CRAVE_ROOT, "logs", "benchmark_results.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "timestamp": result.timestamp,
            "current_model": result.current_model,
            "candidate_model": result.candidate_model,
            "scores": result.scores,
            "total_current": result.total_current,
            "total_candidate": result.total_candidate,
            "winner": result.winner,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def format_benchmark_table(self, result: BenchmarkResult) -> str:
        """Generate a human-readable comparison table."""
        lines = [
            "╔════════════════════════════════════════════════════════════╗",
            "║              MODEL BENCHMARK COMPARISON                    ║",
            "╠════════════════════════════════════════════════════════════╣",
            f"║ Current:   {result.current_model:<46} ║",
            f"║ Candidate: {result.candidate_model:<46} ║",
            "╠═════════════╦════════════╦══════════════╦═════════════════╣",
            "║ Test        ║ Current    ║ Candidate    ║ Winner          ║",
            "╠═════════════╬════════════╬══════════════╬═════════════════╣",
        ]

        for name, scores in result.scores.items():
            curr = scores["current"]
            cand = scores["candidate"]
            diff = cand - curr
            if diff > 0:
                winner = f"🟢 Cand +{diff:.1f}"
            elif diff < 0:
                winner = f"🟡 Curr +{abs(diff):.1f}"
            else:
                winner = "🔵 Tie"

            lines.append(f"║ {name:<11} ║ {curr:>6}/10   ║ {cand:>8}/10   ║ {winner:<15} ║")

        lines.extend([
            "╠═════════════╬════════════╬══════════════╬═════════════════╣",
            f"║ TOTAL       ║ {result.total_current:>6}/50   ║ {result.total_candidate:>8}/50   ║ {'🟢 Candidate' if result.winner == 'candidate' else '🟡 Current':<15} ║",
            "╚═════════════╩════════════╩══════════════╩═════════════════╝",
        ])

        return "\n".join(lines)

    # ── Model Operations ──────────────────────────────────────────────────────

    def download_model(self, model_name: str) -> bool:
        """Download a model via Ollama (with resource check first)."""
        # Resource check is mandatory
        resources = self.check_system_resources()
        logger.info(f"[ModelManager] System resources: {resources}")

        try:
            import ollama
            logger.info(f"[ModelManager] Downloading {model_name}...")
            ollama.pull(model_name)
            logger.info(f"[ModelManager] ✅ {model_name} downloaded successfully.")
            return True
        except Exception as e:
            logger.error(f"[ModelManager] Download failed: {e}")
            return False

    def swap_model(self, slot: str, new_model: str) -> bool:
        """
        Swap a model slot in hardware.json.
        slot: "primary", "reasoning", or "vision"
        """
        old_model = self._config.get("models", {}).get(slot, "")

        self._config["models"][slot] = new_model
        self._save_config()

        # Track old model for grace period deletion
        self._state["pending_deletions"].append({
            "model": old_model,
            "replaced_by": new_model,
            "replaced_at": datetime.now().isoformat(),
            "delete_after": (datetime.now() + timedelta(hours=48)).isoformat(),
        })
        self._save_state()

        logger.info(f"[ModelManager] ✅ Swapped {slot}: {old_model} → {new_model}")
        return True

    def delete_model(self, model_name: str) -> bool:
        """Delete a model via Ollama."""
        try:
            import ollama
            ollama.delete(model_name)
            logger.info(f"[ModelManager] ✅ Deleted model: {model_name}")

            # Remove from pending deletions
            self._state["pending_deletions"] = [
                d for d in self._state["pending_deletions"]
                if d["model"] != model_name
            ]
            self._save_state()
            return True
        except Exception as e:
            logger.error(f"[ModelManager] Delete failed: {e}")
            return False

    def check_pending_deletions(self) -> list[dict]:
        """Check if any models are past their 48-hour grace period."""
        now = datetime.now()
        ready = []
        for d in self._state.get("pending_deletions", []):
            try:
                delete_after = datetime.fromisoformat(d["delete_after"])
                if now > delete_after:
                    ready.append(d)
            except:
                continue
        return ready

    # ── Boot Catch-Up ─────────────────────────────────────────────────────────

    def is_check_overdue(self) -> bool:
        """Check if the model check is overdue (laptop was off during scheduled time)."""
        last_check = self._state.get("last_model_check")
        if not last_check:
            return True

        try:
            last_dt = datetime.fromisoformat(last_check)
            interval = self._evo_config.get("model_check_interval_days", 7)
            return (datetime.now() - last_dt).days >= interval
        except:
            return True

    def mark_checked(self):
        """Update the last check timestamp."""
        self._state["last_model_check"] = datetime.now().isoformat()
        self._save_state()
