Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "D:\CRAVE\crave_autoboot.bat" & Chr(34), 0, False
Set WshShell = Nothing
