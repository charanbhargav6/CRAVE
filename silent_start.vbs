' CRAVE Silent Auto-Start (Windows only)
' ────────────────────────────────────────
' This script is placed in the Windows Startup folder to launch
' the CRAVE bot + dashboard silently on login.
'
' NOTE: Windows-only.  Linux/WSL users should use a systemd
' service or crontab @reboot instead.  See .env.example for details.

Set WshShell = CreateObject("WScript.Shell")
Set Env      = WshShell.Environment("Process")

' Read CRAVE_ROOT from env, fallback to D:\CRAVE
crave_root = Env("CRAVE_ROOT")
If crave_root = "" Then crave_root = "D:\CRAVE"

' 1. Start the CRAVE bot silently
WshShell.CurrentDirectory = crave_root
WshShell.Run "python run_bot.py", 0, False

' 2. Start the CRAVE dashboard silently
WshShell.CurrentDirectory = crave_root & "\crave-dashboard"
WshShell.Run "cmd /c npm run dev", 0, False
