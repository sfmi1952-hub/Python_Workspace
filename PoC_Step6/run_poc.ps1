# PoC_Step6 - 사외 SOTA LLM (Claude Opus 4.7) vs 사내 sLM (GPT-OSS) 진단코드 추출 비교 실험
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " PoC_Step6 : 진단코드 추출 LLM 성능 비교 실험" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# 환경변수 안내 (사전 세팅 필요)
Write-Host "[필수 환경변수]" -ForegroundColor Yellow
Write-Host "  Claude Opus 4.7:"
Write-Host "    `$env:ANTHROPIC_API_KEY = 'sk-ant-...'"
Write-Host "    (또는 Bedrock 사용 시: `$env:ANTHROPIC_USE_BEDROCK = 'true'; `$env:AWS_REGION = 'us-east-1')"
Write-Host ""
Write-Host "  사내 GPT-OSS:"
Write-Host "    `$env:GPT_OSS_API_BASE = 'http://gpt-oss.internal:8000/v1'"
Write-Host "    `$env:GPT_OSS_API_KEY  = '<사내키 또는 EMPTY>'"
Write-Host "    `$env:GPT_OSS_MODEL    = 'gpt-oss-120b'"
Write-Host ""

# Venv Python 우선 사용 (PoC_Step3 와 동일한 venv 공유)
$VenvPython = Join-Path $PSScriptRoot "..\venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
    Write-Host "Using venv python: $PythonExe" -ForegroundColor Green
} else {
    Write-Warning "Venv not found at $VenvPython, falling back to global python."
    $PythonExe = "python"
}

# 인자 전달 (예: .\run_poc.ps1 --target alpha)
$ScriptArgs = $args
Write-Host ""
Write-Host "Running: $PythonExe run_comparison.py $ScriptArgs" -ForegroundColor Green
Write-Host ""

& $PythonExe (Join-Path $PSScriptRoot "run_comparison.py") @ScriptArgs

Write-Host ""
Write-Host "결과 파일 위치: $(Join-Path $PSScriptRoot 'data\result')" -ForegroundColor Cyan
