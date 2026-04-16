<div align="center">

# 🧠 CRAVE

### **Cognitive Reasoning And Vocal Engine**

*A fully autonomous, offline-first, multi-agent AI assistant for Windows*

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2011-0078D6?logo=windows&logoColor=white)](https://microsoft.com/windows)
[![License](https://img.shields.io/badge/License-Source%20Available-green)](LICENSE)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-black?logo=data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=)](https://ollama.com)

</div>

---

## What is CRAVE?

CRAVE is a **production-grade local AI assistant** that operates as an autonomous agentic system on your Windows machine. Unlike standard chat interfaces, CRAVE controls your operating system, builds trading algorithms, executes hardware-level GUI automation, generates YouTube content, and performs security operations — all triggered by voice or text commands.

> **No cloud subscriptions. No monthly fees. Your data stays on your machine.**

---

## ✨ Core Capabilities

### 🎙️ Voice-First Interface
- **Wake Word**: Say "Hey CRAVE" to activate (OpenWakeWord, offline)
- **Speech-to-Text**: `faster_whisper` with adaptive model selection (small/medium)
- **Neural TTS**: Microsoft Edge-TTS with multi-engine fallback chain
- **Global Translation**: Speak in any language — auto-translated to English

### 🔐 Military-Grade Security (L0-L4 RBAC)
- **4-Level Authorization**: PIN → Password → Passphrase → 2FA
- **DPAPI Vault**: API keys encrypted with Windows kernel-space credentials
- **Face ID**: OpenCV LBPH recognition for biometric authentication
- **Auto-Lockdown**: Failed auth attempts trigger system-wide lockdown with Telegram alerts

### 📈 Autonomous Trading Engine
- **5-Agent Pipeline**: Data → Strategy → Risk → Backtest → Execution
- **Multi-Exchange**: Alpaca (stocks), Binance (crypto), MT5 (forex)
- **Smart Money Concepts**: FVG, CHoCH, Order Blocks, volume confirmation
- **Hard-Coded Risk Rules**: 2% max per trade, 5% trailing drawdown halt

### 🎬 Content Creation Pipeline
- **YouTube Shorts**: Niche research → Script → Voiceover → Video assembly → Upload
- **Image Generation**: Pollinations API + FastSD CPU (offline fallback)
- **FFmpeg Integration**: Video editing, subtitle overlay, audio extraction

### 🛡️ Security & Hacking
- **WSL2 Kali Linux**: Nmap, Gobuster, Hydra controlled by AI reasoning
- **Authorization Gate**: Mandatory confirmation before any offensive operation
- **Auto-Reports**: Penetration test results compiled automatically

### 🧬 Self-Evolution Engine
- **Autonomous Code Patching**: Multi-model consensus → AST verification → Sandbox testing
- **Dynamic Model Upgrades**: Monitors RAM to auto-upgrade LLM models
- **Dual-Channel Auth**: SMTP OTP + Telegram verification for destructive changes

---

## 🏗️ Architecture

```
main.py (Entry Point)
├── CRAVEOrb (PyQt6 UI)          ← Floating animated orb + status bar
├── Orchestrator (Brain)          ← Intent classification → 18+ handlers
│   ├── VoicePipeline             ← Wake word + mic + Whisper STT
│   ├── ModelRouter               ← Ollama + API waterfall routing
│   │   ├── Gemini (cloud)
│   │   ├── Groq (speed)
│   │   ├── OpenRouter (fallback)
│   │   └── Ollama (offline)
│   ├── TTS Engine                ← Edge-TTS → Kokoro → pyttsx3
│   ├── SecurityLayer             ← RBAC + DPAPI Vault + Face ID
│   └── Agents
│       ├── TelegramAgent         ← 13 remote commands + Ghost Protocol
│       ├── TradingPipeline       ← 5 agents (data/strategy/risk/exec/backtest)
│       ├── YouTubeAgent          ← Full content automation
│       ├── KaliAgent             ← WSL2 hacking operations
│       ├── ResearchAgent         ← Auto-learning + skill persistence
│       ├── ScreenAgent           ← Vision analysis via mss + LLM
│       ├── BrowserAgent          ← Headless Chromium scraping
│       ├── FileAgent             ← Secure file operations
│       └── ... (12+ more)
└── ConfigWatcher                 ← Hot-reload hardware.json
```

---

## 📁 Project Structure

```
D:\CRAVE\
├── main.py                   # Entry point — python main.py
├── config/
│   ├── hardware.json         # System configuration (models, RAM, API routing)
│   └── orb_settings.json     # UI position persistence
├── src/
│   ├── core/                 # Engine: orchestrator, model router, voice, TTS
│   ├── agents/               # 20 specialized agents
│   ├── security/             # RBAC, DPAPI vault, face ID, 2FA
│   ├── ui/                   # PyQt6 animated orb interface
│   └── tools/                # Calendar sync, weekly audit
├── Sub_Projects/
│   ├── Trading/              # 5-agent trading engine
│   └── Hacking/              # WSL2 Kali integration
├── data/                     # Runtime data (auto-generated)
├── Knowledge/                # Learned skills (auto-generated)
├── requirements.txt          # Python dependencies
└── .env.example              # API key template
```

---

## 🚀 Quick Start

### Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| **Python** | 3.11+ | Core runtime |
| **Ollama** | Latest | Local LLM inference |
| **Windows** | 10/11 | DPAPI vault, WMI thermals |
| **FFmpeg** | 6.0+ | Video processing (optional) |
| **WSL2 + Kali** | Latest | Hacking module (optional) |

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/charanbhargav6/CRAVE.git
cd CRAVE

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Ollama models
ollama pull qwen2.5:14b
ollama pull deepseek-r1:14b
ollama pull llama3.2-vision:11b

# 5. Configure environment
copy .env.example .env
# Edit .env with your API keys (Gemini, Groq, Telegram, etc.)

# 6. Configure hardware
# Edit config/hardware.json — set crave_root to your install path
# See config/hardware.example.json for reference

# 7. Launch CRAVE
python main.py
```

### First Boot

On first launch, CRAVE will:
1. Generate a new DPAPI-encrypted master key
2. Encrypt your `.env` file into the secure vault (plain-text is shredded)
3. Run the security setup wizard (set L2 PIN, L3 password, L4 passphrase)
4. Display the animated Orb UI
5. Start the voice listener and Telegram bot

---

## ⚙️ Configuration

### `config/hardware.json`

This is the central configuration file. Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `ram_gb` | 16 | Your system RAM (affects model loading strategy) |
| `concurrent_models` | false | Set `true` if you have 32GB+ RAM |
| `tts_engine` | "edge-tts" | TTS engine: "edge-tts", "kokoro", or "pyttsx3" |
| `wake_word` | "crave" | Wake word for voice activation |
| `cpu_temp_limit_celsius` | 90 | Thermal throttle threshold |
| `api_routing.enabled` | true | Enable cloud API fallback |
| `api_routing.strict_privacy_mode` | true | Force offline for sensitive queries |

See `config/hardware.example.json` for a complete template with all options.

---

## 🔐 Security Model

CRAVE uses a **5-layer security architecture**:

1. **DPAPI Encryption** — Master key tied to your Windows login
2. **NTFS ACL Lock** — Vault folder restricted to your user account only
3. **Hidden + System Attributes** — Vault files invisible in Explorer
4. **HMAC Tamper Detection** — Lockdown files cannot be silently deleted
5. **Audit Logging** — Every vault access logged to `security_events.log`

### Authorization Levels

| Level | Auth Method | Grants Access To |
|-------|-------------|------------------|
| L0 | None | View Orb UI only |
| L1 | Auto (boot) | General chat, status queries |
| L2 | 6-digit PIN | File operations, app control |
| L3 | Strong password | Network ops, script execution |
| L4 | Passphrase + 2FA | Trading, code changes, system admin |

---

## 📱 Telegram Remote Control

Control CRAVE from your phone with these commands:

| Command | Action |
|---------|--------|
| `/status` | System health report |
| `/kill` | Emergency: close all trades + revoke API keys |
| `/long` / `/short` | Override next trade direction |
| `/close` | Close all open positions |
| `/pause` / `/resume` | Toggle autonomous trading |
| `/logs` | Trading P&L summary |
| `/silent N` | Enter silent mode for N minutes |
| `/unlock` | Remote lockdown recovery |
| Any text | Passed to CRAVE as a voice command |

**Ghost Protocol**: All Telegram messages auto-delete after 30 minutes.

---

## 🖥️ Windows Autoboot

CRAVE can start automatically when you log into Windows:

```powershell
# Run as Administrator
powershell -ExecutionPolicy Bypass -File register_autoboot.ps1
```

This registers a hidden boot chain: `.ps1` → `.vbs` → `.bat` that silently starts Ollama and the CRAVE Python pipeline.

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Overview](overview.md) | High-level system capabilities |
| [PRD](PRD.md) | Product requirements & tech stack |
| [Migration Guide](MIGRATION_GUIDE.md) | Moving CRAVE to a new PC (DPAPI) |
| [YouTube OAuth](YOUTUBE_OAUTH_GUIDE.md) | Setting up YouTube upload API |
| [Development Log](DEVELOPMENT_LOG.md) | Architecture & design decisions |
| [Contributing](CONTRIBUTING.md) | How to report issues |

---

## 🛠️ Adding API Keys Securely

After your vault is initialized, use the vault adder to add new keys:

```bash
# Edit vault_adder.py — paste your keys in the placeholder
python vault_adder.py
# Keys are encrypted into the vault, plain-text version is shredded
```

> ⚠️ **Never commit API keys to git.** The `.gitignore` is configured to block all credential files.

---

## 📋 System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **RAM** | 16 GB | 32 GB |
| **Storage** | 30 GB free | 80 GB free |
| **CPU** | Any modern x86-64 | i5-11th gen or better |
| **GPU** | Not required | NVIDIA GPU for faster inference |
| **OS** | Windows 10 | Windows 11 |
| **Python** | 3.11 | 3.11.9 |
| **Internet** | Required for API routing | Optional (offline mode available) |

---

## 📄 License

This project is released under a **Source-Available License**. You may view and use the code for personal purposes. Modification and redistribution of modified versions requires written permission. See [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with 🧠 by [Charan Bhargav](https://github.com/charanbhargav6)**

*CRAVE — Your AI, Your Rules, Your Machine.*

</div>
