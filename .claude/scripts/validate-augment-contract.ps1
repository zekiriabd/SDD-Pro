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

# Parser file_path et tool_name depuis l'input JSON
$filePath = $null
$toolName = $null
try {
    $payload = $inputText | ConvertFrom-Json -ErrorAction Stop
    $filePath = $payload.tool_input.file_path
    if ([string]::IsNullOrWhiteSpace($filePath)) {
        $filePath = $payload.file_path
    }
    $toolName = $payload.tool_name
} catch {
    $match = [regex]::Match($inputText, '"file_path"\s*:\s*"([^"]+)"')
    if ($match.Success) {
        $filePath = $match.Groups[1].Value
    }
    $toolMatch = [regex]::Match($inputText, '"tool_name"\s*:\s*"([^"]+)"')
    if ($toolMatch.Success) {
        $toolName = $toolMatch.Groups[1].Value
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

# Skip total si operation Write (creation de fichier).
# Note (2026-05-11) : `preserves:` ET `adds:` decrivent ce qui doit
# etre present APRES une augmentation (Edit/MultiEdit). Sur Write
# (creation skeleton par arch, ou creation DTO par dev-*), aucune
# obligation contractuelle n'est evaluee — le contrat s'applique
# uniquement sur les Edit ulterieurs.
if ($toolName -eq 'Write') {
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

# Extraire le bloc YAML-like dedie a CE fichier dans le plan
# Format attendu (dev-backend STEP 5.5 / dev-frontend STEP 6.5) :
#   - path: workspace/output/src/.../EanService.kt
#     operation: augment
#     preserves: [...]
#     adds: [...]
#     covers_acs: [AC-3]
#   - path: ... (bloc suivant)
# On extrait UNIQUEMENT le bloc dont path: matche $filePath, pour
# eviter que les preserves:/adds: d'un autre fichier fuient (bug
# scoping cross-file corrige le 2026-05-11).
$normalizedFile = $filePath -replace '\\', '/'
$blockMatches = [regex]::Matches($planText, '(?m)^[-\s]*path:\s*([^\r\n]+?)\s*$')
$blockText = $null
for ($i = 0; $i -lt $blockMatches.Count; $i++) {
    $blockStart = $blockMatches[$i].Index
    $blockEnd = if ($i + 1 -lt $blockMatches.Count) { $blockMatches[$i + 1].Index } else { $planText.Length }
    $candidatePath = ($blockMatches[$i].Groups[1].Value -replace '\\', '/').Trim()
    $candidateLeaf = Split-Path -Leaf $candidatePath
    if ($candidatePath -eq $normalizedFile -or $normalizedFile.EndsWith($candidatePath) -or $candidateLeaf -eq $fileName) {
        $blockText = $planText.Substring($blockStart, $blockEnd - $blockStart)
        break
    }
}

# Si aucun bloc dedie trouve : le fichier est mentionne dans le plan
# mais pas comme entree principale (ex. cite dans adds: d'un autre
# fichier). Pas de contrat applicable, exit 0.
if (-not $blockText) {
    exit 0
}

# Extraire les preserves: a l'interieur du bloc UNIQUEMENT
$preservesMatch = [regex]::Match($blockText, '(?ms)preserves:\s*\[([^\]]*)\]')

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

# Extraire les adds: a l'interieur du bloc dedie UNIQUEMENT
$addsMatch = [regex]::Match($blockText, '(?ms)adds:\s*\[([^\]]*)\]')

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
