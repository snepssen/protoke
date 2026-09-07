@echo off
rem Windows launcher. Prefers .venv so an installed transcription engine is
rem picked up, then falls back to the py launcher or python on PATH.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py %*
  goto :eof
)
where py >nul 2>&1
if %errorlevel%==0 (
  py -3 app.py %*
  goto :eof
)
where python >nul 2>&1
if %errorlevel%==0 (
  python app.py %*
  goto :eof
)
echo Python 3.10 or newer is required but was not found on PATH.
exit /b 1
