@echo off
rem Windows launcher. Offers to install anything missing first, then prefers
rem .venv so the installed transcription engine is picked up.
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
%PYTHON% bootstrap.py --check
if errorlevel 1 (
  %PYTHON% bootstrap.py || exit /b 1
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py %*
  goto :eof
)
%PYTHON% app.py %*
