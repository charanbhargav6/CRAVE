# CRAVE — Development Log

This document captures the technical architecture, key design decisions, and system specifications for the CRAVE AI assistant.

---

## System Specifications

- **Target Hardware**: Intel i5-11400H, 16 GB RAM, Intel Iris Xe (integrated GPU)
- **OS**: Windows 11
- **Python**: 3.11.9 with virtual environment at `.venv/`

### Installed Ollama Models

| Model | Size | Role |
|-------|------|------|
| qwen2.5:14b | ~9 GB | Primary brain — chat, tools, coordination |
| deepseek-r1:14b | ~9 GB | Reasoning — math, trading, code analysis |
| llama3.2-vision:11b | ~7 GB | Vision — screen analysis, image understanding |

Models are loaded sequentially (16 GB RAM constraint). Vision model unloads everything else before loading.

### Additional Models

| Model | Size | Role |
|-------|------|------|
| Whisper small | 244 MB | Quick voice commands (< 30 sec) |
| Whisper medium | 500 MB | Long/technical commands (30+ sec) |

---

## Architecture Principles

1. **Event-Driven Execution** — Signals and callbacks, not constant polling. Wake word triggers voice pipeline; trade signals trigger execution.

2. **Lazy Loading** — Models and agents load only when needed, unload after. Gemma3 (vision) is never co-loaded with other models.

3. **Fail Gracefully** — If Ollama crashes → show error on Orb. If WiFi drops → cascade to offline. Module errors are isolated — never take down the whole system.

4. **Log Everything** — Every decision, error, and state change goes to `crave.log`. Security events go to `security_events.log`. Trading decisions go to `trading_live.log`.

---

## 11-Phase Build Plan

### Phase 1 — Foundation
- `config/hardware.json` — Central configuration (RAM mode, model routing, API config)
- `src/verify_env.py` — Environment verification (Ollama, models, folders, packages)

### Phase 2 — Model Router
- `src/core/model_router.py` — Hybrid routing engine
- Waterfall: Gemini → Groq → OpenRouter → Ollama (offline fallback)
- Privacy filter forces offline routing for sensitive keywords
- Tavily AI search for pre-trade news context

### Phase 3 — Voice Pipeline
- `src/core/voice.py` — OpenWakeWord + adaptive Whisper (small/medium auto-selection)
- `src/core/tts.py` — Edge-TTS primary with Kokoro → pyttsx3 fallback chain
- `src/core/audio_utils.py` — Shared audio helpers

### Phase 4 — Orchestrator
- `src/core/orchestrator.py` — Intent classification → 18+ handlers
- LangGraph-compatible state management
- 20-message sliding context window with compression
- Thread-safe Orb UI callbacks via pyqtSignal

### Phase 5 — Hybrid API Router
- Cascading API waterfall with rate-limit backoff
- Trade consensus: API result + local DeepSeek second opinion
- Strict privacy mode configurable in `hardware.json`

### Phase 5b — Security Layer
- `src/security/rbac.py` — L1-L4 tiered auth with bcrypt hashing
- `src/security/encryption.py` — DPAPI + Fernet AES-256 vault
- Cross-level password rejection, auto-idle demotion, HMAC lockdown

### Phase 6 — Orb UI
- `src/ui/orb.py` — PyQt6 floating animated orb
- 7 color states, breathing pulse, sonar ripples, cyber-glitch effects
- Silent mode: Ctrl+Shift+J → PIN gate → text input
- Draggable with position persistence

### Phase 7 — Tool Integrations
- Screen analysis (mss → vision model), browser automation (Playwright)
- CapCut UI automation, FFmpeg video processing
- File ops with security gates, PowerPoint generation
- D-ID avatar API, FastSD CPU image generation, n8n webhooks

### Phase 8 — Trading Engine
- 5-agent pipeline: Data → Strategy → Risk → Backtest → Execution
- Smart Money Concepts (FVG, Order Blocks, CHoCH, volume)
- Alpaca, Binance (ccxt), MT5 multi-exchange support
- 2% max risk, dynamic leverage scoring (A+/A/B/C setups)
- Trailing stop-loss daemon, slippage protection
- Kill-switch: closes all trades + revokes all API keys atomically

### Phase 8.1 — Telegram Remote Control
- 13 commands with Ghost Protocol (auto-delete after 30 min)
- Scheduler: 8 AM daily briefing with `/authorize` gate
- Free-text pass-through to Orchestrator

### Phase 9 — Self-Learning
- `src/agents/research_agent.py` — Auto-research loop → SKILL.md generation
- `src/core/memory_bank.py` — Trading decision journal with consistency analysis
- Knowledge persistence in `Knowledge/skills/`

### Phase 10 — Production & Autoboot
- `src/core/thermal_monitor.py` — WMI CPU temperature guard (90°C pause, 95°C halt)
- `src/core/logging_config.py` — Rotating file + console logging
- Windows autoboot: `.ps1` → `.vbs` → `.bat` hidden launch chain
- GitHub Actions CI/CD pipeline

