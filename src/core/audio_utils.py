"""
CRAVE Phase 3 - Audio Utilities
Save to: D:\\CRAVE\\src\\core\audio_utils.py

Shared helpers used by voice.py and tts.py.
No external state. Pure utility functions.
"""

import os
import json
import struct
import wave
import tempfile
import numpy as np

# ── config loader ────────────────────────────────────────────────────────────

_cfg_cache = None

def load_config():
    global _cfg_cache
    if _cfg_cache is not None:
        return _cfg_cache
    cfg_path = os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "config", "hardware.json")
    try:
        with open(cfg_path) as f:
            _cfg_cache = json.load(f)
    except Exception:
        # safe defaults if config missing
        _cfg_cache = {
            "crave_root": os.environ.get("CRAVE_ROOT", r"D:\CRAVE"),
            "whisper": {
                "short_model": "small",
                "long_model": "medium",
                "long_threshold_seconds": 30
            }
        }
    return _cfg_cache


def reload_config():
    """Force re-read config from disk (Phase 10 hot-reload)."""
    global _cfg_cache
    _cfg_cache = None
    return load_config()


def crave_root():
    return load_config().get("crave_root", os.environ.get("CRAVE_ROOT", r"D:\CRAVE"))


def models_dir():
    return os.path.join(crave_root(), "models")


# ── audio frame helpers ───────────────────────────────────────────────────────

def pcm_frames_to_numpy(frames, sample_width=2):
    """Convert raw PCM bytes to float32 numpy array in range [-1, 1]."""
    fmt = {1: np.int8, 2: np.int16, 4: np.int32}.get(sample_width, np.int16)
    arr = np.frombuffer(b"".join(frames), dtype=fmt).astype(np.float32)
    arr /= float(np.iinfo(fmt).max)
    return arr


def save_pcm_to_wav(frames, sample_rate, sample_width, channels, path):
    """Write raw PCM frames to a .wav file on disk."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(frames))


def frames_duration_seconds(frames, sample_rate, sample_width, channels):
    """Return how many seconds of audio are in these frames."""
    total_bytes = sum(len(f) for f in frames)
    bytes_per_second = sample_rate * sample_width * channels
    return total_bytes / bytes_per_second if bytes_per_second > 0 else 0


def is_silent(frame, threshold=500, sample_width=2):
    """Return True if this PCM frame is below the silence threshold."""
    fmt = {1: np.int8, 2: np.int16, 4: np.int32}.get(sample_width, np.int16)
    data = np.frombuffer(frame, dtype=fmt)
    return np.abs(data).mean() < threshold


# ── temporary file helpers ────────────────────────────────────────────────────

def make_temp_wav():
    """Return a path to a temp .wav file (caller must delete it)."""
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    return path


def delete_file_safe(path):
    """Delete a file, ignoring errors if it doesn't exist."""
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass


# ── text helpers ──────────────────────────────────────────────────────────────

TECHNICAL_KEYWORDS = {
    # coding / terminal
    "python", "javascript", "function", "variable", "import",
    "install", "command", "terminal", "powershell", "script",
    "error", "exception", "traceback", "debug",
    # hacking / security
    "nmap", "exploit", "payload", "metasploit", "sqlmap",
    "kali", "ctf", "flag", "vulnerability", "hash",
    # trading
    "forex", "eurusd", "gbpusd", "usdjpy", "lot", "pips",
    "backtest", "strategy", "drawdown", "stoploss",
    # general long-form indicators
    "explain", "describe", "summarize", "analyze", "write",
    "generate", "create", "build", "compare",
}

def needs_medium_whisper(text_or_duration, duration_seconds=None):
    """
    Decide if Whisper medium should be used.
    Pass either:
      - a string (checks for technical keywords)
      - a float duration in seconds
      - both
    """
    cfg = load_config().get("whisper", {})
    threshold = cfg.get("long_threshold_seconds", 30)

    if duration_seconds is not None and duration_seconds >= threshold:
        return True

    if isinstance(text_or_duration, str):
        lower = text_or_duration.lower()
        for kw in TECHNICAL_KEYWORDS:
            if kw in lower:
                return True

    return False