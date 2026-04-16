# CRAVE Autoboot Task Scheduler Auto-Registration
# Must run with Administrator privileges!

$TaskName = "CRAVE_Autoboot"
$ActionPath = "wscript.exe"
$ActionArgs = "`"D:\CRAVE\crave_autoboot.vbs`""
$ActionCwd = "D:\CRAVE"

# Creates the principal to run under the current logged in user
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

# Triggers precisely on Desktop presentation
$Trigger = New-ScheduledTaskTrigger -AtLogon

# Action calls the hidden wrapper
$Action = New-ScheduledTaskAction -Execute $ActionPath -Argument $ActionArgs -WorkingDirectory $ActionCwd

# Configure settings (Don't stop if on battery, don't kill after 3 days)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0

Write-Host "Registering Windows Task: $TaskName"
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force

Write-Host "==========================="
Write-Host "CRAVE Autoboot Registered Successfully!"
Write-Host "It will now silently boot your AI assistant entirely in the background the moment you log in."
Write-Host "==========================="
