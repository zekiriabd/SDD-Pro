# mark-breaking-resolved.ps1
# Externalise la logique de "Cleanup BREAKING CHANGES post-build" des
# agents dev-backend (STEP 8.5) et dev-frontend (STEP 11.5).
#
# Workload déterministe : recherche le H2 "## BREAKING CHANGES" dans
# le CLAUDE.md du projet, vérifie cohérence avec les fichiers modifiés
# par cette US, marque RESOLVED.
#
# Usage:
#   .\mark-breaking-resolved.ps1 -ClaudeMdPath workspace/output/src/AppName/CLAUDE.md `
#     -ModifiedFiles "Pages/Bebes.razor,Components/BebeForm.razor" `
#     -BuildCommand "dotnet build" `
#     [-DryRun]
#
# Exit codes:
#   0  Section absente ou déjà RESOLVED → skip silencieux (no-op)
#   1  Section présente, marquée RESOLVED avec succès
#   2  Section présente mais cohérence avec ModifiedFiles non détectée → skip
#   3  Erreur (fichier absent, parsing échec)

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)] [string]$ClaudeMdPath,
  [Parameter(Mandatory=$true)] [string]$ModifiedFiles,   # liste séparée par virgules
  [string]$BuildCommand = "dotnet build",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ClaudeMdPath)) {
  Write-Host "ERROR: CLAUDE.md not found: $ClaudeMdPath"
  exit 3
}

$content = Get-Content -Path $ClaudeMdPath -Raw

# 1. Détecter section "## BREAKING CHANGES" (sans suffixe RESOLVED)
$h2Pattern = '(?m)^##\s+BREAKING\s+CHANGES\s*$'
$h2ResolvedPattern = '(?m)^##\s+BREAKING\s+CHANGES\s+—\s+RESOLVED'

if ($content -notmatch $h2Pattern) {
  # Pas de section ou déjà RESOLVED
  if ($content -match $h2ResolvedPattern) {
    Write-Host "[SKIP] Section BREAKING CHANGES déjà marquée RESOLVED"
  } else {
    Write-Host "[SKIP] Aucune section BREAKING CHANGES dans le CLAUDE.md"
  }
  exit 0
}

# 2. Extraire le bloc de la section BREAKING CHANGES (entre ## BREAKING CHANGES et le prochain ## )
$sectionPattern = '(?ms)^##\s+BREAKING\s+CHANGES\s*$\r?\n(.*?)(?=^##\s|\z)'
if ($content -notmatch $sectionPattern) {
  Write-Host "ERROR: Impossible d'extraire le contenu de la section BREAKING CHANGES"
  exit 3
}
$sectionBody = $matches[1]

# 3. Vérifier cohérence : la section mentionne-t-elle au moins un des
#    fichiers modifiés par cette US ?
$modifiedList = $ModifiedFiles -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
$coherent = $false
$matchingFiles = @()
foreach ($f in $modifiedList) {
  # Match sur le nom court ou le chemin partiel
  $shortName = [System.IO.Path]::GetFileName($f)
  if ($sectionBody -match [regex]::Escape($shortName)) {
    $coherent = $true
    $matchingFiles += $shortName
  } elseif ($sectionBody -match [regex]::Escape($f)) {
    $coherent = $true
    $matchingFiles += $f
  }
}

if (-not $coherent) {
  Write-Host "[SKIP] Section BREAKING CHANGES présente mais aucun fichier modifié par cette US n'est mentionné — laisser l'autre US la résoudre"
  exit 2
}

# 4. Marquer RESOLVED
$today = (Get-Date).ToString("yyyy-MM-dd")
$resolvedHeader = "## BREAKING CHANGES — RESOLVED $today"
$encart = @"
> **Statut** : ✅ RESOLU — `$BuildCommand` passe (0 erreur).
> Archive historique. Suppression au prochain ``/arch-init``.

"@

$newContent = $content -replace `
  '(?m)^##\s+BREAKING\s+CHANGES\s*$', `
  ($resolvedHeader + "`r`n" + $encart)

if ($DryRun) {
  Write-Host "[DRY-RUN] Marquerait RESOLVED — fichiers concordants : $($matchingFiles -join ', ')"
  exit 1
}

# 5. Écrire (atomique via tmp + rename)
$tmpPath = "$ClaudeMdPath.tmp"
Set-Content -Path $tmpPath -Value $newContent -NoNewline -Encoding UTF8
Move-Item -Path $tmpPath -Destination $ClaudeMdPath -Force

Write-Host "[OK] Section BREAKING CHANGES marquée RESOLVED ($today)"
Write-Host "      Fichiers concordants : $($matchingFiles -join ', ')"
exit 1
