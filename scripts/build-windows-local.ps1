# Rúnmál local Windows package builder
# Builds entirely on the current Windows machine. No GitHub Actions or hosted CI.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if ($env:OS -ne "Windows_NT") {
    throw "This builder must be run on Windows."
}

function Resolve-Python312 {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try {
            & py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)"
            if ($LASTEXITCODE -eq 0) { return @("py", "-3.12") }
        } catch { }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        & python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)"
        if ($LASTEXITCODE -eq 0) { return @("python") }
    }

    throw "Python 3.12 or newer is required to build Rúnmál locally."
}

$PythonCmd = Resolve-Python312
$BuildVenv = Join-Path $RepoRoot ".runmal-build-venv"
$VenvPython = Join-Path $BuildVenv "Scripts\python.exe"
$VenvPyInstaller = Join-Path $BuildVenv "Scripts\pyinstaller.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating isolated local build environment..."
    if ($PythonCmd.Count -eq 2) {
        & $PythonCmd[0] $PythonCmd[1] -m venv $BuildVenv
    } else {
        & $PythonCmd[0] -m venv $BuildVenv
    }
}

Write-Host "Installing Rúnmál build dependencies locally..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e . pyinstaller pillow

$Version = (& $VenvPython -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])").Trim()

New-Item -ItemType Directory -Force build, artifacts | Out-Null

Write-Host "Building Windows application icon..."
& $VenvPython -c "from PIL import Image; im=Image.open('docs/images/runmal-emblem.png').convert('RGBA'); im.save('build/runmal.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"

Write-Host "Building standalone Windows Rúnmál application..."
& $VenvPyInstaller --noconfirm --clean --onedir --windowed `
    --name Runmal `
    --icon build/runmal.ico `
    --hidden-import tkinter `
    --hidden-import tkinter.messagebox `
    --hidden-import tkinter.scrolledtext `
    --hidden-import aiosqlite `
    --collect-all sqlite_vec `
    --collect-all runmal `
    src/runmal/launcher/frozen_entry.py

$RunmalExe = Join-Path $RepoRoot "dist\Runmal\Runmal.exe"
if (-not (Test-Path $RunmalExe)) {
    throw "PyInstaller did not create dist\Runmal\Runmal.exe"
}

Write-Host "Smoke-testing launcher..."
& $RunmalExe status
if ($LASTEXITCODE -ne 0) { throw "Frozen Windows launcher smoke test failed." }

Write-Host "Smoke-testing local server..."
$Port = 18098
$Proc = Start-Process -FilePath $RunmalExe -ArgumentList "_serve","--port",$Port -PassThru -WindowStyle Hidden
try {
    $Ready = $false
    for ($i = 0; $i -lt 100; $i++) {
        try {
            $Response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/healthz" -TimeoutSec 1
            if ($Response.status -eq "ok") {
                $Ready = $true
                break
            }
        } catch { }
        Start-Sleep -Milliseconds 200
    }
    if (-not $Ready) { throw "Frozen Windows server failed its /healthz check." }
} finally {
    if (-not $Proc.HasExited) { Stop-Process -Id $Proc.Id -Force }
}

$InnoCandidates = @(@(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) })

if (-not $InnoCandidates) {
    throw "Inno Setup 6 is required to create Runmal-Setup.exe. Install it from https://jrsoftware.org/isdl.php and run this builder again."
}

$Iscc = $InnoCandidates[0]
Write-Host "Building Windows installer locally with Inno Setup..."
& $Iscc "/DMyAppVersion=$Version" "packaging\windows\runmal.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }

$BuiltInstaller = Join-Path $RepoRoot "artifacts\Runmal-Setup.exe"
$RootInstaller = Join-Path $RepoRoot "Runmal-Setup.exe"
if (-not (Test-Path $BuiltInstaller)) { throw "Installer was not created." }
Copy-Item -Force $BuiltInstaller $RootInstaller

$Hash = (Get-FileHash -Algorithm SHA256 $RootInstaller).Hash.ToLowerInvariant()
Write-Host ""
Write-Host "Rúnmál Windows installer built successfully."
Write-Host "File: $RootInstaller"
Write-Host "SHA-256: $Hash"
Write-Host ""
Write-Host "This build was produced locally on this Windows machine. No GitHub Actions were used."
