@echo off
setlocal
cd /d "%~dp0\.."
if not defined OLLAMA_MODEL set OLLAMA_MODEL=llama3.1:8b
python -m main.app --host 127.0.0.1 --http-port 8080 --ws-port 8765 --ollama-model %OLLAMA_MODEL%
endlocal
