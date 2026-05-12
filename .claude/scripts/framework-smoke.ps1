# framework-smoke.ps1 (ASCII-only to avoid encoding issues)
# Smoke test framework-side : validates SDD_Pro internal coherence
# without running a pipeline (no /sdd-full, no agent invoked).
#
# Checks:
# 1. Expected agents/*.md exist with valid frontmatter
# 2. Expected rules/*.md exist
# 3. Expected templates/* exist
# 4. Expected scripts/*.ps1 exist
# 5. Expected commands/*.md exist
# 6. No Inline Rules drift (delegates to validate-inline-rules.ps1)
# 7. CLAUDE.md cites principal commands
# 8. docs/{architecture,workflow,conventions}.md exist
#
# Usage:
#   .\framework-smoke.ps1
#   .\framework-smoke.ps1 -Json
#   .\framework-smoke.ps1 -Strict   (exit 1 on FAIL)

[CmdletBinding()]
param(
  [switch]$Json,
  [switch]$Strict
)

$ErrorActionPreference = "Stop"
$claudeRoot = Join-Path $PSScriptRoot ".."

$checks = New-Object System.Collections.Generic.List[object]

function Add-Check([string]$name, [string]$status, [string]$message) {
  $checks.Add([pscustomobject]@{
    name    = $name
    status  = $status
    message = $message
  })
}

# Check 1 : agents (v6.0 — validator retiré)
$agentsDir = Join-Path $claudeRoot "agents"
$expectedAgents = @('po','arch','dev-backend','dev-frontend','elicitor','qa')
foreach ($a in $expectedAgents) {
  $f = Join-Path $agentsDir "$a.md"
  if (-not (Test-Path $f)) {
    Add-Check "agent-$a" "FAIL" "Missing: $f"
    continue
  }
  $content = Get-Content -Path $f -Raw
  if ($content -notmatch "(?ms)^---\s*\n.*?name:\s*$a\s*\n") {
    Add-Check "agent-$a" "WARN" "Frontmatter name field missing or wrong"
  } else {
    Add-Check "agent-$a" "OK" "agents/$a.md present"
  }
}

# Check 2 : rules
$rulesDir = Join-Path $claudeRoot "rules"
$expectedRules = @(
  'responsibilities','us-granularity','constitution','file-ownership',
  'qa-ownership','qa-coverage','stack-completeness','library-policy'
)
foreach ($r in $expectedRules) {
  $f = Join-Path $rulesDir "$r.md"
  if (-not (Test-Path $f)) {
    Add-Check "rule-$r" "FAIL" "Missing: $f"
  } else {
    Add-Check "rule-$r" "OK" "rules/$r.md present"
  }
}

# Check 3 : templates
$templatesDir = Join-Path $claudeRoot "templates"
$expectedTemplates = @(
  'spec.template.md','us.template.md','constitution.template.md',
  'adr.template.md','readiness.template.md','risks-assumptions.template.md',
  'qa-report.template.md','coverage.template.json','quality.template.json'
)
foreach ($t in $expectedTemplates) {
  $f = Join-Path $templatesDir $t
  if (-not (Test-Path $f)) {
    Add-Check "template-$t" "FAIL" "Missing: $f"
  } else {
    Add-Check "template-$t" "OK" "templates/$t present"
  }
}

# Check 4 : scripts
$scriptsDir = Join-Path $claudeRoot "scripts"
$expectedScripts = @(
  'validate-readiness.ps1','parse-coverage.ps1','quality-scan.ps1',
  'measure-batch.ps1','detect-capabilities.ps1','validate-inline-rules.ps1',
  'framework-smoke.ps1',
  'validate-fidelity.ps1','mark-breaking-resolved.ps1','acquire-libname-lock.ps1'
)
foreach ($s in $expectedScripts) {
  $f = Join-Path $scriptsDir $s
  if (-not (Test-Path $f)) {
    Add-Check "script-$s" "FAIL" "Missing: $f"
  } else {
    Add-Check "script-$s" "OK" "scripts/$s present"
  }
}

