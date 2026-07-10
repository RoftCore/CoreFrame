param(
  [string]$InstallDir = "$env:USERPROFILE\CoreFrame",
  [switch]$NoPath
)

$RepoUrl = "https://github.com/RoftCore/CoreFrame.git"

Write-Host "==> CoreFrame Installer" -ForegroundColor Cyan
Write-Host ""

# 1. Check git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "[-] git not found. Install Git for Windows first." -ForegroundColor Red
  exit 1
}

# 2. Check python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
  Write-Host "[-] Python not found. Install Python 3.9+ first." -ForegroundColor Red
  exit 1
}
Write-Host "[*] Python: $($py.Source)" -ForegroundColor Green

# 3. Clone
if (Test-Path $InstallDir) {
  Write-Host "[*] Updating existing installation..." -ForegroundColor Yellow
  Push-Location $InstallDir
  git pull
  Pop-Location
} else {
  Write-Host "[*] Cloning CoreFrame..." -ForegroundColor Gray
  git clone $RepoUrl $InstallDir
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[-] Clone failed" -ForegroundColor Red
    exit 1
  }
}

# 4. Create venv
$venv = "$InstallDir\venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
  Write-Host "[*] Creating virtual environment..." -ForegroundColor Gray
  python -m venv $venv
  if ($LASTEXITCODE -ne 0) { Write-Host "[-] venv failed" -ForegroundColor Red; exit 1 }
}

# 5. Install requirements
Write-Host "[*] Installing dependencies..." -ForegroundColor Gray
& "$venv\Scripts\pip" install -r "$InstallDir\requirements.txt" --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "[-] pip install failed" -ForegroundColor Red; exit 1 }

# 6. Create PATH launcher
if (-not $NoPath) {
  $launcherDir = "$env:USERPROFILE\local\bin"
  $null = New-Item -ItemType Directory -Path $launcherDir -Force
  $launcher = "$launcherDir\coreframe.cmd"
  @"
@echo off
"$InstallDir\venv\Scripts\python.exe" "$InstallDir\run_coreframe.pyw" %*
"@ | Out-File -FilePath $launcher -Encoding ASCII
  Write-Host "[+] Created: $launcher" -ForegroundColor Green

  # Add to PATH if not already
  $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
  if ($userPath -notlike "*$launcherDir*") {
    [Environment]::SetEnvironmentVariable("PATH", "$userPath;$launcherDir", "User")
    $env:PATH = "$env:PATH;$launcherDir"
    Write-Host "[+] Added $launcherDir to user PATH" -ForegroundColor Green
  }
}

Write-Host ""
Write-Host "==> Done!" -ForegroundColor Cyan
Write-Host "    Type 'coreframe' to start CoreFrame"
Write-Host "    Type 'coreframe --dev' for debug mode"
Write-Host "    Open http://127.0.0.1:8420 in your browser"
