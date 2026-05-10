# SDD_Pro — PreToolUse hook
# Avertit quand Edit/Write/MultiEdit cible un fichier propriété du framework.
# Non bloquant : émet WARNING sur stderr, exit 0.
# Adapté depuis SDD_Lite v2.22.4 — paths Pro (.claude/agents/, .claude/rules/, etc.)

$inputText = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($inputText)) {
    exit 0
}

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

$normalized = $filePath -replace '\\', '/'

# Fichiers propriétaire framework SDD_Pro
$frameworkOwned = @(
    '.claude/rules/',
    '.claude/stacks/',
    '.claude/agents/',
    '.claude/templates/',
    '.claude/scripts/',
    '.claude/hooks/',
    '.claude/commands/',
    '.claude/loader.yml',
    '.claude/CLAUDE.md',
    '.claude/MIGRATION.md',
    '.claude/CHANGELOG.md'
)

foreach ($path in $frameworkOwned) {
    if ($normalized.Contains($path)) {
        [Console]::Error.WriteLine("WARNING: '$filePath' est un fichier propriete framework SDD_Pro.")
        [Console]::Error.WriteLine("         Les agents produit (po, arch, dev-*, qa, dashboard) ne doivent pas le modifier.")
        [Console]::Error.WriteLine("         Maintenance framework autorisee deliberement (Tech Lead).")
        break
    }
}

# Rappels specifiques
if ($normalized.Contains('.claude/CLAUDE.md')) {
    [Console]::Error.WriteLine("         Rappel: synchroniser .claude/CHANGELOG.md et docs/ si changement architectural.")
}
if ($normalized.Contains('.claude/loader.yml')) {
    [Console]::Error.WriteLine("         Rappel: loader.yml doit refleter les reads/writes reels des agents.")
}

exit 0
