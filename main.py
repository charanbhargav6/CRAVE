"""
CRAVE — Main Entry Point
Save to: D:\\CRAVE\\main.py

Launches the CRAVE Orb UI and connects it to the Orchestrator.
Run: python main.py

Architecture:
  main.py
    → CRAVEOrb (UI)          ← PyQt6 floating window
    → Orchestrator (brain)    ← routes commands, manages agents
      → VoicePipeline         ← wake word + mic + Whisper
      → ModelRouter            ← Ollama + API waterfall
      → TTS                   ← Kokoro speech
"""

import os
import sys

# Change HuggingFace cache to D: drive before ANY module imports huggingface_hub
os.environ["HF_HOME"] = "D:\\CRAVE\\models\\huggingface"

import threading

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# CRITICAL: Pre-load openwakeword before any other module loads CUDA/DLLs
# This prevents DLL initialization conflicts with faster_whisper/ctranslate2
try:
    import openwakeword  # noqa: F401 — forces onnxruntime DLLs to load first
except Exception:
    pass

from src.ui.orb import CRAVEOrb
from src.core.orchestrator import get_orchestrator
from src.core.logging_config import setup_logging

from PyQt6.QtWidgets import QApplication


def main():
    # Initialize logging FIRST — all modules log to file from this point
    setup_logging()

    # 0. Start watching hardware.json for hot-reloads
    try:
        from src.core.config_watcher import ConfigWatcher
        watcher = ConfigWatcher()
        watcher.start_watching(os.path.join("D:\\CRAVE", "config", "hardware.json"))
    except Exception as e:
        print(f"Warning: Hot-reload watcher failed to start: {e}")

    print("=" * 50)
    print("  CRAVE 2026 — Starting Up...")
    print("=" * 50)

    # 1. Create Qt Application
    app = QApplication.instance() or QApplication(sys.argv)

    # 2. Create the Orb UI
    orb = CRAVEOrb()

    # 3. Create the Orchestrator
    orchestrator = get_orchestrator()

    # 4. Connect Orb ↔ Orchestrator
    orb.set_orchestrator(orchestrator)

    # Wire callbacks: Orchestrator → Orb (thread-safe via signals)
    orchestrator.set_callbacks(
        state_change=orb.set_state,
        command_received=orb.show_user_command,
        response=orb.show_crave_reply,
        wake=orb.show_bar,
    )

    # 5. Show the Orb
    orb.show()
    print("[Main] Orb UI visible")

    # 6. Start Orchestrator in background (voice + command loop)
    def start_orchestrator():
        try:
            orchestrator.start()
        except Exception as e:
            print(f"[Main] Orchestrator startup error: {e}")
            orb.set_state("error")
            orb.show_crave_reply(f"Startup error: {e}")

    t = threading.Thread(target=start_orchestrator, daemon=True, name="CRAVEStart")
    t.start()

    # 7. Run the Qt event loop (blocks until window closed)
    print("[Main] CRAVE is running. Close the Orb window to exit.")
    exit_code = app.exec()

    # 8. Cleanup
    print("[Main] Shutting down...")
    orchestrator.stop()
    os._exit(0)


if __name__ == "__main__":
    main()
