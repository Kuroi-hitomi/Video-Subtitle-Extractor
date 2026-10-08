@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -X utf8 %*
  exit /b
)
where python >nul 2>nul
if not errorlevel 1 (
  python -X utf8 %*
  exit /b
)
echo Python was not found. Install 64-bit Python with Tcl/Tk support.
exit /b 1
