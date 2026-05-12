# =============================================================================
# SDD_Pro - State Machine & Event Log (Phase 0 foundation)
# =============================================================================
# Couche minimale d'observabilite pour les commandes /sdd-full, /dev-run,
# /qa-generate. Persiste un state.json par run + un events.jsonl global.
# Aucune obligation pour les commandes existantes : adoption progressive.
#
# Schema state file (workspace/output/.state/run-{runId}.json) :
#   {
#     "runId": "guid", "specNumber": 1, "specName": "spec-connexion",
#     "command": "/sdd-full", "tags": ["force"],
#     "startedAt": ISO, "endedAt": null,
#     "status": "running" | "success" | "partial" | "failed",
#     "currentPhase": "spec-validate",
#     "phases": {
#       "us-generate":   { "status": "pass", "startedAt": ISO, "endedAt": ISO, "payload": {...} },
#       "spec-validate": { "status": "warn", ... }
#     }
#   }
#
# Schema events (workspace/output/.state/events.jsonl, append-only) :
#   {"ts":ISO,"runId":"...","specNumber":N,"event":"run.start","cmd":"..."}
#   {"ts":ISO,"runId":"...","event":"phase.start","phase":"..."}
#   {"ts":ISO,"runId":"...","event":"phase.end","phase":"...","status":"...","payload":{...}}
#   {"ts":ISO,"runId":"...","event":"run.end","status":"...","durationMs":N}
#
# API:
#   -Action new-run    -SpecNumber N [-Command C] [-Tags "a,b,c"]   -> stdout: runId
#   -Action set-phase  -RunId R -Phase P -Status start|pass|warn|fail|skip [-PayloadJson '{}']
#   -Action end-run    -RunId R [-Status success|partial|failed]
#   -Action get-run    -SpecNumber N [-Latest]                       -> stdout: runId
#   -Action show-run   -RunId R                                      -> stdout: state JSON
#   -Action list-runs  [-SpecNumber N] [-Limit 10]                   -> stdout: tableau
#   -Action emit-event -RunId R -EventType T [-PayloadJson '{}']     -> primitive bas-niveau
#
# Exit 0 si OK, exit 1 sur erreur d'API (runId inconnu, etc.).
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('new-run','set-phase','end-run','get-run','show-run','list-runs','emit-event')]
    [string]$Action,

    [int]$SpecNumber = 0,
    [string]$RunId = "",
    [string]$Phase = "",
    [ValidateSet('','start','pass','warn','fail','skip','running','success','partial','failed')]
    [string]$Status = "",
    [string]$Command = "",
    [string]$Tags = "",
    [string]$PayloadJson = "",
    [string]$EventType = "",
    [int]$Limit = 10,
    [switch]$Latest
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Get-Location).Path
$StateDir    = Join-Path $ProjectRoot 'workspace/output/.state'
$EventsFile  = Join-Path $StateDir 'events.jsonl'

if (-not (Test-Path $StateDir)) { New-Item -ItemType Directory -Path $StateDir -Force | Out-Null }

