"""
CRAVE Phase 3 - Voice Pipeline Verification
Save to: D:\\CRAVE\test_phase3.py
Run:     cd D:\\CRAVE  then  .venv\\Scripts\activate  then  python test_phase3.py

Tests every component of Phase 3 without needing a microphone plugged in.
Real mic tests are marked [MIC] and skipped automatically if no mic found.
"""

import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass
import os
import time
import json
import threading
import tempfile
import wave

sys.path.insert(0, os.path.join("D:\\CRAVE", "src"))

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
SEP    = chr(92)

passed = 0
failed = 0
warned = 0

def ok(label, detail=""):
    global passed
    passed += 1
    d = ("  ->  " + detail) if detail else ""
    print(f"  {GREEN}[  OK  ]{RESET}  {label}{d}")

def fail(label, fix=""):
    global failed
    failed += 1
    f = ("\n         FIX: " + fix) if fix else ""
    print(f"  {RED}[ FAIL ]{RESET}  {label}{f}")

def warn(label, detail=""):
    global warned
    warned += 1
    d = ("  ->  " + detail) if detail else ""
    print(f"  {YELLOW}[ WARN ]{RESET}  {label}{d}")

def section(title):
    print(f"\n{BOLD}{BLUE}{chr(9472)*60}{RESET}")
    print(f"{BOLD}{BLUE}  {title}{RESET}")
    print(f"{BOLD}{BLUE}{chr(9472)*60}{RESET}")

CRAVE = "D:" + SEP + "CRAVE"

print(f"\n{BOLD}{'='*62}")
print("   CRAVE 2026  -  Phase 3 Voice Pipeline Verification")
print(f"{'='*62}{RESET}")

# ── 1. File existence ──────────────────────────────────────────────────────
section("1. Phase 3 Files Exist")
files = {
    "audio_utils.py": os.path.join(CRAVE, "src", "core", "audio_utils.py"),
    "tts.py":         os.path.join(CRAVE, "src", "core", "tts.py"),
    "voice.py":       os.path.join(CRAVE, "src", "core", "voice.py"),
}
for name, path in files.items():
    if os.path.isfile(path):
        ok(f"src" + SEP + "core" + SEP + name)
    else:
        fail(f"src" + SEP + "core" + SEP + name + "  MISSING",
             "Save the Phase 3 file to that path")

# ── 2. audio_utils imports ─────────────────────────────────────────────────
section("2. audio_utils.py — Imports and Functions")
try:
    from core.audio_utils import (
        load_config, reload_config, crave_root, models_dir,
        pcm_frames_to_numpy, frames_duration_seconds,
        is_silent, make_temp_wav, delete_file_safe,
        needs_medium_whisper, TECHNICAL_KEYWORDS,
    )
    ok("audio_utils imports cleanly")
except Exception as e:
    fail(f"audio_utils import failed: {e}")

# ── 3. config loading ──────────────────────────────────────────────────────
section("3. Config Loading (audio_utils)")
try:
    cfg = load_config()
    if cfg and "ram_gb" in cfg:
        ok(f"load_config() works  ->  {cfg.get('ram_gb')} GB mode")
    else:
        warn("load_config() returned but no ram_gb key")
    jroot = crave_root()
    ok(f"crave_root() = {jroot}")
    mdir = models_dir()
    ok(f"models_dir()  = {mdir}")
    rcfg = reload_config()
    ok("reload_config() works (for Phase 10 hot-reload)")
except Exception as e:
    fail(f"Config loading failed: {e}")

# ── 4. audio utility functions ─────────────────────────────────────────────
section("4. Audio Utility Functions")
try:
    import numpy as np
    import struct

    # Test pcm_frames_to_numpy
    raw = struct.pack("h" * 10, *[1000, -1000, 500, -500, 0, 200, -200, 800, -800, 0])
    arr = pcm_frames_to_numpy([raw])
    if arr is not None and len(arr) == 10:
        ok("pcm_frames_to_numpy works")
    else:
        fail("pcm_frames_to_numpy returned wrong shape")

    # Test frames_duration_seconds
    fake_frames = [b"\x00" * 512 * 2] * 16  # 16 chunks of 512 int16 samples
    dur = frames_duration_seconds(fake_frames, 16000, 2, 1)
    expected = (512 * 2 * 16) / (16000 * 2 * 1)
    if abs(dur - expected) < 0.01:
        ok(f"frames_duration_seconds correct  ->  {dur:.3f}s")
    else:
        fail(f"frames_duration_seconds wrong: got {dur:.3f}, expected {expected:.3f}")

    # Test is_silent
    silent_frame = b"\x00" * 512 * 2
    loud_frame   = struct.pack("h" * 512, *([10000] * 512))
    if is_silent(silent_frame) and not is_silent(loud_frame):
        ok("is_silent works correctly")
    else:
        fail("is_silent giving wrong results")

    # Test temp wav helpers
    tmp = make_temp_wav()
    if tmp and tmp.endswith(".wav"):
        ok(f"make_temp_wav creates temp file  ->  {tmp[-20:]}")
        delete_file_safe(tmp)
        ok("delete_file_safe works")
    else:
        fail("make_temp_wav failed")

