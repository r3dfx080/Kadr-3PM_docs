@echo off
rem Double-click: start the editable viewer (kb/tools/serve.py) and open it in the browser.
rem If the server is already running, only the browser opens. Close this window to stop the server.
cd /d "%~dp0"
set URL=http://127.0.0.1:8765/kb/viewer/index.html
netstat -ano | findstr /r /c:"127.0.0.1:8765 .*LISTENING" >nul && (start "" %URL% & exit /b)
start "" cmd /c "timeout /t 2 /nobreak >nul & start "" %URL%"
python -I -X utf8 kb/tools/serve.py
pause
