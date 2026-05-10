# validate-libs-catalog.ps1
# Valide tous les fichiers .claude/stacks/**/*.libs.json contre le schema
# .claude/templates/libs-catalog.schema.json + checks de coherence
# (versionRef pointe sur une cle existante, capability/triggers presents
# pour onDemand, etc.). Exit 0 si tout vert, 1 sinon.

param(
    [string] $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [switch] $Json
)

$ErrorActionPreference = 'Stop'
$catalogs = Get-ChildItem -Path (Join-Path $RepoRoot '.claude\stacks') -Filter '*.libs.json' -Recurse -File
$errors   = @()
$warnings = @()
$summary  = @()

foreach ($file in $catalogs) {
    $rel = $file.FullName.Substring($RepoRoot.Length + 1).Replace('\','/')
    try {
        $raw = Get-Content -Raw -Path $file.FullName -Encoding UTF8
        $cat = $raw | ConvertFrom-Json -ErrorAction Stop
    } catch {
        $errors += [pscustomobject]@{ File = $rel; Code = 'JSON_PARSE'; Message = $_.Exception.Message }
        continue
    }

    # Required top-level keys
    foreach ($key in @('stackId','category','schemaVersion','buildSystem','versions','core')) {
        if (-not ($cat.PSObject.Properties.Name -contains $key)) {
            $errors += [pscustomobject]@{ File = $rel; Code = 'MISSING_KEY'; Message = "missing top-level '$key'" }
        }
    }

    if (-not $cat.stackId) { continue }

    # stackId matches filename (without .libs.json)
    $expectedId = $file.BaseName -replace '\.libs$',''
    if ($cat.stackId -ne $expectedId) {
        $errors += [pscustomobject]@{ File = $rel; Code = 'STACK_ID_MISMATCH'; Message = "stackId='$($cat.stackId)' != filename '$expectedId'" }
    }

    # category matches parent dir name
    $expectedCat = Split-Path -Leaf $file.Directory
    if ($cat.category -ne $expectedCat) {
        $errors += [pscustomobject]@{ File = $rel; Code = 'CATEGORY_MISMATCH'; Message = "category='$($cat.category)' != parent dir '$expectedCat'" }
    }

    # schemaVersion = 1
    if ($cat.schemaVersion -ne 1) {
        $errors += [pscustomobject]@{ File = $rel; Code = 'SCHEMA_VERSION'; Message = "schemaVersion=$($cat.schemaVersion), expected 1" }
    }

    # buildSystem in enum
    $buildSystems = @('dotnet','npm','pnpm','yarn','gradle','maven','pip','poetry','uv','cargo','go-mod')
    if ($cat.buildSystem -notin $buildSystems) {
        $errors += [pscustomobject]@{ File = $rel; Code = 'BAD_BUILDSYSTEM'; Message = "buildSystem='$($cat.buildSystem)' not in [$($buildSystems -join ', ')]" }
    }

    # versions keys must match pattern
    $versionsKeys = @()
    if ($cat.versions) {
        foreach ($prop in $cat.versions.PSObject.Properties) {
            $versionsKeys += $prop.Name
            if ($prop.Name -notmatch '^[a-z][a-z0-9-]*$') {
                $errors += [pscustomobject]@{ File = $rel; Code = 'BAD_VERSION_KEY'; Message = "versions.$($prop.Name) not kebab-case" }
            }
            if ([string]::IsNullOrWhiteSpace($prop.Value)) {
                $errors += [pscustomobject]@{ File = $rel; Code = 'EMPTY_VERSION'; Message = "versions.$($prop.Name) is empty" }
            }
            if ($prop.Value -match '-(alpha|beta|rc|preview|snapshot)') {
                $warnings += [pscustomobject]@{ File = $rel; Code = 'PRERELEASE'; Message = "versions.$($prop.Name)='$($prop.Value)' is pre-release" }
            }
        }
    }

    # libraries: validate each
    $allLibs = @()
    if ($cat.core)     { $allLibs += $cat.core     | ForEach-Object { @{ Lib = $_; Section = 'core'     } } }
    if ($cat.onDemand) { $allLibs += $cat.onDemand | ForEach-Object { @{ Lib = $_; Section = 'onDemand' } } }

    foreach ($entry in $allLibs) {
        $lib = $entry.Lib
        $sec = $entry.Section
        # id optional in compact form — derive from module last segment for diagnostics
        $libId = if ($lib.id) { $lib.id } elseif ($lib.module) {
            if ($lib.module -match ':') { ($lib.module -split ':')[-1] }
            elseif ($lib.module -match '^@.+/(.+)$') { $Matches[1] }
            else { $lib.module }
        } else { '?' }
        $libRef = "$sec.$libId"

        if (-not $lib.module) { $errors += [pscustomobject]@{ File = $rel; Code = 'MISSING_MODULE'; Message = "$libRef missing module" } }

        # version | ref | versionRef — at most one
        $hasVer    = [bool]$lib.version
        $hasRef    = [bool]$lib.ref
        $hasVerRef = [bool]$lib.versionRef
        $refCount  = @($hasVer, $hasRef, $hasVerRef) | Where-Object { $_ } | Measure-Object | Select-Object -ExpandProperty Count
        if ($refCount -gt 1) {
            $errors += [pscustomobject]@{ File = $rel; Code = 'VERSION_BOTH'; Message = "$libRef has more than one of {version, ref, versionRef}" }
        }
        $refKey = if ($hasRef) { $lib.ref } elseif ($hasVerRef) { $lib.versionRef } else { $null }
        if ($refKey -and $refKey -notin $versionsKeys) {
            $errors += [pscustomobject]@{ File = $rel; Code = 'BAD_VERSIONREF'; Message = "$libRef ref='$refKey' not declared in versions{}" }
        }

        if ($sec -eq 'onDemand') {
            if (-not $lib.capability) {
                $errors += [pscustomobject]@{ File = $rel; Code = 'ONDEMAND_NO_CAP'; Message = "$libRef missing capability" }
            }
            if (-not $lib.triggers -or $lib.triggers.Count -eq 0) {
                $errors += [pscustomobject]@{ File = $rel; Code = 'ONDEMAND_NO_TRIGGERS'; Message = "$libRef missing triggers[]" }
            }
        }
    }

    # plugins: ref/versionRef must resolve
    if ($cat.plugins) {
        foreach ($p in $cat.plugins) {
            $pRef = if ($p.ref) { $p.ref } elseif ($p.versionRef) { $p.versionRef } else { $null }
            if ($pRef -and $pRef -notin $versionsKeys) {
                $errors += [pscustomobject]@{ File = $rel; Code = 'BAD_VERSIONREF'; Message = "plugins.$($p.id) ref='$pRef' not declared" }
            }
        }
    }

    # dbDrivers (backend only): module required, ref must resolve
    if ($cat.dbDrivers) {
        foreach ($prop in $cat.dbDrivers.PSObject.Properties) {
            $d = $prop.Value
            if (-not $d.module) {
                $errors += [pscustomobject]@{ File = $rel; Code = 'DRIVER_NO_MODULE'; Message = "dbDrivers.$($prop.Name) missing module" }
            }
            $dRef = if ($d.ref) { $d.ref } elseif ($d.versionRef) { $d.versionRef } else { $null }
            if ($dRef -and $dRef -notin $versionsKeys) {
                $errors += [pscustomobject]@{ File = $rel; Code = 'BAD_VERSIONREF'; Message = "dbDrivers.$($prop.Name) ref='$dRef' not declared" }
            }
        }
    }

    $coreCount     = if ($cat.core)     { @($cat.core).Count }     else { 0 }
    $onDemandCount = if ($cat.onDemand) { @($cat.onDemand).Count } else { 0 }
    $pluginCount   = if ($cat.plugins)  { @($cat.plugins).Count }  else { 0 }

    $summary += [pscustomobject]@{
        File          = $rel
        StackId       = $cat.stackId
        Category      = $cat.category
        BuildSystem   = $cat.buildSystem
        Versions      = $versionsKeys.Count
        Core          = $coreCount
        OnDemand      = $onDemandCount
        Plugins       = $pluginCount
    }
}

if ($Json) {
    @{
        catalogs = $summary
        errors   = $errors
        warnings = $warnings
        passed   = ($errors.Count -eq 0)
    } | ConvertTo-Json -Depth 6
} else {
    Write-Host ""
    Write-Host "Catalogs scanned : $($catalogs.Count)" -ForegroundColor Cyan
    foreach ($s in $summary) {
        Write-Host ("  [{0}] {1,-30} core={2,3} onDemand={3,2} plugins={4,2} versions={5,2}" -f $s.BuildSystem, $s.StackId, $s.Core, $s.OnDemand, $s.Plugins, $s.Versions)
    }
    Write-Host ""
    if ($warnings.Count -gt 0) {
        Write-Host "Warnings ($($warnings.Count)) :" -ForegroundColor Yellow
        $warnings | ForEach-Object { Write-Host ("  WARN  {0,-30} {1,-20} {2}" -f $_.File, $_.Code, $_.Message) -ForegroundColor Yellow }
        Write-Host ""
    }
    if ($errors.Count -gt 0) {
        Write-Host "Errors ($($errors.Count)) :" -ForegroundColor Red
        $errors | ForEach-Object { Write-Host ("  ERROR {0,-30} {1,-20} {2}" -f $_.File, $_.Code, $_.Message) -ForegroundColor Red }
        Write-Host ""
        Write-Host "FAIL" -ForegroundColor Red
        exit 1
    }
    Write-Host "OK" -ForegroundColor Green
}

if ($errors.Count -gt 0) { exit 1 } else { exit 0 }
