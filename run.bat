@echo off
REM Run from source (first run installs PySide6 into a local .venv).
cd /d "%~dp0"
if not exist .venv (
    py -3 -m venv .venv || python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
)
start "" .venv\Scripts\pythonw.exe Import2Flex.pyw %*
