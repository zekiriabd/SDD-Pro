# sync-stack-md.ps1
# Régénère depuis le .libs.json compagnon les sections du .md balisées par
# des marqueurs HTML invisibles. Trois zones supportées :
#
#   1) Tableau §2.4 Librairies
#      Marqueurs : <!-- LIBS_CATALOG_START --> ... <!-- LIBS_CATALOG_END -->
#
#   2) Bloc bash des install commands core (ajouté 2026-05-08)
#      Marqueurs : <!-- CORE_PACKAGES_START --> ... <!-- CORE_PACKAGES_END -->
#      Contenu généré : 1 fenced bash block contenant les commandes
#      d'installation des libs core[] (1 par lib pour dotnet, groupées
#      pour npm/pnpm/uv/pip).
#
#   3) Bloc bash des install commands on-demand (ajouté 2026-05-08)
#      Marqueurs : <!-- ONDEMAND_PACKAGES_START --> ... <!-- ONDEMAND_PACKAGES_END -->
#      Contenu généré : 1 fenced bash block, groupé par capability,
#      avec les alternatives commentées en "OU".
#
# Les zones (2) et (3) sont optionnelles : si les marqueurs n'existent pas
# dans le .md, elles sont silencieusement ignorées (warning soft).

param(
    [Parameter(Mandatory)] [string] $StackId,
    [string] $RepoRoot,
    [switch] $DryRun
)

if (-not $RepoRoot) {
    $scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    if (-not $scriptRoot) { $scriptRoot = (Get-Location).Path }
    $RepoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..')).Path
}

$ErrorActionPreference = 'Stop'

$jsonPath = Get-ChildItem -Path (Join-Path $RepoRoot '.claude\stacks') -Recurse -Filter "$StackId.libs.json" |
            Select-Object -First 1
if (-not $jsonPath) { Write-Error "Catalog not found for stackId=$StackId"; exit 1 }

$mdPath = Join-Path $jsonPath.Directory.FullName "$StackId.md"
if (-not (Test-Path $mdPath)) { Write-Error "Companion .md not found: $mdPath"; exit 1 }

$cat = Get-Content -Raw -Path $jsonPath.FullName -Encoding UTF8 | ConvertFrom-Json

# --- Helpers ---

function Resolve-Version($lib, $catalog) {
    if ($lib.version)    { return $lib.version }
    $refKey = if ($lib.ref) { $lib.ref } elseif ($lib.versionRef) { $lib.versionRef } else { $null }
    if ($refKey -and $catalog.versions.$refKey) { return $catalog.versions.$refKey }
    return ''
}

function Resolve-LibId($lib) {
    if ($lib.id) { return $lib.id }
    $m = $lib.module
    if (-not $m) { return '?' }
    # Maven/Gradle 'group:artifact' -> id = artifact (last segment)
    if ($m -match ':') { return ($m -split ':')[-1] }
    # npm scoped '@scope/pkg' -> id = full '@scope/pkg' (preserve scope for clarity)
    # NuGet 'PackageName', PyPI 'package' -> id = module
    return $m
}

function Get-PrimaryProjectFile($catalog) {
    if ($catalog.manifest -and $catalog.manifest.files -and @($catalog.manifest.files).Count -gt 0) {
        return @($catalog.manifest.files)[0]
    }
    return $null
}

function Get-PrimaryProjectDir($catalog) {
    $f = Get-PrimaryProjectFile $catalog
    if (-not $f) { return $null }
    # Strip last "/filename"
    if ($f -match '^(.+)/[^/]+$') { return $Matches[1] }
    return $f
}

