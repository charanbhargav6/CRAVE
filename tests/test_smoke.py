"""
CRAVE Smoke Test Suite
Run: python tests/test_smoke.py
Target: <60 seconds, catches 80% of regressions before they hit main.py

Exit code 0 = all pass, 1 = failure with exact module name + error
"""

import os
import sys
import time
import json
import traceback

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

CRAVE_ROOT = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")
os.environ["CRAVE_ROOT"] = CRAVE_ROOT

PASS = "\033[92m✅ PASS\033[0m"
FAIL = "\033[91m❌ FAIL\033[0m"

results = []


def run_test(name: str, fn):
    """Runs a single test function, catches all exceptions."""
    try:
        start = time.time()
        fn()
        elapsed = time.time() - start
        print(f"  {PASS}  {name} ({elapsed:.2f}s)")
        results.append((name, True, None))
    except Exception as e:
        print(f"  {FAIL}  {name}: {e}")
        results.append((name, False, str(e)))


# ── Test Functions ────────────────────────────────────────────────────────────


def test_core_imports():
    """Test all core module imports — catches syntax errors & missing deps."""
    from src.core import audio_utils
    from src.core import logging_config
    from src.core import memory_bank
    from src.core import model_router
    from src.core import orchestrator
    from src.core import scheduler
    from src.core import thermal_monitor
    from src.core import tts
    from src.core import voice


def test_security_imports():
    """Test security module imports."""
    from src.security import encryption
    from src.security import rbac
    from src.security import telegram_gate


def test_agent_imports():
    """Test agent module imports — catches broken agent files."""
    from src.agents import browser_agent
    from src.agents import email_agent
    from src.agents import file_agent
    from src.agents import gui_agent
    from src.agents import kali_agent
    from src.agents import research_agent
    from src.agents import screen_agent
    from src.agents import telegram_agent


def test_hardware_json():
    """Verify hardware.json loads and has critical keys."""
    config_path = os.path.join(CRAVE_ROOT, "config", "hardware.json")
    assert os.path.exists(config_path), f"hardware.json not found at {config_path}"

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    required_keys = ["ram_gb", "ollama_host", "models", "whisper", "wake_word"]
    for key in required_keys:
        assert key in cfg, f"Missing required key: {key}"

    assert "primary" in cfg["models"], "Missing models.primary"
    assert "reasoning" in cfg["models"], "Missing models.reasoning"


def test_ollama_ping():
    """Ping Ollama API — catches dead model server."""
    import requests

    host = "http://127.0.0.1:11434"
    try:
        resp = requests.get(f"{host}/api/tags", timeout=5)
        assert resp.status_code == 200, f"Ollama returned {resp.status_code}"
    except requests.ConnectionError:
        raise AssertionError(
            "Ollama is not running! Start it with: ollama serve"
        )


def test_credentials_exist():
    """Verify encrypted credentials file exists."""
    # Check all known vault locations
    candidates = [
        os.path.join(CRAVE_ROOT, ".env.enc"),
        os.path.join(CRAVE_ROOT, "data", "vault", ".env.enc"),
        os.path.join(CRAVE_ROOT, "data", "vault", "credentials.json.enc"),
        os.path.join(CRAVE_ROOT, "data", "credentials.json.enc"),
        os.path.join(CRAVE_ROOT, "config", "creds.enc"),
    ]
    
    found = [p for p in candidates if os.path.exists(p)]
    if not found:
        raise AssertionError(
            "No encrypted credentials found in any known location. "
            f"Checked: {', '.join(os.path.basename(p) for p in candidates)}"
        )


def test_tts_init():
    """Verify TTS engine initializes without crash (silent check)."""
    from src.core.tts import tts_status, set_silent_mode

    set_silent_mode(True)  # Don't actually speak
    status = tts_status()
    # We only need to verify the module loaded — audio hardware may not be available in CI
    assert isinstance(status, dict), "tts_status() did not return a dict"
    assert "silent_mode" in status, "tts_status() missing silent_mode key"


