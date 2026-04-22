"""
CRAVE Phase 3 - Voice Input Pipeline
Save to: D:\\CRAVE\\src\\core\voice.py

Responsibilities:
  1. Always-on wake word detection ("Hey Mycroft") via openwakeword built-in model
  2. Microphone capture after wake word
  3. Silence detection to know when user stopped speaking
  4. Adaptive Whisper transcription (small vs medium auto-selected)
  5. Silent mode aware — disables wake word when Ctrl+Shift+J active
  6. Provides a clean interface for Phase 4 Orchestrator to use

Usage (Phase 4 will call this):
    from src.core.voice import VoicePipeline
    vp = VoicePipeline()
    vp.start()                        # begin listening for wake word
    text = vp.listen_once()           # block until one full command captured
    vp.stop()
"""

import os
import sys
import time
import queue
import struct
import threading
import tempfile
import wave

# ── safe imports ──────────────────────────────────────────────────────────────
try:
    import pyaudio
    _PYAUDIO_AVAILABLE = True
except ImportError:
    _PYAUDIO_AVAILABLE = False

# IMPORTANT: openwakeword (onnxruntime) MUST load BEFORE faster_whisper (ctranslate2)
# to avoid DLL initialization conflicts on Windows with CUDA
try:
    from openwakeword.model import Model as OWWModel
    import numpy as np
    _OWW_AVAILABLE = True
except Exception as _oww_err:
    OWWModel = None
    _OWW_AVAILABLE = False
    print(f"[Voice] openwakeword unavailable: {type(_oww_err).__name__}: {_oww_err}")

try:
    from faster_whisper import WhisperModel
    _WHISPER_AVAILABLE = True
except ImportError:
    _WHISPER_AVAILABLE = False

from .audio_utils import (
    load_config, crave_root, models_dir,
    is_silent, frames_duration_seconds,
    save_pcm_to_wav, make_temp_wav,
    delete_file_safe, needs_medium_whisper,
)

from src.core.tts import is_speaking

# ── audio constants ───────────────────────────────────────────────────────────
SAMPLE_RATE     = 16000   # Hz — Whisper and openwakeword both want 16kHz
CHANNELS        = 1       # mono
SAMPLE_WIDTH    = 2       # bytes (int16)
CHUNK_SIZE      = 512     # frames per pyaudio read
SILENCE_THRESH  = 1200    # Base ambient threshold
SILENCE_SECS    = 2.5     # Increased to 2.5s to prevent dropping out mid-sentence during pauses
MAX_RECORD_SECS = 60.0    # Hard stop indefinitely test