### Phase 11 — Self-Evolution & Agentic Expansion
- `src/core/self_modifier.py` — AST-verified autonomous code patching
- `src/core/model_manager.py` — Dynamic RAM-based model upgrades
- `src/core/sandbox_runner.py` — Isolated code execution environment
- `src/core/git_safety.py` — Uncommitted change isolation
- `src/security/confirmation_gate.py` — Dual-channel SMTP OTP + Telegram verification

---

## Key Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | 14B models over 8B | Fits in 16 GB RAM sequentially, significantly better quality |
| 2 | Edge-TTS over ElevenLabs | Free, premium quality. pyttsx3 as offline fallback |
| 3 | DPAPI over .env files | Zero plaintext credentials on disk. Locked to Windows user |
| 4 | RAM guard at 2.5 GB | Prevents Ollama OOM errors during concurrent loads |
| 5 | Sequential model loading | 16 GB constraint — only one large model at a time |
| 6 | PyQt6 for UI | Transparent windows, smooth animations, native feel |
| 7 | WSL2 Kali over VirtualBox | Lighter (2 GB vs 4 GB RAM), faster startup |
| 8 | Event-driven over polling | Saves CPU, RAM, and battery on extended sessions |
| 9 | Adaptive Whisper | Small for quick commands, medium for technical content |
| 10 | Telegram exponential backoff | Prevents log spam; auto-recovers when network returns |

---

## Risk Rules (Hard-Coded)

- Max risk: 2% per position, always
- Leverage: dynamic by setup quality (A+=20×, A=15×, B=8×, C=3×)
- Absolute ceiling: 50× forex, 20× crypto
- Drawdown hits 5% → auto-revert to paper trading
- No FOMO: stale signals are always skipped
- News trading on prop firms: completely disabled
- Paper trading minimum: 4 weeks before live

---

## File Manifest

### Core Engine (`src/core/`)
| File | Description |
|------|-------------|
| `orchestrator.py` | Brain — intent classification + handler routing |
| `model_router.py` | Ollama + API waterfall + privacy filter |
| `voice.py` | Wake word + mic + Whisper STT |
| `tts.py` | TTS speech output with fallback chain |
| `audio_utils.py` | Shared audio helpers |
| `memory_bank.py` | Trading decision journal |
| `scheduler.py` | 8 AM cron + log rotation |
| `thermal_monitor.py` | CPU temp guard (WMI) |
| `logging_config.py` | Rotating file + console logging |
| `self_modifier.py` | Autonomous code patching |
| `model_manager.py` | Dynamic model upgrades |
| `sandbox_runner.py` | Isolated code execution |
| `git_safety.py` | Git change isolation |
| `knowledge_store.py` | Knowledge graph management |
| `config_watcher.py` | Live config hot-reload |
| `mcp_handler.py` | MCP server integration |
| `reasoning_log.py` | Decision transparency logging |

### Agents (`src/agents/`)
| File | Description |
|------|-------------|
| `telegram_agent.py` | 13-command remote control + Ghost Protocol |
| `research_agent.py` | Auto-learning + skill persistence |
| `screen_agent.py` | mss → vision model analysis |
| `kali_agent.py` | WSL2 Kali subprocess control |
| `ffmpeg_agent.py` | Headless video editing |
| `browser_agent.py` | Headless Chromium scraping |
| `file_agent.py` | Secure file read/write |
| `ppt_agent.py` | PowerPoint generation |
| `capcut_agent.py` | CapCut UI automation |
| `did_agent.py` | D-ID avatar video API |
| `fastsd_agent.py` | Offline image generation |
| `n8n_agent.py` | n8n webhook trigger |
| `youtube_shorts_agent.py` | Full content pipeline |
| `youtube_uploader.py` | YouTube API upload |
| `email_agent.py` | SMTP email automation |
| `whatsapp_agent.py` | WhatsApp GUI automation |
| `visual_agent.py` | Visual content generation |
| `llm_scout.py` | Model discovery + benchmarking |
| `pentagi_agent.py` | PentAGI integration |

### Security (`src/security/`)
| File | Description |
|------|-------------|
| `rbac.py` | L1-L4 auth + lockdown + idle timer |
| `encryption.py` | DPAPI + Fernet AES-256 vault |
| `face_id.py` | OpenCV LBPH biometric auth |
| `change_password.py` | L4 + 2FA password change |
| `unlock.py` | Terminal lockdown recovery |
| `telegram_gate.py` | Remote Telegram unlock |
| `confirmation_gate.py` | Dual-channel OTP verification |
| `contact_vault.py` | Encrypted contact storage |
| `threat_detector.py` | Security event analysis |
| `intruder_cam.py` | Camera capture on auth failure |

### Trading Engine (`Sub_Projects/Trading/`)
| File | Description |
|------|-------------|
| `data_agent.py` | Multi-exchange OHLCV + news feeds |
| `strategy_agent.py` | SMC analysis + FVG + pivot detection |
| `risk_agent.py` | 2% risk + ATR stop loss + drawdown |
| `execution_agent.py` | Alpaca/Binance API + trailing SL |
| `backtest_agent.py` | Historical simulation + R-multiples |

---

*Total: 60+ Python files, 8,000+ lines of production code.*
*Last updated: April 2026*
