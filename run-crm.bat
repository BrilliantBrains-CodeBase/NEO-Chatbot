@echo off
title NEO CRM (http://localhost:3000)
cd /d "%~dp0frontend\crm"
echo Starting NEO CRM at http://localhost:3000
call npm run dev
pause
