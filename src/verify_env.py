"""
CRAVE Phase 1 - Environment Verification Script
Save to: D:\\CRAVE\\src\\verify_env.py
Run:     cd D:\\CRAVE  then  .venv\\Scripts\\activate  then  python src\\verify_env.py
"""

import sys, os, json, subprocess, importlib.util

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

passed = 0
failed = 0
CRAVE = "D:" + chr(92) + "CRAVE"
SEP    = chr(92)

def p(rel):
    return CRAVE + SEP + rel.replace("/", SEP)

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
    d = ("  ->  " + detail) if detail else ""
    print(f"  {YELLOW}[ WARN ]{RESET}  {label}{d}")

def section(title):
    print(f"\n{BOLD}{BLUE}{chr(9472)*55}{RESET}")
    print(f"{BOLD}{BLUE}  {title}{RESET}")
    print(f"{BOLD}{BLUE}{chr(9472)*55}{RESET}")

print(f"\n{BOLD}{'='*57}")
print("   CRAVE 2026  -  Phase 1 Environment Check")
print(f"{'='*57}{RESET}")

# 1. Python version
section("1. Python Version")
major, minor = sys.version_info.major, sys.version_info.minor
ver = f"{major}.{minor}.{sys.version_info.micro}"
if major == 3 and minor == 11:
    ok(f"Python {ver}")
else:
    fail(f"Python {ver}  (need 3.11.x)", "python.org/downloads -> download 3.11")

# 2. Virtual environment
section("2. Virtual Environment")
if sys.prefix != sys.base_prefix:
    ok("Running inside .venv")
else:
    fail("Not inside .venv", "Run: " + CRAVE + SEP + ".venv" + SEP + "Scripts" + SEP + "activate")

if os.path.isdir(p(".venv")):
    ok(CRAVE + SEP + ".venv  exists")
else:
    fail(CRAVE + SEP + ".venv  not found", "cd " + CRAVE + " && python -m venv .venv")

# 3. Hardware config
section("3. Hardware Config File")
cfg_path = p("config/hardware.json")
if os.path.isfile(cfg_path):
    ok(CRAVE + SEP + "config" + SEP + "hardware.json  found")
    try:
        with open(cfg_path) as f:
            cfg = json.load(f)
        need = ["ram_gb", "concurrent_models", "ollama_host", "models", "whisper"]
        miss = [k for k in need if k not in cfg]
        if not miss:
            ok("hardware.json has all required keys")
            ok(f"RAM: {cfg.get('ram_gb')} GB   concurrent: {cfg.get('concurrent_models')}")
        else:
            fail(f"hardware.json missing keys: {miss}", "Re-copy hardware.json from Phase 1 files")
    except Exception as e:
        fail(f"hardware.json parse error: {e}")
else:
    fail(CRAVE + SEP + "config" + SEP + "hardware.json  not found",
         "Copy the hardware.json to " + CRAVE + SEP + "config" + SEP)

# 4. Folder structure
section("4. Folder Structure")
folders = [
    "config", "data", "Knowledge", "Knowledge/skills",
    "Logs", "Main_Lead", "models", "plugins",
    "src", "src/core", "src/agents", "src/security",
    "src/tools", "src/ui",
    "tools/ffmpeg", "tools/fastsd",
    "Sub_Projects/Trading", "Sub_Projects/Hacking",
]
for rel in folders:
    full = p(rel)
    display = CRAVE + SEP + rel.replace("/", SEP)
    if os.path.isdir(full):
        ok(display)
    else:
        fail(display + "  MISSING", "mkdir " + full)

# 5. __init__.py files
section("5. Python Package Files")
inits = ["src", "src/core", "src/agents", "src/security", "src/tools", "src/ui"]
for rel in inits:
    fp = p(rel + "/__init__.py")
    display = CRAVE + SEP + rel.replace("/",SEP) + SEP + "__init__.py"
    if os.path.isfile(fp):
        ok(display)
    else:
        fail(display + "  MISSING", "type nul > " + fp)

# 6. Environment variables
section("6. Environment Variables")
om = os.environ.get("OLLAMA_MODELS", "")
if "CRAVE" in om or "crave" in om:
    ok("OLLAMA_MODELS = " + om)
else:
    fail("OLLAMA_MODELS not set correctly  (got: " + repr(om) + ")",
         "System Properties -> Env Vars -> OLLAMA_MODELS = " + CRAVE + SEP + "Ollama" + SEP + "Models")

oh = os.environ.get("OLLAMA_HOST", "")
if oh:
    ok("OLLAMA_HOST = " + oh)
else:
    warn("OLLAMA_HOST not set  (OK - default 127.0.0.1:11434 used)")

# 7. Ollama service + models
section("7. Ollama Service and Models")
try:
    import urllib.request
    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as r:
        data = json.loads(r.read())
    names = [m["name"] for m in data.get("models", [])]
    ok(f"Ollama running  ({len(names)} models loaded)")
    for m in ["qwen3:8b-q4_K_M",
              "deepseek-r1:8b-0528-qwen3-q4_K_M",
              "gemma3:12b-it-q4_K_M"]:
        if any(m in n for n in names):
            ok("Model ready: " + m)
        else:
            fail("Model missing: " + m, "ollama pull " + m)
except Exception as e:
    fail("Ollama not reachable: " + str(e),
         "Open a new CMD window and run:  ollama serve")
    warn("Skipping model checks (Ollama offline)")

