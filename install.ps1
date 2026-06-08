# Spectral — Windows user-space installer (no admin required)
#
# One-liner install (run in PowerShell):
#   irm https://raw.githubusercontent.com/eisenkult/spectral/main/install.ps1 | iex
#
# After install, launch from the install directory:
#   cd "$env:LOCALAPPDATA\spectral" ; .venv\Scripts\python main.py $env:USERPROFILE\Music
# Or use the launcher (if %LOCALAPPDATA%\Microsoft\WindowsApps is in PATH):
#   spectral $env:USERPROFILE\Music

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoUrl    = 'https://github.com/eisenkult/spectral.git'
$InstallDir = Join-Path $env:LOCALAPPDATA 'spectral'
$BinDir     = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps'
$MinMajor   = 3
$MinMinor   = 9

# ── helpers ───────────────────────────────────────────────────────────────────
function Say  { param($msg) Write-Host "==> $msg" -ForegroundColor Green }
function Info { param($msg) Write-Host "  -> $msg" -ForegroundColor Cyan }
function Warn { param($msg) Write-Host "warn: $msg" -ForegroundColor Yellow }
function Die  { param($msg) Write-Host "error: $msg" -ForegroundColor Red; exit 1 }

# ── python check ──────────────────────────────────────────────────────────────
function Find-Python {
    foreach ($cmd in @('python', 'python3', 'py')) {
        $exe = Get-Command $cmd -ErrorAction SilentlyContinue
        if (-not $exe) { continue }
        $ok = & $exe -c @"
import sys
major, minor = sys.version_info[:2]
print('yes' if (major > $MinMajor or (major == $MinMajor and minor >= $MinMinor)) else 'no')
"@ 2>$null
        if ($ok -eq 'yes') { return $exe.Source }
    }
    return $null
}

function Check-Python {
    Say 'Checking Python...'
    $script:Python = Find-Python
    if (-not $script:Python) {
        Warn "Python $MinMajor.$MinMinor+ not found."
        Die  "Download Python from https://www.python.org/downloads/  (check 'Add to PATH' during install)"
    }
    $ver = & $script:Python --version 2>&1
    Info "Found: $ver"

    # verify venv module
    $venvOk = & $script:Python -c 'import venv; print("ok")' 2>$null
    if ($venvOk -ne 'ok') {
        Die 'Python venv module is missing. Reinstall Python from python.org.'
    }
}

# ── git check ─────────────────────────────────────────────────────────────────
function Check-Git {
    Say 'Checking git...'
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Die "git not found. Install Git from https://git-scm.com/download/win"
    }
    Info "Found: $(git --version)"
}

# ── clone or update ───────────────────────────────────────────────────────────
function Fetch-Repo {
    if (Test-Path (Join-Path $InstallDir '.git')) {
        Say "Updating existing installation at $InstallDir..."
        git -C $InstallDir pull --ff-only
    } else {
        Say "Cloning Spectral into $InstallDir..."
        $parent = Split-Path $InstallDir
        if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
        git clone --depth=1 $RepoUrl $InstallDir
    }
}

# ── venv + pip install ────────────────────────────────────────────────────────
function Setup-Venv {
    $venvDir = Join-Path $InstallDir '.venv'
    Say 'Creating virtual environment...'
    & $script:Python -m venv $venvDir

    $pip = Join-Path $venvDir 'Scripts\pip.exe'
    Say 'Installing Python dependencies...'
    & $pip install --upgrade pip --quiet
    & $pip install -r (Join-Path $InstallDir 'requirements.txt')
}

# ── write launcher ────────────────────────────────────────────────────────────
function Write-Launcher {
    # Write a .cmd shim to a directory already on PATH
    $launcher = Join-Path $BinDir 'spectral.cmd'
    $pythonExe = Join-Path $InstallDir '.venv\Scripts\python.exe'
    $mainPy    = Join-Path $InstallDir 'main.py'

    if (-not (Test-Path $BinDir)) { New-Item -ItemType Directory -Path $BinDir | Out-Null }

    @"
@echo off
"$pythonExe" "$mainPy" %*
"@ | Set-Content -Path $launcher -Encoding ASCII

    Info "Launcher written to $launcher"

    # WindowsApps is in PATH by default on Win10/11 — check just in case
    $inPath = ($env:PATH -split ';') -contains $BinDir
    if (-not $inPath) {
        Warn "$BinDir is not in PATH."
        Warn "Add it via: System Properties > Environment Variables > PATH"
    }
}

# ── main ──────────────────────────────────────────────────────────────────────
function Main {
    Say 'Spectral installer (Windows)'
    Check-Python
    Check-Git
    Fetch-Repo
    Setup-Venv
    Write-Launcher

    Say 'Done!'
    Write-Host ''
    Write-Host '  Launch from the install directory:'
    Write-Host "    cd `"$InstallDir`""
    Write-Host '    .venv\Scripts\python main.py %USERPROFILE%\Music'
    Write-Host ''
    Write-Host '  Or use the launcher (if PATH is set up):'
    Write-Host "    spectral $env:USERPROFILE\Music"
    Write-Host ''
    Write-Host '  Note: sounddevice bundles PortAudio on Windows — no extra audio setup needed.'
}

Main
