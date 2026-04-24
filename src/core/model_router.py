"""
CRAVE Phase 5 — Secure Hybrid API Router
File: D:\CRAVE\src\core\model_router.py

Features:
- Privacy Filter -> Strict offline Ollama routing on sensitive data
- Waterfall API Routing (Gemini -> Groq -> OpenRouter -> Ollama)
- Tavily AI hook for pre-trade searching
"""

import json
import time
import logging
import os
import re
from pathlib import Path
from typing import Optional, Dict, List, Any

import ollama
from dotenv import load_dotenv
import requests
import psutil

from google import genai
from groq import Groq
from openai import OpenAI
from tavily import TavilyClient

def _find_crave_root() -> str:
    env_root = os.environ.get("CRAVE_ROOT")
    if env_root and os.path.isdir(env_root):
        return env_root
    default = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")
    if os.path.isdir(default):
        return default
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "config" / "hardware.json").exists():
            return str(parent)
    return default

# Load standard .env
env_path = os.path.join(_find_crave_root(), ".env")
load_dotenv(env_path)

# ─── Logging ────────────────────────────────────────────────────────────
logger = logging.getLogger("crave.model_router")

# ─── Task Type Constants ────────────────────────────────────────────────
TASK_PRIMARY   = "primary"      
TASK_REASONING = "reasoning"    
TASK_VISION    = "vision"       

ALL_TASK_TYPES = (TASK_PRIMARY, TASK_REASONING, TASK_VISION)

# ─── Keyword Classification ────────────────────────────────────────────
REASONING_KEYWORDS = [
    "calculate", "solve", "math", "equation", "formula", "code", "debug",
    "program", "function", "algorithm", "script", "compile", "syntax",
    "reason", "prove", "derive", "optimize", "logic", "analyze"
]

VISION_KEYWORDS = [
    "screen", "screenshot", "what do you see", "what's on my screen",
    "analyze image", "look at", "describe image", "read text from", "identify"
]

TRADE_KEYWORDS = [
    "trade", "trading", "buy", "sell", "long", "short", "forex", "crypto",
    "stock", "market", "position", "close all", "kill switch", "pause"
]

PRIVACY_KEYWORDS = [
    "password", "private key", "bank account", "social security", "credit card",
    "nmap", "exploit", "payload", "vulnerability", "shellcode", "kali"
]

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"

