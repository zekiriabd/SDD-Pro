# detect-capabilities.ps1
# Workload deterministe : detecte les capabilities §2.4.b declenchees par
# une US (et son mockup HTML eventuel) selon les triggers regex documentes
# dans le stack backend actif.
#
# Sortie JSON consommee par dev-backend STEP 5.bis (depuis v5.0).
# Remplace ~70 lignes de prose LLM par un script deterministe (~0 token).
#
# Usage:
#   .\detect-capabilities.ps1 -UsPath workspace/output/us/1-2-Bebes.md `
#     -StackPath .claude/stacks/backend/dotnet-minimalapi.md `
#     -StackProjectConfigPath workspace/input/stack/stack.md
#     [-HtmlPath workspace/input/ui/1-2-Bebes.html]

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)] [string]$UsPath,
  [Parameter(Mandatory=$true)] [string]$StackPath,
  [Parameter(Mandatory=$true)] [string]$StackProjectConfigPath,
  [string]$HtmlPath = "",
  [string]$ProjectFile = ""    # csproj/package.json/etc. — pour detecter "lib deja installee"
)

$ErrorActionPreference = "Stop"

function Read-FileSafe([string]$path) {
  if (-not (Test-Path $path)) { return "" }
  return Get-Content -Path $path -Raw
}

# Inputs
$us = Read-FileSafe $UsPath
$stack = Read-FileSafe $StackPath
$config = Read-FileSafe $StackProjectConfigPath
$html = if ($HtmlPath) { Read-FileSafe $HtmlPath } else { "" }
$csproj = if ($ProjectFile) { Read-FileSafe $ProjectFile } else { "" }

# 1. Parser §2.4.b ON-DEMAND du stack backend
# Format attendu :
#   ### 2.4.b On-Demand
#   | Capability | Lib (default) | Version | Triggers |
#   |---|---|---|---|
#   | excel | EPPlus | 7.4.0 | xlsx, export.*excel, .xls$ |
#   | pdf   | QuestPDF | 2024.x | pdf, export.*pdf |
$capabilities = @()
$inSection = $false
$sectionPattern = '###\s*2\.4\.b'

$stackLines = $stack -split "`n"
foreach ($line in $stackLines) {
  if ($line -match $sectionPattern) { $inSection = $true; continue }
  if ($inSection -and $line -match '^###\s') { break }   # section suivante
  if (-not $inSection) { continue }
  # Lignes de tableau : | name | lib | version | triggers |
  if ($line -match '^\|\s*([a-zA-Z0-9_-]+)\s*\|\s*([^\|]+?)\s*\|\s*([^\|]+?)\s*\|\s*([^\|]+?)\s*\|') {
    $name = $matches[1].Trim()
    $lib  = $matches[2].Trim()
    $ver  = $matches[3].Trim()
    $trigStr = $matches[4].Trim()
    # Skip ligne d'en-tete et separateurs
    if ($name -in @('Capability','---','-')) { continue }
    if ($lib -match '^-+$') { continue }
    $triggers = $trigStr -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    $capabilities += [pscustomobject]@{
      name     = $name
      lib      = $lib
      version  = $ver
      triggers = $triggers
    }
  }
}

# 2. Parser overrides ## Capabilities Override + Capabilities: dans Project Config
$forcedCaps = @()
$overrideMap = @{}

# Capabilities: excel, pdf
if ($config -match '(?im)^\s*Capabilities\s*:\s*([^\r\n]+)') {
  $forcedCaps = ($matches[1] -split ',') | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ }
}

# ## Capabilities Override
#   excel: closedxml
#   pdf: itext7
if ($config -match '(?ims)##\s*Capabilities\s+Override\s*\r?\n((?:\s+\w+\s*:\s*\S+\s*\r?\n?)+)') {
  $block = $matches[1]
  foreach ($l in ($block -split "`n")) {
    if ($l -match '^\s*([a-zA-Z0-9_-]+)\s*:\s*([a-zA-Z0-9_.-]+)') {
      $overrideMap[$matches[1].Trim().ToLower()] = $matches[2].Trim()
    }
  }
}

# 3. Pour chaque capability, determiner status
$haystack = "$us`n$html"
$results = @()

foreach ($c in $capabilities) {
  $isForcedRaw = ($forcedCaps -contains $c.name.ToLower())
  $isForced = [bool]$isForcedRaw
  $isAuto = $false
  $matchedTriggers = @()

  if (-not $isForced) {
    foreach ($t in $c.triggers) {
      if ($t -and ($haystack -match $t)) {
        $isAuto = $true
        $matchedTriggers += $t
      }
    }
  }

  # Override lib si applicable
  $libToUse = if ($overrideMap.ContainsKey($c.name.ToLower())) {
    $overrideMap[$c.name.ToLower()]
  } else {
    $c.lib
  }

  # Detection lib deja en csproj
  $libAlreadyPresent = $false
  if ($csproj -and $csproj -match [regex]::Escape($c.lib)) {
    $libAlreadyPresent = $true
  }

  $status = if ($isForced) {
    "TRIGGERED-FORCED"
  } elseif ($isAuto -and -not $libAlreadyPresent) {
    "TRIGGERED-AUTO"
  } elseif ($isAuto -and $libAlreadyPresent) {
    "USE-EXISTING"
  } elseif (-not $isAuto -and $libAlreadyPresent) {
    "PRESENT-NO-TRIGGER"
  } else {
    "SKIPPED-NO-TRIGGER"
  }

  $results += [pscustomobject]@{
    capability       = $c.name
    lib              = $libToUse
    lib_default      = $c.lib
    version          = $c.version
    status           = $status
    triggers_matched = $matchedTriggers
    forced_via_config = $isForced
    override_applied = ($overrideMap.ContainsKey($c.name.ToLower()))
    install_required = ($status -in @("TRIGGERED-FORCED","TRIGGERED-AUTO"))
  }
}

# 4. Sortie JSON
$summary = [pscustomobject]@{
  scanned_at      = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
  us_path         = $UsPath
  stack_path      = $StackPath
  total           = $results.Count
  to_install      = ($results | Where-Object { $_.install_required }).Count
  use_existing    = ($results | Where-Object status -eq "USE-EXISTING").Count
  skipped         = ($results | Where-Object status -eq "SKIPPED-NO-TRIGGER").Count
  present_unused  = ($results | Where-Object status -eq "PRESENT-NO-TRIGGER").Count
}

$output = [pscustomobject]@{
  summary      = $summary
  capabilities = $results
}

$output | ConvertTo-Json -Depth 5
