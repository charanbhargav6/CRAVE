@echo off
title CRAVE System Status
if defined CRAVE_ROOT (
    python "%CRAVE_ROOT%\crave_status.py"
) else (
    python D:\CRAVE\crave_status.py
)