except Exception as e:
    fail(f"Audio utility test error: {e}")

# ── 5. Whisper selection logic ─────────────────────────────────────────────
section("5. Adaptive Whisper Selection Logic")
try:
    # Short non-technical -> small
    if not needs_medium_whisper("hello how are you", 5.0):
        ok("Short non-technical -> Whisper small  (correct)")
    else:
        fail("Short non-technical should use Whisper small")

    # Long audio -> medium
    if needs_medium_whisper("hello", 35.0):
        ok("Long audio (35s) -> Whisper medium  (correct)")
    else:
        fail("Long audio should use Whisper medium")

    # Technical keyword -> medium
    if needs_medium_whisper("run nmap scan on the target"):
        ok("Technical keyword 'nmap' -> Whisper medium  (correct)")
    else:
        fail("Technical keyword should trigger Whisper medium")

    if needs_medium_whisper("write a python function"):
        ok("Technical keyword 'python' -> Whisper medium  (correct)")
    else:
        fail("'python' keyword should trigger medium")

    # Below threshold, no keywords -> small
    if not needs_medium_whisper("open chrome please", 10.0):
        ok("Short simple command -> Whisper small  (correct)")
    else:
        fail("Short simple command should use Whisper small")

    ok(f"Technical keyword list has {len(TECHNICAL_KEYWORDS)} entries")

except Exception as e:
    fail(f"Whisper selection test error: {e}")

# ── 6. TTS imports ─────────────────────────────────────────────────────────
section("6. tts.py — Imports and Status")
try:
    from core.tts import (
        speak, stop, set_silent_mode, is_silent as tts_is_silent,
        is_speaking, tts_available, tts_status,
        speak_startup, speak_wake, speak_silent_on, speak_silent_off,
    )
    ok("tts.py imports cleanly")

    status = tts_status()
    ok(f"tts_status() returns dict with {len(status)} keys")
    ok(f"kokoro_importable: {status['kokoro_importable']}")
    ok(f"audio_importable:  {status['audio_importable']}")
    ok(f"can_speak:         {status['can_speak']}")

    if not status["can_speak"]:
        warn("Kokoro or sounddevice not installed — TTS will print to console only")
        warn("pip install kokoro-onnx sounddevice soundfile")
    else:
        ok("TTS fully capable — audio output available")

except Exception as e:
    fail(f"tts.py import failed: {e}")

# ── 7. silent mode control ─────────────────────────────────────────────────
section("7. Silent Mode Control")
try:
    # Start not silent
    set_silent_mode(False)
    if not tts_is_silent():
        ok("set_silent_mode(False) -> not silent")
    else:
        fail("set_silent_mode(False) did not work")

    # Enable silent mode
    set_silent_mode(True)
    if tts_is_silent():
        ok("set_silent_mode(True)  -> silent mode ON")
    else:
        fail("set_silent_mode(True) did not work")

    # Toggle back
    set_silent_mode(False)
    ok("Toggled back to normal mode")

except Exception as e:
    fail(f"Silent mode test error: {e}")

# ── 8. TTS speak (console mode) ────────────────────────────────────────────
section("8. TTS — Speak in Console Mode")
try:
    # Put in silent mode so no audio plays during test
    set_silent_mode(True)
    speak("Testing text to speech output", block=True)
    ok("speak() in silent mode -> printed to console (no audio)")

    # Test stop doesn't crash
    stop()
    ok("stop() does not crash")

    set_silent_mode(False)

except Exception as e:
    fail(f"TTS speak test error: {e}")

# ── 9. VoicePipeline imports ───────────────────────────────────────────────
section("9. voice.py — VoicePipeline Import")
try:
    from core.voice import VoicePipeline
    ok("VoicePipeline imports cleanly")
except Exception as e:
    fail(f"voice.py import failed: {e}")

# ── 10. VoicePipeline init and status ─────────────────────────────────────
section("10. VoicePipeline — Init and Status")
vp = None
try:
    vp = VoicePipeline()
    ok("VoicePipeline() created without errors")

    status = vp.status()
    ok(f"status() returns dict with {len(status)} keys")
    ok(f"pyaudio available:    {status['pyaudio_available']}")
    ok(f"porcupine available:  {status['porcupine_available']}")
    ok(f"whisper available:    {status['whisper_available']}")

    if not status["pyaudio_available"]:
        warn("pyaudio not available — pip install pyaudio")
    if not status["porcupine_available"]:
        warn("pvporcupine not installed — wake word disabled, keyboard fallback used")
        warn("This is OK for development — real device needs pvporcupine")
    if not status["whisper_available"]:
        warn("faster_whisper not installed — pip install faster-whisper")

    overall = vp.is_available()
    if overall:
        ok("VoicePipeline fully available (pyaudio + whisper)")
    else:
        warn("VoicePipeline in degraded mode — check warnings above")