def test_memory_bank():
    """Verify MemoryBank JSON DB creates and reads properly."""
    from src.core.memory_bank import MemoryBank

    mb = MemoryBank()
    # Should not crash, should create db files if missing
    assert os.path.exists(mb.db_file), f"Trading memory DB not found at {mb.db_file}"
    assert os.path.exists(mb.task_db_file), f"Task memory DB not found at {mb.task_db_file}"

    # Read test
    stats = mb.analyze_consistency()
    assert isinstance(stats, dict), "analyze_consistency() did not return a dict"


def test_screen_capture():
    """Verify mss can capture at least one monitor."""
    try:
        import mss

        with mss.mss() as sct:
            monitors = sct.monitors
            assert len(monitors) > 0, "No monitors detected by mss"
            # Capture a tiny region to verify it works
            region = {"top": 0, "left": 0, "width": 10, "height": 10}
            img = sct.grab(region)
            assert img is not None, "mss.grab() returned None"
    except ImportError:
        raise AssertionError("mss not installed: pip install mss")


def test_telegram_token_format():
    """Verify Telegram token exists and has valid format (if configured)."""
    # Load env vars from vault
    try:
        from src.security.encryption import crypto_manager
        crypto_manager.decrypt_env_to_memory()
    except Exception:
        pass  # Vault may not be decryptable without master key in CI

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if token:
        # Telegram tokens are formatted as: <numbers>:<alphanumeric>
        parts = token.split(":")
        assert len(parts) == 2, f"Telegram token has wrong format: expected 2 parts, got {len(parts)}"
        assert parts[0].isdigit(), "Telegram token first part should be numeric"
        assert len(parts[1]) > 10, "Telegram token second part too short"

    if chat_id:
        # Chat IDs may be negative (groups) or positive (users)
        clean = chat_id.lstrip("-")
        assert clean.isdigit(), f"TELEGRAM_CHAT_ID is not numeric: {chat_id}"


def test_risk_agent_mock():
    """Mock a trade signal through RiskAgent to catch type errors."""
    try:
        from Sub_Projects.Trading.risk_agent import RiskAgent
        import pandas as pd
        import numpy as np

        risk = RiskAgent()

        # Create minimal mock OHLCV data
        dates = pd.date_range("2026-01-01", periods=100, freq="h")
        df = pd.DataFrame({
            "open": np.random.uniform(1800, 1900, 100),
            "high": np.random.uniform(1900, 2000, 100),
            "low": np.random.uniform(1700, 1800, 100),
            "close": np.random.uniform(1800, 1900, 100),
            "volume": np.random.uniform(1000, 5000, 100),
        }, index=dates)

        signal = {
            "action": "buy",
            "price": 1850.0,
            "is_swing_trade": False,
        }

        result = risk.validate_trade_signal(100.0, signal, df)
        assert isinstance(result, dict), "validate_trade_signal() did not return a dict"
        assert "approved" in result, "Result missing 'approved' key"
    except ImportError:
        # Trading module may not be fully installed
        pass


# ── Main Runner ───────────────────────────────────────────────────────────────


def main():
    start_time = time.time()
    print("\n" + "=" * 60)
    print("  🧪 CRAVE SMOKE TEST SUITE")
    print("=" * 60 + "\n")

    tests = [
        ("Core Module Imports", test_core_imports),
        ("Security Module Imports", test_security_imports),
        ("Agent Module Imports", test_agent_imports),
        ("hardware.json Validation", test_hardware_json),
        ("Ollama Ping", test_ollama_ping),
        ("Encrypted Credentials", test_credentials_exist),
        ("TTS Engine Init", test_tts_init),
        ("MemoryBank DB", test_memory_bank),
        ("Screen Capture (mss)", test_screen_capture),
        ("Telegram Token Format", test_telegram_token_format),
        ("RiskAgent Mock Signal", test_risk_agent_mock),
    ]

    for name, fn in tests:
        run_test(name, fn)

    elapsed = time.time() - start_time

    # Summary
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    total = len(results)

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed, {failed} failed  ({elapsed:.1f}s)")

    if failed > 0:
        print(f"\n  Failed tests:")
        for name, ok, err in results:
            if not ok:
                print(f"    ❌ {name}: {err}")
        print(f"{'=' * 60}\n")
        sys.exit(1)
    else:
        print(f"  All systems nominal. Safe to run main.py.")
        print(f"{'=' * 60}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
