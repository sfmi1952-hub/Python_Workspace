# run_poc.ps1
Write-Host "Started PoC Step 1 Environment" -ForegroundColor Cyan

# 1. Generate Samples (if minimal)
python create_samples.py

# 2. Start Backend (Port 8001)
Write-Host "Starting Backend on Port 8001..." -ForegroundColor Green
Write-Host "A new window should open for the Backend." -ForegroundColor Yellow
# Use the venv python explicitly
$VenvPython = "..\venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    Start-Process cmd -ArgumentList "/k title PoC Backend (8001) && $VenvPython server.py" -WorkingDirectory "$PSScriptRoot"
}
else {
    Write-Warning "Venv not found at $VenvPython, trying global python..."
    Start-Process cmd -ArgumentList "/k title PoC Backend (8001) && python server.py" -WorkingDirectory "$PSScriptRoot"
}

# 3. Start Frontend (Port 5174)
Write-Host "Starting Frontend on Port 5174..." -ForegroundColor Green
Set-Location "$PSScriptRoot\web_ui"
# Ensure we have the path to npm
$env:Path = $env:Path + ";C:\Program Files\nodejs"
npm run dev
