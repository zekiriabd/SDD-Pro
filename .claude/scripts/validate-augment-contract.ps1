# SDD_Pro - PostToolUse hook (Edit|Write|MultiEdit)
#
# Verifie qu'apres une edition de fichier code (workspace/output/src/),
# les contrats preserves: et adds: declares dans le plan de la US
# courante sont respectes (substring check deterministe, 0 token LLM).
#
# - Si le fichier edite ne fait PAS partie de workspace/output/src/ -> exit 0 (skip)
# - Si la US courante est ambigue (pas de plan dispatche) -> exit 0 (skip silent)
# - Si preserves: viole -> exit 2 + ERROR 3 lignes [PRESERVES_VIOLATED]
# - Si adds: non present -> exit 2 + ERROR 3 lignes [ADDS_VIOLATED]
# - Sinon exit 0
#
# Le hook est non-bloquant cote framework : un exit 2 emet juste un
# WARNING dans le chat (cf. chat-output.md) que l'agent ou le Tech Lead
# peut ignorer si justifie. Il n'interrompt pas la session Claude Code.

$ErrorActionPreference = 'Stop'

$inputText = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($inputText)) {
    exit 0
}

# Parser file_path depuis l'input JSON
$filePath = $null
try {
    $payload = $inputText | ConvertFrom-Json -ErrorAction Stop
    $filePath = $payload.tool_input.file_path
    if ([string]::IsNullOrWhiteSpace($filePath)) {
        $filePath = $payload.file_path
    }
} catch {
    $match = [regex]::Match($inputText, '"file_path"\s*:\s*"([^"]+)"')
    if ($match.Success) {
        $filePath = $match.Groups[1].Value
    }
}

if ([string]::IsNullOrWhiteSpace($filePath)) {
    exit 0
}

# Normaliser
$normalized = $filePath -replace '\\', '/'

# Skip si hors workspace/output/src/
if (-not $normalized.Contains('workspace/output/src/')) {
    exit 0
}

# Skip si fichier de test (propriete QA)
$testPatterns = @('*.Tests/', '__tests__/', '.spec.', '.test.', 'Tests.cs', 'test_', '_test.py', 'Test.kt', 'Spec.kt')
foreach ($pat in $testPatterns) {
    if ($normalized.Contains($pat)) {
        exit 0
    }
}

# Lire le fichier edite
if (-not (Test-Path $filePath)) {
    exit 0
}
$content = Get-Content -Path $filePath -Raw -ErrorAction SilentlyContinue
if ([string]::IsNullOrWhiteSpace($content)) {
    exit 0
}

# Trouver les plans dev-* qui pourraient contenir preserves/adds pour ce fichier
$plansDir = Join-Path (Get-Location) 'workspace/output/plans'
if (-not (Test-Path $plansDir)) {
    exit 0
}

$plans = Get-ChildItem -Path $plansDir -Filter '*.md' -ErrorAction SilentlyContinue
if (-not $plans) {
    exit 0
}

# Recherche du fichier dans les plans
$matchingPlan = $null
$fileName = Split-Path -Leaf $filePath
foreach ($plan in $plans) {
    $planContent = Get-Content -Path $plan.FullName -Raw -ErrorAction SilentlyContinue
    if ($planContent -and ($planContent.Contains($filePath) -or $planContent.Contains($fileName))) {
        $matchingPlan = $plan
        break
    }
}

if (-not $matchingPlan) {
    exit 0  # pas de plan = mode inline, on ne peut pas valider
}

$planText = Get-Content -Path $matchingPlan.FullName -Raw

# Extraire les preserves: pour ce fichier (regex multiline)
$preservesPattern = '(?ms)' + [regex]::Escape($fileName) + '.*?preserves:\s*\[([^\]]*)\]'
$preservesMatch = [regex]::Match($planText, $preservesPattern)

if ($preservesMatch.Success) {
    $preservesList = $preservesMatch.Groups[1].Value -split ',' | ForEach-Object { $_.Trim().Trim('"').Trim("'") } | Where-Object { $_ }
    foreach ($id in $preservesList) {
        if (-not $content.Contains($id)) {
            $msg1 = "ERROR: PostToolUse hook on " + $filePath
            $msg2 = "CAUSE: [PRESERVES_VIOLATED] identifiant '" + $id + "' (declare preserves: dans " + $matchingPlan.Name + ") absent du fichier apres edition"
            $msg3 = "FIX: re-dispatcher l'agent ou restaurer manuellement '" + $id + "' dans " + $filePath
            [Console]::Error.WriteLine($msg1)
            [Console]::Error.WriteLine($msg2)
            [Console]::Error.WriteLine($msg3)
            exit 2
        }
    }
}

# Extraire les adds: pour ce fichier
$addsPattern = '(?ms)' + [regex]::Escape($fileName) + '.*?adds:\s*\[([^\]]*)\]'
$addsMatch = [regex]::Match($planText, $addsPattern)

if ($addsMatch.Success) {
    $addsList = $addsMatch.Groups[1].Value -split ',' | ForEach-Object { $_.Trim().Trim('"').Trim("'") } | Where-Object { $_ }
    foreach ($id in $addsList) {
        if (-not $content.Contains($id)) {
            $msg1 = "ERROR: PostToolUse hook on " + $filePath
            $msg2 = "CAUSE: [ADDS_VIOLATED] identifiant '" + $id + "' (declare adds: dans " + $matchingPlan.Name + ") non present apres ecriture"
            $msg3 = "FIX: re-dispatcher l'agent ou ajouter '" + $id + "' manuellement dans " + $filePath
            [Console]::Error.WriteLine($msg1)
            [Console]::Error.WriteLine($msg2)
            [Console]::Error.WriteLine($msg3)
            exit 2
        }
    }
}

exit 0
