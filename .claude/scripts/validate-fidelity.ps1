# validate-fidelity.ps1
# Externalise STEP 10 (vérif tokens hex) et STEP 11 (fidelity check
# text-based) de dev-frontend en workload déterministe.
# Remplace ~80 lignes de prose LLM par un script (~0 token).
#
# Usage:
#   .\validate-fidelity.ps1 -HtmlPath workspace/input/ui/1-2-Bebes.html `
#     -GeneratedDir workspace/output/src/AppName `
#     [-ThemePath workspace/output/src/AppName/wwwroot/css/theme.css] `
#     [-HexToleranceMaxPct 5] `
#     [-Json]
#
# Sortie JSON : { summary, tokens, labels, components, errors }
# Exit codes:
#   0  OK (matchs exacts ou tolérés)
#   1  WARN (matchs tolérés à signaler dans le rapport agent)
#   2  FAIL (libellé/composant absent du markup, hex non matché)

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)] [string]$HtmlPath,
  [Parameter(Mandatory=$true)] [string]$GeneratedDir,
  [string]$ThemePath = "",
  [int]$HexToleranceMaxPct = 5,
  [switch]$Json
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $HtmlPath)) {
  Write-Host "FAIL: HTML mockup not found: $HtmlPath"
  exit 2
}
if (-not (Test-Path $GeneratedDir)) {
  Write-Host "FAIL: Generated dir not found: $GeneratedDir"
  exit 2
}

$html = Get-Content -Path $HtmlPath -Raw

# ============================================================
# STEP 10 — Vérification tokens hex (3 modes : exact, tolérance, primitive DS)
# ============================================================

# 1. Extraire tous les hex du HTML (style inline + bloc <style>)
$hexPattern = '#([0-9a-fA-F]{6})\b'
$hexMatches = [regex]::Matches($html, $hexPattern)
$hexExpected = @($hexMatches | ForEach-Object { $_.Groups[1].Value.ToLower() } | Sort-Object -Unique)

# 2. Lire le theme (si fourni) + collecter tous les .css/.razor.css du dir généré
$themeContent = ""
if ($ThemePath -and (Test-Path $ThemePath)) {
  $themeContent = Get-Content -Path $ThemePath -Raw
}
$allCssFiles = Get-ChildItem -Path $GeneratedDir -Recurse -Include "*.css","*.razor.css" -ErrorAction SilentlyContinue
$cssAggregated = $themeContent + "`n" + (($allCssFiles | ForEach-Object { Get-Content $_.FullName -Raw }) -join "`n")

# 3. Pour chaque hex, tester les 3 modes
$tokensReport = @()
foreach ($hex in $hexExpected) {
  $rEx = [Convert]::ToInt32($hex.Substring(0,2), 16)
  $gEx = [Convert]::ToInt32($hex.Substring(2,2), 16)
  $bEx = [Convert]::ToInt32($hex.Substring(4,2), 16)

  # Mode 1: match exact
  $exactRegex = "(?i)#$hex\b"
  $exactMatch = [regex]::IsMatch($cssAggregated, $exactRegex)

  # Mode 2: match tolérance ±X% RGB euclidien
  $toleratedMatch = $false
  $toleratedHex = $null
  if (-not $exactMatch -and $HexToleranceMaxPct -gt 0) {
    $cssHexMatches = [regex]::Matches($cssAggregated, '#([0-9a-fA-F]{6})\b')
    foreach ($m in $cssHexMatches) {
      $cHex = $m.Groups[1].Value.ToLower()
      $rC = [Convert]::ToInt32($cHex.Substring(0,2), 16)
      $gC = [Convert]::ToInt32($cHex.Substring(2,2), 16)
      $bC = [Convert]::ToInt32($cHex.Substring(4,2), 16)
      $d = [Math]::Sqrt(([Math]::Pow($rEx - $rC, 2) + [Math]::Pow($gEx - $gC, 2) + [Math]::Pow($bEx - $bC, 2)) / (3 * 65025)) * 100
      if ($d -le $HexToleranceMaxPct) {
        $toleratedMatch = $true
        $toleratedHex = $cHex
        break
      }
    }
  }

  # Mode 3: override humain dans HTML
  $overrideMatch = $html -match "ui-fidelity-override:\s*hex-$hex"

  $status = if ($exactMatch) { "MATCH-EXACT" }
            elseif ($toleratedMatch) { "MATCH-TOLERATED" }
            elseif ($overrideMatch) { "MATCH-OVERRIDE" }
            else { "MISSING" }

  $tokensReport += [pscustomobject]@{
    hex            = "#$hex"
    rgb            = "$rEx,$gEx,$bEx"
    status         = $status
    matched_hex    = if ($toleratedMatch) { "#$toleratedHex" } else { $null }
  }
}

# ============================================================
# STEP 11 — Fidelity check text-based
# ============================================================

# 11.1 Extraire les libellés visibles (texte entre tags hors <script>/<style>)
$htmlClean = $html -replace '(?is)<script[^>]*>.*?</script>', ''
$htmlClean = $htmlClean -replace '(?is)<style[^>]*>.*?</style>', ''
$labelMatches = [regex]::Matches($htmlClean, '>([^<>\r\n]{3,80})<')
$labels = @($labelMatches | ForEach-Object {
  $t = $_.Groups[1].Value.Trim()
  if ($t -and $t -notmatch '^[\s\d\.,;:|\-_]+$') { $t }
} | Where-Object { $_ } | Sort-Object -Unique)

# 11.2 Extraire structures sémantiques majeures
$structuralTags = @('header','aside','main','nav','footer','section','table','form','dialog','select')
$structuralPresent = @()
foreach ($tag in $structuralTags) {
  if ($html -match "<$tag\b") { $structuralPresent += $tag }
}

