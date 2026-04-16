"""
CRAVE Live Dashboard
Run: python -m src.ui.dashboard

A rich-based terminal dashboard for real-time system monitoring.
Reads shared state files, does NOT import or start the orchestrator.
"""

import os
import sys
import json
import time
import datetime
import platform

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

CRAVE_ROOT = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

try:
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.console import Console
    from rich.text import Text
    from rich import box
    _RICH = True
except ImportError:
    _RICH = False
    print("❌ 'rich' not installed. Run: pip install rich")
    sys.exit(1)


def _get_cpu_temp() -> str:
    """Get CPU temperature if available."""
    if not _PSUTIL:
        return "N/A"
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for name, entries in temps.items():
                if entries:
                    return f"{entries[0].current:.0f}°C"
        # Fallback for Windows (no temp sensor via psutil)
        return "N/A (Windows)"
    except:
        return "N/A"


def _get_ram_usage() -> str:
    """Get RAM usage percentage."""
    if not _PSUTIL:
        return "N/A"
    mem = psutil.virtual_memory()
    return f"{mem.percent}% ({mem.used / (1024**3):.1f}/{mem.total / (1024**3):.1f} GB)"


def _get_cpu_usage() -> str:
    """Get CPU usage."""
    if not _PSUTIL:
        return "N/A"
    return f"{psutil.cpu_percent(interval=0.5)}%"


def _get_active_model() -> str:
    """Read active model from hardware.json."""
    try:
        with open(os.path.join(CRAVE_ROOT, "config", "hardware.json"), "r") as f:
            cfg = json.load(f)
        return cfg.get("models", {}).get("primary", "unknown")
    except:
        return "config error"


def _get_tts_engine() -> str:
    """Read TTS engine selection."""
    try:
        with open(os.path.join(CRAVE_ROOT, "config", "hardware.json"), "r") as f:
            cfg = json.load(f)
        return cfg.get("tts_engine", "edge-tts")
    except:
        return "unknown"


def _check_ollama() -> str:
    """Check if Ollama is responding."""
    try:
        import requests
        resp = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            return f"✅ Online ({len(models)} models)"
        return f"⚠️ HTTP {resp.status_code}"
    except:
        return "❌ Offline"


def _check_telegram() -> str:
    """Check telegram token validity."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return "⚠️ No token"
    parts = token.split(":")
    if len(parts) == 2 and parts[0].isdigit():
        return f"✅ Token set (***{parts[0][-3:]})"
    return "❌ Invalid format"


def _get_face_id_status() -> str:
    """Check face enrollment status."""
    enc_path = os.path.join(CRAVE_ROOT, "data", "face_encodings.dat")
    if os.path.exists(enc_path):
        return "✅ Enrolled"
    return "⚠️ Not enrolled"


def _get_uptime() -> str:
    """Get system uptime."""
    if not _PSUTIL:
        return "N/A"
    boot = psutil.boot_time()
    uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(boot)
    hours = int(uptime.total_seconds() // 3600)
    mins = int((uptime.total_seconds() % 3600) // 60)
    return f"{hours}h {mins}m"


def _last_log_lines(n: int = 5) -> list[str]:
    """Read last N lines from crave.log."""
    log_path = os.path.join(CRAVE_ROOT, "logs", "crave.log")
    if not os.path.exists(log_path):
        return ["(no log file found)"]
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return [l.strip()[:80] for l in lines[-n:]] if lines else ["(empty log)"]
    except:
        return ["(read error)"]


def _build_dashboard() -> Layout:
    """Build the full dashboard layout."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=8),
    )

    # Header
    header_text = Text("  🧠 CRAVE LIVE DASHBOARD", style="bold cyan")
    header_text.append(f"  │  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", style="dim")
    layout["header"].update(Panel(header_text, style="cyan"))

    # Body — two columns
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )

    # Left: System Stats
    sys_table = Table(title="System", box=box.ROUNDED, border_style="green", expand=True)
    sys_table.add_column("Metric", style="bold")
    sys_table.add_column("Value", style="green")
    sys_table.add_row("CPU Usage", _get_cpu_usage())
    sys_table.add_row("CPU Temp", _get_cpu_temp())
    sys_table.add_row("RAM Usage", _get_ram_usage())
    sys_table.add_row("Uptime", _get_uptime())
    sys_table.add_row("Platform", f"{platform.system()} {platform.release()}")

    layout["left"].update(sys_table)

    # Right: CRAVE Status
    crave_table = Table(title="CRAVE", box=box.ROUNDED, border_style="magenta", expand=True)
    crave_table.add_column("Component", style="bold")
    crave_table.add_column("Status", style="magenta")
    crave_table.add_row("Ollama", _check_ollama())
    crave_table.add_row("Active Model", _get_active_model())
    crave_table.add_row("TTS Engine", _get_tts_engine())
    crave_table.add_row("Telegram", _check_telegram())
    crave_table.add_row("Face ID", _get_face_id_status())
    
    # Check Evolution status
    try:
        evo_state = "Idle"
        state_path = os.path.join(CRAVE_ROOT, "data", "model_manager_state.json")
        if os.path.exists(state_path):
            with open(state_path, "r") as f:
                state = json.load(f)
                last_chk = state.get("last_model_check")
                if last_chk:
                    dt = datetime.datetime.fromisoformat(last_chk)
                    evo_state = f"Checked {dt.strftime('%b %d')}"
        
        sandbox_path = os.path.join(CRAVE_ROOT, ".sandbox")
        if os.path.exists(sandbox_path) and os.listdir(sandbox_path):
            evo_state = "⚠️ Self-Modifying"
            
        crave_table.add_row("Evolution", evo_state)
    except:
        pass

    layout["right"].update(crave_table)

    # Footer: Recent Logs
    log_lines = _last_log_lines(5)
    log_text = "\n".join(log_lines)
    layout["footer"].update(
        Panel(log_text, title="Recent Logs", border_style="yellow", style="dim")
    )

    return layout


def main():
    """Run the live dashboard with 5-second refresh."""
    console = Console()
    console.clear()

    print("  Starting CRAVE Dashboard... (Ctrl+C to exit)\n")

    try:
        with Live(_build_dashboard(), console=console, refresh_per_second=0.2) as live:
            while True:
                time.sleep(5)
                live.update(_build_dashboard())
    except KeyboardInterrupt:
        print("\n  Dashboard closed.")


if __name__ == "__main__":
    main()
