# Windows PowerShell Launcher for SOXL Stock Dashboard
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host " Starting SOXL Dashboard Local CORS Proxy Server" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

# Find python executable
$PythonCmd = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { $null }

if (-not $PythonCmd) {
    Write-Host "Error: Python is not installed or not in PATH!" -ForegroundColor Red
    Write-Host "Please install Python 3 from https://www.python.org/"
    Read-Host "Press [Enter] to exit..."
    exit 1
}

# Check port 8080
$PortInUse = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue

if ($PortInUse) {
    Write-Host "Port 8080 is already in use. Local proxy might already be running." -ForegroundColor Yellow
} else {
    Write-Host "Starting local CORS proxy on http://localhost:8080 ..." -ForegroundColor Green
    Start-Process -FilePath $PythonCmd -ArgumentList "local_proxy.py 8080" -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

Write-Host "Opening dashboard in default web browser..." -ForegroundColor Green
Start-Process "http://localhost:8080/"

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "Dashboard is running at http://localhost:8080/" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Cyan
Read-Host "Press [Enter] to close this window..."
