@echo off
REM ════════════════════════════════════════════════════
REM  CRAVE 2026 - Phase 1 One-Click Setup
REM  Save to: D:\CRAVE\crave_setup.bat
REM  Run: Right-click → Run as administrator
REM ════════════════════════════════════════════════════

echo.
echo  ========================================
echo   CRAVE 2026 - Phase 1 Setup
echo  ========================================
echo.

REM ── Go to D:\CRAVE ──────────────────────────────────
cd /d D:\CRAVE

REM ── Create any missing folders ───────────────────────
echo [1/6] Creating folders...
mkdir config 2>nul
mkdir data 2>nul
mkdir Knowledge 2>nul
mkdir Knowledge\skills 2>nul
mkdir Logs 2>nul
mkdir Main_Lead 2>nul
mkdir models 2>nul
mkdir plugins 2>nul
mkdir src 2>nul
mkdir src\core 2>nul
mkdir src\agents 2>nul
mkdir src\security 2>nul
mkdir src\tools 2>nul
mkdir src\ui 2>nul
mkdir tools\ffmpeg 2>nul
mkdir tools\fastsd 2>nul
mkdir Sub_Projects\Trading 2>nul
mkdir Sub_Projects\Hacking 2>nul
echo    Done.

REM ── Create __init__.py files ─────────────────────────
echo [2/6] Creating Python package files...
type nul > src\__init__.py
type nul > src\core\__init__.py
type nul > src\agents\__init__.py
type nul > src\security\__init__.py
type nul > src\tools\__init__.py
type nul > src\ui\__init__.py
echo    Done.

REM ── Create virtual environment if not exists ─────────
echo [3/6] Checking virtual environment...
if not exist ".venv\Scripts\activate.bat" (
    echo    Creating .venv ...
    python -m venv .venv
    echo    Done.
) else (
    echo    .venv already exists - skipping.
)

REM ── Activate venv ────────────────────────────────────
echo [4/6] Activating virtual environment...
call .venv\Scripts\activate.bat
echo    Done.

REM ── Install missing packages ─────────────────────────
echo [5/6] Installing packages (this may take a few minutes)...
pip install --quiet --upgrade pip
pip install --quiet faster-whisper kokoro-onnx pvporcupine PyQt6
pip install --quiet langchain langgraph ollama
pip install --quiet cryptography bcrypt python-pptx python-telegram-bot
pip install --quiet requests psutil pyaudio ffmpeg-python
pip install --quiet pywinauto pyautogui selenium playwright
pip install --quiet alpaca-trade-api MetaTrader5 backtrader backtesting
pip install --quiet paramiko schedule sounddevice soundfile numpy mss
echo    Done.

REM ── Run verify script ────────────────────────────────
echo [6/6] Running verification...
echo.
python src\verify_env.py
echo.

echo  ========================================
echo   Setup complete. See results above.
echo  ========================================
echo.
pause
