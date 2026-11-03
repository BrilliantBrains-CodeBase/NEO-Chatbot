@echo off
title NEO Chatbot Widgets (http://127.0.0.1:5173)
cd /d "%~dp0frontend\widgets"
echo Starting chatbot widgets playground at http://127.0.0.1:5173
call npm run dev
pause
