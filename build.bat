@echo off
REM Builds the app into dist\Import2Flex\ and, if Inno Setup 6 is installed,
REM the installer dist\Import2Flex-Setup-<version>.exe.
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

pyinstaller --noconfirm --clean --windowed ^
    --name Import2Flex --icon build\icon.ico ^
    Import2Flex.pyw || goto :error
echo Built: %CD%\dist\Import2Flex\Import2Flex.exe

for /f %%v in ('python -c "import import2flex; print(import2flex.__version__)"') do set VERSION=%%v
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo.
    echo Inno Setup 6 not found - skipping the installer.
    echo Get it from https://jrsoftware.org/isdl.php to build Import2Flex-Setup.exe
    exit /b 0
)
"%ISCC%" /DMyAppVersion=%VERSION% installer\Import2Flex.iss || goto :error
echo Built: %CD%\dist\Import2Flex-Setup-%VERSION%.exe
exit /b 0

:error
echo Build failed.
exit /b 1
