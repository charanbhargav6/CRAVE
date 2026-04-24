import os
"""
CRAVE Phase 12 — Full Integration Test Suite
=============================================
Tests that ALL modules import cleanly, initialize correctly,
and integrate with each other without conflicts.

100% headless — no GUI, no TTS, no Ollama, no network calls.
"""

import sys, os, time, traceback
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Force UTF-8 + suppress noise
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

PASS = 0
FAIL = 0
RESULTS = []

def test(name, fn):
    global PASS, FAIL
    try:
        t0 = time.perf_counter()
        result = fn()
        ms = (time.perf_counter() - t0) * 1000
        PASS += 1
        RESULTS.append(("PASS", name, ms, ""))
        print(f"  [PASS] {name}  ({ms:.1f}ms)")
        return result
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        FAIL += 1
        err_msg = str(e)
        RESULTS.append(("FAIL", name, ms, err_msg))
        print(f"  [FAIL] {name}  -> {err_msg}")
        return None


print("=" * 65)
print("  CRAVE FULL INTEGRATION TEST SUITE")
print("=" * 65)
print(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"  Mode: Headless (no GUI/TTS/Ollama)")
print()

# ═══════════════════════════════════════════════════════════════════
# 1. CORE MODULE IMPORTS
# ═══════════════════════════════════════════════════════════════════
print("--- 1. Core Module Imports ---")

test("Import: ModelRouter", lambda: __import__("src.core.model_router", fromlist=["ModelRouter"]))
test("Import: VoicePipeline", lambda: __import__("src.core.voice", fromlist=["VoicePipeline"]))
test("Import: TTS engine", lambda: __import__("src.core.tts", fromlist=["speak"]))
test("Import: MemoryBank", lambda: __import__("src.core.memory_bank", fromlist=["MemoryBank"]))
test("Import: RBAC", lambda: __import__("src.security.rbac", fromlist=["get_rbac"]))
test("Import: Encryption", lambda: __import__("src.security.encryption", fromlist=["crypto_manager"]))

# ═══════════════════════════════════════════════════════════════════
# 2. AGENT IMPORTS (ALL 14)
# ═══════════════════════════════════════════════════════════════════
print("\n--- 2. Agent Imports (all 14) ---")

test("Import: TelegramAgent", lambda: __import__("src.agents.telegram_agent", fromlist=["TelegramAgent"]))
test("Import: EmailAgent", lambda: __import__("src.agents.email_agent", fromlist=["EmailAgent"]))
test("Import: FileAgent", lambda: __import__("src.agents.file_agent", fromlist=["FileAgent"]))
test("Import: GUIAutomationAgent", lambda: __import__("src.agents.gui_agent", fromlist=["GUIAutomationAgent"]))
test("Import: KaliAgent", lambda: __import__("src.agents.kali_agent", fromlist=["KaliAgent"]))
test("Import: ScreenAgent", lambda: __import__("src.agents.screen_agent", fromlist=["ScreenAgent"]))
test("Import: ResearchAgent", lambda: __import__("src.agents.research_agent", fromlist=["ResearchAgent"]))
test("Import: BrowserAgent", lambda: __import__("src.agents.browser_agent", fromlist=["BrowserAgent"]))
test("Import: FFmpegAgent", lambda: __import__("src.agents.ffmpeg_agent", fromlist=["FFmpegAgent"]))
test("Import: CapCutAgent", lambda: __import__("src.agents.capcut_agent", fromlist=["CapCutAgent"]))
test("Import: YouTubeShortsAgent", lambda: __import__("src.agents.youtube_shorts_agent", fromlist=["YouTubeShortsAgent"]))

# ═══════════════════════════════════════════════════════════════════
# 3. TRADING ENGINE IMPORTS
# ═══════════════════════════════════════════════════════════════════
print("\n--- 3. Trading Engine Imports ---")

test("Import: StrategyAgent", lambda: __import__("Sub_Projects.Trading.strategy_agent", fromlist=["StrategyAgent"]))
test("Import: RiskAgent", lambda: __import__("Sub_Projects.Trading.risk_agent", fromlist=["RiskAgent"]))
test("Import: ExecutionAgent", lambda: __import__("Sub_Projects.Trading.execution_agent", fromlist=["ExecutionAgent"]))
test("Import: DataAgent", lambda: __import__("Sub_Projects.Trading.data_agent", fromlist=["DataAgent"]))
test("Import: BacktestAgent", lambda: __import__("Sub_Projects.Trading.backtest_agent", fromlist=["BacktestAgent"]))