# 11.3 Lire tous les fichiers générés (Pages, Components, Layouts)
$renderFiles = Get-ChildItem -Path $GeneratedDir -Recurse -Include "*.razor","*.tsx","*.jsx","*.vue","*.html","*.cshtml" -ErrorAction SilentlyContinue
$renderAggregated = ($renderFiles | ForEach-Object { Get-Content $_.FullName -Raw }) -join "`n"

# 11.4 Vérifier présence des libellés
$labelsReport = @()
foreach ($lbl in $labels) {
  # Skip si trop courte ou trop générique
  if ($lbl.Length -lt 4) { continue }
  # Match exact (case-insensitive)
  $found = $renderAggregated -match [regex]::Escape($lbl)
  $labelsReport += [pscustomobject]@{
    label  = $lbl
    status = if ($found) { "FOUND" } else { "MISSING" }
  }
}

# 11.5 Vérifier composants DS attendus
# (heuristique : si HTML a <table>, on attend RadzenDataGrid OU <Table OR <v-data-table)
$componentsReport = @()
$dsExpectations = @{
  'table'  = @('RadzenDataGrid','<Table','v-data-table','MudTable')
  'button' = @('RadzenButton','<Button','v-btn','MudButton')
  'form'   = @('RadzenTemplateForm','<Form','v-form','EditForm')
  'dialog' = @('DialogService','<Dialog','v-dialog','MudDialog')
  'select' = @('RadzenDropDown','<Select','v-select','MudSelect')
}
foreach ($tag in $structuralPresent) {
  if ($dsExpectations.ContainsKey($tag)) {
    $expected = $dsExpectations[$tag]
    $found = $false
    $matchedComponent = $null
    foreach ($comp in $expected) {
      if ($renderAggregated -match [regex]::Escape($comp)) {
        $found = $true
        $matchedComponent = $comp
        break
      }
    }
    $componentsReport += [pscustomobject]@{
      html_tag         = $tag
      expected_any_of  = $expected -join " | "
      matched_component = $matchedComponent
      status           = if ($found) { "FOUND" } else { "MISSING" }
    }
  }
}

# ============================================================
# Synthèse
# ============================================================
$tokensMissing  = @($tokensReport      | Where-Object status -eq "MISSING").Count
$tokensTol      = @($tokensReport      | Where-Object status -eq "MATCH-TOLERATED").Count
$labelsMissing  = @($labelsReport      | Where-Object status -eq "MISSING").Count
$compsMissing   = @($componentsReport  | Where-Object status -eq "MISSING").Count

$exitCode = if (($tokensMissing -gt 0) -or ($labelsMissing -gt 5) -or ($compsMissing -gt 0)) { 2 }
            elseif (($tokensTol -gt 0) -or ($labelsMissing -gt 0)) { 1 }
            else { 0 }

if ($Json) {
  $result = [pscustomobject]@{
    summary = [pscustomobject]@{
      hex_total          = $tokensReport.Count
      hex_exact          = @($tokensReport | Where-Object status -eq "MATCH-EXACT").Count
      hex_tolerated      = $tokensTol
      hex_override       = @($tokensReport | Where-Object status -eq "MATCH-OVERRIDE").Count
      hex_missing        = $tokensMissing
      labels_total       = $labelsReport.Count
      labels_found       = @($labelsReport | Where-Object status -eq "FOUND").Count
      labels_missing     = $labelsMissing
      components_total   = $componentsReport.Count
      components_found   = @($componentsReport | Where-Object status -eq "FOUND").Count
      components_missing = $compsMissing
      decision           = if ($exitCode -eq 0) { "PASS" } elseif ($exitCode -eq 1) { "WARN" } else { "FAIL" }
    }
    tokens     = $tokensReport
    labels     = $labelsReport
    components = $componentsReport
  }
  $result | ConvertTo-Json -Depth 5
} else {
  Write-Host ""
  Write-Host "=== Fidelity Check ===" -ForegroundColor Cyan
  Write-Host ("Tokens hex : {0} total / {1} exact / {2} toleres / {3} override / {4} missing" -f $tokensReport.Count, @($tokensReport | Where-Object status -eq "MATCH-EXACT").Count, $tokensTol, @($tokensReport | Where-Object status -eq "MATCH-OVERRIDE").Count, $tokensMissing)
  Write-Host ("Labels     : {0} total / {1} found / {2} missing" -f $labelsReport.Count, @($labelsReport | Where-Object status -eq "FOUND").Count, $labelsMissing)
  Write-Host ("Components : {0} total / {1} found / {2} missing" -f $componentsReport.Count, @($componentsReport | Where-Object status -eq "FOUND").Count, $compsMissing)

  if ($tokensMissing -gt 0) {
    Write-Host ""
    Write-Host "[FAIL] Tokens hex manquants :" -ForegroundColor Red
    $tokensReport | Where-Object status -eq "MISSING" | Format-Table -AutoSize hex, rgb
  }
  if ($labelsMissing -gt 0) {
    Write-Host ""
    Write-Host "[WARN/FAIL] Libelles manquants :" -ForegroundColor Yellow
    $labelsReport | Where-Object status -eq "MISSING" | Format-Table -AutoSize label
  }
  if ($compsMissing -gt 0) {
    Write-Host ""
    Write-Host "[FAIL] Composants DS manquants :" -ForegroundColor Red
    $componentsReport | Where-Object status -eq "MISSING" | Format-Table -AutoSize html_tag, expected_any_of
  }

  $decision = if ($exitCode -eq 0) { "PASS" } elseif ($exitCode -eq 1) { "WARN" } else { "FAIL" }
  Write-Host ""
  Write-Host "Decision : $decision (exit $exitCode)"
}

exit $exitCode
