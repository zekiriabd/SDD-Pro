# acquire-libname-lock.ps1
# Externalise la procédure de lock file LibName (L2 file-ownership.md §4)
# pour les agents dev-backend et dev-frontend qui écrivent dans
# workspace/output/src/{LibName}/.
#
# Workload déterministe : création atomique du .lock, vérification
# stale-lock, lecture de l'AGENT_ID propriétaire en cas d'échec.
#
# Usage (acquire) :
#   .\acquire-libname-lock.ps1 -LibPath workspace/output/src/Shared `
#     -Entity BebeDto -AgentId "dev-backend-1-2"
#
# Usage (release) :
#   .\acquire-libname-lock.ps1 -LibPath workspace/output/src/Shared `
#     -Entity BebeDto -AgentId "dev-backend-1-2" -Release
#
# Exit codes:
#   0  Lock acquired (ou same agent re-entrant) / Released
#   1  Lock held by another agent → STOP + ERROR [LIBNAME_LOCK_HELD]
#   2  Stale lock détecté et écrasé (recovery)
#   3  Erreur (chemin invalide, permission, etc.)
#
# Sortie JSON sur stdout pour parsing par l'agent.

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)] [string]$LibPath,
  [Parameter(Mandatory=$true)] [string]$Entity,
  [Parameter(Mandatory=$true)] [string]$AgentId,
  [switch]$Release,
  [int]$StaleThresholdSeconds = 1800   # 30 min
)

$ErrorActionPreference = "Stop"

$locksDir = Join-Path $LibPath ".locks"
$lockFile = Join-Path $locksDir "$Entity.lock"

if (-not (Test-Path $LibPath)) {
  $r = [pscustomobject]@{ status = "ERROR"; message = "LibPath not found: $LibPath" }
  $r | ConvertTo-Json -Compress
  exit 3
}

# RELEASE
if ($Release) {
  if (Test-Path $lockFile) {
    $owner = (Get-Content $lockFile -Raw -ErrorAction SilentlyContinue) -split ':' | Select-Object -First 1
    if ($owner -ne $AgentId) {
      $r = [pscustomobject]@{
        status   = "ERROR"
        message  = "Cannot release lock owned by another agent ($owner)"
        entity   = $Entity
        owner    = $owner
      }
      $r | ConvertTo-Json -Compress
      exit 3
    }
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    $r = [pscustomobject]@{ status = "RELEASED"; entity = $Entity; agent = $AgentId }
    $r | ConvertTo-Json -Compress
    exit 0
  } else {
    $r = [pscustomobject]@{ status = "NO-LOCK"; entity = $Entity; message = "Lock already released or never existed" }
    $r | ConvertTo-Json -Compress
    exit 0
  }
}

# ACQUIRE
# 1. Créer le dossier .locks/ si absent
if (-not (Test-Path $locksDir)) {
  New-Item -ItemType Directory -Path $locksDir -Force | Out-Null
}

# 2. Si lock existe, vérifier propriétaire et stale
if (Test-Path $lockFile) {
  $lockContent = Get-Content $lockFile -Raw -ErrorAction SilentlyContinue
  $parts = $lockContent -split ':'
  $owner = $parts[0]
  $ts = if ($parts.Count -ge 2) { [int64]$parts[1] } else { 0 }
  $now = [int64](Get-Date -UFormat %s)
  $age = $now - $ts

  # Same agent → idempotent re-entry
  if ($owner -eq $AgentId) {
    $r = [pscustomobject]@{
      status  = "RE-ENTRANT"
      entity  = $Entity
      agent   = $AgentId
      message = "Lock already held by same agent (idempotent)"
    }
    $r | ConvertTo-Json -Compress
    exit 0
  }

  # Stale lock (> 30 min) → écraser
  if ($age -gt $StaleThresholdSeconds) {
    Set-Content -Path $lockFile -Value "${AgentId}:$now" -NoNewline -Encoding ASCII
    $r = [pscustomobject]@{
      status        = "ACQUIRED-STALE-OVERRIDE"
      entity        = $Entity
      agent         = $AgentId
      previous_owner = $owner
      previous_age_seconds = $age
      message       = "Stale lock (age $age s > $StaleThresholdSeconds s) overridden"
    }
    $r | ConvertTo-Json -Compress
    exit 2
  }

  # Lock held by another active agent → STOP
  $r = [pscustomobject]@{
    status      = "LOCK-HELD"
    entity      = $Entity
    agent       = $AgentId
    held_by     = $owner
    held_for_seconds = $age
    error_class = "[LIBNAME_LOCK_HELD]"
    message     = "Entity locked by $owner (held for $age seconds). STOP + ERROR for the calling agent."
  }
  $r | ConvertTo-Json -Compress
  exit 1
}

# 3. Lock libre → créer atomiquement
$now = [int64](Get-Date -UFormat %s)
try {
  # Création atomique : si quelqu'un crée le fichier entre la vérif et
  # l'écriture, on aura une erreur. PowerShell n'a pas d'équivalent
  # exact de O_CREAT|O_EXCL ; on contourne via [System.IO.File]::Open.
  $stream = [System.IO.File]::Open($lockFile, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
  $writer = New-Object System.IO.StreamWriter($stream)
  $writer.Write("${AgentId}:$now")
  $writer.Close()
  $stream.Close()
} catch [System.IO.IOException] {
  # Race condition : un autre process a créé le lock entre temps.
  # Re-check et appliquer la même logique (re-entrant ou held).
  Start-Sleep -Milliseconds 50
  & $PSCommandPath -LibPath $LibPath -Entity $Entity -AgentId $AgentId -StaleThresholdSeconds $StaleThresholdSeconds
  exit $LASTEXITCODE
}

$r = [pscustomobject]@{
  status  = "ACQUIRED"
  entity  = $Entity
  agent   = $AgentId
  message = "Lock acquired successfully"
}
$r | ConvertTo-Json -Compress
exit 0
