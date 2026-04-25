Set WshShell = CreateObject("WScript.Shell")

' 1. Start the CRAVE bot silently
WshShell.CurrentDirectory = "D:\CRAVE"
WshShell.Run "python run_bot.py", 0, False

' 2. Start the CRAVE dashboard silently
WshShell.CurrentDirectory = "D:\CRAVE\crave-dashboard"
WshShell.Run "cmd /c npm run dev", 0, False
