Write-Host "==> CoreFrame Installer" -ForegroundColor Cyan
Write-Host ""

# 1. Check python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
  Write-Host "[-] Python not found. Install Python 3.9+ first." -ForegroundColor Red
  exit 1
}
Write-Host "[*] Python: $($py.Source)" -ForegroundColor Green

# 2. Install via pip
Write-Host "[*] Installing coreframe-roftcore..." -ForegroundColor Gray
pip install coreframe-roftcore --quiet
if ($LASTEXITCODE -ne 0) {
  Write-Host "[-] pip install failed" -ForegroundColor Red
  exit 1
}

Write-Host ""
Write-Host "==> Done!" -ForegroundColor Cyan
Write-Host "    Type 'coreframe' to start CoreFrame"
Write-Host "    Type 'coreframe --dev' for debug mode"
Write-Host "    Open http://127.0.0.1:5000 in your browser"
