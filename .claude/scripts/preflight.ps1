# preflight.ps1
# HARD-GATE pre-flight pour dev-backend / dev-frontend (Phase A + B).
# Déterministe, 0 token LLM. Externalise les checks A1-A4 + B1-B5.
#
# Usage:
#   .\preflight.ps1 -Family backend  -Arg "1-2"
#   .\preflight.ps1 -Family frontend -Arg "1-2:plan"
#
# Output: JSON unique sur stdout
#   { ok: bool, family, n, m, planOnly, name, htmlPath, appOrBackendName,
#     activeStacks: { backend, frontend, uiDs, auth }, errors: [{code, hint}] }
#
# Exit codes:
#   0 = OK (ou WARN-only si PlanOnly et project file absent)
#   1 = ERROR (au moins 1 précondition critique échouée)

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('backend', 'frontend')]
    [string]$Family,

    [Parameter(Mandatory)]
    [string]$Arg,

    [string]$WorkspaceRoot = (Get-Location).Path
)

$ErrorActionPreference = 'Stop'
Set-Location $WorkspaceRoot

$result = [ordered]@{
    ok                = $true
    family            = $Family
    n                 = $null
    m                 = $null
    planOnly          = $false
    name              = $null
    htmlPath          = $null
    appOrBackendName  = $null
    activeStacks      = [ordered]@{ backend = $null; frontend = $null; uiDs = $null; auth = $null }
    errors            = New-Object System.Collections.ArrayList
}

function Add-Err($code, $hint) {
    [void]$result.errors.Add([ordered]@{ code = $code; hint = $hint })
    $result.ok = $false
}

# ------------------ A1 — argument regex --------------------
if ($Arg -notmatch '^(\d+)-(\d+)(:plan)?$') {
    Add-Err 'INVALID_ARG' "argument doit matcher ^\d+-\d+(:plan)?$ (recu: $Arg)"
    $result | ConvertTo-Json -Depth 6 -Compress
    exit 1
}
$result.n        = [int]$Matches[1]
$result.m        = [int]$Matches[2]
$result.planOnly = [bool]$Matches[3]

# ------------------ A2 — US file existe et unique ----------
$usFiles = @(Get-ChildItem -Path "workspace/output/us" -Filter "$($result.n)-$($result.m)-*.md" -File -ErrorAction SilentlyContinue)
if ($usFiles.Count -eq 0) {
    Add-Err 'US_NOT_FOUND' "lancer /us-generate $($result.n) pour generer l'US"
} elseif ($usFiles.Count -gt 1) {
    Add-Err 'US_AMBIGUOUS' "plusieurs fichiers workspace/output/us/$($result.n)-$($result.m)-*.md trouves, n'en garder qu'un"
} else {
    if ($usFiles[0].BaseName -match '^\d+-\d+-(.+)$') { $result.name = $Matches[1] }
}

# ------------------ A3 — stack.md existe -------------------
$stackPath = "workspace/input/stack/stack.md"
if (-not (Test-Path $stackPath)) {
    Add-Err 'STACK_MISSING' "verifier que workspace/input/stack/stack.md existe"
    $result | ConvertTo-Json -Depth 6 -Compress
    exit 1
}

