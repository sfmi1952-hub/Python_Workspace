# Start Backend
Write-Host "Starting Python Backend..." -ForegroundColor Green
Start-Process cmd -ArgumentList "/k python server.py" -WorkingDirectory "$PSScriptRoot"

# Start Frontend
Write-Host "Starting React Frontend..." -ForegroundColor Green
Set-Location "$PSScriptRoot\web_ui"
# Ensure we have the path to npm
$env:Path = $env:Path + ";C:\Program Files\nodejs"
npm run dev