# 8. FFmpeg
section("8. FFmpeg")
try:
    r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    if r.returncode == 0:
        ok("ffmpeg in PATH  ->  " + r.stdout.split("\n")[0][:55])
    else:
        fail("ffmpeg not found in PATH",
             "Add " + CRAVE + SEP + "tools" + SEP + "ffmpeg" + SEP +
             "ffmpeg-8.1-essentials_build" + SEP + "bin  to System PATH, then restart CMD")
except FileNotFoundError:
    fail("ffmpeg not found in PATH (WinError 2)",
         "Add " + CRAVE + SEP + "tools" + SEP + "ffmpeg" + SEP +
         "ffmpeg-8.1-essentials_build" + SEP + "bin  to System PATH, then restart CMD")

# 9. Python packages
section("9. Python Packages")
pkgs = {
    "faster_whisper":   "faster-whisper",
    "kokoro_onnx":      "kokoro-onnx",
    "pvporcupine":      "pvporcupine",
    "PyQt6":            "PyQt6",
    "langchain":        "langchain",
    "langgraph":        "langgraph",
    "ollama":           "ollama",
    "cryptography":     "cryptography",
    "bcrypt":           "bcrypt",
    "pptx":             "python-pptx",
    "telegram":         "python-telegram-bot",
    "requests":         "requests",
    "psutil":           "psutil",
    "pyaudio":          "pyaudio",
    "ffmpeg":           "ffmpeg-python",
    "pywinauto":        "pywinauto",
    "pyautogui":        "pyautogui",
    "selenium":         "selenium",
    "playwright":       "playwright",
    "alpaca_trade_api": "alpaca-trade-api",
    "MetaTrader5":      "MetaTrader5",
    "backtrader":       "backtrader",
    "backtesting":      "backtesting",
    "paramiko":         "paramiko",
    "schedule":         "schedule",
    "sounddevice":      "sounddevice",
    "soundfile":        "soundfile",
    "numpy":            "numpy",
    "mss":              "mss",
}
for imp, pip_name in pkgs.items():
    if importlib.util.find_spec(imp) is not None:
        ok(pip_name)
    else:
        fail(pip_name + "  not installed", "pip install " + pip_name)

# 10. Whisper
section("10. Whisper (auto-downloads on first voice command)")
try:
    from faster_whisper import WhisperModel
    ok("faster_whisper importable")
    warn("Whisper small  (244 MB)  ->  downloads on first Hey-CRAVE wake")
    warn("Whisper medium (500 MB)  ->  downloads on first long command")
    ok("Both models save to " + CRAVE + SEP + "models" + SEP)
except Exception as e:
    fail("faster_whisper error: " + str(e), "pip install faster-whisper")

# 11. WSL2 + Kali
section("11. WSL2 + Kali Linux  (needed for Phase 7)")
try:
    wsl = subprocess.run(["wsl","--list","--verbose"], capture_output=True, text=True)
    if wsl.returncode == 0:
        if "kali" in wsl.stdout.lower():
            ok("Kali Linux found in WSL2")
            kt = subprocess.run(["wsl","-d","kali-linux","uname","-r"],
                                capture_output=True, text=True, timeout=15)
            if kt.returncode == 0:
                ok("Kali responds: " + kt.stdout.strip()[:40])
            else:
                fail("Kali WSL2 not responding", "Open Kali from Start Menu and finish setup")
        else:
            warn("Kali Linux NOT in WSL2 yet  ->  needed for Phase 7 only")
    else:
        warn("WSL2 not ready yet  ->  needed for Phase 7 hacking module")
except FileNotFoundError:
    warn("WSL is not installed or not in PATH -> needed for Phase 7 hacking module")

# 12. mss screen capture
section("12. mss Direct Screen Capture")
try:
    import mss
    with mss.mss() as s:
        monitors = s.monitors
    ok(f"mss working  ->  {len(monitors)-1} monitor(s)")
except ImportError:
    fail("mss not installed", "pip install mss")
except Exception as e:
    warn("mss installed but: " + str(e))

# 13. Telegram token
section("13. Telegram Bot Token  (needed for Phase 5 security)")
tok = p("data/telegram_token.txt")
if os.path.isfile(tok):
    with open(tok) as f:
        t = f.read().strip()
    if len(t) > 20:
        ok("Telegram token found in data" + SEP + "telegram_token.txt")
    else:
        fail("telegram_token.txt is empty", "Paste your BotFather token into the file")
else:
    warn("telegram_token.txt not created yet")
    warn("Get from @BotFather on Telegram  ->  paste into " + CRAVE + SEP + "data" + SEP + "telegram_token.txt")

# Summary
section("FINAL RESULT")
total = passed + failed
bar_w = 40
filled = int(bar_w * passed / total) if total else 0
bar = chr(9608) * filled + chr(9617) * (bar_w - filled)
pct = int(100 * passed / total) if total else 0
print(f"\n  [{bar}]  {pct}%")
print(f"\n  {GREEN}{BOLD}{passed} passed{RESET}   {RED}{BOLD}{failed} failed{RESET}   ({total} total)\n")
if failed == 0:
    print(f"  {GREEN}{BOLD}ALL PASSED  -  Phase 1 complete!{RESET}")
    print(f"  {GREEN}Next step: tell Claude 'Write Phase 2'{RESET}\n")
elif failed <= 3:
    print(f"  {YELLOW}{BOLD}Almost there - fix the {failed} item(s) above then re-run.{RESET}\n")
else:
    print(f"  {RED}{BOLD}Fix the FAIL items above, re-run this script after each fix.{RESET}\n")