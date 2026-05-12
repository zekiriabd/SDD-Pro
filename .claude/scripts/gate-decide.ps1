# gate-decide.ps1
# Lecture / ecriture atomique de workspace/console/status.json -> gates.{n}.afterX
# Partage le meme lock file (workspace/console/.status.lock) que la console Node.
# Appele par /sdd-full pour poser des gates pending et detecter les decisions humaines.
#
# Usage:
#   .\gate-decide.ps1 -Action read         -SpecNum 1 -Phase afterUS
#       -> ecrit sur stdout : pending|validated|skipped|none
#
#   .\gate-decide.ps1 -Action pose-pending -SpecNum 1 -Phase afterUS
#       -> pose decision=pending, askedAt=now
#
#   .\gate-decide.ps1 -Action set -SpecNum 1 -Phase afterUS -Decision skipped -AnsweredBy "user@x.fr"
#       -> pose decision=skipped|validated, answeredAt=now
#
#   .\gate-decide.ps1 -Action is-resolved -SpecNum 1 -Phase afterUS
#       -> exit 0 si validated|skipped, exit 1 sinon

[CmdletBinding()]
param(
  [Parameter(Mandatory)]
  [ValidateSet('read', 'pose-pending', 'set', 'is-resolved')]
  [string]$Action,

  [Parameter(Mandatory)][int]$SpecNum,

  [Parameter(Mandatory)]
  [ValidateSet('afterUS', 'afterReadiness', 'afterPlan', 'afterCode')]
  [string]$Phase,

  [ValidateSet('pending', 'validated', 'skipped', 'none')]
  [string]$Decision = 'none',

  [string]$AnsweredBy = "$env:USERNAME@local",
  [string]$StatusFile = "workspace/console/status.json",
  [switch]$Json
)

$ErrorActionPreference = 'Stop'

# ───────── Helpers ─────────

function ConvertTo-PlainHashtable {
  param($InputObject)
  if ($null -eq $InputObject) { return $null }
  if ($InputObject -is [System.Collections.IDictionary]) {
    $h = @{}
    foreach ($k in $InputObject.Keys) { $h[$k] = ConvertTo-PlainHashtable $InputObject[$k] }
    return $h
  }
  if ($InputObject -is [PSCustomObject]) {
    $h = @{}
    foreach ($p in $InputObject.PSObject.Properties) { $h[$p.Name] = ConvertTo-PlainHashtable $p.Value }
    return $h
  }
  if ($InputObject -is [System.Collections.IList] -and -not ($InputObject -is [string])) {
    return @(foreach ($i in $InputObject) { ConvertTo-PlainHashtable $i })
  }
  return $InputObject
}

