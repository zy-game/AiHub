@echo off
echo Stopping old server...
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul

echo Starting AiHub server...
cd /d E:\AiHub
python main.py
