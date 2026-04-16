# CRAVE: Comprehensive Product Requirements Document (PRD)

## 1. Product Overview
**Project Name:** CRAVE  
**Product Vision:** A highly autonomous, production-grade local AI assistant. CRAVE acts not merely as a chatbot, but as an agentic operating system orchestrator capable of managing daily tasks, creating autonomous content pipelines (YouTube), executing financial strategies, monitoring PC thermals, and evolving its own source code through rigorous multi-model consensus and sandbox testing.

**Target Environment:** Local Windows Workstation, running 24/7 as a background service with a minimal, floating GUI.

---

## 2. System Architecture & Tech Stack

CRAVE is structured into modular layers allowing seamless swapping of AI models while retaining rigid security.

### 2.1 Core Stack
*   **Operating Model:** Multi-Threaded Queue Architecture
*   **Primary Language:** Python 3.11
*   **UI Framework:** PyQt6 (Frameless, Custom Painted Event loops)
*   **Vision & Hardware:** `opencv-contrib-python` (Face ID), `mss` (Screen Agent), `customtkinter`
*   **Data Broker:** PyYAML, JSON, SQLite

### 2.2 The Neural Pipeline
*   **Wake Word Engine:** `openwakeword` (ONNX runtime) — Ultra-fast, offline.
*   **Speech-to-Text (STT):** `faster-whisper` (CTranslate2) — Local offline transcribing.
*   **Model Router (The Brain):** A cascading intelligence switchboard:
    *   *Primary Ops:* Locally-hosted Ollama (e.g., `qwen2.5:14b`)
    *   *Complex Chains:* Groq API / OpenRouter
    *   *Multimodal / Screen:* Google Gemini / Groq Vision
*   **Text-to-Speech (TTS):** Edge-TTS (Primary) and Kokoro (Local Fallback)

---

## 3. Core Features & Modularity

### 3.1 Advanced Sub-Agents
1.  **Lead Orchestrator:** Manages state, routes intents, tracks history, and manages context compression via local AI summaries.
2.  **Trading Execution Engine (Phase 8):** Listens to mathematical models to execute rapid API calls (Alpaca/Binance), featuring a local background Trailing Stop-Loss algorithm and a 60-second "Dead Man's Switch".
3.  **YouTube Automation Agent (Phase 11):** Niche research, script generation, audio TTS generation, B-Roll fetching, and FFmpeg video assembly directly into a finished product.
4.  **Security & Cryptography (L1 / L2 / L3 Access):**
    *   `L1`: System boot (Encrypted `.env` injection via Windows DPAPI).
    *   `L2`: Adaptive Face Recognition (LBPH via OpenCV CLAHE) unlocking the silent-mode portal.
    *   `L3`: External Destructive Commands — Validated via SMTP Telegram bots.
5.  **Self-Evolution Engine (Phase 11):** CRAVE can rewrite its own code. It parses user intent, queries an advanced model (e.g., Sonnet 3.5), passes the patch through an AST (Abstract Syntax Tree) safety scanner, and merges diffs automatically.

---

## 4. Stability & Security Hardening
CRAVE is designed for 100% 24/7 uptime without degradation.

*   **Hot-Reloading:** `watchdog` monitors `hardware.json` so parameters (Face ID tolerance, CPU warnings) can be updated live without restarting the daemon.
*   **VRAM Management (Garbage Collection):** Scheduled 4-hour checks automatically flush `ollama.exe` from VRAM if the system is idle, mathematically destroying Python/Torch memory leaks.
*   **Thermal Monitoring:** Polls OS WMI to monitor Motherboard/CPU temperatures, engaging Silent Mode if the system throttles.
*   **Sandbox CI/CD Protection:** The self-modifier executes raw changes only inside an isolated `.venv` clone to verify syntax via `flake8` before merging to the primary node.
*   **Context Token Compression:** Long sessions automatically collapse the oldest 30 prompts into a 3-bullet factual summary using a secondary local LLM, capping memory limits while preserving facts.

---

## 5. Non-Functional Requirements (NFRs)
1.  **Latency:** Wake word to STT routing must occur in < 400ms.
2.  **Security:** Absolute ZERO plain-text API credentials on the hard drive. All keys are dynamically loaded into memory via DPAPI during engine startup.
3.  **Offline Capability:** The Orchestrator must be able to fall back to `Ollama`, `openwakeword`, and `Kokoro` if the outbound internet connection dies (Privacy Mode).
4.  **Extensibility:** New agents must sub-class `BaseAgent` and be wired into `classify_intent` without modifying the core STT loop.

---

## 6. Official Sign-off
**Status:** ALL PHASES COMPLETE AND INTEGRATED.
**Conflicts:** 0 Remaining. (Hot-reloading, face recognition, and UI math bounds manually aligned in Version 1.0.0).
**Deployment Readiness:** 10/10. Ready for headless daemonization or user-managed execution via `main.py`.
