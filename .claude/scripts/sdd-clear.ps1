# sdd-clear.ps1
# Logique exécutoire de la commande /sdd-clear (extracted v5.0).
# Workload déterministe, 0 token LLM. La commande markdown
# (.claude/commands/sdd-clear.md) appelle ce script.
#
# Usage:
#   .\sdd-clear.ps1                            # dry-run global
#   .\sdd-clear.ps1 -SpecNumber 1              # dry-run scope SPEC 1
#   .\sdd-clear.ps1 -Force                     # exécution réelle global
#   .\sdd-clear.ps1 -SpecNumber 1 -Force       # exécution réelle SPEC 1
#   .\sdd-clear.ps1 -Force -Quiet              # rapport 1-ligne

[CmdletBinding()]
param(
  [int]$SpecNumber = 0,
  [switch]$Force,
  [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$base = Join-Path (Get-Location) 'workspace/output'

if (-not (Test-Path $base)) {
  Write-Host "/sdd-clear — Aucun workspace/output/ — rien à nettoyer."
  exit 0
}

# 1. Scope global — tous les sous-répertoires de workspace/output/
$dirs = @('context','db','plans','qa','src','us','validation')

# v5.0 — Préserver toujours workspace/output/.audit/ (traçabilité --force bypass)
# (jamais purgé par sdd-clear)

$targets = @()

if ($SpecNumber -gt 0) {
  # 2. Scope par-SPEC
  $n = $SpecNumber
  $patterns = @(
    @{ Path = (Join-Path $base 'us');         Filter = "$n-*.md" },
    @{ Path = (Join-Path $base 'plans');      Filter = "$n-*" },
    @{ Path = (Join-Path $base 'validation'); Filter = "$n-readiness.md" }
  )
  foreach ($p in $patterns) {
    if (Test-Path $p.Path) {
      $targets += Get-ChildItem -Path $p.Path -Filter $p.Filter -ErrorAction SilentlyContinue
    }
  }
  $qaPath = Join-Path $base "qa/feat-$n"
  if (Test-Path $qaPath) {
    $targets += Get-ChildItem -Path $qaPath -Recurse -File -ErrorAction SilentlyContinue
  }
} else {
  # Scope global
  foreach ($d in $dirs) {
    $p = Join-Path $base $d
    if (Test-Path $p) {
      $targets += Get-ChildItem -Path $p -Recurse -Force -File -ErrorAction SilentlyContinue
    }
  }
}

# 3. Garde-fou : aucun chemin hors workspace/output/
$baseFull = (Resolve-Path $base).Path
foreach ($t in $targets) {
  if (-not $t.FullName.StartsWith($baseFull, [StringComparison]::OrdinalIgnoreCase)) {
    Write-Host "ERROR: /sdd-clear — chemin hors périmètre"
    Write-Host "CAUSE: tentative de suppression de `"$($t.FullName)`" qui ne réside pas sous workspace/output/"
    Write-Host "FIX: signaler le bug du framework — sdd-clear ne doit jamais sortir de workspace/output/"
    exit 2
  }
}

# 4. Calculer résumé
$count = @($targets).Count
$totalSize = ($targets | Measure-Object -Property Length -Sum).Sum
$totalSizeKb = if ($totalSize) { [math]::Round($totalSize / 1KB, 1) } else { 0 }

if ($count -eq 0) {
  Write-Host "/sdd-clear — rien à nettoyer"
  Write-Host "Aucun fichier généré dans le scope demandé."
  exit 0
}

# 5. Preview
$scopeLabel = if ($SpecNumber -gt 0) { "SPEC $SpecNumber" } else { "global" }
$mode = if ($Force) { "EXÉCUTION" } else { "DRY-RUN" }

if (-not $Quiet) {
  Write-Host ""
  Write-Host "/sdd-clear — Preview du nettoyage"
  Write-Host "Scope    : $scopeLabel"
  Write-Host "Mode     : $mode"
  Write-Host ""
  Write-Host "Ventilation par répertoire :"
  $byDir = $targets | Group-Object { $_.Directory.Name }
  foreach ($g in ($byDir | Sort-Object Name)) {
    $sz = ($g.Group | Measure-Object -Property Length -Sum).Sum
    $szKb = if ($sz) { [math]::Round($sz / 1KB, 1) } else { 0 }
    Write-Host ("  {0,-22} : {1,4} fichier(s)   ({2,8} KB)" -f $g.Name, $g.Count, $szKb)
  }
  Write-Host ("  ----------------------")
  Write-Host ("  TOTAL                  : {0,4} fichier(s)   ({1,8} KB)" -f $count, $totalSizeKb)
  Write-Host ""
}

# 6. Exécution conditionnelle
if (-not $Force) {
  Write-Host "DRY-RUN terminé. Aucun fichier supprimé."
  Write-Host "Pour exécuter : /sdd-clear$(if ($SpecNumber -gt 0) { " $SpecNumber" }) --force"
  exit 0
}

# 7. Suppression réelle (force)
$startTs = Get-Date

if ($SpecNumber -gt 0) {
  foreach ($f in $targets) {
    Remove-Item -Path $f.FullName -Force -ErrorAction SilentlyContinue
  }
  $qaPath = Join-Path $base "qa/feat-$SpecNumber"
  if ((Test-Path $qaPath) -and -not (Get-ChildItem $qaPath -Force)) {
    Remove-Item $qaPath -Recurse -Force -ErrorAction SilentlyContinue
  }
} else {
  foreach ($d in $dirs) {
    $p = Join-Path $base $d
    if (Test-Path $p) {
      Get-ChildItem -Path $p -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne '.gitkeep' } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

$duration = ((Get-Date) - $startTs).TotalSeconds

# 8. Rapport post-exec
if ($Quiet) {
  Write-Host ("✓ /sdd-clear — {0} fichier(s) supprimé(s) ({1} KB), scope={2}" -f $count, $totalSizeKb, $scopeLabel)
} else {
  Write-Host "/sdd-clear — nettoyage terminé"
  Write-Host ("Scope    : {0}" -f $scopeLabel)
  Write-Host ("Supprimé : {0} fichier(s) ({1} KB libérés)" -f $count, $totalSizeKb)
  Write-Host ("Durée    : {0:N2}s" -f $duration)
  Write-Host "Préservés: workspace/input/**, workspace/output/.audit/**"
  Write-Host ""
  $resumeCmd = if ($SpecNumber -gt 0) { "/sdd-full $SpecNumber" } else { "/spec-generate {Nom}" }
  Write-Host "Pour repartir : $resumeCmd"
}

exit 0
