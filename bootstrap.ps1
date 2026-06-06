<#
.SYNOPSIS
    SDD_Pro project bootstrap — Windows PowerShell wrapper for bootstrap.py.

.DESCRIPTION
    Thin wrapper around bootstrap.py that :
      - Locates a Python 3.10+ interpreter (py launcher → python3 → python)
      - Validates UTF-8 encoding (PSDefault on Windows is sometimes UTF-16)
      - Forwards arguments verbatim to bootstrap.py
      - Returns the script's exit code

    All real logic lives in bootstrap.py to keep a single source of truth.

.PARAMETER Combo
    Skip the stack-choice prompt. Valid values: c1, c2, custom.

.PARAMETER DryRun
    Show actions without writing files / installing.

.PARAMETER SkipInstall
    Skip pip / npm install (CI use).

.PARAMETER Force
    Overwrite existing workspace/input/ without confirmation.

.EXAMPLE
    .\bootstrap.ps1
    Interactive bootstrap (asks all questions).

.EXAMPLE
    .\bootstrap.ps1 -Combo c1
    Use validated combo C1 (.NET + React + shadcn + Azure AD).

.EXAMPLE
    .\bootstrap.ps1 -DryRun
    Show what would happen without writing anything.
#>

[CmdletBinding()]
param(
    # Audit P0-doc 2026-06-05 — synced with bootstrap.py CLI (c1..c5 + custom)
    [ValidateSet('c1', 'c2', 'c3', 'c4', 'c5', 'custom')]
    [string]$Combo,

    [switch]$DryRun,
    [switch]$SkipInstall,
    [switch]$Force,
    [switch]$AutoInit,

    # Optional env vars for CI scripted mode (mirror bootstrap.py SDD_* env)
    [string]$AppName,
    [string]$BackendName,
    [string]$FrontendName
)

$ErrorActionPreference = 'Stop'

# Force UTF-8 console encoding (Windows defaults to cp1252 which breaks emojis)
$env:PYTHONIOENCODING = 'utf-8'
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # Older PowerShell hosts (ISE) — best effort
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BootstrapPy = Join-Path $ScriptDir 'bootstrap.py'

if (-not (Test-Path $BootstrapPy)) {
    Write-Error "bootstrap.py not found at $BootstrapPy"
    exit 2
}

# Locate a usable Python interpreter (3.10+)
function Find-Python {
    $candidates = @('py', 'python3', 'python')
    foreach ($cmd in $candidates) {
        try {
            $version = & $cmd --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $version -match 'Python\s+(\d+)\.(\d+)') {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 10)) {
                    return $cmd
                }
            }
        } catch {
            continue
        }
    }
    return $null
}

$Python = Find-Python
if (-not $Python) {
    Write-Host '❌ No Python 3.10+ found.' -ForegroundColor Red
    Write-Host 'Install from https://www.python.org/ (or use winget : winget install Python.Python.3.12)' -ForegroundColor Yellow
    exit 3
}

# Forward CLI flags + env vars (audit P0-doc 2026-06-05 — synced with bootstrap.py)
$Args = @($BootstrapPy)
if ($Combo)       { $Args += @('--combo', $Combo) }
if ($DryRun)      { $Args += '--dry-run' }
if ($SkipInstall) { $Args += '--skip-install' }
if ($Force)       { $Args += '--force' }
if ($AutoInit)    { $Args += '--auto-init' }

# CI / scripted mode : propagate SDD_* env vars expected by bootstrap.py
if ($AppName)      { $env:SDD_APP_NAME = $AppName }
if ($BackendName)  { $env:SDD_BACKEND_NAME = $BackendName }
if ($FrontendName) { $env:SDD_FRONTEND_NAME = $FrontendName }
if ($Combo -and -not $env:SDD_COMBO) { $env:SDD_COMBO = $Combo }

# Run with cwd = ScriptDir so bootstrap.py's REPO_ROOT detection works
Push-Location $ScriptDir
try {
    & $Python @Args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
