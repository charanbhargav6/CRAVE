# CRAVE — Project State Manifest (Single Source of Truth)

## System Score: 68/100 (up from 62 after Phase A+B hardening)

## What Actually Works (Verified in Logs)
- ✅ PyQt6 Orb UI — EQ wave visualizer, terminal, system tray, CPU/RAM metrics
- ✅ DPAPI Vault — Encrypts/decrypts API keys, injects 9 keys into os.environ
- ✅ Face ID — LBPH recognition confirmed (distance=40.50, auto-elevates to L2)
- ✅ Model Router — Waterfall: Gemini→Groq→OpenRouter→Ollama with privacy filter
- ✅ API Key Loading — Fixed race condition; reinit_api_clients() runs after vault decrypt
- ✅ Backtest Engine v9.3 — R-multiple, Monte Carlo, asset-specific ATR, trend filtering
- ✅ Telegram Bot — 13 commands, Ghost Protocol, now with error handler + retry backoff
- ✅ TTS — Edge-TTS primary with fallback chain: Kokoro→pyttsx3→console print
- ✅ Ollama RAM Guard — Pre-checks available RAM before model load, force-unloads if low
- ✅ Thermal Monitor — WMI-based CPU temperature daemon
- ✅ Config Hot-Reload — ConfigWatcher detects hardware.json changes live
- ✅ Self-Evolution Engine — AST-verified code patching with sandbox + git safety
- ✅ Context Compression — Token-aware context window management
- ✅ Learning + Skill Persistence — _handle_learn now saves skills via ResearchAgent

## What Needs Runtime Verification (Code Exists, Untested E2E)
- ⚠️ Voice Wake Word — Whisper + openwakeword code present, needs E2E voice test
- ⚠️ Screen Analysis — Vision pipeline exists, never triggered in logs
- ⚠️ Live Trading — 5-agent pipeline coded, needs paper trade week
- ⚠️ WhatsApp Agent — pyautogui automation, never tested
- ⚠️ Email Agent — SMTP wrapper (syntax error fixed), needs SMTP creds test
- ⚠️ Self-Modifier Auto-Recovery — Invoked on crash, effectiveness unverified

## What's Missing (No Code)
- ❌ Hacking Module — `Sub_Projects/Hacking/` is empty
- ❌ ChromaDB Vector Search — Mentioned in plans, never imported or implemented
- ❌ Dead Man's Switch — Listed in Phase 10 TODO, never built
- ❌ YouTube Shorts Pipeline — Agent file exists, never executed
- ❌ Unit Tests for Trading — Zero test coverage on position sizing / risk logic

## Core Architecture
### Processing (`src/core/`)
- `orchestrator.py` — 1,700+ lines. Intent classification → 18+ handlers. Auto-recovery, adaptive personality.
- `model_router.py` — Hybrid API waterfall + Ollama local. RAM guard prevents OOM. API diagnostic logging.
- `tts.py` — 4-engine fallback chain: Edge-TTS → Kokoro → pyttsx3 → console
- `self_modifier.py` — AST-verified autonomous code patcher with sandbox + git safety

### UI (`src/ui/`)
- `orb.py` — PyQt6 FRIDAY-style dashboard. EQ wave visualizer + terminal + system tray.

### Agents (`src/agents/`)
- `telegram_agent.py` — Ghost Protocol, 13 commands, error handler + exponential backoff retry
- `research_agent.py` — Skills persistence to `Knowledge/skills/`. Reuses orchestrator's router.
- `visual_agent.py` — DuckDuckGo → Pollinations → matplotlib fallback chain
- `email_agent.py` — SMTP with ML success prediction (syntax error fixed)

### Security (`src/security/`)
- `encryption.py` — DPAPI vault, Fernet encryption, NTFS ACL lockdown
- `rbac.py` — 5-level auth (L0-L4), bcrypt PIN, idle timeout
- `face_id.py` — OpenCV LBPH with 2-hour recheck cycle

## Hardware Config
| Key | Value |
|-----|-------|
| Models (Installed) | qwen2.5:14b, deepseek-r1:14b, llama3.2-vision:11b |
| RAM | 16GB (sequential loading, 2.5GB headroom enforced) |
| TTS Engine | edge-tts (online) with pyttsx3 fallback (offline) |
| Ollama Host | http://127.0.0.1:11434 |

## Recent Fixes (2026-04-13 Phase A+B)
1. **API key race condition** — reinit_api_clients() after vault decrypt
2. **Telegram crash recovery** — Error handler + retry loop (5→60s backoff)
3. **TTS offline fallback** — 4-engine cascade, never goes mute
4. **Ollama RAM guard** — psutil pre-check, force-unload if <2.5GB free
5. **Dual singleton removed** — Cleaned dead get_orchestrator() from orb.py
6. **Learning persistence** — _handle_learn now saves skills via ResearchAgent
7. **ResearchAgent router** — Reuses orchestrator's router (has vault keys)
8. **email_agent.py syntax** — Fixed stray `import time` breaking class body
9. **62/62 py_compile clean** — Zero syntax errors across entire codebase

## Decision Log
| Decision | Rationale |
|----------|-----------|
| 14B models over 8B | User freed 35GB space. 14B fits in 16GB RAM sequentially. |
| Edge-TTS over ElevenLabs | Free, premium quality. pyttsx3 as offline fallback. |
| DPAPI over .env files | Zero plaintext credentials on disk. Locked to Windows user. |
| RAM guard at 2.5GB | Prevents Ollama status 500 OOM on 16GB during concurrent loads. |
| Telegram exponential backoff | Prevents log spam; auto-recovers when network returns. |

---
*Last updated: 2026-04-13. Phase A+B hardening complete. 62/62 files compile clean.*