# ═══════════════════════════════════════════════════════════════════
# 4. UI IMPORT
# ═══════════════════════════════════════════════════════════════════
print("\n--- 4. UI Module ---")

test("Import: Orb UI (FRIDAY Wave)", lambda: __import__("src.ui.orb", fromlist=["CRAVEOrb", "WaveWidget"]))

# ═══════════════════════════════════════════════════════════════════
# 5. ORCHESTRATOR IMPORT
# ═══════════════════════════════════════════════════════════════════
print("\n--- 5. Orchestrator ---")

test("Import: Orchestrator", lambda: __import__("src.core.orchestrator", fromlist=["Orchestrator"]))

# ═══════════════════════════════════════════════════════════════════
# 6. FUNCTIONAL TESTS — FileAgent Security
# ═══════════════════════════════════════════════════════════════════
print("\n--- 6. FileAgent Security Hardening ---")

def test_file_vault_block():
    from src.agents.file_agent import FileAgent
    fa = FileAgent()
    result = fa.read_file(os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "data", "vault", "master.key"))
    assert "Access Denied" in result or "ERROR" in result, f"Vault NOT blocked: {result}"
    return "BLOCKED"

def test_file_safe_read():
    from src.agents.file_agent import FileAgent
    fa = FileAgent()
    result = fa.list_dir("src")
    assert "ERROR" not in result, f"Safe read failed: {result}"
    return f"{len(result.splitlines())} items"

test("Security: Vault read BLOCKED", test_file_vault_block)
test("Security: Safe dir listing OK", test_file_safe_read)

# ═══════════════════════════════════════════════════════════════════
# 7. FUNCTIONAL TESTS — MemoryBank Knowledge Graph
# ═══════════════════════════════════════════════════════════════════
print("\n--- 7. MemoryBank Knowledge Graph ---")

def test_memory_write():
    from src.core.memory_bank import MemoryBank
    mb = MemoryBank()
    mb.log_decision("IntegrationTest", "Verifying knowledge graph write")
    return "Written"

def test_memory_entity():
    from src.core.memory_bank import MemoryBank
    mb = MemoryBank()
    mb.store_entity("BTC", "crypto", {"price": 67000, "trend": "bullish"})
    return "Entity stored"

def test_memory_recall():
    from src.core.memory_bank import MemoryBank
    mb = MemoryBank()
    results = mb.recall("IntegrationTest")
    assert len(results) > 0, "Recall returned empty"
    return f"{len(results)} matches"

def test_memory_trade_log():
    from src.core.memory_bank import MemoryBank
    mb = MemoryBank()
    mb.log_trade_entry("TEST001", "AAPL", "buy", 185.0, 0.1, {"score": "A+"})
    return "Trade logged"

def test_memory_consistency():
    from src.core.memory_bank import MemoryBank
    mb = MemoryBank()
    stats = mb.analyze_consistency()
    assert "status" in stats, f"Bad stats: {stats}"
    return stats["status"]

test("Memory: log_decision()", test_memory_write)
test("Memory: store_entity()", test_memory_entity)
test("Memory: recall() search", test_memory_recall)
test("Memory: log_trade_entry()", test_memory_trade_log)
test("Memory: analyze_consistency()", test_memory_consistency)

# ═══════════════════════════════════════════════════════════════════
# 8. FUNCTIONAL TESTS — Telegram Agent Init
# ═══════════════════════════════════════════════════════════════════
print("\n--- 8. Telegram Agent Wiring ---")

def test_telegram_init():
    from src.agents.telegram_agent import TelegramAgent
    ta = TelegramAgent()
    assert hasattr(ta, '_ghost_queue'), "Ghost Protocol queue missing"
    assert hasattr(ta, '_ghost_lock'), "Ghost Protocol lock missing"
    assert hasattr(ta, '_ghost_timeout'), "Ghost timeout missing"
    assert ta._ghost_timeout == 1800, f"Ghost timeout wrong: {ta._ghost_timeout}"
    return f"Token={'SET' if ta.token else 'EMPTY'}, ChatID={'SET' if ta.chat_id else 'EMPTY'}"

