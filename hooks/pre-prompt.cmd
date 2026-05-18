@echo off
REM Windows CMD wrapper — delegates to Python runner
setlocal

set "PLUGIN_DIR=%~dp0.."

if exist "%PLUGIN_DIR%\.venv\Scripts\python.exe" (
  set "PY=%PLUGIN_DIR%\.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

"%PY%" "%PLUGIN_DIR%\scripts\hook_runner.py"