# ------------------ A4 — HTML mockup unique (frontend only)
if ($Family -eq 'frontend') {
    $htmlFiles = @(Get-ChildItem -Path "workspace/input/ui" -Filter "$($result.n)-$($result.m)-*.html" -File -ErrorAction SilentlyContinue)
    if ($htmlFiles.Count -gt 1) {
        Add-Err 'HTML_AMBIGUOUS' "plusieurs fichiers workspace/input/ui/$($result.n)-$($result.m)-*.html, n'en garder qu'un"
    } elseif ($htmlFiles.Count -eq 1) {
        $result.htmlPath = $htmlFiles[0].FullName.Replace('\', '/')
    }
}

# ------------------ Read stack.md once --------------------
$stackContent = Get-Content $stackPath -Raw -Encoding UTF8

# ------------------ B1 — Active Tech Specs ----------------
$activeTechBlock = if ($stackContent -match '(?ms)^##\s+Active\s+Tech\s+Specs\s*$(.*?)^##\s') { $Matches[1] } else { '' }
$activeUiBlock   = if ($stackContent -match '(?ms)^##\s+Active\s+UI\s+Specs\s*$(.*?)^##\s')   { $Matches[1] } else { '' }
$activeAuthBlock = if ($stackContent -match '(?ms)^##\s+Active\s+Auth\s+Specs\s*$(.*?)^##\s') { $Matches[1] } else { '' }

# Active stack ids — format reel: "- .claude/stacks/{cat}/{id}.md"
function Get-ActiveIds($block, $category) {
    $ids = @()
    foreach ($line in ($block -split "`r?`n")) {
        if ($line -match "\.claude/stacks/$category/([\w-]+)\.md") {
            $ids += $Matches[1]
        }
    }
    $ids
}

$beIds   = Get-ActiveIds $activeTechBlock 'backend'
$feIds   = Get-ActiveIds $activeTechBlock 'frontend'
$uiIds   = Get-ActiveIds $activeUiBlock   'ui'
$authIds = Get-ActiveIds $activeAuthBlock 'auth'
$result.activeStacks.backend  = $beIds   -join ','
$result.activeStacks.frontend = $feIds   -join ','
$result.activeStacks.uiDs     = $uiIds   -join ','
$result.activeStacks.auth     = $authIds -join ','

if ($Family -eq 'backend' -and $beIds.Count -eq 0) {
    Add-Err 'STACK_NOT_SELECTED' "decommenter un backend dans ## Active Tech Specs"
}
if ($Family -eq 'frontend' -and $feIds.Count -eq 0) {
    Add-Err 'STACK_NOT_SELECTED' "decommenter un frontend dans ## Active Tech Specs"
}

# ------------------ B2 — Project Config field --------------
$pcBlock = if ($stackContent -match '(?ms)^##\s+Project\s+Config\s*$(.*?)(^##\s|\z)') { $Matches[1] } else { '' }
$keyName = if ($Family -eq 'backend') { 'BackendName' } else { 'AppName' }
if ($pcBlock -match "(?m)^\s*$($keyName)\s*:\s*(\S+)") {
    $result.appOrBackendName = $Matches[1]
} else {
    Add-Err 'STACK_MALFORMED' "renseigner $($keyName) dans ## Project Config"
}

# ------------------ B3 — CLAUDE.md projet ------------------
if ($result.appOrBackendName) {
    $projDigest = "workspace/output/src/$($result.appOrBackendName)/CLAUDE.md"
    if (-not (Test-Path $projDigest)) {
        Add-Err 'STACK_DIGEST_MISSING' "lancer /dev-run avant /dev-$Family (ou bootstrap arch)"
    }
}

# ------------------ B4 — project file ----------------------
if ($result.appOrBackendName) {
    $projDir = "workspace/output/src/$($result.appOrBackendName)"
    $projectFiles = @()
    foreach ($pat in @('*.csproj', 'package.json', 'pyproject.toml', 'build.gradle.kts', 'angular.json')) {
        $projectFiles += Get-ChildItem -Path $projDir -Filter $pat -File -ErrorAction SilentlyContinue
    }
    if ($projectFiles.Count -eq 0) {
        $hint = "lancer /dev-run (Phase A bootstrap projets)"
        if ($result.planOnly) {
            # En mode :plan, B4 est WARN-only — log mais ne bloque pas
            [void]$result.errors.Add([ordered]@{ code = 'PROJECT_NOT_INIT_WARN'; hint = "$hint (WARN-only en mode :plan)" })
        } else {
            Add-Err 'PROJECT_NOT_INIT' $hint
        }
    }
}

# ------------------ B5 — UI DS si HTML present (frontend) --
if ($Family -eq 'frontend' -and $result.htmlPath -and $uiIds.Count -eq 0) {
    Add-Err 'UI_DS_NOT_SELECTED' "decommenter un design system (radzen-blazor, shadcn, vuetify)"
}

# ------------------ Output JSON ----------------------------
$result | ConvertTo-Json -Depth 6 -Compress
if (-not $result.ok) { exit 1 } else { exit 0 }
