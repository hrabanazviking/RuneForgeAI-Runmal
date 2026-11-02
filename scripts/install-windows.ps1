param(
    [string]$Ref = "main",
    [bool]$DesktopShortcut = $true,
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Repo = "hrabanazviking/RuneForgeAI-Runmal"
$InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\Runmal"
$RuntimeRoot = Join-Path $InstallRoot "python"
$VenvRoot = Join-Path $InstallRoot "venv"
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("runmal-install-" + [guid]::NewGuid().ToString("N"))
$PythonVersion = "3.12.10"

function Write-Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
}

function Test-Python312([string]$Python) {
    if (-not (Test-Path $Python)) { return $false }
    try {
        $version = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        return $version.Trim() -eq "3.12"
    } catch {
        return $false
    }
}

function Install-PrivatePython {
    if (Test-Python312 (Join-Path $RuntimeRoot "python.exe")) {
        return (Join-Path $RuntimeRoot "python.exe")
    }

    Write-Step "Installing Rúnmál's private Python runtime"
    New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null

    $arch = $env:PROCESSOR_ARCHITECTURE.ToUpperInvariant()
    $suffix = if ($arch -eq "ARM64") { "arm64" } else { "amd64" }
    $installer = Join-Path $TempRoot "python-installer.exe"
    $url = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-$suffix.exe"
    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing

    $arguments = @(
        "/quiet",
        "InstallAllUsers=0",
        "Include_launcher=0",
        "Include_test=0",
        "Include_pip=1",
        "Include_tcltk=1",
        "PrependPath=0",
        "Shortcuts=0",
        "TargetDir=`"$RuntimeRoot`""
    )
    $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Python runtime installation failed with exit code $($process.ExitCode)."
    }

    $python = Join-Path $RuntimeRoot "python.exe"
    if (-not (Test-Python312 $python)) {
        throw "Rúnmál's Python runtime was installed but could not be started."
    }
    return $python
}

function New-Shortcut(
    [string]$Path,
    [string]$Target,
    [string]$Arguments,
    [string]$WorkingDirectory
) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $Target
    $shortcut.Arguments = $Arguments
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.Description = "Rúnmál — sovereign local AI chat"
    $shortcut.Save()
}

try {
    New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null

    $python = Install-PrivatePython

    Write-Step "Downloading Rúnmál"
    $zip = Join-Path $TempRoot "runmal.zip"
    $archiveUrl = "https://github.com/$Repo/archive/refs/heads/$Ref.zip"
    Invoke-WebRequest -Uri $archiveUrl -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath (Join-Path $TempRoot "source") -Force
    $source = Get-ChildItem -Path (Join-Path $TempRoot "source") -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName "pyproject.toml") } |
        Select-Object -First 1
    if (-not $source) {
        throw "The downloaded Rúnmál archive did not contain pyproject.toml."
    }

    Write-Step "Creating the private Rúnmál environment"
    if (-not (Test-Path (Join-Path $VenvRoot "Scripts\python.exe"))) {
        & $python -m venv $VenvRoot
    }
    $venvPython = Join-Path $VenvRoot "Scripts\python.exe"
    & $venvPython -m pip install --disable-pip-version-check --upgrade pip
    & $venvPython -m pip install --disable-pip-version-check --upgrade $source.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "Rúnmál package installation failed."
    }

    Write-Step "Creating Rúnmál shortcuts"
    $pythonw = Join-Path $VenvRoot "Scripts\pythonw.exe"
    $startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    New-Shortcut `
        -Path (Join-Path $startMenu "Rúnmál.lnk") `
        -Target $pythonw `
        -Arguments "-m runmal.launcher open" `
        -WorkingDirectory $InstallRoot
    New-Shortcut `
        -Path (Join-Path $startMenu "Rúnmál Control Center.lnk") `
        -Target $pythonw `
        -Arguments "-m runmal.launcher control" `
        -WorkingDirectory $InstallRoot

    if ($DesktopShortcut) {
        $desktop = [Environment]::GetFolderPath("Desktop")
        New-Shortcut `
            -Path (Join-Path $desktop "Rúnmál.lnk") `
            -Target $pythonw `
            -Arguments "-m runmal.launcher open" `
            -WorkingDirectory $InstallRoot
    }

    Write-Step "Checking the installation"
    & $venvPython -m runmal.launcher doctor

    Write-Host "`nRúnmál is installed." -ForegroundColor Green
    Write-Host "Use the Rúnmál icon in the Start Menu or on the Desktop."

    if (-not $NoLaunch) {
        Start-Process -FilePath $pythonw -ArgumentList "-m", "runmal.launcher", "open" -WorkingDirectory $InstallRoot
    }
}
catch {
    Write-Host "`nRúnmál installation failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "No personal Rúnmál data was removed."
    exit 1
}
finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $TempRoot
}
