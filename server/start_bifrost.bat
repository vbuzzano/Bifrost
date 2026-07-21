@echo off
REM Launches Bifrost server headless (pythonw, no console window).
REM stdout/stderr are redirected to bifrost.log - pythonw has no console,
REM so unredirected print() calls would crash with AttributeError.
REM -u = unbuffered, so the log actually has content if it crashes early
REM instead of losing everything sitting in an unflushed buffer.
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    ".venv\Scripts\pythonw.exe" -u main.py >> bifrost.log 2>&1
) else (
    pythonw -u main.py >> bifrost.log 2>&1
)
