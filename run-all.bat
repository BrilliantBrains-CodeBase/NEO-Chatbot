@echo off
rem Starts everything in order, each in its own window: backend, widgets, CRM, test sites.
rem Close old server windows first, or the ports will be busy.

echo 1/4 Starting backend...
start "NEO Backend" cmd /k "%~dp0run-backend.bat"
echo     waiting for backend to be ready...
:wait_backend
timeout /t 2 /nobreak >nul
curl -s -o nul http://127.0.0.1:8000/v1/health/ready || goto wait_backend

echo 2/4 Starting chatbot widgets...
start "NEO Widgets" cmd /k "%~dp0run-widgets.bat"

echo 3/4 Starting CRM...
start "NEO CRM" cmd /k "%~dp0run-crm.bat"

echo 4/4 Starting test sites...
start "Test sites" cmd /k "%~dp0run-test-sites.bat"

echo.
echo Backend     http://localhost:8000/docs
echo Widgets     http://127.0.0.1:5173/playground/
echo CRM         http://localhost:3000
echo Test sites  http://127.0.0.1:4173
