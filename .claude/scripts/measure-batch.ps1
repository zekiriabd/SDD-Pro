# measure-batch.ps1
# Parse les session logs Claude Code et agrege par attributionSkill (commande slash).
# Usage:
#   .\measure-batch.ps1                      # toutes les sessions du projet courant
#   .\measure-batch.ps1 -SessionId <uuid>    # une session precise
#   .\measure-batch.ps1 -Since "2026-05-05"  # sessions a partir d'une date
#   .\measure-batch.ps1 -OutFile metrics.csv

[CmdletBinding()]
param(
  [string]$SessionId = "",
  [string]$Since = "",
  [string]$OutFile = "",
  [string]$ProjectSlug = "g--Templates-New-SDD-SDD-Pro"
)

$ErrorActionPreference = "Stop"
$projectsRoot = Join-Path $env:USERPROFILE ".claude\projects"
$projectDir = Join-Path $projectsRoot $ProjectSlug

if (-not (Test-Path $projectDir)) {
  Write-Error "Project dir not found: $projectDir"
  exit 1
}

$files = Get-ChildItem -Path $projectDir -Filter "*.jsonl" -File
if ($SessionId) { $files = $files | Where-Object { $_.BaseName -eq $SessionId } }
if ($Since) {
  $sinceDt = [datetime]::Parse($Since)
  $files = $files | Where-Object { $_.LastWriteTime -ge $sinceDt }
}

if ($files.Count -eq 0) {
  Write-Host "No session files matched."
  exit 0
}

Write-Host "Processing $($files.Count) session file(s)..." -ForegroundColor Cyan

$rows = New-Object System.Collections.Generic.List[object]

foreach ($f in $files) {
  $sid = $f.BaseName
  $lineNum = 0
  Get-Content -Path $f.FullName | ForEach-Object {
    $lineNum++
    if (-not $_) { return }
    try { $j = $_ | ConvertFrom-Json } catch { return }
    if ($j.type -ne "assistant") { return }
    if (-not $j.message) { return }
    if (-not $j.message.usage) { return }

    $u = $j.message.usage
    $rows.Add([pscustomobject]@{
      session       = $sid
      timestamp     = $j.timestamp
      cwd           = $j.cwd
      skill         = if ($j.attributionSkill) { $j.attributionSkill } else { "(none)" }
      model         = $j.message.model
      input         = [int]($u.input_tokens | ForEach-Object { if ($_) { $_ } else { 0 } })
      cache_create  = [int]($u.cache_creation_input_tokens | ForEach-Object { if ($_) { $_ } else { 0 } })
      cache_read    = [int]($u.cache_read_input_tokens | ForEach-Object { if ($_) { $_ } else { 0 } })
      output        = [int]($u.output_tokens | ForEach-Object { if ($_) { $_ } else { 0 } })
      isSidechain   = [bool]$j.isSidechain
    })
  }
}

if ($rows.Count -eq 0) {
  Write-Host "No assistant messages with usage found."
  exit 0
}

# Aggregation par session + skill
$byCmd = $rows | Group-Object session, skill | ForEach-Object {
  $g = $_.Group
  $first = ($g | Sort-Object timestamp | Select-Object -First 1).timestamp
  $last  = ($g | Sort-Object timestamp | Select-Object -Last 1).timestamp
  $duration = if ($first -and $last) {
    [int]([datetime]$last - [datetime]$first).TotalSeconds
  } else { 0 }
  [pscustomobject]@{
    session       = ($g[0].session)
    skill         = ($g[0].skill)
    messages      = $g.Count
    sub_calls     = ($g | Where-Object { $_.isSidechain } | Measure-Object).Count
    input         = ($g | Measure-Object input -Sum).Sum
    cache_create  = ($g | Measure-Object cache_create -Sum).Sum
    cache_read    = ($g | Measure-Object cache_read -Sum).Sum
    output        = ($g | Measure-Object output -Sum).Sum
    total_in      = ($g | Measure-Object input -Sum).Sum + ($g | Measure-Object cache_create -Sum).Sum + ($g | Measure-Object cache_read -Sum).Sum
    duration_s    = $duration
    started       = $first
  }
} | Sort-Object started

# Affichage console
Write-Host ""
Write-Host "=== Per-command breakdown (per session) ===" -ForegroundColor Yellow
$byCmd | Format-Table -AutoSize session, skill, messages, sub_calls, total_in, output, duration_s, started

# Totaux globaux par skill (toutes sessions confondues)
$bySkill = $rows | Group-Object skill | ForEach-Object {
  $g = $_.Group
  [pscustomobject]@{
    skill         = $_.Name
    messages      = $g.Count
    input         = ($g | Measure-Object input -Sum).Sum
    cache_create  = ($g | Measure-Object cache_create -Sum).Sum
    cache_read    = ($g | Measure-Object cache_read -Sum).Sum
    output        = ($g | Measure-Object output -Sum).Sum
    total_in      = ($g | Measure-Object input -Sum).Sum + ($g | Measure-Object cache_create -Sum).Sum + ($g | Measure-Object cache_read -Sum).Sum
  }
} | Sort-Object total_in -Descending

Write-Host "=== Totaux globaux par skill (toutes sessions) ===" -ForegroundColor Yellow
$bySkill | Format-Table -AutoSize

# Total absolu
$totIn  = ($rows | Measure-Object input -Sum).Sum + ($rows | Measure-Object cache_create -Sum).Sum + ($rows | Measure-Object cache_read -Sum).Sum
$totOut = ($rows | Measure-Object output -Sum).Sum
$cacheCreate = ($rows | Measure-Object cache_create -Sum).Sum
$cacheRead = ($rows | Measure-Object cache_read -Sum).Sum
$cacheHitPct = if (($cacheCreate + $cacheRead) -gt 0) {
  [math]::Round(100 * $cacheRead / ($cacheCreate + $cacheRead), 1)
} else { 0 }

Write-Host "=== Grand total ===" -ForegroundColor Green
Write-Host "  Messages assistant : $($rows.Count)"
Write-Host "  Total input  (input + cache_create + cache_read) : $totIn"
Write-Host "  Total output : $totOut"
Write-Host "  Cache hit ratio (read / (create+read))            : $cacheHitPct %"
Write-Host ""

if ($OutFile) {
  $byCmd | Export-Csv -Path $OutFile -NoTypeInformation -Encoding UTF8
  Write-Host "CSV written to: $OutFile" -ForegroundColor Cyan
}
