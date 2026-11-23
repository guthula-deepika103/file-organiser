@echo off
REM Double-click to start the File Organizer web app (opens http://127.0.0.1:5000)
cd /d "%~dp0"
where py >nul 2>nul && (py -3 run_app.py web & goto :end)
python run_app.py web
:end
pause
