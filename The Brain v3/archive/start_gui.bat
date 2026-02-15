@echo off
REM start_gui.bat - launch the Dual Ollama Chat GUI
REM Edit the settings below if you want to change defaults before launch.

SETLOCAL ENABLEDELAYEDEXPANSION

rem Python executable (change if you use a virtualenv)
set "PYTHON=python"

rem Path to the GUI script (keeps it portable when placed in same folder)
set "SCRIPT=%~dp0gui_ollama_chat.py"

echo Launching Dual Ollama Chat GUI...
echo Script: %SCRIPT%
echo Python: %PYTHON%
echo.

%PYTHON% "%SCRIPT%"

echo.
echo GUI exited. Press any key to close this window.
pause >nul
