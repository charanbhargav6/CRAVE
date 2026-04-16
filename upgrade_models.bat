@echo off
echo Starting CRAVE Auto-Upgrade Protocol...
echo Purging older 8B models...
"D:\CRAVE\Ollama\App\ollama.exe" rm qwen3:8b-q4_K_M
"D:\CRAVE\Ollama\App\ollama.exe" rm deepseek-r1:8b-0528-qwen3-q4_K_M
"D:\CRAVE\Ollama\App\ollama.exe" rm gemma3:12b-it-q4_K_M
echo ------------------------------------------
echo Pulling qwen2.5:14b (Primary Engine)...
"D:\CRAVE\Ollama\App\ollama.exe" pull qwen2.5:14b
echo ------------------------------------------
echo Pulling deepseek-r1:14b (Reasoning Engine)...
"D:\CRAVE\Ollama\App\ollama.exe" pull deepseek-r1:14b
echo ------------------------------------------
echo Pulling llama3.2-vision:11b (Vision Sandbox)...
"D:\CRAVE\Ollama\App\ollama.exe" pull llama3.2-vision:11b
echo ------------------------------------------
echo Upgrade Complete! You can now safely close this window.
pause
