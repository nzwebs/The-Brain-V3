@echo off
rem Launch GUI without a console window (uses pythonw). No terminal will appear.
set "SCRIPT=%~dp0gui_ollama_chat.py"
start "" pythonw "%SCRIPT%"
exit
