@echo off
REM Start script for multi_ollama_chat.py
REM Edit variables below to change behavior before running.

SETLOCAL ENABLEDELAYEDEXPANSION

rem Defaults (edit these values as needed)
set "TOPIC=the benefits of remote work"
set "TURNS=10"
set "DELAY=1"
set "HUMANIZE=--humanize"
set "GREETING=Hello, how are you?"
set "MODEL_A=llama2"
set "MODEL_B=llama2"
set "PERSONA_A="
set "PERSONA_B="
set "LOG=%~dp0chat_log.txt"

echo Starting multi_ollama_chat.py with these settings:
echo  TOPIC=%TOPIC%
echo  TURNS=%TURNS%  DELAY=%DELAY%
echo  MODEL_A=%MODEL_A%  MODEL_B=%MODEL_B%
echo  HUMANIZE=%HUMANIZE%  GREETING=%GREETING%
echo  LOG=%LOG%
echo.

python "%~dp0multi_ollama_chat.py" --topic "%TOPIC%" --turns %TURNS% --delay %DELAY% %HUMANIZE% --greeting "%GREETING%" --model-a "%MODEL_A%" --model-b "%MODEL_B%" --persona-a "%PERSONA_A%" --persona-b "%PERSONA_B%" --log "%LOG%"

echo.
echo Press any key to exit...
pause >nul