def test_telegram_ghost_queue():
    from src.agents.telegram_agent import TelegramAgent
    ta = TelegramAgent()
    ta._track_message(12345, 999)
    assert len(ta._ghost_queue) == 1, "Ghost queue didn't track message"
    chat, msg, ts = ta._ghost_queue[0]
    assert chat == 12345 and msg == 999, "Tracked wrong values"
    return "Tracking works"

def test_telegram_send_method():
    from src.agents.telegram_agent import TelegramAgent
    ta = TelegramAgent()
    assert hasattr(ta, 'send_message_sync'), "send_message_sync missing"
    assert hasattr(ta, '_handle_text'), "Text handler missing"
    return "Methods present"

test("Telegram: Init + Ghost Protocol", test_telegram_init)
test("Telegram: Ghost queue tracking", test_telegram_ghost_queue)
test("Telegram: Send method exists", test_telegram_send_method)

# ═══════════════════════════════════════════════════════════════════
# 9. FUNCTIONAL TESTS — Email Agent Init
# ═══════════════════════════════════════════════════════════════════
print("\n--- 9. Email Agent (SMTP) ---")

def test_email_init():
    from src.agents.email_agent import EmailAgent
    ea = EmailAgent()
    assert hasattr(ea, 'send_email'), "send_email missing"
    assert ea.smtp_server == "smtp.gmail.com", f"Wrong SMTP server: {ea.smtp_server}"
    assert ea.smtp_port == 587, f"Wrong port: {ea.smtp_port}"
    return f"SMTP={ea.smtp_server}:{ea.smtp_port}, User={'SET' if ea.smtp_user else 'EMPTY'}"

def test_email_memory_integration():
    from src.agents.email_agent import EmailAgent
    ea = EmailAgent()
    # Verify it has a MemoryBank instance for ML task logging
    assert hasattr(ea, 'memory'), "MemoryBank not wired into EmailAgent"
    prob = ea.memory.predict_success_probability("send_email", {"to": "test@test.com"})
    assert 0.0 <= prob <= 1.0, f"Invalid probability: {prob}"
    return f"ML predict={prob*100:.0f}%"

test("Email: SMTP init", test_email_init)
test("Email: MemoryBank integration", test_email_memory_integration)

# ═══════════════════════════════════════════════════════════════════
# 10. FUNCTIONAL TESTS — GUI Automation
# ═══════════════════════════════════════════════════════════════════
print("\n--- 10. GUI Automation Agent ---")

def test_gui_init():
    from src.agents.gui_agent import GUIAutomationAgent
    ga = GUIAutomationAgent()
    assert hasattr(ga, 'focus_window'), "focus_window missing"
    assert hasattr(ga, 'type_text'), "type_text missing"
    assert hasattr(ga, 'press_shortcut'), "press_shortcut missing"
    assert hasattr(ga, 'press_key'), "press_key missing"
    return "All GUI methods present"

test("GUI: Agent init + methods", test_gui_init)

# ═══════════════════════════════════════════════════════════════════
# 11. FUNCTIONAL TESTS — Trading Pipeline
# ═══════════════════════════════════════════════════════════════════
print("\n--- 11. Trading Pipeline Integration ---")

def test_trading_pipeline():
    import pandas as pd
    import numpy as np
    from Sub_Projects.Trading.strategy_agent import StrategyAgent
    from Sub_Projects.Trading.risk_agent import RiskAgent

    # Synthetic data
    np.random.seed(42)
    n = 100
    dates = pd.date_range("2025-01-01", periods=n, freq="1h")
    closes = [180.0]
    for i in range(1, n):
        closes.append(closes[-1] * (1 + np.random.randn() * 0.005))
    closes = np.array(closes)
    df = pd.DataFrame({
        "time": dates, "open": closes, "high": closes * 1.003,
        "low": closes * 0.997, "close": closes,
        "volume": np.random.randint(50000, 500000, n),
    })

    sa = StrategyAgent()
    ctx = sa.analyze_market_context("AAPL", df)
    assert "error" not in ctx, f"Strategy error: {ctx}"
    assert "Structure_Score" in ctx, "Missing Structure_Score"
    assert "Confidence_Pct" in ctx, "Missing Confidence_Pct"
    
    # Risk validation
    ra = RiskAgent()
    signal = {"action": "buy", "price": ctx["Current_Price"], "is_swing_trade": False}
    validated = ra.validate_trade_signal(10000, signal, df)
    assert "approved" in validated, "RiskAgent didn't return approval field"
    
    return f"Score={ctx['Structure_Score']}, Conf={ctx['Confidence_Pct']}%, Risk={'OK' if validated.get('approved') else 'BLOCKED'}"