class VoicePipeline:
    """
    Full voice input pipeline.

    Lifecycle:
      __init__ → validates config + loads models
      start()  → begins wake-word listener in background thread
      stop()   → cleans up all resources

    Main interface for Phase 4:
      listen_once()  → blocks until one command transcribed, returns str
      transcribe()   → transcribe a given wav file path, returns str
    """

    def __init__(self):
        self._cfg         = load_config()
        self._whisper_cfg = self._cfg.get("whisper", {})
        self._silent_mode = False     # synced from tts.py by Orchestrator
        self._running     = False
        self._wake_thread = None
        self._command_queue = queue.Queue()

        # Whisper model instances — lazy loaded
        self._whisper_small  = None
        self._whisper_medium = None
        self._whisper_lock   = threading.Lock()

        # PyAudio instance
        self._pa = None
        self._stream = None

        # OpenWakeWord handle
        self._oww_model = None

        print("[Voice] VoicePipeline initialised")

    # ── public API ────────────────────────────────────────────────────────────

    def start(self):
        """Start the background wake-word listener."""
        if self._running:
            return
        if not self._check_dependencies():
            print("[Voice] Cannot start — missing dependencies (see warnings above)")
            return
        self._running = True
        self._wake_thread = threading.Thread(
            target=self._wake_word_loop,
            daemon=True,
            name="CRAVEWakeWord"
        )
        self._wake_thread.start()
        print("[Voice] Wake-word listener started — say 'Hey CRAVE'")

    def stop(self):
        """Stop the listener and release all resources."""
        self._running = False
        self._cleanup_audio()
        self._cleanup_oww()
        if self._wake_thread:
            self._wake_thread.join(timeout=3)
        print("[Voice] Pipeline stopped")

    def set_silent_mode(self, value: bool):
        """Called by Orb UI (Phase 6) to toggle wake-word on/off."""
        self._silent_mode = value
        state = "OFF (silent)" if value else "ON"
        print(f"[Voice] Wake word listener: {state}")

    def listen_once(self, timeout: float = 30.0) -> str:
        """
        Block until one complete voice command is captured and transcribed.
        Returns the transcribed text, or "" on timeout/error.
        Called by Phase 4 Orchestrator after wake word fires.
        """
        return self._record_and_transcribe()

    def transcribe(self, wav_path: str) -> str:
        """
        Transcribe an existing wav file.
        Used by Phase 7 ScreenAgent when it receives audio from clipboard.
        """
        return self._run_whisper(wav_path)

    def is_available(self) -> bool:
        return _PYAUDIO_AVAILABLE and _WHISPER_AVAILABLE

    def status(self) -> dict:
        return {
            "pyaudio_available":    _PYAUDIO_AVAILABLE,
            "oww_available":        _OWW_AVAILABLE,
            "whisper_available":    _WHISPER_AVAILABLE,
            "running":              self._running,
            "silent_mode":          self._silent_mode,
            "whisper_small_loaded": self._whisper_small is not None,
            "whisper_medium_loaded":self._whisper_medium is not None,
        }

    def command_available(self) -> bool:
        """Check if a parsed voice command is in the queue."""
        return not self._command_queue.empty()
        
    def get_next_command(self, timeout: float = 0.05) -> str:
        """Get the next command from the queue, or empty string on timeout."""
        try:
            return self._command_queue.get(timeout=timeout)
        except queue.Empty:
            return ""

    # ── dependency check ──────────────────────────────────────────────────────

    def _check_dependencies(self) -> bool:
        ok = True
        if not _PYAUDIO_AVAILABLE:
            print("[Voice] WARNING: pyaudio not installed — pip install pyaudio")
            ok = False
        if not _WHISPER_AVAILABLE:
            print("[Voice] WARNING: faster_whisper not installed — pip install faster-whisper")
            ok = False
        if not _OWW_AVAILABLE:
            print("[Voice] WARNING: openwakeword not installed — will use keyboard fallback")
            # Not hard failure — we can still work without wake word
        return ok

    # ── wake word loop ────────────────────────────────────────────────────────

    def _has_console(self) -> bool:
        """Detect if we have a console (False when running under pythonw.exe)."""
        try:
            sys.stdin.fileno()
            return True
        except Exception:
            return False

    def _wake_word_loop(self):
        """
        Background thread: continuously listens for wake word.
        When detected, records the command and puts text in queue.
        Falls back to keyboard input if OpenWakeWord unavailable.
        """
        if _OWW_AVAILABLE:
            self._run_oww_loop()
        elif self._has_console():
            self._run_keyboard_fallback_loop()
        else:
            print("[Voice] No wake word engine and no console — voice input disabled")

    def _run_oww_loop(self):
        """Wake-word detection using OpenWakeWord built-in 'hey_mycroft' model."""
        try:
            # Use the built-in hey_mycroft model (no custom file needed)
            self._oww_model = OWWModel(
                wakeword_models=['hey_mycroft_v0.1']
            )
            self._pa = pyaudio.PyAudio()
            
            # openwakeword processes best on 80ms chunks -> 1280 frames at 16kHz
            chunk_size = 1280
            
            self._stream = self._pa.open(
                rate=SAMPLE_RATE,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=chunk_size,
            )
            print("[Voice] OpenWakeWord engine ready (Listening for 'Hey Mycroft')")

            last_trigger_time = 0.0
            cooldown_seconds = 3.0
            threshold = 0.5  # Official recommended default for built-in models
            
            _debug_max_score = 0.0
            _debug_time = time.time()
            
            # Continuous listening logic
            is_awake = False
            last_awake_time = 0.0

            while self._running:
                if self._silent_mode or is_speaking():
                    time.sleep(0.1)
                    continue

                if is_awake and (time.time() - last_awake_time > 3600):
                    print("[Voice] 1-hour idle limit reached. Sleeping.")
                    is_awake = False

                try:
                    pcm = self._stream.read(chunk_size, exception_on_overflow=False)
                    audio = np.frombuffer(pcm, dtype=np.int16)
                    
                    if is_awake:
                        amplitude = np.abs(audio).mean()
                        if amplitude > SILENCE_THRESH:
                            self._stream.stop_stream()
                            text = self._record_and_transcribe()
                            if text:
                                last_awake_time = time.time()
                                self._command_queue.put(text)
                            self._stream.start_stream()
                        else:
                            time.sleep(0.01)
                    else:
                        prediction = self._oww_model.predict(audio)
                        score = prediction.get("hey_mycroft_v0.1", 0.0)
                        
                        if score > threshold and (time.time() - last_trigger_time > cooldown_seconds):
                            print(f"[Voice] Wake word detected! System Awake for 1 Hour. (Score: {score:.2f})")
                            last_trigger_time = time.time()
                            is_awake = True
                            last_awake_time = time.time()
                            
                            self._oww_model.reset()
                            self._command_queue.put("__wake__")
                            self._stream.stop_stream()
                            text = self._record_and_transcribe()
                            if text:
                                self._command_queue.put(text)
                            self._stream.start_stream()
                except Exception as e:
                    if self._running:
                        print(f"[Voice] Stream read error: {e}")
                    time.sleep(0.05)

        except Exception as e:
            print(f"[Voice] OpenWakeWord init failed: {e}")
            if self._has_console():
                print("[Voice] Falling back to keyboard input")
                self._run_keyboard_fallback_loop()
            else:
                print("[Voice] No console available — voice input disabled")
        finally:
            self._cleanup_audio()
            self._cleanup_oww()

    def _run_keyboard_fallback_loop(self):
        """
        Fallback when OpenWakeWord is unavailable.
        User presses Enter in terminal to trigger recording.
        Useful for testing Phase 3 if mic/audio issues occur.
        """
        print("[Voice] FALLBACK MODE: Press Enter to start recording a command.")
        print("[Voice] Type text directly and press Enter to skip mic input.")
        while self._running:
            try:
                user_input = input("  [Press Enter to speak, or type command]: ").strip()
                if not self._running:
                    break
                if user_input:
                    # Direct text input — skip mic
                    self._command_queue.put(user_input)
                else:
                    # Press Enter with no text → record from mic
                    self._command_queue.put("__wake__")
                    text = self._record_and_transcribe()
                    if text:
                        self._command_queue.put(text)
            except (EOFError, KeyboardInterrupt):
                break

    # ── recording ─────────────────────────────────────────────────────────────

    def _record_and_transcribe(self) -> str:
        """
        Record audio from mic until silence, then transcribe.
        Returns transcribed text string.
        """
        wav_path = None
        try:
            frames = self._record_until_silence()
            if not frames:
                return ""

            duration = frames_duration_seconds(
                frames, SAMPLE_RATE, SAMPLE_WIDTH, CHANNELS
            )
            print(f"[Voice] Captured {duration:.1f}s of audio")

            # Save to temp wav
            wav_path = make_temp_wav()
            save_pcm_to_wav(frames, SAMPLE_RATE, SAMPLE_WIDTH, CHANNELS, wav_path)

            # Transcribe
            text = self._run_whisper(wav_path, duration_hint=duration)
            print(f"[Voice] Transcribed: '{text}'")
            return text

        except Exception as e:
            print(f"[Voice] Record/transcribe error: {e}")
            return ""
        finally:
            delete_file_safe(wav_path)

    def _record_until_silence(self):
        """
        Open mic, record until SILENCE_SECS of silence detected.
        Returns list of raw PCM byte frames.
        """
        if not _PYAUDIO_AVAILABLE:
            return []

        pa = None
        stream = None
        frames = []

        try:
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
            )
            print("[Voice] Recording... (speak now)")

            silence_chunks = 0
            chunks_per_silence = int(SAMPLE_RATE / CHUNK_SIZE * SILENCE_SECS)
            max_chunks = int(SAMPLE_RATE / CHUNK_SIZE * MAX_RECORD_SECS)
            max_amplitude = 0.0

            for _ in range(max_chunks):
                if is_speaking():
                    return []
                
                data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                frames.append(data)

                # Check silence
                import struct as _struct
                import numpy as _np
                samples = _np.frombuffer(data, dtype=_np.int16)
                amplitude = _np.abs(samples).mean()
                if amplitude > max_amplitude:
                    max_amplitude = amplitude

                # Dynamic silence threshold: higher of base threshold or 15% of peak voice
                dynamic_silence = max(SILENCE_THRESH, max_amplitude * 0.15)

                if amplitude < dynamic_silence:
                    silence_chunks += 1
                else:
                    silence_chunks = 0

                if silence_chunks >= chunks_per_silence and len(frames) > chunks_per_silence:
                    break  # enough silence — user stopped speaking
            
            print(f"[Voice:Diag] Recording max amplitude was: {max_amplitude:.1f}")

        except Exception as e:
            print(f"[Voice] Mic error: {e}")
        finally:
            try:
                if stream:
                    stream.stop_stream()
                    stream.close()
                if pa:
                    pa.terminate()
            except Exception:
                pass

        return frames

    # ── Whisper transcription ─────────────────────────────────────────────────

    def _get_whisper(self, use_medium: bool):
        """Load and return the appropriate Whisper model."""
        with self._whisper_lock:
            if use_medium:
                if self._whisper_medium is None:
                    mdir = models_dir()
                    print("[Voice] Loading Whisper small.en (first use — downloading if needed)...")
                    self._whisper_medium = WhisperModel(
                        "small.en",
                        device="cpu",
                        compute_type="int8",
                        download_root=mdir,
                    )
                    print("[Voice] Whisper small.en ready")
                return self._whisper_medium
            else:
                if self._whisper_small is None:
                    mdir = models_dir()
                    print("[Voice] Loading Whisper base.en (fast processing)...")
                    self._whisper_small = WhisperModel(
                        "base.en",
                        device="cpu",
                        compute_type="int8",
                        download_root=mdir,
                    )
                    print("[Voice] Whisper base.en ready")
                return self._whisper_small

    def _run_whisper(self, wav_path: str, duration_hint: float = 0.0) -> str:
        """
        Transcribe a wav file.
        Automatically picks small vs medium based on duration + content.
        """
        if not _WHISPER_AVAILABLE:
            return ""
        if not os.path.isfile(wav_path):
            return ""

        try:
            use_medium = needs_medium_whisper(None, duration_hint)
            model = self._get_whisper(use_medium)
            size = "medium" if use_medium else "small"
            print(f"[Voice] Transcribing with Whisper {size}...")

            segments, _ = model.transcribe(
                wav_path,
                task="transcribe",
                language="en",
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=600),
            )

            parts = [seg.text.strip() for seg in segments if seg.text.strip()]
            text = " ".join(parts).strip()

            # Filter common Whisper silence hallucinations
            hallucinations = [
                "thank you.", "thank you", "thanks for watching", "thanks for watching.",
                "bye-bye.", "bye-bye", "bye.", "goodbye.",
                "okay.", "okay", "yeah.", "yeah", "you", "you.",
                "i hope you enjoyed this video", "please subscribe",
                "like and subscribe", "see you next time",
                "thanks for watching bye", "subscribe to my channel",
                "the end.", "the end", "hmm.", "hmm", "uh.", "uh",
                "so.", "so", "i mean.", "right.", "one.",
            ]
            if text.lower().strip().rstrip('.') in [h.rstrip('.') for h in hallucinations] or len(text) < 3:
                print(f"[Voice] Filtered hallucination: '{text}'")
                return ""

            # If medium was not pre-selected but result contains tech keywords,
            # re-transcribe with medium for better accuracy (only if quick run)
            if not use_medium and needs_medium_whisper(text):
                print("[Voice] Technical content detected — upgrading to Whisper medium")
                model = self._get_whisper(use_medium=True)
                segments, _ = model.transcribe(
                    wav_path,
                    task="transcribe",
                    language="en",
                    beam_size=5,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=600),
                )
                parts = [seg.text.strip() for seg in segments if seg.text.strip()]
                text = " ".join(parts).strip()

            return text

        except Exception as e:
            print(f"[Voice] Whisper error: {e}")
            return ""

    # ── command queue access ──────────────────────────────────────────────────

    def get_next_command(self, timeout: float = None) -> str:
        """
        Get the next command from the queue.
        Returns "__wake__" when wake word fires (before command recorded).
        Returns the transcribed text for actual commands.
        Returns "" on timeout.
        Called by Phase 4 Orchestrator.
        """
        try:
            return self._command_queue.get(timeout=timeout)
        except queue.Empty:
            return ""

    def command_available(self) -> bool:
        return not self._command_queue.empty()

    # ── cleanup ───────────────────────────────────────────────────────────────

    def _cleanup_audio(self):
        try:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
                self._stream = None
        except Exception:
            pass
        try:
            if self._pa:
                self._pa.terminate()
                self._pa = None
        except Exception:
            pass

    def _cleanup_oww(self):
        self._oww_model = None

    def __del__(self):
        self.stop()