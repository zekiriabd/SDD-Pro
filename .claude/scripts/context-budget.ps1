# SDD_Pro - Context budget gate
# Rend .claude/loader.yml executable: expansion des reads, controle des globs,
# budget par agent et ledger JSONL tokens/time/cout.

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('po','arch','dev-backend','dev-frontend','qa','dashboard','elicitor')]
  [string]$Agent,

  [int]$SpecNumber = 0,
  [string]$UsId = "",
  [string]$RepoRoot = "",
  [string]$RunId = "",
  [string]$OutFile = "",
  [switch]$Json,
  [switch]$AllowUnboundedGlobs,
  [int]$BytesPerToken = 4,
  [double]$InputUsdPerMillionTokens = 3.0
)

$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) {
  $scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
  $RepoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..')).Path
}
$started = Get-Date
if (-not $RunId) { $RunId = [guid]::NewGuid().ToString('n') }
if (-not $OutFile) {
  $OutFile = Join-Path $RepoRoot 'workspace\output\.audit\context-budget.jsonl'
}

$defaultBudgets = @{
  'po'           = 60000
  'elicitor'     = 70000
  'arch'         = 180000
  'dev-backend'  = 120000
  'dev-frontend' = 140000
  'qa'           = 280000
  'dashboard'    = 180000
}

