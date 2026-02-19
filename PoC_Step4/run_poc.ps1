# run_poc.ps1
Write-Host "Started PoC Step 4 Environment (Risk-Based Inference)" -ForegroundColor Cyan

# 1. Start Backend (Port 8002)
Write-Host "Starting Backend on Port 8002..." -ForegroundColor Green
Write-Host "A new window should open for the Backend." -ForegroundColor Yellow

# Use the shared venv python (Assuming it's in Python_Workspace/venv)
$VenvPython = "..\venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    Start-Process cmd -ArgumentList "/k title PoC Step 4 Backend (8002) && $VenvPython server.py" -WorkingDirectory "$PSScriptRoot"
}
else {
    Write-Warning "Venv not found at $VenvPython, trying global python..."
    Start-Process cmd -ArgumentList "/k title PoC Step 4 Backend (8002) && python server.py" -WorkingDirectory "$PSScriptRoot"
}

# 2. Start Frontend
Write-Host "Starting Frontend..." -ForegroundColor Green
Set-Location "$PSScriptRoot\web_ui"
# Ensure we have the path to npm
$env:Path = $env:Path + ";C:\Program Files\nodejs"
npm run dev
