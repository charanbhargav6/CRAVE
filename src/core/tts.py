"""
CRAVE Phase 3+ — Text-to-Speech (Selectable Engine)
Save to: D:\\CRAVE\\src\\core\\tts.py

Supports two engines (configurable via hardware.json "tts_engine"):
  "edge-tts"  — Microsoft Edge Neural TTS (online, premium quality) [DEFAULT]
  "kokoro"    — Kokoro ONNX (offline, local, no internet needed)

Silent-mode aware: mutes output when Ctrl+Shift+J is active.
"""

import os
import sys
import json
import threading
import time
import asyncio
import tempfile
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("crave.core.tts")

CRAVE_ROOT = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")
CONFIG_PATH = os.path.join(CRAVE_ROOT, "config", "hardware.json")

# ── module state ─────────────────────────────────────────────────────────────
_silent_mode   = False
_speaking      = False
_speak_thread  = None

# Audio playback dependency
try:
    import pygame
    _PYGAME_AVAILABLE = True
except ImportError:
    _PYGAME_AVAILABLE = False


# ── Engine Abstraction ───────────────────────────────────────────────────────

class TTSEngine(ABC):
    """Base class for TTS engines."""

    @abstractmethod
    def generate(self, text: str, output_path: str) -> bool:
        """Generate speech audio file. Returns True on success."""
        ...

    @abstractmethod
    def name(self) -> str:
        ...


class EdgeTTSEngine(TTSEngine):
    """Microsoft Edge Neural TTS — requires internet."""

    VOICE_NAME = "en-US-ChristopherNeural"

    def __init__(self):
        try:
            import edge_tts
            self._available = True
        except ImportError:
            self._available = False
            logger.warning("[TTS] edge-tts not installed.")

    def name(self) -> str:
        return "edge-tts"

    def generate(self, text: str, output_path: str) -> bool:
        if not self._available:
            return False
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text, self.VOICE_NAME, rate="+5%")
            asyncio.run(communicate.save(output_path))
            return True
        except Exception as e:
            logger.error(f"[TTS] Edge-TTS generation error: {e}")
            return False


class KokoroTTSEngine(TTSEngine):
    """Kokoro ONNX — fully offline local TTS."""

    def __init__(self):
        try:
            from kokoro_onnx import Kokoro
            if not os.path.exists("kokoro-v0_19.onnx") or not os.path.exists("voices.json"):
                raise FileNotFoundError("Local model files ('kokoro-v0_19.onnx' / 'voices.json') not found.")
            self._kokoro = Kokoro("kokoro-v0_19.onnx", "voices.json")
            self._available = True
            logger.info("[TTS] Kokoro ONNX offline engine loaded.")
        except ImportError:
            self._available = False
            logger.warning("[TTS] kokoro-onnx not installed.")
        except Exception as e:
            self._available = False
            logger.debug(f"[TTS] Kokoro offline TTS not initialized: {e}")

    def name(self) -> str:
        return "kokoro"

    def generate(self, text: str, output_path: str) -> bool:
        if not self._available:
            return False
        try:
            import soundfile as sf

            samples, sr = self._kokoro.create(
                text,
                voice="af_heart",  # Default voice
                speed=1.0,
                lang="en-us",
            )
            sf.write(output_path, samples, sr)
            return True
        except Exception as e:
            logger.error(f"[TTS] Kokoro generation error: {e}")
            return False


class ElevenLabsTTSEngine(TTSEngine):
    """ElevenLabs premium Neural TTS — requires internet and ELEVENLABS_API_KEY."""

    def __init__(self):
        try:
            import elevenlabs
            self._available = True
            logger.info("[TTS] ElevenLabs engine loaded.")
        except ImportError:
            self._available = False
            logger.warning("[TTS] elevenlabs not installed.")

    def name(self) -> str:
        return "elevenlabs"

    def generate(self, text: str, output_path: str) -> bool:
        if not self._available:
            return False
            
        key = os.environ.get("ELEVENLABS_API_KEY", "")
        if not key:
            logger.warning("ELEVENLABS_API_KEY is not set.")
            return False
            
        # Extract desired voice ID from config or fallback to one of the user's favorites
        voice_id = "UgBBYS2sOqTuMpoF3BR0"
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            voice_id = cfg.get("elevenlabs_voice_id", "UgBBYS2sOqTuMpoF3BR0")
        except:
            pass
            
        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=key)
            
            # Using v2 generate
            audio = client.generate(
                text=text,
                voice=voice_id,
                model="eleven_multilingual_v2"
            )
            
            with open(output_path, "wb") as f:
                for chunk in audio:
                    f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"[TTS] ElevenLabs generation error: {e}")
            return False


class Pyttsx3TTSEngine(TTSEngine):
    """pyttsx3 — fully offline, zero-dependency fallback TTS (low quality but always works)."""

    def __init__(self):
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._available = True
            logger.info("[TTS] pyttsx3 fallback engine loaded.")
        except (ImportError, Exception) as e:
            self._available = False
            self._engine = None
            logger.warning(f"[TTS] pyttsx3 not available: {e}")

    def name(self) -> str:
        return "pyttsx3"

    def generate(self, text: str, output_path: str) -> bool:
        """pyttsx3 speaks directly — doesn't generate a file. Returns False to signal
        that _play_audio_file should be skipped; the speech already happened."""
        if not self._available:
            return False
        try:
            self._engine.say(text)
            self._engine.runAndWait()
            return True  # Speech happened live, no file needed
        except Exception as e:
            logger.error(f"[TTS] pyttsx3 error: {e}")
            return False


# ── Engine Factory ───────────────────────────────────────────────────────────