function Get-RelPath([string]$Path) {
  $full = [System.IO.Path]::GetFullPath($Path)
  if ($full.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    return $full.Substring($RepoRoot.Length).TrimStart('\','/').Replace('\','/')
  }
  return $full.Replace('\','/')
}

function Read-ProjectConfig {
  $config = @{}
  $stackPath = Join-Path $RepoRoot 'workspace\input\stack\stack.md'
  if (-not (Test-Path $stackPath)) { return $config }
  foreach ($line in Get-Content -Path $stackPath -Encoding UTF8) {
    if ($line -match '^\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.+?)\s*$') {
      $config[$Matches[1]] = $Matches[2].Trim()
    }
  }
  return $config
}

function Get-ActiveStackPaths {
  $stackPath = Join-Path $RepoRoot 'workspace\input\stack\stack.md'
  if (-not (Test-Path $stackPath)) { return @() }
  $paths = @()
  foreach ($line in Get-Content -Path $stackPath -Encoding UTF8) {
    if ($line -match '^\s*-\s*(\.claude/stacks/[^\s]+\.md)\s*$') {
      $paths += $Matches[1]
    }
  }
  return $paths
}

function Parse-LoaderReads([string]$AgentName) {
  $loader = Join-Path $RepoRoot '.claude\loader.yml'
  $lines = Get-Content -Path $loader -Encoding UTF8
  $inAgent = $false
  $inReads = $false
  $reads = @()

  foreach ($line in $lines) {
    if ($line -match '^([a-z][a-z-]*):\s*$') {
      $inAgent = ($Matches[1] -eq $AgentName)
      $inReads = $false
      continue
    }
    if (-not $inAgent) { continue }
    if ($line -match '^\s{2}reads:\s*$') { $inReads = $true; continue }
    if ($line -match '^\s{2}[a-zA-Z_]+:\s*') { $inReads = $false; continue }
    if ($inReads -and $line -match '^\s{4}-\s*(.+?)\s*(#.*)?$') {
      $item = $Matches[1].Trim().Trim('"').Trim("'")
      if ($item -and $item -notmatch '^\#') { $reads += $item }
    }
  }
  return $reads
}

function Resolve-Pattern([string]$Pattern, [hashtable]$Config) {
  $results = @()
  $p = $Pattern

  if ($p -match '\{cat\}/\{active\}') {
    return Get-ActiveStackPaths
  }
  if ($p -match '^\.claude/stacks/([^/]+)/\{active\}\.md$') {
    $cat = $Matches[1]
    return @(Get-ActiveStackPaths | Where-Object { $_ -like ".claude/stacks/$cat/*.md" })
  }

  if ($UsId) {
    $p = $p.Replace('{n}-{m}', $UsId)
  }
  if ($SpecNumber -gt 0) {
    $p = $p.Replace('{n}', [string]$SpecNumber)
  }
  foreach ($key in @('AppName','BackendName','LibName')) {
    if ($Config.ContainsKey($key)) {
      $p = $p.Replace("{$key}", $Config[$key])
    }
  }
  if ($p -match '\{[A-Za-z][A-Za-z0-9_]*\}' -and $p -notmatch '\{Project\}') {
    return @()
  }
  if ($p -match '\{Project\}') {
    foreach ($key in @('AppName','BackendName','LibName')) {
      if ($Config.ContainsKey($key) -and $Config[$key]) {
        $results += $p.Replace('{Project}', $Config[$key])
      }
    }
    return $results
  }
  return @($p)
}

function Test-UnboundedGlob([string]$Pattern) {
  if ($Pattern -notmatch '[\*\?]') { return $false }
  if ($Pattern -match '\{n\}|\{n\}-\{m\}|feat-\{n\}|\{AppName\}|\{BackendName\}|\{LibName\}|\{Project\}') { return $false }
  if ($Pattern -match '^workspace/output/context/adrs/ADR-\*\.md$') { return $false }
  return $true
}

function Test-ExcludedContextFile([System.IO.FileInfo]$File) {
  $rel = Get-RelPath $File.FullName
  if ($rel -match '(^|/)(node_modules|bin|obj|TestResults)(/|$)') { return $true }
  if ($rel -match '/wwwroot/css/(bootstrap|open-iconic)/') { return $true }
  if ($rel -match '\.(dll|exe|pdb|cache|map|woff|ttf|otf|eot|ico)$') { return $true }
  return $false
}

function Expand-Files([string]$Pattern) {
  $fullPattern = Join-Path $RepoRoot $Pattern
  if ($Pattern -notmatch '[\*\?]') {
    if (Test-Path $fullPattern -PathType Leaf) { return @(Get-Item -LiteralPath $fullPattern | Where-Object { -not (Test-ExcludedContextFile $_) }) }
    if (Test-Path $fullPattern -PathType Container) {
      return @(Get-ChildItem -LiteralPath $fullPattern -File | Where-Object { -not (Test-ExcludedContextFile $_) })
    }
    return @()
  }

  $normalized = $fullPattern.Replace('/','\')
  $firstWildcard = $normalized.IndexOfAny([char[]]'*?')
  $prefix = $normalized.Substring(0, $firstWildcard)
  $root = Split-Path -Parent $prefix
  while ($root -and -not (Test-Path $root -PathType Container)) {
    $root = Split-Path -Parent $root
  }
  if (-not $root) { return @() }

  $regex = '^' + [regex]::Escape($normalized).Replace('\*\*', '.*').Replace('\*', '[^\\]*').Replace('\?', '.') + '$'
  return @(Get-ChildItem -LiteralPath $root -Recurse -File | Where-Object { ($_.FullName -match $regex) -and -not (Test-ExcludedContextFile $_) })
}

$reads = Parse-LoaderReads $Agent
$config = Read-ProjectConfig
$errors = @()
$warnings = @()
$expanded = New-Object System.Collections.Generic.List[object]
$seen = @{}

foreach ($read in $reads) {
  if ((Test-UnboundedGlob $read) -and -not $AllowUnboundedGlobs) {
    $errors += [pscustomobject]@{ code = 'UNBOUNDED_GLOB'; pattern = $read; message = 'Glob sans borne SPEC/US refuse' }
    continue
  }
  foreach ($pattern in Resolve-Pattern $read $config) {
    foreach ($file in Expand-Files $pattern) {
      $rel = Get-RelPath $file.FullName
      if ($seen.ContainsKey($rel)) { continue }
      $seen[$rel] = $true
      $expanded.Add([pscustomobject]@{
        path = $rel
        bytes = [int64]$file.Length
        sourcePattern = $read
      })
    }
    if (($pattern -notmatch '[\*\?]') -and -not (Test-Path (Join-Path $RepoRoot $pattern))) {
      $warnings += [pscustomobject]@{ code = 'READ_MISSING'; pattern = $pattern; message = 'Read declare mais fichier absent' }
    }
  }
}

$totalBytes = [int64](($expanded | Measure-Object bytes -Sum).Sum)
$estimatedTokens = [int][math]::Ceiling($totalBytes / [double]$BytesPerToken)
$budgetBytes = [int64]$defaultBudgets[$Agent]
$budgetTokens = [int][math]::Ceiling($budgetBytes / [double]$BytesPerToken)
if ($totalBytes -gt $budgetBytes) {
  $errors += [pscustomobject]@{
    code = 'BUDGET_EXCEEDED'
    message = "Context bytes $totalBytes > budget $budgetBytes for agent $Agent"
  }
}

$elapsed = [int]((Get-Date) - $started).TotalMilliseconds
$record = [pscustomobject]@{
  timestamp = (Get-Date).ToUniversalTime().ToString('o')
  runId = $RunId
  agent = $Agent
  specNumber = if ($SpecNumber -gt 0) { $SpecNumber } else { $null }
  usId = if ($UsId) { $UsId } else { $null }
  result = if ($errors.Count -eq 0) { 'pass' } else { 'fail' }
  files = $expanded.Count
  bytes = $totalBytes
  estimatedInputTokens = $estimatedTokens
  budgetBytes = $budgetBytes
  budgetTokens = $budgetTokens
  estimatedInputCostUsd = [math]::Round(($estimatedTokens / 1000000.0) * $InputUsdPerMillionTokens, 6)
  elapsedMs = $elapsed
  errors = $errors
  warnings = $warnings
}

$outDir = Split-Path -Parent $OutFile
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
($record | ConvertTo-Json -Depth 8 -Compress) | Add-Content -Path $OutFile -Encoding UTF8

if ($Json) {
  $record | ConvertTo-Json -Depth 8
} else {
  Write-Host ("context-budget {0}: {1} files, {2} bytes, ~{3} tokens / budget ~{4} tokens, USD {5}" -f $Agent, $expanded.Count, $totalBytes, $estimatedTokens, $budgetTokens, $record.estimatedInputCostUsd)
  if ($warnings.Count -gt 0) {
    $warnings | ForEach-Object { Write-Host ("WARN  {0}: {1}" -f $_.code, $_.pattern) -ForegroundColor Yellow }
  }
  if ($errors.Count -gt 0) {
    $errors | ForEach-Object { Write-Host ("ERROR {0}: {1}" -f $_.code, $_.message) -ForegroundColor Red }
  }
}

if ($errors.Count -gt 0) { exit 1 }
exit 0
