@echo off
rem Install everything Protoke needs without asking: ffmpeg with libass via
rem winget, and .venv with the Parakeet transcription engine.
rem   setup.bat --with-separation   also vocal separation (PyTorch, ~1 GB)
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
%PYTHON% bootstrap.py --yes %*
if not exist ".venv\Scripts\python.exe" exit /b 1
echo.
".venv\Scripts\python.exe" app.py --engines
echo.
echo Setup complete. Start the app with:  start.bat