# Check 5 : commands
$commandsDir = Join-Path $claudeRoot "commands"
$expectedCommands = @(
  'spec-generate','spec-deepen','spec-validate','us-generate','arch-init',
  'dev-plan','dev-backend','dev-frontend','dev-run','sdd-full','qa-generate',
  'sdd-status'
)
foreach ($c in $expectedCommands) {
  $f = Join-Path $commandsDir "$c.md"
  if (-not (Test-Path $f)) {
    Add-Check "command-$c" "FAIL" "Missing: $f"
  } else {
    Add-Check "command-$c" "OK" "commands/$c.md present"
  }
}

# Check 6 : Inline Rules drift
$driftScript = Join-Path $scriptsDir "validate-inline-rules.ps1"
if (Test-Path $driftScript) {
  try {
    $driftOutput = & $driftScript -Json 2>$null | Out-String
    $driftJson = $driftOutput | ConvertFrom-Json
    $dCount = [int]$driftJson.summary.drift_suspected
    $mCount = [int]$driftJson.summary.missing_rule
    $okCount = [int]$driftJson.summary.ok
    if ($dCount -gt 0) {
      Add-Check "inline-rules-drift" "WARN" "$dCount drift suspected"
    } elseif ($mCount -gt 0) {
      Add-Check "inline-rules-drift" "FAIL" "$mCount missing rules referenced by agents"
    } else {
      Add-Check "inline-rules-drift" "OK" "$okCount refs coherent, 0 drift"
    }
  } catch {
    Add-Check "inline-rules-drift" "WARN" "Could not parse drift detector output"
  }
}

# Check 7 : CLAUDE.md cite les commandes principales
$claudeMd = Join-Path $claudeRoot "CLAUDE.md"
if (Test-Path $claudeMd) {
  $cmContent = Get-Content -Path $claudeMd -Raw
  $missingCmds = @()
  foreach ($c in @('spec-generate','us-generate','dev-run','sdd-full','qa-generate','sdd-status')) {
    if ($cmContent -notmatch "/$c") { $missingCmds += $c }
  }
  if ($missingCmds.Count -gt 0) {
    Add-Check "claude-md-commands" "WARN" "Commands not cited in CLAUDE.md: $($missingCmds -join ', ')"
  } else {
    Add-Check "claude-md-commands" "OK" "Principal commands referenced in CLAUDE.md"
  }
}

# Check 8 : docs/ (v5.0 — README.md retiré comme obsolète v3)
$docsDir = Join-Path $claudeRoot "docs"
foreach ($d in @('architecture.md','workflow.md','conventions.md')) {
  $f = Join-Path $docsDir $d
  if (-not (Test-Path $f)) {
    Add-Check "docs-$d" "WARN" "Missing: docs/$d"
  } else {
    Add-Check "docs-$d" "OK" "docs/$d present"
  }
}

# Output
$ok = @($checks | Where-Object status -eq "OK").Count
$warn = @($checks | Where-Object status -eq "WARN").Count
$fail = @($checks | Where-Object status -eq "FAIL").Count

if ($Json) {
  $result = [pscustomobject]@{
    scanned_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    summary = [pscustomobject]@{
      total = $checks.Count
      ok    = $ok
      warn  = $warn
      fail  = $fail
    }
    checks = $checks
  }
  $result | ConvertTo-Json -Depth 4
} else {
  Write-Host ""
  Write-Host "=== SDD_Pro Framework Smoke Test ===" -ForegroundColor Cyan
  Write-Host ""

  $fails = @($checks | Where-Object status -eq "FAIL")
  if ($fails.Count -gt 0) {
    Write-Host "[FAIL] $($fails.Count) error(s):" -ForegroundColor Red
    $fails | Format-Table -AutoSize name, message
  }

  $warns = @($checks | Where-Object status -eq "WARN")
  if ($warns.Count -gt 0) {
    Write-Host "[WARN] $($warns.Count) warning(s):" -ForegroundColor Yellow
    $warns | Format-Table -AutoSize name, message
  }

  if ($fails.Count -eq 0 -and $warns.Count -eq 0) {
    Write-Host "[OK] All checks pass ($ok / $($checks.Count))" -ForegroundColor Green
  }

  Write-Host ""
  Write-Host "Summary: OK=$ok  WARN=$warn  FAIL=$fail  total=$($checks.Count)"
  Write-Host ""
}

if ($Strict -and $fail -gt 0) { exit 1 }
if ($fail -gt 0) { exit 1 }
exit 0
