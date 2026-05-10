# validate-inline-rules.ps1
# Detecte le drift entre les inline rules dans agents/*.md et les rule files
# .claude/rules/*.md correspondants.
#
# Strategie : pour chaque agent qui contient une section "## Inline Rules",
# extraire les references "substance de \`{rule}.md ...\`" et verifier que
# le rule file n'a pas ete modifie APRES l'agent (mtime). Si oui, drift
# probable : l'agent inline une version potentiellement obsolete.
#
# Usage:
#   .\validate-inline-rules.ps1                # rapport humain
#   .\validate-inline-rules.ps1 -Json          # sortie JSON (CI)
#   .\validate-inline-rules.ps1 -Strict        # exit 1 si drift detecte

[CmdletBinding()]
param(
  [switch]$Json,
  [switch]$Strict
)

$ErrorActionPreference = "Stop"

$claudeRoot = Join-Path $PSScriptRoot ".."
$agentsDir = Join-Path $claudeRoot "agents"
$rulesDir  = Join-Path $claudeRoot "rules"

if (-not (Test-Path $agentsDir)) {
  Write-Error "Agents dir not found: $agentsDir"
  exit 1
}
if (-not (Test-Path $rulesDir)) {
  Write-Error "Rules dir not found: $rulesDir"
  exit 1
}

$agents = Get-ChildItem -Path $agentsDir -Filter "*.md" -File
$rules = Get-ChildItem -Path $rulesDir -Filter "*.md" -File

# Indexer les rule files par nom (sans extension)
$rulesByName = @{}
foreach ($r in $rules) {
  $rulesByName[$r.BaseName] = $r
}

$findings = New-Object System.Collections.Generic.List[object]

foreach ($agent in $agents) {
  $content = Get-Content -Path $agent.FullName -Raw
  $agentMtime = $agent.LastWriteTimeUtc

  # Detecter section "## Inline Rules"
  if ($content -notmatch "(?ms)^## Inline Rules") { continue }

  # Extraire les references "substance de `{rule}.md`" (pattern flexible)
  # Match: substance de `XYZ.md` ou substance de `XYZ.md ...`
  $substancePattern = 'substance de\s*`([a-zA-Z0-9_-]+)\.md'
  $matches = [regex]::Matches($content, $substancePattern)

  # Aussi : refs explicites @.claude/rules/{name}.md
  $atPattern = '@\.claude/rules/([a-zA-Z0-9_-]+)\.md'
  $atMatches = [regex]::Matches($content, $atPattern)

  # Force tableau (sinon PS concat 2 strings au lieu de 2 arrays)
  $allRefs = @()
  foreach ($m in $matches)   { $allRefs += $m.Groups[1].Value }
  foreach ($m in $atMatches) { $allRefs += $m.Groups[1].Value }
  $referencedRules = @($allRefs | Sort-Object -Unique)

  foreach ($ruleName in $referencedRules) {
    if (-not $rulesByName.ContainsKey($ruleName)) {
      $findings.Add([pscustomobject]@{
        agent       = $agent.Name
        rule        = "$ruleName.md"
        status      = "MISSING_RULE"
        rule_mtime  = $null
        agent_mtime = $agentMtime
        delta_days  = $null
        message     = "Agent reference une rule inexistante"
      })
      continue
    }

    $ruleFile = $rulesByName[$ruleName]
    $ruleMtime = $ruleFile.LastWriteTimeUtc

    if ($ruleMtime -gt $agentMtime) {
      $deltaDays = [math]::Round(($ruleMtime - $agentMtime).TotalDays, 1)
      $findings.Add([pscustomobject]@{
        agent       = $agent.Name
        rule        = "$ruleName.md"
        status      = "DRIFT_SUSPECTED"
        rule_mtime  = $ruleMtime.ToString("yyyy-MM-ddTHH:mm:ssZ")
        agent_mtime = $agentMtime.ToString("yyyy-MM-ddTHH:mm:ssZ")
        delta_days  = $deltaDays
        message     = "Rule modifiee $deltaDays jours apres l'agent : verifier que les Inline Rules de l'agent sont a jour"
      })
    } else {
      $findings.Add([pscustomobject]@{
        agent       = $agent.Name
        rule        = "$ruleName.md"
        status      = "OK"
        rule_mtime  = $ruleMtime.ToString("yyyy-MM-ddTHH:mm:ssZ")
        agent_mtime = $agentMtime.ToString("yyyy-MM-ddTHH:mm:ssZ")
        delta_days  = $null
        message     = "OK"
      })
    }
  }
}

# Sortie
if ($Json) {
  $result = [pscustomobject]@{
    scanned_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    agents_count = $agents.Count
    rules_count = $rules.Count
    findings = $findings
    summary = [pscustomobject]@{
      ok               = ($findings | Where-Object status -eq "OK").Count
      drift_suspected  = ($findings | Where-Object status -eq "DRIFT_SUSPECTED").Count
      missing_rule     = ($findings | Where-Object status -eq "MISSING_RULE").Count
    }
  }
  $result | ConvertTo-Json -Depth 5
} else {
  Write-Host ""
  Write-Host "=== Inline Rules Drift Detection ===" -ForegroundColor Cyan
  Write-Host "Agents scannes  : $($agents.Count)"
  Write-Host "Rules disponibles : $($rules.Count)"
  Write-Host ""

  $drift = $findings | Where-Object status -eq "DRIFT_SUSPECTED"
  $missing = $findings | Where-Object status -eq "MISSING_RULE"
  $ok = $findings | Where-Object status -eq "OK"

  if ($missing.Count -gt 0) {
    Write-Host "[MISSING_RULE] Agent reference une rule introuvable :" -ForegroundColor Red
    $missing | Format-Table -AutoSize agent, rule, message
  }

  if ($drift.Count -gt 0) {
    Write-Host "[DRIFT_SUSPECTED] Rule modifiee apres l'agent qui l'inline :" -ForegroundColor Yellow
    $drift | Format-Table -AutoSize agent, rule, delta_days, rule_mtime, agent_mtime
    Write-Host "Action recommandee : relire l'agent et verifier que les Inline Rules" -ForegroundColor Yellow
    Write-Host "couvrent toujours la substance courante de la rule."             -ForegroundColor Yellow
  }

  if ($ok.Count -gt 0) {
    Write-Host "[OK] $($ok.Count) references coherentes (rule plus ancienne que l'agent)." -ForegroundColor Green
  }

  Write-Host ""
  $okCount = @($ok).Count
  $driftCount = @($drift).Count
  $missingCount = @($missing).Count
  Write-Host "Resume : OK=$okCount  DRIFT=$driftCount  MISSING=$missingCount"
}

# Exit code
if ($Strict -and (($findings | Where-Object { $_.status -ne "OK" }).Count -gt 0)) {
  exit 1
}
exit 0
