# SDD_Pro - PreToolUse Agent hook
# Rend context-budget.ps1 executoire : intercepte l'invocation de l'Agent tool,
# parse subagent_type + best-effort SpecNumber/UsId du prompt, et delegue
# au gate context-budget.ps1. Ecrit le ledger JSONL dans .audit/.
#
# Mode pilote par env $env:SDD_BUDGET_MODE :
#   - "warn"   (default) : ecrit ledger + stderr WARNING, exit 0
#   - "strict"           : bloque l'invocation si budget exceeded (exit 2)
#   - "off"              : skip total (exit 0 silencieux)
#
# Conventions :
# - PowerShell 5.1 compatible (pas de ternaire, pas de ??)
# - stderr pour les messages, stdout reserve aux signaux Claude
# - exit 0 = pass, exit 2 = block (PreToolUse contract)

$ErrorActionPreference = 'Stop'

$mode = $env:SDD_BUDGET_MODE
if (-not $mode) { $mode = 'warn' }
if ($mode -eq 'off') { exit 0 }

$inputText = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($inputText)) { exit 0 }

try {
    $payload = $inputText | ConvertFrom-Json -ErrorAction Stop
} catch {
    exit 0
}

$subagent = $null
if ($payload.tool_input -and $payload.tool_input.subagent_type) {
    $subagent = [string]$payload.tool_input.subagent_type
}
if ([string]::IsNullOrWhiteSpace($subagent)) { exit 0 }

# Agents reconnus par context-budget.ps1 (ValidateSet)
$allowed = @('po','arch','dev-backend','dev-frontend','qa','dashboard','elicitor')
if ($allowed -notcontains $subagent) { exit 0 }

# Extraction best-effort SpecNumber / UsId depuis prompt + description
$prompt = ""
if ($payload.tool_input.prompt) { $prompt = [string]$payload.tool_input.prompt }
$descr = ""
if ($payload.tool_input.description) { $descr = [string]$payload.tool_input.description }
$haystack = "$prompt $descr"

$specNumber = 0
$usId = ""

$mUs = [regex]::Match($haystack, '\b(\d{1,3})-(\d{1,3})(?:-[A-Za-z][A-Za-z0-9\-]*)?\b')
if ($mUs.Success) {
    $usId = "$($mUs.Groups[1].Value)-$($mUs.Groups[2].Value)"
    $specNumber = [int]$mUs.Groups[1].Value
} else {
    $mSpec = [regex]::Match($haystack, '(?i)\b(?:spec|feat-?|sdd-full|us-generate|dev-run|dev-plan|qa-generate)\s*[-:]?\s*(\d{1,3})\b')
    if ($mSpec.Success) { $specNumber = [int]$mSpec.Groups[1].Value }
}

$scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$scriptPath = Join-Path $scriptRoot '..\scripts\context-budget.ps1'
if (-not (Test-Path $scriptPath)) {
    [Console]::Error.WriteLine("WARN preflight-agent-budget: context-budget.ps1 introuvable ($scriptPath)")
    exit 0
}

$cbArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$scriptPath,'-Agent',$subagent)
if ($specNumber -gt 0) { $cbArgs += @('-SpecNumber',[string]$specNumber) }
if ($usId)             { $cbArgs += @('-UsId',$usId) }

$psBin = (Get-Command powershell -ErrorAction SilentlyContinue)
if (-not $psBin) { $psBin = (Get-Command pwsh -ErrorAction SilentlyContinue) }
if (-not $psBin) {
    [Console]::Error.WriteLine("WARN preflight-agent-budget: powershell/pwsh introuvable")
    exit 0
}

$cbOutput = & $psBin.Source @cbArgs 2>&1
$cbCode = $LASTEXITCODE

# Forwarder la sortie sur stderr (visible dans Claude)
foreach ($line in $cbOutput) {
    [Console]::Error.WriteLine([string]$line)
}

if ($cbCode -ne 0) {
    if ($mode -eq 'strict') {
        [Console]::Error.WriteLine("ERROR: preflight-agent-budget - agent '$subagent' refuse")
        [Console]::Error.WriteLine("CAUSE: context-budget.ps1 exit=$cbCode (BUDGET_EXCEEDED ou UNBOUNDED_GLOB)")
        [Console]::Error.WriteLine("FIX: voir workspace/output/.audit/context-budget.jsonl ; reduire reads/ du loader OU exporter `$env:SDD_BUDGET_MODE='warn'")
        exit 2
    } else {
        [Console]::Error.WriteLine("WARN preflight-agent-budget: budget depasse pour '$subagent' (mode=warn, non bloquant)")
    }
}

exit 0