function Format-CorePackageLines($libs, $catalog) {
    $bs          = $catalog.buildSystem
    $projectFile = Get-PrimaryProjectFile $catalog
    $projectDir  = Get-PrimaryProjectDir  $catalog
    $lines       = @()

    if (-not $libs -or @($libs).Count -eq 0) {
        $lines += '# (aucune lib core declaree)'
        return $lines
    }

    switch ($bs) {
        'dotnet' {
            foreach ($lib in $libs) {
                $v = Resolve-Version $lib $catalog
                $line = "dotnet add $projectFile package $($lib.module)"
                if ($v) { $line += " --version $v" }
                $lines += $line
            }
        }
        { $_ -in @('npm','pnpm','yarn') } {
            $cmd = if ($bs -eq 'npm') { 'npm install' } else { "$bs add" }
            $items = @($libs | ForEach-Object {
                $v = Resolve-Version $_ $catalog
                if ($v) { "$($_.module)@$v" } else { $_.module }
            })
            $lines += "(cd $projectDir && $cmd \"
            for ($i = 0; $i -lt $items.Count; $i++) {
                $sep = if ($i -lt $items.Count - 1) { ' \' } else { ')' }
                $lines += "  $($items[$i])$sep"
            }
        }
        'uv' {
            $items = @($libs | ForEach-Object {
                $v = Resolve-Version $_ $catalog
                if ($v) { "$($_.module)==$v" } else { $_.module }
            })
            $lines += "uv add --project $projectDir \"
            for ($i = 0; $i -lt $items.Count; $i++) {
                $sep = if ($i -lt $items.Count - 1) { ' \' } else { '' }
                $lines += "  $($items[$i])$sep"
            }
        }
        'pip' {
            $items = @($libs | ForEach-Object {
                $v = Resolve-Version $_ $catalog
                if ($v) { "`"$($_.module)==$v`"" } else { "`"$($_.module)`"" }
            })
            $lines += "(cd $projectDir && pip install \"
            for ($i = 0; $i -lt $items.Count; $i++) {
                $sep = if ($i -lt $items.Count - 1) { ' \' } else { ')' }
                $lines += "  $($items[$i])$sep"
            }
        }
        'poetry' {
            $items = @($libs | ForEach-Object {
                $v = Resolve-Version $_ $catalog
                if ($v) { "$($_.module)@$v" } else { $_.module }
            })
            $lines += "(cd $projectDir && poetry add \"
            for ($i = 0; $i -lt $items.Count; $i++) {
                $sep = if ($i -lt $items.Count - 1) { ' \' } else { ')' }
                $lines += "  $($items[$i])$sep"
            }
        }
        'gradle' {
            $catalogPath = if ($catalog.manifest.versionCatalogPath) { $catalog.manifest.versionCatalogPath } else { 'gradle/libs.versions.toml' }
            $lines += "# Gradle managed via build.gradle.kts + $catalogPath."
            $lines += "# Versions auto-derivees de $($catalog.stackId).libs.json -- regenerer le catalog Gradle"
            $lines += "# en cas de bump (cf. gradle/libs.versions.toml)."
        }
        'maven' {
            $lines += "# Maven managed via pom.xml -- les versions vivent dans <properties> du pom."
            $lines += "# Sync depuis $($catalog.stackId).libs.json a faire manuellement (pas de CLI atomique)."
        }
        'cargo' {
            foreach ($lib in $libs) {
                $v = Resolve-Version $lib $catalog
                $line = "cargo add $($lib.module)"
                if ($v) { $line += " --vers $v" }
                $lines += $line
            }
        }
        'go-mod' {
            foreach ($lib in $libs) {
                $v = Resolve-Version $lib $catalog
                $line = "go get $($lib.module)"
                if ($v) { $line += "@v$v" }
                $lines += $line
            }
        }
        default {
            $lines += "# buildSystem '$bs' non supporte par sync-stack-md.ps1 -- regenerer manuellement."
        }
    }

    return $lines
}

function Format-OnDemandPackageLines($libs, $catalog) {
    $bs          = $catalog.buildSystem
    $projectFile = Get-PrimaryProjectFile $catalog
    $projectDir  = Get-PrimaryProjectDir  $catalog
    $lines       = @()

    if (-not $libs -or @($libs).Count -eq 0) {
        $lines += '# (aucune lib on-demand declaree)'
        return $lines
    }

    # Group by capability
    $groups = $libs | Group-Object -Property capability

    foreach ($g in $groups) {
        if ($lines.Count -gt 0) { $lines += '' }
        $lines += "# capability: $($g.Name)"

        $primary = @($g.Group | Where-Object { -not $_.alternative })
        $alt     = @($g.Group | Where-Object { $_.alternative })

        switch ($bs) {
            'dotnet' {
                foreach ($lib in $primary) {
                    $v = Resolve-Version $lib $catalog
                    $line = "dotnet add $projectFile package $($lib.module)"
                    if ($v) { $line += " --version $v" }
                    $lines += $line
                }
                foreach ($a in $alt) {
                    $av = Resolve-Version $a $catalog
                    $cmt = "# OU (alt mutuellement exclusif) : dotnet add $projectFile package $($a.module)"
                    if ($av) { $cmt += " --version $av" }
                    $lines += $cmt
                }
            }
            { $_ -in @('npm','pnpm','yarn') } {
                $cmd = if ($bs -eq 'npm') { 'npm install' } else { "$bs add" }
                if ($primary.Count -gt 0) {
                    $items = @($primary | ForEach-Object {
                        $v = Resolve-Version $_ $catalog
                        if ($v) { "$($_.module)@$v" } else { $_.module }
                    })
                    $lines += "(cd $projectDir && $cmd $($items -join ' '))"
                }
                foreach ($a in $alt) {
                    $av = Resolve-Version $a $catalog
                    $token = if ($av) { "$($a.module)@$av" } else { $a.module }
                    $lines += "# OU (alt) : (cd $projectDir && $cmd $token)"
                }
            }
            'uv' {
                if ($primary.Count -gt 0) {
                    $items = @($primary | ForEach-Object {
                        $v = Resolve-Version $_ $catalog
                        if ($v) { "$($_.module)==$v" } else { $_.module }
                    })
                    $lines += "uv add --project $projectDir $($items -join ' ')"
                }
                foreach ($a in $alt) {
                    $av = Resolve-Version $a $catalog
                    $token = if ($av) { "$($a.module)==$av" } else { $a.module }
                    $lines += "# OU (alt) : uv add --project $projectDir $token"
                }
            }
            'pip' {
                if ($primary.Count -gt 0) {
                    $items = @($primary | ForEach-Object {
                        $v = Resolve-Version $_ $catalog
                        if ($v) { "`"$($_.module)==$v`"" } else { "`"$($_.module)`"" }
                    })
                    $lines += "(cd $projectDir && pip install $($items -join ' '))"
                }
                foreach ($a in $alt) {
                    $av = Resolve-Version $a $catalog
                    $token = if ($av) { "`"$($a.module)==$av`"" } else { "`"$($a.module)`"" }
                    $lines += "# OU (alt) : (cd $projectDir && pip install $token)"
                }
            }
            'poetry' {
                if ($primary.Count -gt 0) {
                    $items = @($primary | ForEach-Object {
                        $v = Resolve-Version $_ $catalog
                        if ($v) { "$($_.module)@$v" } else { $_.module }
                    })
                    $lines += "(cd $projectDir && poetry add $($items -join ' '))"
                }
                foreach ($a in $alt) {
                    $av = Resolve-Version $a $catalog
                    $token = if ($av) { "$($a.module)@$av" } else { $a.module }
                    $lines += "# OU (alt) : (cd $projectDir && poetry add $token)"
                }
            }
            'gradle' {
                $lines += "# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts"
                foreach ($lib in $primary) {
                    $lines += "#   implementation(`"$($lib.module):$(Resolve-Version $lib $catalog)`")"
                }
                foreach ($a in $alt) {
                    $lines += "#   OU (alt) implementation(`"$($a.module):$(Resolve-Version $a $catalog)`")"
                }
            }
            default {
                foreach ($lib in $primary) {
                    $lines += "# $bs : install $($lib.module) (version $(Resolve-Version $lib $catalog))"
                }
                foreach ($a in $alt) {
                    $lines += "# $bs : OU (alt) install $($a.module) (version $(Resolve-Version $a $catalog))"
                }
            }
        }
    }

    return $lines
}

function Build-FencedBlock($comment, $lines) {
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine('```bash')
    [void]$sb.AppendLine("# $comment")
    foreach ($l in $lines) { [void]$sb.AppendLine($l) }
    [void]$sb.Append('```')
    return $sb.ToString()
}

function Replace-MarkedSection($md, $startMarker, $endMarker, $newContent) {
    if (-not ($md -match [regex]::Escape($startMarker))) { return $md }
    if (-not ($md -match [regex]::Escape($endMarker)))   { return $md }
    $pattern = "(?s)$([regex]::Escape($startMarker)).*?$([regex]::Escape($endMarker))"
    $replacement = "$startMarker`r`n$newContent`r`n$endMarker"
    return [regex]::Replace($md, $pattern, $replacement)
}

# --- Build §2.4 Librairies markdown section ---

$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine("### 2.4 Librairies")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("> Source de verite : ``.claude/stacks/$($cat.category)/$StackId.libs.json``. Ne pas editer cette section manuellement -- utiliser ``.claude/scripts/sync-stack-md.ps1 -StackId $StackId``.")
[void]$sb.AppendLine("")

[void]$sb.AppendLine("#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("| Lib | Version | Role |")
[void]$sb.AppendLine("|-----|---------|------|")
foreach ($lib in $cat.core) {
    $v = Resolve-Version $lib $cat
    $id = Resolve-LibId $lib
    $r  = if ($lib.rationale) { $lib.rationale } else { '' }
    [void]$sb.AppendLine("| $id | $v | $r |")
}
[void]$sb.AppendLine("")

if ($cat.onDemand -and $cat.onDemand.Count -gt 0) {
    [void]$sb.AppendLine("### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("Triggers (regex case-insensitive) cherches par ``detect-capabilities.ps1`` dans l'US + ACs.")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("| Capability | Lib | Version | Triggers |")
    [void]$sb.AppendLine("|---|---|---|---|")
    foreach ($lib in $cat.onDemand) {
        $v = Resolve-Version $lib $cat
        $id = Resolve-LibId $lib
        $alt = if ($lib.alternative) { ' (alt)' } else { '' }
        $triggers = ($lib.triggers -join ', ')
        [void]$sb.AppendLine("| $($lib.capability) | $id$alt | $v | $triggers |")
    }
    [void]$sb.AppendLine("")
}

if ($cat.plugins -and $cat.plugins.Count -gt 0) {
    [void]$sb.AppendLine("#### 2.4.c Plugins build-system")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("| Plugin | Version | Role |")
    [void]$sb.AppendLine("|---|---|---|")
    foreach ($p in $cat.plugins) {
        $v = Resolve-Version $p $cat
        $r = if ($p.rationale) { $p.rationale } else { '' }
        [void]$sb.AppendLine("| $($p.id) | $v | $r |")
    }
    [void]$sb.AppendLine("")
}

if ($cat.dbDrivers -and $cat.dbDrivers.PSObject.Properties.Count -gt 0) {
    [void]$sb.AppendLine("#### 2.4.d DB Drivers (selectionne par arch selon DatabaseType)")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("| DatabaseType | Module | Version | Scope |")
    [void]$sb.AppendLine("|---|---|---|---|")
    foreach ($k in $cat.dbDrivers.PSObject.Properties.Name) {
        $d = $cat.dbDrivers.$k
        $v = Resolve-Version $d $cat
        $scope = if ($d.scope) { $d.scope } else { 'runtime' }
        [void]$sb.AppendLine("| $k | ``$($d.module)`` | $v | $scope |")
    }
    [void]$sb.AppendLine("")
}

$generatedTable = $sb.ToString().TrimEnd()

# --- Build CORE_PACKAGES + ONDEMAND_PACKAGES blocks ---

$coreLines     = Format-CorePackageLines      $cat.core     $cat
$onDemandLines = Format-OnDemandPackageLines  $cat.onDemand $cat

$coreBlock     = Build-FencedBlock "Auto-genere depuis $StackId.libs.json -- ne pas editer (utiliser sync-stack-md.ps1)." $coreLines
$onDemandBlock = Build-FencedBlock "Auto-genere depuis $StackId.libs.json (on-demand) -- installe par dev-* si l'US declenche un trigger." $onDemandLines

# --- Inject into .md ---

$md = Get-Content -Raw -Path $mdPath -Encoding UTF8

# Zone 1 : §2.4 (existing behavior, fallback if marker missing)
$startLibs = '<!-- LIBS_CATALOG_START -->'
$endLibs   = '<!-- LIBS_CATALOG_END -->'
if ($md -match [regex]::Escape($startLibs) -and $md -match [regex]::Escape($endLibs)) {
    $md = Replace-MarkedSection $md $startLibs $endLibs $generatedTable
} else {
    $pattern = "(?ms)^#{2,3} 2\.4 Librairies.*?(?=^#{1,3} )"
    if ($md -match $pattern) {
        $md = [regex]::Replace($md, $pattern, "$startLibs`r`n$generatedTable`r`n$endLibs`r`n`r`n")
    } else {
        Write-Error "Cannot find '## 2.4 Librairies' or '### 2.4 Librairies' section in $mdPath. Insert <!-- LIBS_CATALOG_START --> / <!-- LIBS_CATALOG_END --> markers manually."
        exit 1
    }
}

# Zone 2 : CORE_PACKAGES (optional — soft skip if absent)
$coreInjected = $false
if ($md -match '<!-- CORE_PACKAGES_START -->') {
    $md = Replace-MarkedSection $md '<!-- CORE_PACKAGES_START -->' '<!-- CORE_PACKAGES_END -->' $coreBlock
    $coreInjected = $true
}

# Zone 3 : ONDEMAND_PACKAGES (optional — soft skip if absent)
$onDemandInjected = $false
if ($md -match '<!-- ONDEMAND_PACKAGES_START -->') {
    $md = Replace-MarkedSection $md '<!-- ONDEMAND_PACKAGES_START -->' '<!-- ONDEMAND_PACKAGES_END -->' $onDemandBlock
    $onDemandInjected = $true
}

if ($DryRun) {
    Write-Host "=== DRY RUN -- generated for $StackId ===" -ForegroundColor Cyan
    Write-Host "[Zone 1: 2.4 table]" -ForegroundColor Yellow
    Write-Host $generatedTable
    Write-Host ""
    Write-Host "[Zone 2: CORE_PACKAGES] (markers present: $coreInjected)" -ForegroundColor Yellow
    Write-Host $coreBlock
    Write-Host ""
    Write-Host "[Zone 3: ONDEMAND_PACKAGES] (markers present: $onDemandInjected)" -ForegroundColor Yellow
    Write-Host $onDemandBlock
} else {
    Set-Content -Path $mdPath -Value $md -Encoding UTF8 -NoNewline
    $coreN     = if ($cat.core)     { @($cat.core).Count }     else { 0 }
    $onDemandN = if ($cat.onDemand) { @($cat.onDemand).Count } else { 0 }
    $pluginsN  = if ($cat.plugins)  { @($cat.plugins).Count }  else { 0 }
    $driversN  = if ($cat.dbDrivers) { @($cat.dbDrivers.PSObject.Properties).Count } else { 0 }
    $zoneFlags = @()
    if ($coreInjected)     { $zoneFlags += 'core-pkg' }
    if ($onDemandInjected) { $zoneFlags += 'ondemand-pkg' }
    $zonesStr = if ($zoneFlags.Count -gt 0) { ", zones=[2.4-table, $($zoneFlags -join ', ')]" } else { ', zones=[2.4-table]' }
    Write-Host ("OK {0}.md synced from {0}.libs.json [core={1}, onDemand={2}, plugins={3}, dbDrivers={4}]{5}" -f $StackId, $coreN, $onDemandN, $pluginsN, $driversN, $zonesStr)
}
