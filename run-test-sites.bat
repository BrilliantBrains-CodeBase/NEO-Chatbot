@echo off
title Chatbot test sites (http://127.0.0.1:4173)
cd /d "%~dp0..\test-sites"
echo Test sites at http://127.0.0.1:4173  (backend must be running on port 8000)
start "" http://127.0.0.1:4173/
python -m http.server 4173 --bind 127.0.0.1
pause
