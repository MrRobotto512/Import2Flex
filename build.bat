@echo off
REM Builds dist\Import2Flex.exe (a single file - no Python needed to run it).
setlocal
cd /d "%~dp0"

if not exist .venv (
    py -3 -m venv .venv || python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip >nul
python -m pip install -r requirements-dev.txt || goto :error
python -m pytest -q || goto :error
python tools\make_icon.py || goto :error

pyinstaller --noconfirm --clean --onefile --windowed ^
    --name Import2Flex --icon build\icon.ico ^
    Import2Flex.pyw || goto :error

echo.
echo Built: %CD%\dist\Import2Flex.exe
exit /b 0

:error
echo Build failed.
exit /b 1
