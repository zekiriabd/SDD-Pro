# SDD_Pro — SubagentStop hook
#
# Audit la matrice file-ownership.md §1 après chaque dispatch d'un
# sub-agent. Vérifie que les fichiers modifiés pendant le dispatch
# matchent bien les patterns "Owner" autorisés pour cet agent.
#
# Stratégie déterministe (0 token LLM) :
# - Détecter l'agent invoqué via input JSON (`tool_input.subagent_type`)
# - Glob les fichiers modifiés depuis $env:SDD_DISPATCH_START_TS (set
#   par /dev-run, /sdd-full, /qa-generate au début du dispatch). Si non
#   set, fallback : derniers 5 minutes.
# - Pour chaque fichier modifié, comparer son path aux patterns Owner
#   de l'agent dans la matrice file-ownership.md §1.
# - Toute violation → append à workspace/output/.audit/ownership-violations.log
#   (silence chat strict, cf. chat-output.md).
#
# Le hook NE BLOQUE PAS la session : il loggue et continue. Le Tech
# Lead consulte le log post-batch.

$ErrorActionPreference = 'Stop'

$inputText = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($inputText)) {
    exit 0
}

# Parser l'agent invoqué
$subagentType = $null
try {
    $payload = $inputText | ConvertFrom-Json -ErrorAction Stop
    $subagentType = $payload.tool_input.subagent_type
    if ([string]::IsNullOrWhiteSpace($subagentType)) {
        $subagentType = $payload.subagent_type
    }
} catch {
    $match = [regex]::Match($inputText, '"subagent_type"\s*:\s*"([^"]+)"')
    if ($match.Success) {
        $subagentType = $match.Groups[1].Value
    }
}

if ([string]::IsNullOrWhiteSpace($subagentType)) {
    exit 0
}

# Matrice ownership simplifiée (extracted from file-ownership.md §1)
# Format : agent → liste de patterns autorisés (regex sur path normalisé)
$ownershipMatrix = @{
    'po' = @(
        '^workspace/output/us/.+\.md$',
        '^workspace/output/context/constitution\.md$'  # append-only §3 §2
    )
    'arch' = @(
        '^workspace/output/src/[^/]+\.sln$',
        '^workspace/output/src/[^/]+/(\w+\.csproj|package\.json|pyproject\.toml|build\.gradle.*)$',
        '^workspace/output/src/[^/]+/Entities/.+',
        '^workspace/output/src/[^/]+/CLAUDE\.md$',
        '^workspace/output/db/.+',
        '^workspace/output/context/(constitution\.md|adrs/.+)$'
    )
    'dev-backend' = @(
        '^workspace/output/src/[^/]+/(Services|Endpoints|DTOs|Mappers|Validators|Controllers)/.+',
        '^workspace/output/src/[^/]+/Program\.cs$',
        '^workspace/output/src/[^/]+/Models/.+',  # backend models
        '^workspace/output/plans/.+\.back\.md$',
        '^workspace/output/context/adrs/ADR-.+\.md$'
    )
    'dev-frontend' = @(
        '^workspace/output/src/[^/]+/(Pages|Components|Layouts|Auth)/.+',
        '^workspace/output/src/[^/]+/wwwroot/.+',
        '^workspace/output/src/[^/]+/Program\.cs$',
        '^.+\.razor\.css$',
        '^workspace/output/plans/.+\.front\.md$',
        '^workspace/output/context/adrs/ADR-.+\.md$'
    )
    'qa' = @(
        '^workspace/output/src/.+\.Tests/.+',
        '^workspace/output/src/.+/__tests__/.+',
        '^workspace/output/src/.+\.(spec|test)\.(ts|tsx|js|jsx)$',
        '^workspace/output/src/.+(Test|Spec)\.kt$',
        '^workspace/output/src/.+test_.+\.py$',
        '^workspace/output/qa/feat-.+/(report\.md|coverage\.json|quality\.json|api-tests\.(json|md))$'
    )
    'dashboard' = @(
        '^workspace/output/dashboard/README\.html$',
        '^workspace/output/context/adrs/INDEX\.md$',
        '^workspace/output/qa/feat-[^/]+/dashboard\.html$'
    )
    'elicitor' = @(
        '^workspace/input/specs/.+\.md$',  # append-only
        '^workspace/output/context/constitution\.md$'  # append-only §7
    )
}

if (-not $ownershipMatrix.ContainsKey($subagentType)) {
    exit 0  # agent inconnu, pas d'audit
}

$allowedPatterns = $ownershipMatrix[$subagentType]

# Trouver les fichiers modifiés récemment dans workspace/
$workspaceRoot = Join-Path (Get-Location) 'workspace'
if (-not (Test-Path $workspaceRoot)) {
    exit 0
}

# Fenêtre temporelle : depuis $env:SDD_DISPATCH_START_TS ou 5 dernières minutes
$cutoffTime = (Get-Date).AddMinutes(-5)
if ($env:SDD_DISPATCH_START_TS) {
    try {
        $cutoffTime = [DateTime]::Parse($env:SDD_DISPATCH_START_TS)
    } catch {
        # Format invalide, fallback 5 min
    }
}

$modified = Get-ChildItem -Path $workspaceRoot -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -gt $cutoffTime }

if (-not $modified) {
    exit 0
}

$violations = @()
$repoRoot = (Get-Location).Path -replace '\\', '/'

foreach ($file in $modified) {
    $relativePath = ($file.FullName -replace '\\', '/').Replace($repoRoot, '').TrimStart('/')

    # Vérifier si le path matche au moins un pattern autorisé
    $matched = $false
    foreach ($pattern in $allowedPatterns) {
        if ($relativePath -match $pattern) {
            $matched = $true
            break
        }
    }

    if (-not $matched) {
        # Ignorer .audit/ et fichiers temp
        if ($relativePath -match '\.audit/' -or $relativePath -match '\.tmp$') {
            continue
        }
        $violations += $relativePath
    }
}

if ($violations.Count -eq 0) {
    exit 0
}

# Append au log
$auditDir = Join-Path (Get-Location) 'workspace/output/.audit'
if (-not (Test-Path $auditDir)) {
    New-Item -Path $auditDir -ItemType Directory -Force | Out-Null
}

$logFile = Join-Path $auditDir 'ownership-violations.log'
$timestamp = (Get-Date).ToUniversalTime().ToString('o')

foreach ($violation in $violations) {
    $line = "$timestamp [FILE_OWNERSHIP] $subagentType wrote $violation (pattern hors matrice file-ownership.md §1)"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

# Pas de stderr (silence strict). Le Tech Lead consulte le log.
exit 0
