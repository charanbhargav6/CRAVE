# CRAVE AI: Master System Overview
**The 11-Phase Autonomous Agentic Assistant**

CRAVE is a highly secure, offline-first, multi-agent AI assistant designed to run exclusively on local Windows hardware. Unlike standard chat interfaces, CRAVE is an **Agentic System**—it controls your operating system, builds trading algorithms, executes hardware-level GUIs, and generates YouTube content completely autonomously.

---

## 🌟 Core capabilities
### 1. The Autonomous OS & GUI Operator
CRAVE doesn't just return text; it has "hands" through a specialized **GUI Agent**. 
* **App Control**: Automatically launches Edge/Chrome and opens specific websites.
* **Typing & Focus**: Focuses specific windows and uses `pyautogui` / `pyperclip` to instantly type or paste large generated code blocks.
* **Fail-Safe Security**: Any GUI hijacking can be instantly aborted by dragging the mouse to the top-left pixel (0,0) of the monitor.
* **Command Chaining**: The Orchestrator intercepts commands like *"Open Notepad, write python code, and save to desktop"* and generates mathematical execution trajectories for the GUI Agent to follow.

### 2. High-Fidelity Audio & Translation
* **Neural TTS**: Powered by Microsoft Edge-TTS, CRAVE responds in hyper-realistic, resonant neural voices instead of traditional robotic synthesizers. 
* **Global Translation**: You can speak to CRAVE in **any language** in the world. The `faster_whisper` engine intercepts the audio and translates it to English natively before processing the command.

### 3. Supreme Security Pipeline (L1-L4 RBAC)
* CRAVE locks down actions based on authorization. Low-tier actions (Chat) are free. Apps and File edits require a PIN. 
* Sensitive actions (Trading executions, wiping servers, password changes) require a 4-word Passphrase (L4).
* A master DPAPI-gated **Security Vault** automatically encrypts all API keys, `.env` files, and OAuth tokens directly into Windows kernel space, deleting the original plain-text files so no malicious scripts can steal them.

### 4. Self-Evolution Engine (Phase 11)
* **Autonomous Upgrades**: CRAVE actively monitors your RAM usage and available disk storage to dynamically auto-upgrade its own LLM brains when better multi-billion parameter models release.
* **Code Self-Modification**: Features an unparalleled localized CI/CD pipeline where CRAVE runs multi-model consensus checks to write new python modules, tests them in a sealed virtual environment (`.sandbox`), diffs the changes, and requests approval via a Dual-Channel Gate before permanently rewriting its own source code to `main`.
* **Dual-Channel Authentication**: Destructive infrastructure changes trigger a bi-modal prompt requiring local Face ID/L4 Passphrase overrides OR remote one-time rotating OTP codes via SMTP verifiable through Telegram.

---

## 🤖 The Multi-Agent Ecosystem

### The Trading Engine (Alpaca/ccxt)
A 5-agent pipeline that autonomously backtests and live-trades across Forex, Crypto, and Stocks. Uses `yfinance` to simulate historical P&L with scalable time intervals, overriding models dynamically via Macro News Sentiment. 

### The YouTube Creator Agent
Fully autonomous content pipeline:
1. Brainstorms niches via `ModelRouter`.
2. Scripts high-retention text and generates Image Prompts.
3. Uses the free Pollinations API to generate high-resolution vertical 9:16 images.
4. Generates a Voiceover using Edge-TTS.
5. Invokes `FFmpeg` to stitch the visual and audio into an MP4.
6. Uploads the finalized video to specific YouTube Channels securely as "Private".

### The Hacking & Security Agent
Deep integration with WSL2 (Kali Linux). Capable of running Nmap scans, performing exploit enumeration, and executing terminal commands upon L4 Authorization. 

### Additional Micro-Agents
* **Email & WhatsApp Agent**: Extracts target context and sends communications automatically.
* **Vision & Screen Agent**: Uses `mss` to capture the desktop directly into RAM (leaving zero forensic traces on disk), compressing it for the vision model via Ollama.
* **PPT & CapCut Agent**: Hooks directly into PPT generation via Python and physically drives CapCut's desktop interface to enforce editing cuts.

---

## ⚙️ The Technical Foundation
* **The Orb UI**: A highly kinetic PyQt6 GUI sphere that floats on your desktop, shifting colors, radiating sonar ripples, and captioning system logs to you in real-time. 
* **Windows Autoboot Daemon**: A deeply embedded hidden script stack (`.ps1` -> `.vbs` -> `.bat`) that wakes up Ollama and the CRAVE python pipeline totally invisibly in the background the second you log into Windows. 
* **Thermal Monitoring**: A threaded OS-level tracker polls WMI CPU thermals natively. If CRAVE's intense LLMs push the CPU past 90°C, it pauses all active computation and alerts your phone via Telegram. At 95°C, it violently shuts down the system.
* **Telegram Control Protocol**: Full remote access from your phone to `/status`, `/kill`, `/backtest`, or text normal queries to CRAVE while away from your PC.