function Acquire-StatusLock {
  param([string]$LockPath, [int]$RetryCount = 5, [int]$BackoffMs = 50, [int]$TtlMs = 10000)
  for ($i = 0; $i -lt $RetryCount; $i++) {
    try {
      $stream = [System.IO.File]::Open($LockPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
      $writer = New-Object System.IO.StreamWriter($stream)
      $now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
      $writer.Write("ps:${PID}:${now}")
      $writer.Flush(); $writer.Close(); $stream.Close()
      return
    }
    catch [System.IO.IOException] {
      try {
        $content = [System.IO.File]::ReadAllText($LockPath)
        $parts = $content -split ':'
        $ts = $parts[$parts.Length - 1] -as [long]
        $now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        if ($ts -and ($now - $ts) -gt $TtlMs) {
          Remove-Item $LockPath -Force -ErrorAction SilentlyContinue
          continue
        }
      }
      catch { }
      Start-Sleep -Milliseconds ($BackoffMs * ($i + 1))
    }
  }
  throw "[LOCK_HELD] Cannot acquire $LockPath after $RetryCount attempts"
}

function Release-StatusLock {
  param([string]$LockPath)
  Remove-Item $LockPath -Force -ErrorAction SilentlyContinue
}

function Read-Status {
  param([string]$Path)
  if (-not (Test-Path $Path)) {
    return @{ version = 1; updatedAt = (Get-Date).ToUniversalTime().ToString("o"); specs = @{}; gates = @{} }
  }
  $raw = [System.IO.File]::ReadAllText($Path)
  if ([string]::IsNullOrWhiteSpace($raw)) {
    return @{ version = 1; specs = @{}; gates = @{} }
  }
  $obj = $raw | ConvertFrom-Json
  $h = ConvertTo-PlainHashtable $obj
  if (-not $h.ContainsKey('specs')) { $h['specs'] = @{} }
  if (-not $h.ContainsKey('gates')) { $h['gates'] = @{} }
  return $h
}

function Write-Status {
  param([string]$Path, $Status)
  $Status['updatedAt'] = (Get-Date).ToUniversalTime().ToString("o")
  $json = $Status | ConvertTo-Json -Depth 12
  $tmp = "$Path.tmp.$PID"
  $utf8NoBom = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($tmp, $json, $utf8NoBom)
  Move-Item -Force $tmp $Path
}

function Ensure-Gate {
  param($Status, [string]$SpecKey, [string]$Phase)
  if (-not $Status['gates']) { $Status['gates'] = @{} }
  if (-not $Status['gates'].ContainsKey($SpecKey)) { $Status['gates'][$SpecKey] = @{} }
  if (-not $Status['gates'][$SpecKey].ContainsKey($Phase)) { $Status['gates'][$SpecKey][$Phase] = @{} }
  return $Status['gates'][$SpecKey][$Phase]
}

# ───────── Action dispatcher ─────────

$specKey = "$SpecNum"
$lockPath = Join-Path (Split-Path $StatusFile -Parent) ".status.lock"

switch ($Action) {

  'read' {
    if (-not (Test-Path $StatusFile)) {
      if ($Json) { '{"decision":"none"}' } else { 'none' }
      exit 0
    }
    $status = Read-Status $StatusFile
    $gate = $null
    if ($status['gates'] -and $status['gates'].ContainsKey($specKey) -and $status['gates'][$specKey].ContainsKey($Phase)) {
      $gate = $status['gates'][$specKey][$Phase]
    }
    $decision = if ($gate -and $gate.ContainsKey('decision')) { $gate['decision'] } else { 'none' }
    if ($Json) {
      $payload = if ($gate) { $gate } else { @{ decision = 'none' } }
      $payload | ConvertTo-Json -Compress
    } else {
      Write-Output $decision
    }
    exit 0
  }

  'is-resolved' {
    if (-not (Test-Path $StatusFile)) { exit 1 }
    $status = Read-Status $StatusFile
    $gate = $null
    if ($status['gates'] -and $status['gates'].ContainsKey($specKey) -and $status['gates'][$specKey].ContainsKey($Phase)) {
      $gate = $status['gates'][$specKey][$Phase]
    }
    if (-not $gate) { exit 1 }
    if ($gate['decision'] -eq 'validated' -or $gate['decision'] -eq 'skipped') { exit 0 }
    exit 1
  }

  'pose-pending' {
    Acquire-StatusLock $lockPath
    try {
      $status = Read-Status $StatusFile
      $gate = Ensure-Gate $status $specKey $Phase
      $gate['decision'] = 'pending'
      $gate['askedAt'] = (Get-Date).ToUniversalTime().ToString("o")
      $gate.Remove('answeredAt') | Out-Null
      $gate.Remove('answeredBy') | Out-Null
      Write-Status $StatusFile $status
      if ($Json) { ($gate | ConvertTo-Json -Compress) } else { Write-Output 'pending' }
    }
    finally { Release-StatusLock $lockPath }
    exit 0
  }

  'set' {
    if ($Decision -eq 'none') { throw "Action 'set' requires -Decision (validated|skipped|pending)" }
    Acquire-StatusLock $lockPath
    try {
      $status = Read-Status $StatusFile
      $gate = Ensure-Gate $status $specKey $Phase
      $gate['decision'] = $Decision
      $gate['answeredAt'] = (Get-Date).ToUniversalTime().ToString("o")
      $gate['answeredBy'] = $AnsweredBy
      Write-Status $StatusFile $status
      if ($Json) { ($gate | ConvertTo-Json -Compress) } else { Write-Output $Decision }
    }
    finally { Release-StatusLock $lockPath }
    exit 0
  }
}
