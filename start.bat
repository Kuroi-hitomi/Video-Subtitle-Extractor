@echo off
setlocal
cd /d "%~dp0"
call "%~dp0run_python.bat" runtime_launcher.py start
if errorlevel 1 pause
