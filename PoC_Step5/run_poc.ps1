Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  PoC Step 5: Adobe vs Baseline Comparison " -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

$VenvPython = "..\venv\Scripts\python.exe"

# Default file paths (modify as needed)
$DocxFile = "data\input\docx\sample.docx"
$PdfFile  = "data\input\pdf\sample.pdf"
$GtFile   = "data\input\ground_truth\expected.xlsx"

# Check virtual environment
if (-Not (Test-Path $VenvPython)) {
    Write-Warning "Virtual environment not found at $VenvPython"
    Write-Host "Trying global python..." -ForegroundColor Yellow
    $VenvPython = "python"
}

# Check input files
$MissingFiles = @()
if (-Not (Test-Path $DocxFile)) { $MissingFiles += $DocxFile }
if (-Not (Test-Path $PdfFile))  { $MissingFiles += $PdfFile }
if (-Not (Test-Path $GtFile))   { $MissingFiles += $GtFile }

if ($MissingFiles.Count -gt 0) {
    Write-Host ""
    Write-Warning "Missing input files:"
    foreach ($f in $MissingFiles) {
        Write-Host "  - $f" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "Please place your test files in the data/input/ directories:" -ForegroundColor Yellow
    Write-Host "  - data/input/docx/    : .docx files" -ForegroundColor Yellow
    Write-Host "  - data/input/pdf/     : .pdf files" -ForegroundColor Yellow
    Write-Host "  - data/input/ground_truth/ : ground truth .xlsx" -ForegroundColor Yellow
    Write-Host ""

    # Ask user to continue anyway
    $choice = Read-Host "Run with available files only? (y/n)"
    if ($choice -ne "y") { exit 1 }
}

# Run comparison
Write-Host ""
Write-Host "Starting comparison pipeline..." -ForegroundColor Green

$Args = @()
if (Test-Path $DocxFile) { $Args += "--docx"; $Args += $DocxFile }
if (Test-Path $PdfFile)  { $Args += "--pdf";  $Args += $PdfFile }
$Args += "--ground-truth"
$Args += $GtFile
$Args += "-v"

# Determine method based on available files
if ((Test-Path $DocxFile) -and (Test-Path $PdfFile)) {
    $Args += "--method"; $Args += "both"
} elseif (Test-Path $DocxFile) {
    $Args += "--method"; $Args += "method1"
} elseif (Test-Path $PdfFile) {
    $Args += "--method"; $Args += "method2"
}

& $VenvPython run_cli.py @Args

Write-Host ""
Write-Host "Done! Check data/output/ for results." -ForegroundColor Green
