# init-status-json.ps1
# Bootstrap idempotent de workspace/console/status.json
# Cree le fichier squelette s il n existe pas. Ne touche rien sinon.
# Le scan dynamique des specs/US/plans est fait par le serveur Fastify
# au runtime (GET /api/tree) ; ce script ne fait que poser le fichier vide.

[CmdletBinding()]
param(
  [string]$Path = "workspace/console/status.json",
  [switch]$Force
)

$ErrorActionPreference = 'Stop'

if ((Test-Path $Path) -and -not $Force) {
  Write-Host "[skip] $Path existe deja (idempotent). Utiliser -Force pour ecraser."
  exit 0
}

$dir = Split-Path -Parent $Path
if ($dir -and -not (Test-Path $dir)) {
  New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

$skeleton = [ordered]@{
  version   = 1
  updatedAt = (Get-Date).ToUniversalTime().ToString("o")
  specs     = [ordered]@{}
  gates     = [ordered]@{}
}

# Ecriture UTF-8 sans BOM (compat Node.js JSON.parse strict)
$json = $skeleton | ConvertTo-Json -Depth 10
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText((Resolve-Path $dir).Path + [IO.Path]::DirectorySeparatorChar + (Split-Path -Leaf $Path), $json, $utf8NoBom)

Write-Host "[ok] $Path bootstrap (squelette vide)"