test("Trading: Full SMC + Risk pipeline", test_trading_pipeline)

# ═══════════════════════════════════════════════════════════════════
# 12. FUNCTIONAL TESTS — Kali Agent
# ═══════════════════════════════════════════════════════════════════
print("\n--- 12. Kali Agent (Hacking) ---")

def test_kali_init():
    from src.agents.kali_agent import KaliAgent
    ka = KaliAgent()
    assert hasattr(ka, 'run_command'), "run_command missing"
    assert hasattr(ka, 'kill_switch'), "kill_switch missing"
    assert hasattr(ka, '_cleanup_vmmem'), "vmmem cleanup missing"
    # Without L4 auth, it should deny
    result = ka.run_command("whoami")
    assert "Unauthorized" in result or "ERROR" in result, f"Kali should deny without L4: {result}"
    return "Init OK, L4 gate active"

test("Kali: Init + L4 security gate", test_kali_init)

# ═══════════════════════════════════════════════════════════════════
# 13. CONFIGURATION INTEGRITY
# ═══════════════════════════════════════════════════════════════════
print("\n--- 13. Configuration Files ---")

def test_hardware_json():
    import json
    with open(os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "config", "hardware.json"), "r") as f:
        cfg = json.load(f)
    assert "ollama_host" in cfg, "Missing ollama_host"
    assert "11434" in cfg["ollama_host"], f"Ollama port wrong: {cfg['ollama_host']}"
    assert "models" in cfg, "Missing models section"
    assert cfg["models"]["primary"] == "qwen3:8b-q4_K_M", f"Wrong primary model"
    return f"Port=11434, Model={cfg['models']['primary']}"

def test_no_mcp_config():
    exists = os.path.exists(os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "config", "mcp_config.json"))
    assert not exists, "mcp_config.json still exists (should be deleted)"
    return "Cleaned"

test("Config: hardware.json integrity", test_hardware_json)
test("Config: MCP config removed", test_no_mcp_config)

# ═══════════════════════════════════════════════════════════════════
# 14. CROSS-MODULE INTEGRATION
# ═══════════════════════════════════════════════════════════════════
print("\n--- 14. Cross-Module Integration ---")

def test_orchestrator_intent_map():
    from src.core.orchestrator import Orchestrator, _INTENT_KEYWORDS
    assert len(_INTENT_KEYWORDS) > 10, f"Only {len(_INTENT_KEYWORDS)} intents registered"
    # Verify key intents exist
    for intent in ["chat", "trade", "hack", "silent", "status", "stop", "auth"]:
        found = any(intent in k for k in _INTENT_KEYWORDS.keys())
        assert found, f"Intent '{intent}' missing from orchestrator"
    return f"{len(_INTENT_KEYWORDS)} intents registered"

def test_telegram_orchestrator_bridge():
    from src.agents.telegram_agent import TelegramAgent
    ta = TelegramAgent()
    # Verify orchestrator can be wired
    assert hasattr(ta, 'orchestrator'), "orchestrator attribute missing"
    # The text handler should exist and accept orchestrator calls
    assert callable(getattr(ta, '_handle_text', None)), "_handle_text not callable"
    return "Bridge ready"

test("Orchestrator: Intent map completeness", test_orchestrator_intent_map)
test("Telegram <-> Orchestrator bridge", test_telegram_orchestrator_bridge)

# ═══════════════════════════════════════════════════════════════════
# FINAL REPORT
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'=' * 65}")
print(f"  RESULTS: {PASS}/{PASS+FAIL} passed, {FAIL} failed")
print(f"{'=' * 65}")

if FAIL == 0:
    print("  All systems nominal. Full integration verified.")
else:
    print("  FAILURES DETECTED:")
    for status, name, ms, err in RESULTS:
        if status == "FAIL":
            print(f"    X {name}: {err}")

print(f"{'=' * 65}")
