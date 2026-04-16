@echo off
REM CRAVE Autoboot Batch Wrapper — Zero Visibility Mode
REM Called by crave_autoboot.vbs (hidden window). No CMD windows will appear.

REM 0. Kill existing ghost instances to free up the Microphone and RAM
wmic process where "commandline like '%%main.py%%' and name='python.exe'" call terminate >nul 2>&1
wmic process where "commandline like '%%main.py%%' and name='pythonw.exe'" call terminate >nul 2>&1
wmic process where "name='ollama.exe'" call terminate >nul 2>&1

REM 1. Boot Ollama silently in background (no window, logs to file)
start /b "" "D:\CRAVE\Ollama\App\ollama.exe" serve > "D:\CRAVE\Logs\ollama_boot.log" 2>&1

REM 2. Wait 5 seconds for Ollama to initialize
timeout /t 5 /nobreak >nul

REM 3. Boot CRAVE using pythonw.exe (windowless Python — zero CMD)
cd /d "D:\CRAVE"
start "" /b "D:\CRAVE\.venv\Scripts\pythonw.exe" main.py > "D:\CRAVE\Logs\crave_boot.log" 2>&1
exit