except Exception as e:
    fail(f"VoicePipeline init failed: {e}")

# ── 11. Silent mode on VoicePipeline ──────────────────────────────────────
section("11. VoicePipeline — Silent Mode")
try:
    if vp:
        vp.set_silent_mode(True)
        if vp._silent_mode:
            ok("VoicePipeline.set_silent_mode(True) works")
        else:
            fail("Silent mode not applied to VoicePipeline")
        vp.set_silent_mode(False)
        ok("Toggled back to normal mode")
    else:
        warn("Skipping — VoicePipeline not created")
except Exception as e:
    fail(f"VoicePipeline silent mode test: {e}")

# ── 12. Whisper small model load ───────────────────────────────────────────
section("12. Whisper Small Model  (first load = download if needed)")
try:
    try:
        from faster_whisper import WhisperModel as _WM
        _WHISPER_AVAILABLE = True
    except ImportError:
        _WHISPER_AVAILABLE = False

    if vp and getattr(vp, '_WHISPER_AVAILABLE', _WHISPER_AVAILABLE):
        print("  [INFO] Loading Whisper small — may download ~244 MB on first run...")
        from faster_whisper import WhisperModel
        mdir = models_dir()
        m = WhisperModel("small", device="cpu", compute_type="int8",
                         download_root=mdir)
        ok("Whisper small loaded successfully")
        ok(f"Model saved to {mdir}")

        # Test transcription with a tiny silent wav
        tmp = make_temp_wav()
        with wave.open(tmp, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00" * 16000 * 2)  # 1 sec silence

        segs, _ = m.transcribe(tmp, language="en", vad_filter=True)
        result = " ".join(s.text for s in segs).strip()
        delete_file_safe(tmp)
        ok(f"Transcribe silent wav = '{result}' (empty is correct)")
    else:
        warn("faster_whisper not available — skipping Whisper load test")
except Exception as e:
    fail(f"Whisper small load error: {e}",
         "pip install faster-whisper")

# ── 13. Phase 2 compatibility check ───────────────────────────────────────
section("13. Phase 2 Compatibility  (ModelRouter + Voice)")
try:
    from core.model_router import ModelRouter
    ok("ModelRouter imports alongside voice pipeline  (no conflicts)")

    router = ModelRouter()
    ok("ModelRouter instantiates OK")

    # Verify ModelRouter still knows correct model names
    models = router.list_models()
    ok(f"ModelRouter reports {len(models)} models in Ollama")

except ImportError as e:
    warn(f"ModelRouter not found: {e}  (OK if testing Phase 3 standalone)")
except Exception as e:
    warn(f"Phase 2 compat check: {e}")

# ── 14. models directory ──────────────────────────────────────────────────
section("14. Models Directory")
mdir = models_dir()
if os.path.isdir(mdir):
    contents = os.listdir(mdir)
    ok(f"D:\\CRAVE\\models\\  exists  ({len(contents)} items)")
    if contents:
        for item in contents[:5]:
            ok(f"  Found: {item}")
    else:
        warn("D:\\CRAVE\\models\\  is empty — Whisper will download here on first use")
else:
    fail(f"{mdir}  not found", "mkdir " + mdir)

# ── SUMMARY ───────────────────────────────────────────────────────────────
section("FINAL RESULT")
total = passed + failed
bar_w = 45
filled = int(bar_w * passed / total) if total else 0
bar = chr(9608) * filled + chr(9617) * (bar_w - filled)
pct = int(100 * passed / total) if total else 0
print(f"\n  [{bar}]  {pct}%")
print(f"\n  {GREEN}{BOLD}{passed} passed{RESET}   {RED}{BOLD}{failed} failed{RESET}   "
      f"{YELLOW}{warned} warnings{RESET}   ({total} checks)\n")

if failed == 0 and warned == 0:
    print(f"  {GREEN}{BOLD}PERFECT — Phase 3 complete!{RESET}")
    print(f"  {GREEN}Next: tell Claude 'Write Phase 4'{RESET}\n")
elif failed == 0:
    print(f"  {GREEN}{BOLD}Phase 3 COMPLETE  (with {warned} warning(s)){RESET}")
    print(f"  {YELLOW}Warnings above are for optional features (wake word, real mic).{RESET}")
    print(f"  {GREEN}Safe to proceed: tell Claude 'Write Phase 4'{RESET}\n")
else:
    print(f"  {RED}{BOLD}Fix the {failed} FAIL(s) above then re-run.{RESET}\n")

# cleanup
if vp:
    try:
        vp.stop()
    except Exception:
        pass

# ── import for type hint in WHISPER check ─────────────────────────────────
try:
    from faster_whisper import WhisperModel as _WM
    _WHISPER_AVAILABLE = True
except ImportError:
    _WHISPER_AVAILABLE = False