_engine: TTSEngine | None = None
_fallback_engines: list = []  # Ordered fallback chain


def _get_engine() -> TTSEngine | None:
    """Load the configured TTS engine and build fallback chain (lazy singleton)."""
    global _engine, _fallback_engines
    if _engine is not None:
        return _engine

    engine_name = "edge-tts"  # Default
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        engine_name = cfg.get("tts_engine", "edge-tts")
    except Exception:
        pass

    if engine_name == "kokoro":
        _engine = KokoroTTSEngine()
        if not _engine._available:
            logger.info("[TTS] Kokoro unavailable, falling back to edge-tts.")
            _engine = EdgeTTSEngine()
    elif engine_name == "elevenlabs":
        _engine = ElevenLabsTTSEngine()
        if not _engine._available:
            logger.info("[TTS] ElevenLabs unavailable, falling back to edge-tts.")
            _engine = EdgeTTSEngine()
    else:
        _engine = EdgeTTSEngine()

    # Build fallback chain: all OTHER engines in priority order
    _fallback_engines = []
    all_engines = [EdgeTTSEngine, KokoroTTSEngine, Pyttsx3TTSEngine]
    for eng_cls in all_engines:
        if not isinstance(_engine, eng_cls):
            try:
                fb = eng_cls()
                if fb._available:
                    _fallback_engines.append(fb)
            except Exception:
                pass
    
    fb_names = [e.name() for e in _fallback_engines]
    logger.info(f"[TTS] Active engine: {_engine.name()} | Fallbacks: {fb_names if fb_names else 'none'}")
    return _engine


# ── Public API (unchanged interface) ─────────────────────────────────────────

def set_silent_mode(value: bool):
    """Enable or disable TTS output. Called by Orb UI on Ctrl+Shift+J."""
    global _silent_mode
    _silent_mode = value

def is_silent() -> bool:
    return _silent_mode

def is_speaking() -> bool:
    return _speaking


def _play_audio_file(filepath: str):
    """Uses pygame mixer to play audio file blocking-ly."""
    global _speaking
    if not _PYGAME_AVAILABLE:
        return

    try:
        pygame.mixer.init()
        pygame.mixer.music.load(filepath)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy() and _speaking:
            time.sleep(0.05)
    except Exception as e:
        print(f"[TTS] Playback error: {e}", file=sys.stderr)
    finally:
        try:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        except:
            pass

        # Clean up temp file
        try:
            os.remove(filepath)
        except:
            pass


def _speak_blocking(text: str):
    """Generate and play audio in streaming chunks to reduce latency."""
    global _speaking

    engine = _get_engine()
    if engine is None:
        print(f"[CRAVE] {text}")  # Last resort: console
        return

    _speaking = True

    # ── Streaming Chunk Logic ──
    # Split text by periods, exclamation marks, or newlines to stream playback
    import re
    # Match sentences, keeping punctuation
    chunks = re.findall(r'[^.!?\n]+[.!?\n]*', text)
    chunks = [c.strip() for c in chunks if c.strip()]
    
    if not chunks:
        _speaking = False
        return

    engines_to_try = [engine] + _fallback_engines
    
    for chunk in chunks:
        if not _speaking:
            break  # Stop if interrupted
            
        chunk_success = False
        
        for eng in engines_to_try:
            # pyttsx3 speaks directly
            if isinstance(eng, Pyttsx3TTSEngine):
                try:
                    if eng.generate(chunk, ""):
                        chunk_success = True
                        break
                except Exception:
                    continue
            
            suffix = ".mp3" if isinstance(eng, EdgeTTSEngine) else ".wav"
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp_path = temp_file.name
            temp_file.close()

            try:
                success = eng.generate(chunk, temp_path)
                if success and _speaking:
                    logger.debug(f"[TTS] Streaming via {eng.name()} | Chunk: {chunk[:20]}...")
                    _play_audio_file(temp_path)
                    chunk_success = True
                    break
            except Exception as e:
                logger.warning(f"[TTS] {eng.name()} failed: {e}")
            finally:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except:
                    pass
                    
        if not chunk_success:
            print(f"[CRAVE] {chunk}")

    _speaking = False


def speak(text: str, block: bool = False):
    """Speak text aloud using the configured Neural TTS engine."""
    global _speak_thread

    if not text or not text.strip():
        return

    if _silent_mode:
        return

    if block:
        _speak_blocking(text)
    else:
        stop()
        _speak_thread = threading.Thread(
            target=_speak_blocking,
            args=(text,),
            daemon=True
        )
        _speak_thread.start()


def stop():
    """Stop any currently playing speech."""
    global _speaking
    _speaking = False
    if _PYGAME_AVAILABLE:
        try:
            pygame.mixer.music.stop()
        except:
            pass


# ── Convenience Wrappers (unchanged) ─────────────────────────────────────────

def speak_startup():
    """Initial boot sequence greeting."""
    speak("HEY BOSS, HOW CAN I HELP YOU TODAY", block=False)

def speak_wake():
    speak("Yes?", block=False)

def speak_silent_on():
    speak("Silent mode on.", block=True)

def speak_silent_off():
    speak("Silent mode off.", block=True)

def speak_error(detail: str = ""):
    msg = "I encountered an error."
    if detail:
        msg += f" {detail}"
    speak(msg, block=False)

def tts_available() -> bool:
    engine = _get_engine()
    return engine is not None and engine._available

def tts_status() -> dict:
    engine = _get_engine()
    return {
        "engine":           engine.name() if engine else "none",
        "audio_importable": _PYGAME_AVAILABLE,
        "silent_mode":      _silent_mode,
        "speaking":         _speaking,
        "can_speak":        tts_available(),
    }