class ModelRouter:
    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.join(_find_crave_root(), "config", "hardware.json")

        self._config_path = config_path
        self._config = self._load_config()

        # Local Ollama fallback models
        self._models = {
            TASK_PRIMARY:   self._config["models"]["primary"],
            TASK_REASONING: self._config["models"]["reasoning"],
            TASK_VISION:    self._config["models"]["vision"],
        }
        
        # API Hybrid routing configs
        self._api_config = self._config.get("api_routing", {})
        self._api_enabled = self._api_config.get("enabled", False)
        self._api_models = self._api_config.get("models", {})
        
        self._concurrent = self._config.get("concurrent_models", False)
        self._ollama_host = self._config.get("ollama_host", DEFAULT_OLLAMA_HOST)
        self._retry_attempts = self._config.get("retry_attempts", 3)
        self._retry_delay = self._config.get("retry_delay", 2.0)
        self._cpu_temp_limit = self._config.get("cpu_temp_limit_celsius", 90)
        self._current_model = None
        
        # Initialize API Clients
        self._init_api_clients()

        logger.info(f"ModelRouter initialized | API_ENABLED: {self._api_enabled}")

    def _init_api_clients(self):
        # Gemini
        gemini_key = os.environ.get("GEMINI_API_KEY")
        self.gemini_client = genai.Client(api_key=gemini_key) if gemini_key else None
        
        # Groq
        groq_key = os.environ.get("GROQ_API_KEY")
        self.groq_client = Groq(api_key=groq_key) if groq_key else None
        
        # OpenRouter
        or_key = os.environ.get("OPENROUTER_API_KEY")
        self.or_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=or_key,
        ) if or_key else None
        
        # Tavily
        tavily_key = os.environ.get("TAVILY_API_KEY")
        self.tavily_client = TavilyClient(api_key=tavily_key) if tavily_key else None

    def reinit_api_clients(self):
        """Re-read os.environ for API keys that were injected after initial __init__.
        Called by Orchestrator after vault decryption to fix the boot-order race condition."""
        self._init_api_clients()
        # Diagnostic: log which keys are live
        status = {
            "GEMINI": "✓" if self.gemini_client else "✗",
            "GROQ":   "✓" if self.groq_client else "✗",
            "OPENROUTER": "✓" if self.or_client else "✗",
            "TAVILY": "✓" if self.tavily_client else "✗",
        }
        summary = " | ".join([f"{k}={v}" for k, v in status.items()])
        logger.info(f"API clients re-initialized after vault decrypt: {summary}")

    def _load_config(self) -> dict:
        with open(self._config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def reload_config(self):
        self._config = self._load_config()
        self._models = {
            TASK_PRIMARY:   self._config["models"]["primary"],
            TASK_REASONING: self._config["models"]["reasoning"],
            TASK_VISION:    self._config["models"]["vision"],
        }
        self._api_config = self._config.get("api_routing", {})
        self._api_enabled = self._api_config.get("enabled", False)
        self._api_models = self._api_config.get("models", {})
        self._concurrent = self._config.get("concurrent_models", False)
        self._init_api_clients()

    def classify_task(self, user_input: str, task_type: Optional[str] = None, has_images: bool = False) -> str:
        if task_type in ALL_TASK_TYPES:
            return task_type
        if has_images:
            return TASK_VISION
        lower = user_input.lower().strip()
        for kw in VISION_KEYWORDS:
            if kw in lower: return TASK_VISION
        for kw in REASONING_KEYWORDS:
            if kw in lower: return TASK_REASONING
        return TASK_PRIMARY

    def check_privacy(self, user_input: str) -> bool:
        """Returns True if input contains sensitive keywords."""
        lower = user_input.lower().strip()
        for kw in PRIVACY_KEYWORDS:
            if kw in lower:
                return True
        return False
        
    def is_trading(self, user_input: str) -> bool:
        lower = user_input.lower().strip()
        # Exclude casual chat
        if len(lower) < 15 and "how are you" in lower:
            return False
        for kw in TRADE_KEYWORDS:
            if kw in lower:
                return True
        return False

    # ── RAM estimates for Ollama models (GB) ─────────────────────────────
    _MODEL_RAM_ESTIMATES = {
        "14b": 9.0, "11b": 7.5, "8b": 5.0, "7b": 4.5,
        "3b": 2.5, "1b": 1.5,
    }
    _RAM_HEADROOM_GB = 2.5  # Keep at least 2.5 GB free for OS + PyQt6 + Whisper

    def _estimate_model_ram(self, model_name: str) -> float:
        """Estimate RAM needed for a model based on its size tag."""
        lower = model_name.lower()
        for tag, gb in self._MODEL_RAM_ESTIMATES.items():
            if tag in lower:
                return gb
        return 6.0  # Conservative default

    def _check_ram_before_load(self, model_name: str):
        """Pre-check available RAM. If too low, force-unload all models first."""
        try:
            mem = psutil.virtual_memory()
            available_gb = mem.available / (1024 ** 3)
            needed_gb = self._estimate_model_ram(model_name)
            total_needed = needed_gb + self._RAM_HEADROOM_GB

            if available_gb < total_needed:
                logger.warning(
                    f"[RAM Guard] Low memory: {available_gb:.1f}GB free, "
                    f"need ~{total_needed:.1f}GB ({needed_gb:.1f}GB model + {self._RAM_HEADROOM_GB}GB headroom). "
                    f"Force-unloading all Ollama models..."
                )
                # Force-unload current model
                if self._current_model:
                    try:
                        ollama.generate(model=self._current_model, prompt="", keep_alive=0)
                    except Exception:
                        pass
                    self._current_model = None
                # Give OS time to reclaim memory
                time.sleep(2)
                
                # Re-check after unload
                mem2 = psutil.virtual_memory()
                available_after = mem2.available / (1024 ** 3)
                if available_after < needed_gb + 1.0:
                    logger.error(
                        f"[RAM Guard] Still only {available_after:.1f}GB free after unload. "
                        f"Model '{model_name}' may crash. Consider closing other applications."
                    )
            else:
                logger.debug(f"[RAM Guard] OK: {available_gb:.1f}GB free, {needed_gb:.1f}GB needed for {model_name}")
        except Exception as e:
            logger.warning(f"[RAM Guard] Check failed (non-fatal): {e}")

    def _ensure_local_model_loaded(self, local_model_name: str):
        if self._current_model == local_model_name:
            return
        # RAM guard: prevent OOM crashes on 16GB machines
        self._check_ram_before_load(local_model_name)
        if not self._concurrent and self._current_model:
            ollama.generate(model=self._current_model, prompt="", keep_alive=0)
            time.sleep(0.5)
        ollama.generate(model=local_model_name, prompt="hi", keep_alive="10m")
        self._current_model = local_model_name

    def _call_ollama(self, model_name: str, messages: list, options: dict = None) -> str:
        logger.info(f"-> Calling Local Ollama: {model_name}")
        self._ensure_local_model_loaded(model_name)
        kwargs = {"model": model_name, "messages": messages}
        if options: kwargs["options"] = options
        res = ollama.chat(**kwargs)
        return res["message"]["content"]
        
    def _call_gemini(self, model_name: str, messages: list, images: list = None) -> str:
        logger.info(f"-> Calling Gemini API: {model_name}")
        if not self.gemini_client: raise ValueError("No Gemini API key")
        
        # Convert messages to Gemini format
        contents = []
        for msg in messages:
            role = "user" if msg["role"] in ["user", "system"] else "model"
            txt = msg["content"]
            # System instructions are typically passed differently in gemini, but appending to user works for basic chat
            contents.append({"role": role, "parts": [{"text": txt}]})
            
        # Add images to the last user message if any
        if images and role == "user":
             # We assume images are bytes or PIL Images, in Phase 4 they are base64 strings
             pass # To be fully mapped in Vision phase
             
        # Call API
        try:
            # We use generation path for simplicity
            flat_prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
            response = self.gemini_client.models.generate_content(
                model=model_name,
                contents=flat_prompt
            )
            return response.text
        except Exception as e:
            raise Exception(f"Gemini API Error: {e}")

    def _call_groq(self, model_name: str, messages: list) -> str:
        logger.info(f"-> Calling Groq API: {model_name}")
        if not self.groq_client: raise ValueError("No Groq API key")
        # Strip images if any, groq doesn't support them fully yet on llama-3.3
        clean_msgs = [{"role": m["role"], "content": m["content"]} for m in messages]
        resp = self.groq_client.chat.completions.create(
            model=model_name,
            messages=clean_msgs,
            temperature=0.6,
            max_tokens=4096
        )
        return resp.choices[0].message.content

    def _call_openrouter(self, model_name: str, messages: list) -> str:
        logger.info(f"-> Calling OpenRouter API: {model_name}")
        if not self.or_client: raise ValueError("No OpenRouter API key")
        clean_msgs = [{"role": m["role"], "content": m["content"]} for m in messages]
        response = self.or_client.chat.completions.create(
            model=model_name,
            messages=clean_msgs,
        )
        return response.choices[0].message.content
        
    def _run_tavily(self, query: str) -> str:
        if not self.tavily_client: return ""
        try:
            logger.info(f"-> Searching Tavily for: {query}")
            ans = self.tavily_client.search(query=query, search_depth="basic")
            results = "\n".join([f"{r['title']}: {r['content']}" for r in ans.get("results", [])])
            return f"\n\n[Current Market/News Context from Tavily]:\n{results}"
        except Exception as e:
            logger.warning(f"Tavily search failed: {e}")
            return ""

    def chat(self, prompt: str, task_type: Optional[str] = None, messages: Optional[List[Dict[str, Any]]] = None,
             images: Optional[List] = None, stream: bool = False, system_prompt: Optional[str] = None,
             options: Optional[Dict[str, Any]] = None) -> dict:
        
        # Check hot-reload
        try:
            from src.core.config_watcher import CONFIG_RELOAD_EVENT
            if CONFIG_RELOAD_EVENT.is_set():
                logger.info("[ModelRouter] Config reload event detected. Reloading hardware.json...")
                self.reload_config()
                # Do NOT clear the event here, let the watcher timer clear it so other modules catch it
        except ImportError:
            pass

        start = time.time()
        has_images = bool(images)
        classified = self.classify_task(prompt, task_type, has_images)
        local_target = self._models[classified]
        
        msgs = list(messages) if messages else []
        if system_prompt and (not msgs or msgs[0].get("role") != "system"):
            msgs.insert(0, {"role": "system", "content": system_prompt})
            
        is_trade = self.is_trading(prompt)
        is_private = self.check_privacy(prompt)
        
        if is_trade and not is_private:
            tavily_ctx = self._run_tavily(prompt)
            prompt += tavily_ctx
            
        msgs.append({"role": "user", "content": prompt})
        
        response_text = ""
        model_used = ""
        success = False
        
        # 1. Privacy Check
        if is_private and self._api_config.get("strict_privacy_mode", True):
            logger.warning("PRIVACY FILTER TRIGGERED. Disabling APIs -> Offline Ollama.")
            response_text = self._call_ollama(local_target, msgs, options)
            model_used = f"local-ollama-{local_target}"
            success = True
            
        elif not self._api_enabled:
            response_text = self._call_ollama(local_target, msgs, options)
            model_used = f"local-ollama-{local_target}"
            success = True
            
        else:
            # Waterfall API Routing
            # Strategy:
            # - Trade -> Groq -> OpenRouter -> Ollama
            # - Vision/Heavy -> Gemini -> OpenRouter -> Ollama
            # - General -> Gemini -> Groq -> OpenRouter -> Ollama
            
            queue = []
            
            if is_trade:
                queue.append(("groq", self._call_groq, self._api_models.get("groq", "llama-3.3-70b-versatile")))
                queue.append(("openrouter", self._call_openrouter, self._api_models.get("openrouter")))
            elif has_images:
                queue.append(("gemini", self._call_gemini, self._api_models.get("gemini", "gemini-2.0-flash")))
                queue.append(("openrouter", self._call_openrouter, self._api_models.get("openrouter")))
            else:
                queue.append(("gemini", self._call_gemini, self._api_models.get("gemini", "gemini-2.0-flash")))
                queue.append(("groq", self._call_groq, self._api_models.get("groq", "llama-3.3-70b-versatile")))
                queue.append(("openrouter", self._call_openrouter, self._api_models.get("openrouter")))
                
            queue.append(("ollama", self._call_ollama, local_target))
            
            success = False
            for route_name, route_func, route_model in queue:
                if not route_model: continue
                try:
                    if route_name == "ollama":
                        response_text = route_func(route_model, msgs, options)
                    elif route_name == "gemini":
                        response_text = route_func(route_model, msgs, images)
                    else:
                        response_text = route_func(route_model, msgs)
                        
                    model_used = f"{route_name}-{route_model}"
                    success = True
                    break
                except Exception as e:
                    logger.warning(f"Route {route_name} failed: {e}. Cascading downwards...")
                    time.sleep(1) # Brief backoff for rate limits
                    
            if not success:
               response_text = "[ERROR] All fallback APIs and Local Ollama failed."
               model_used = "failed"

        # Multi-model Consensus Check for Long-term valid trades
        if success and is_trade and not is_private and ("long term" in prompt.lower() or "weeks" in prompt.lower()):
            logger.info("Executing Trade Consensus Check via Local Ollama...")
            consensus_prompt = f"Given this trading analysis: {response_text}\nDo you strictly agree with this entry for a long-term hold? Reply YES or NO."
            consensus_msg = [{"role": "user", "content": consensus_prompt}]
            try:
                second_opinion = self._call_ollama(local_target, consensus_msg)
                response_text += f"\n\n[Secondary Offline AI Consensus (DeepSeek/Qwen)]:\n{second_opinion}"
            except Exception as e:
                logger.warning(f"Consensus check failed: {e}")

        elapsed_ms = int((time.time() - start) * 1000)
        logger.info(f"Response from {model_used} in {elapsed_ms}ms")
            
        return {
            "model": model_used,
            "response": response_text,
            "task_type": classified,
            "duration_ms": elapsed_ms,
        }

    def compress_context(self, context: list) -> list:
        """
        Summarizes the oldest N messages in a conversation history to prevent
        token overflow while retaining factual knowledge.
        """
        if len(context) <= 40:
            return context
            
        logger.info(f"[ContextCompressor] History length ({len(context)}) exceeds threshold. Compressing...")
        
        # Take the oldest 30 messages (excluding system prompt if any)
        start_idx = 1 if context and context[0].get("role") == "system" else 0
        end_idx = start_idx + 30
        
        messages_to_compress = context[start_idx:end_idx]
        recent_messages = context[end_idx:]
        
        raw_text = "\n".join([f"{m.get('role')}: {m.get('content')}" for m in messages_to_compress])
        prompt = (
            "Summarize the factual details in these conversational logs in 3-5 bullet points. "
            "Focus only on facts, user preferences, and actionable context. Omit pleasantries.\n\n"
            f"{raw_text}"
        )
        
        try:
            # Route compression to local reasoning model to save API costs
            target = self._models.get(TASK_REASONING, "qwen3:8b")
            summary = self._call_ollama(target, [{"role": "user", "content": prompt}])
            
            compressed_msg = {
                "role": "system", 
                "content": f"[Previous Context Summarized]:\n{summary}"
            }
            
            new_context = []
            if start_idx == 1:
                new_context.append(context[0])
            new_context.append(compressed_msg)
            new_context.extend(recent_messages)
            
            logger.info("[ContextCompressor] Compression successful.")
            return new_context
        except Exception as e:
            logger.error(f"[ContextCompressor] Failed to compress context: {e}")
            # Fallback: just truncate
            return context[start_idx:]

    def force_unload_all(self):
        for model in self._models.values():
            try: ollama.generate(model=model, prompt="", keep_alive=0)
            except: pass
        self._current_model = None

    def health_check(self):
        # Local ollama health check
        try:
            models = ollama.list()
            return {"status": "ok", "api_routing_enabled": self._api_enabled}
        except:
            return {"status": "error"}
