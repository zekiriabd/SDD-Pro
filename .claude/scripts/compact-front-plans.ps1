# SDD_Pro - Compacte les plans frontend consommes par les agents.
# Archive le plan complet puis remplace le fichier par un contrat court.

[CmdletBinding()]
param(
  [string]$PlansDir = "",
  [string]$ArchiveDir = "",
  [int]$TargetBytes = 12000,
  [switch]$WhatIfOnly
)

$ErrorActionPreference = 'Stop'
$scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$repoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..')).Path
if (-not $PlansDir) { $PlansDir = Join-Path $repoRoot 'workspace\output\plans' }
if (-not $ArchiveDir) { $ArchiveDir = Join-Path $repoRoot 'workspace\output\.audit\plan-archive' }

function Get-FrontMatter([string]$Text) {
  if ($Text -match '(?s)^---\r?\n(.*?)\r?\n---\r?\n') { return $Matches[0] }
  return ""
}

function Get-Title([string]$Text) {
  $m = [regex]::Match($Text, '(?m)^#\s+.+$')
  if ($m.Success) { return $m.Value }
  return "# Plan technique frontend"
}

function Get-Section([string]$Text, [string]$HeadingPattern, [int]$MaxChars) {
  $m = [regex]::Match($Text, "(?ms)^##\s+$HeadingPattern.*?(?=^##\s+|\z)")
  if (-not $m.Success) { return "" }
  $s = $m.Value.Trim()
  if ($s.Length -le $MaxChars) { return $s }
  return $s.Substring(0, $MaxChars).TrimEnd() + "`n`n> Section tronquee par compact-front-plans.ps1."
}

function Get-FileRows([string]$Text) {
  $rows = New-Object System.Collections.Generic.List[string]
  $matches = [regex]::Matches($Text, '(?m)^- path:\s*(.+)$')
  foreach ($m in $matches) {
    $path = $m.Groups[1].Value.Trim()
    $rows.Add("- " + '`' + $path + '`')
  }
  if ($rows.Count -eq 0) { return "- Aucun fichier detecte dans le plan original." }
  return ($rows | Select-Object -First 40) -join "`n"
}

function Get-KeyNotes([string]$Text) {
  $notes = New-Object System.Collections.Generic.List[string]
  foreach ($line in ($Text -split "`r?`n")) {
    if ($line -match '^\s*[-*]\s+\*\*(.+?)\*\*') {
      $notes.Add(($line.Trim() -replace '\s+', ' '))
    }
    if ($notes.Count -ge 12) { break }
  }
  if ($notes.Count -eq 0) { return "- Voir archive complete pour les arbitrages detailles." }
  return ($notes -join "`n")
}

if (-not (Test-Path $ArchiveDir)) { New-Item -ItemType Directory -Path $ArchiveDir -Force | Out-Null }

$files = Get-ChildItem -Path $PlansDir -Filter '*.front.md' -File
$summary = @()

foreach ($file in $files) {
  $raw = Get-Content -Raw -Path $file.FullName -Encoding UTF8
  $oldBytes = [Text.Encoding]::UTF8.GetByteCount($raw)
  if ($oldBytes -le $TargetBytes) {
    $summary += [pscustomobject]@{ file = $file.Name; oldBytes = $oldBytes; newBytes = $oldBytes; action = 'skip' }
    continue
  }

  $archiveName = "{0}.{1}.full.md" -f $file.BaseName, (Get-Date -Format 'yyyyMMddTHHmmss')
  $archivePath = Join-Path $ArchiveDir $archiveName
  $relArchive = $archivePath.Substring($repoRoot.Length + 1).Replace('\','/')

  $frontMatter = Get-FrontMatter $raw
  $title = Get-Title $raw
  $limits = Get-Section $raw 'Limites connues.*' 2500
  $compact = @"
$frontMatter$title

> Plan compacte pour consommation agentique recurrente.
> Archive complete : `$relArchive`
> Objectif : garder le contrat d'execution, reduire tokens/cout/latence.

## Contrat d'execution

- Respecter strictement l'US et le mockup HTML declares dans le frontmatter.
- Ne pas relire l'archive complete sauf arbitrage ambigu ou review humaine.
- Preserver les fichiers existants mentionnes dans le plan original.
- Appliquer les regles stack, ownership, QA ownership et anti-derive du projet.

## Fichiers a creer ou modifier

$(Get-FileRows $raw)

## Arbitrages essentiels

$(Get-KeyNotes $raw)

$(if ($limits) { $limits } else { "## Limites connues du plan`n`n- Non detaillees dans la version compacte ; consulter l'archive complete si necessaire." })
"@

  $newBytes = [Text.Encoding]::UTF8.GetByteCount($compact)
  if ($newBytes -gt $TargetBytes) {
    $compact = $compact.Substring(0, [math]::Min($compact.Length, $TargetBytes - 500)).TrimEnd() + "`n`n> Compactage dur applique: consulter l'archive complete pour le detail restant.`n"
    $newBytes = [Text.Encoding]::UTF8.GetByteCount($compact)
  }

  if (-not $WhatIfOnly) {
    Copy-Item -LiteralPath $file.FullName -Destination $archivePath -Force
    Set-Content -Path $file.FullName -Value $compact -Encoding UTF8
  }
  $summary += [pscustomobject]@{ file = $file.Name; oldBytes = $oldBytes; newBytes = $newBytes; action = 'compact'; archive = $relArchive }
}

$summary | Format-Table -AutoSize
