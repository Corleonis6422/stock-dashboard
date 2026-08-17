@echo off
title SOXL Stock Dashboard Launcher
echo =================================================
echo  Starting SOXL Dashboard Local CORS Proxy Server
echo =================================================

rem Get script directory
set "DIR=%~dp0"
cd /d "%DIR%"

rem Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    py --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo Error: Python is not installed or not in PATH!
        echo Please install Python 3 from https://www.python.org/
        pause
        exit /b 1
    ) else (
        set "PY_CMD=py"
    )
) else (
    set "PY_CMD=python"
)

rem Check if port 8080 is in use
netstat -ano | findstr /R /C:":8080 .*LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo Port 8080 is already in use. Local proxy might already be running.
) else (
    echo Starting local CORS proxy on http://localhost:8080 ...
    start /B "" %PY_CMD% "%DIR%local_proxy.py" 8080 >nul 2>&1
    timeout /t 2 /nobreak >nul
)

echo Opening dashboard in default web browser...
start http://localhost:8080/

echo =================================================
echo Dashboard is running at http://localhost:8080/
echo To stop the proxy server, close this window or kill python process.
echo =================================================
echo.
pause