function Get-IsoNow {
    return (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
}

function Get-StatePath([string]$runId) {
    return (Join-Path $StateDir "run-$runId.json")
}

function Read-State([string]$runId) {
    $path = Get-StatePath $runId
    if (-not (Test-Path $path)) { return $null }
    $raw = Get-Content $path -Raw -Encoding UTF8
    return ($raw | ConvertFrom-Json)
}

function Write-State($state) {
    $path = Get-StatePath $state.runId
    $tmp = "$path.tmp"
    $state.updatedAt = Get-IsoNow
    ($state | ConvertTo-Json -Depth 12) | Set-Content -Path $tmp -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $path -Force
}

function Append-Event($obj) {
    $line = ($obj | ConvertTo-Json -Depth 8 -Compress)
    # Retry simple sur lock concurrent
    for ($i = 0; $i -lt 5; $i++) {
        try {
            Add-Content -Path $EventsFile -Value $line -Encoding UTF8 -ErrorAction Stop
            return
        } catch {
            Start-Sleep -Milliseconds (50 * ($i + 1))
        }
    }
    throw "Append-Event failed after 5 retries: $($_.Exception.Message)"
}

function Parse-PayloadJson([string]$s) {
    if ([string]::IsNullOrWhiteSpace($s)) { return $null }
    try { return ($s | ConvertFrom-Json) } catch { return @{ raw = $s } }
}

function Get-SpecName([int]$n) {
    $specs = Join-Path $ProjectRoot 'workspace/input/specs'
    if (-not (Test-Path $specs)) { return $null }
    $f = @(Get-ChildItem -Path $specs -Filter "$n-*.md" -File -ErrorAction SilentlyContinue)
    if ($f.Count -ne 1) { return $null }
    if ($f[0].BaseName -match "^$n-(.+)$") { return $Matches[1] }
    return $null
}

# -----------------------------------------------------------------------------
switch ($Action) {

  'new-run' {
    if ($SpecNumber -le 0) { Write-Error "new-run requires -SpecNumber > 0"; exit 1 }
    $runId = [guid]::NewGuid().ToString('n').Substring(0, 12)
    $tagsArr = @()
    if ($Tags) { $tagsArr = @($Tags.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }
    $state = [pscustomobject]@{
      runId        = $runId
      specNumber   = $SpecNumber
      specName     = (Get-SpecName $SpecNumber)
      command      = if ($Command) { $Command } else { 'unknown' }
      tags         = $tagsArr
      startedAt    = Get-IsoNow
      updatedAt    = Get-IsoNow
      endedAt      = $null
      status       = 'running'
      currentPhase = $null
      phases       = [pscustomobject]@{}
    }
    Write-State $state
    Append-Event ([pscustomobject]@{
      ts = $state.startedAt; runId = $runId; specNumber = $SpecNumber
      event = 'run.start'; cmd = $state.command; tags = $tagsArr
    })
    Write-Output $runId
    exit 0
  }

  'set-phase' {
    if (-not $RunId)  { Write-Error "set-phase requires -RunId"; exit 1 }
    if (-not $Phase)  { Write-Error "set-phase requires -Phase"; exit 1 }
    if (-not $Status) { Write-Error "set-phase requires -Status"; exit 1 }
    $state = Read-State $RunId
    if (-not $state) { Write-Error "Unknown runId: $RunId"; exit 1 }
    $now = Get-IsoNow
    $payload = Parse-PayloadJson $PayloadJson

    $existing = $null
    if ($state.phases.PSObject.Properties.Name -contains $Phase) {
      $existing = $state.phases.$Phase
    }

    if ($Status -eq 'start') {
      $phaseObj = [pscustomobject]@{ status = 'running'; startedAt = $now; endedAt = $null; payload = $payload }
      $eventType = 'phase.start'
    } else {
      $started = if ($existing) { $existing.startedAt } else { $now }
      $phaseObj = [pscustomobject]@{ status = $Status; startedAt = $started; endedAt = $now; payload = $payload }
      $eventType = 'phase.end'
    }

    if ($state.phases.PSObject.Properties.Name -contains $Phase) {
      $state.phases.$Phase = $phaseObj
    } else {
      $state.phases | Add-Member -NotePropertyName $Phase -NotePropertyValue $phaseObj -Force
    }
    $state.currentPhase = $Phase
    Write-State $state

    $evt = [pscustomobject]@{
      ts = $now; runId = $RunId; specNumber = $state.specNumber
      event = $eventType; phase = $Phase; status = $Status
    }
    if ($payload) { $evt | Add-Member -NotePropertyName payload -NotePropertyValue $payload }
    Append-Event $evt
    exit 0
  }

  'end-run' {
    if (-not $RunId) { Write-Error "end-run requires -RunId"; exit 1 }
    $state = Read-State $RunId
    if (-not $state) { Write-Error "Unknown runId: $RunId"; exit 1 }
    $finalStatus = if ($Status) { $Status } else { 'success' }
    $state.status = $finalStatus
    $state.endedAt = Get-IsoNow

    $started = [datetime]::Parse($state.startedAt).ToUniversalTime()
    $ended   = [datetime]::Parse($state.endedAt).ToUniversalTime()
    $durMs = [int]($ended - $started).TotalMilliseconds

    Write-State $state
    Append-Event ([pscustomobject]@{
      ts = $state.endedAt; runId = $RunId; specNumber = $state.specNumber
      event = 'run.end'; status = $finalStatus; durationMs = $durMs
    })
    Write-Output "run $RunId ended status=$finalStatus durationMs=$durMs"
    exit 0
  }

  'get-run' {
    if ($SpecNumber -le 0) { Write-Error "get-run requires -SpecNumber"; exit 1 }
    $files = @(Get-ChildItem -Path $StateDir -Filter 'run-*.json' -File -ErrorAction SilentlyContinue)
    $hits = @()
    foreach ($f in $files) {
      try {
        $s = (Get-Content $f.FullName -Raw -Encoding UTF8) | ConvertFrom-Json
        if ($s.specNumber -eq $SpecNumber) { $hits += $s }
      } catch { }
    }
    if ($hits.Count -eq 0) { exit 1 }
    $sorted = $hits | Sort-Object -Property startedAt -Descending
    if ($Latest) {
      Write-Output $sorted[0].runId
    } else {
      foreach ($h in $sorted) { Write-Output $h.runId }
    }
    exit 0
  }

  'show-run' {
    if (-not $RunId) { Write-Error "show-run requires -RunId"; exit 1 }
    $state = Read-State $RunId
    if (-not $state) { Write-Error "Unknown runId: $RunId"; exit 1 }
    $state | ConvertTo-Json -Depth 12
    exit 0
  }

  'list-runs' {
    $files = @(Get-ChildItem -Path $StateDir -Filter 'run-*.json' -File -ErrorAction SilentlyContinue)
    $runs = @()
    foreach ($f in $files) {
      try {
        $s = (Get-Content $f.FullName -Raw -Encoding UTF8) | ConvertFrom-Json
        if ($SpecNumber -gt 0 -and $s.specNumber -ne $SpecNumber) { continue }
        $runs += [pscustomobject]@{
          runId = $s.runId; spec = $s.specNumber; cmd = $s.command
          status = $s.status; phase = $s.currentPhase
          startedAt = $s.startedAt; endedAt = $s.endedAt
        }
      } catch { }
    }
    $runs | Sort-Object -Property startedAt -Descending | Select-Object -First $Limit | Format-Table -AutoSize
    exit 0
  }

  'emit-event' {
    if (-not $RunId) { Write-Error "emit-event requires -RunId"; exit 1 }
    if (-not $EventType) { Write-Error "emit-event requires -EventType"; exit 1 }
    $payload = Parse-PayloadJson $PayloadJson
    $state = Read-State $RunId
    $specN = if ($state) { $state.specNumber } else { 0 }
    $evt = [pscustomobject]@{
      ts = Get-IsoNow; runId = $RunId; specNumber = $specN; event = $EventType
    }
    if ($payload) { $evt | Add-Member -NotePropertyName payload -NotePropertyValue $payload }
    Append-Event $evt
    exit 0
  }
}
