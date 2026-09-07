@echo off
rem One-time setup: create .venv and install the portable Parakeet engine.
cd /d "%~dp0"

set PYTHON=
where py >nul 2>&1 && set PYTHON=py -3
if "%PYTHON%"=="" (
  where python >nul 2>&1 && set PYTHON=python
)
if "%PYTHON%"=="" (
  echo Python 3.10 or newer is required but was not found on PATH.
  exit /b 1
)

if not exist ".venv" (
  echo Creating .venv
  %PYTHON% -m venv .venv || exit /b 1
)

echo Installing the Parakeet (ONNX) transcription engine
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install "onnx-asr[cpu,hub]" || exit /b 1

echo.
".venv\Scripts\python.exe" app.py --engines
echo.
echo Setup complete. Start the app with:  start.bat
