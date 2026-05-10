# =============================================================================
# SDD_Pro v3.1.0 - Parse coverage outputs vers schema normalise
# =============================================================================
# Usage : pwsh .claude/scripts/parse-coverage.ps1 -SpecNumber {n}
#
# Parse les outputs natifs (cobertura XML, lcov.info, coverage.xml JaCoCo,
# coverage.json c8, etc.) et produit workspace/output/qa/feat-{n}/coverage.json au
# schema normalise defini dans rules/qa-coverage.md sec 2.
#
# Exit 0 = parse OK, exit 1 = aucun fichier coverage trouve, exit 2 = parse error.
# Aucun token consomme - tout est PowerShell pur.
# ASCII-safe pour PowerShell 5.1.
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [int]$SpecNumber,

    [int]$CoverageMin = 80
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Get-Location).Path
$SrcDir      = Join-Path $ProjectRoot 'workspace/output/src'
$QaDir       = Join-Path $ProjectRoot "workspace/output/qa/feat-$SpecNumber"
$StackPath   = Join-Path $ProjectRoot 'workspace/input/stack/stack.md'
$SpecsDir    = Join-Path $ProjectRoot 'workspace/input/specs'

if (-not (Test-Path $QaDir)) { New-Item -ItemType Directory -Path $QaDir -Force | Out-Null }

# Localiser SPEC name
$specName = $null
if (Test-Path $SpecsDir) {
    $specFile = Get-ChildItem -Path $SpecsDir -Filter "$SpecNumber-*.md" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($specFile -and $specFile.BaseName -match "^$SpecNumber-(.+)$") {
        $specName = $Matches[1]
    }
}

# Lire CoverageMin depuis stack.md si present
if (Test-Path $StackPath) {
    $stackContent = Get-Content $StackPath -Raw -Encoding UTF8
    if ($stackContent -match '(?ms)CoverageMin\s*:\s*(\d+)') {
        $CoverageMin = [int]$Matches[1]
    }
}

# -----------------------------------------------------------------------------
# Parsers par format
# -----------------------------------------------------------------------------

function Parse-CoberturaXml {
    param([string]$path, [string]$stackId, [string]$tool)

    [xml]$xml = Get-Content $path -Raw -Encoding UTF8
    $covered = 0; $total = 0; $bcovered = 0; $btotal = 0
    $files = @()

    if ($xml.coverage) {
        $linesCovered = [int]($xml.coverage.'lines-covered' -as [int])
        $linesValid   = [int]($xml.coverage.'lines-valid' -as [int])
        $branchCovered = [int]($xml.coverage.'branches-covered' -as [int])
        $branchValid   = [int]($xml.coverage.'branches-valid' -as [int])

        if ($linesValid -gt 0) {
            $covered = $linesCovered
            $total = $linesValid
        }
        if ($branchValid -gt 0) {
            $bcovered = $branchCovered
            $btotal = $branchValid
        }

        # Files detail (optionnel)
        if ($xml.coverage.packages.package) {
            foreach ($pkg in $xml.coverage.packages.package) {
                if ($pkg.classes.class) {
                    foreach ($cls in $pkg.classes.class) {
                        $clsName = $cls.filename
                        if ($clsName) {
                            $clsLineRate = [double]$cls.'line-rate'
                            $files += [pscustomobject]@{
                                path = $clsName
                                lines_pct = [math]::Round($clsLineRate * 100, 2)
                            }
                        }
                    }
                }
            }
        }
    }

    return @{
        covered = $covered
        total = $total
        bcovered = $bcovered
        btotal = $btotal
        files = $files
    }
}

function Parse-LcovInfo {
    param([string]$path)

    $lines = Get-Content $path -Encoding UTF8
    $covered = 0; $total = 0
    $files = @()
    $currentFile = $null
    $fileLF = 0
    $fileLH = 0

    foreach ($line in $lines) {
        if ($line -match '^SF:(.+)$') {
            $currentFile = $Matches[1].Trim()
            $fileLF = 0
            $fileLH = 0
        } elseif ($line -match '^LF:(\d+)$') {
            $fileLF = [int]$Matches[1]
        } elseif ($line -match '^LH:(\d+)$') {
            $fileLH = [int]$Matches[1]
        } elseif ($line -match '^end_of_record') {
            if ($currentFile -and $fileLF -gt 0) {
                $covered += $fileLH
                $total += $fileLF
                $files += [pscustomobject]@{
                    path = $currentFile
                    lines_pct = [math]::Round(($fileLH / $fileLF) * 100, 2)
                }
            }
        }
    }

    return @{
        covered = $covered
        total = $total
        bcovered = 0
        btotal = 0
        files = $files
    }
}

function Parse-JaCoCoXml {
    param([string]$path)

    [xml]$xml = Get-Content $path -Raw -Encoding UTF8
    $covered = 0; $total = 0; $bcovered = 0; $btotal = 0
    $files = @()

    if ($xml.report) {
        # JaCoCo : counter type="LINE" missed/covered au top level
        foreach ($counter in $xml.report.counter) {
            $type = $counter.type
            $missed = [int]$counter.missed
            $cov = [int]$counter.covered
            if ($type -eq 'LINE') {
                $covered = $cov
                $total = $missed + $cov
            } elseif ($type -eq 'BRANCH') {
                $bcovered = $cov
                $btotal = $missed + $cov
            }
        }

        # Files (sourcefile)
        foreach ($pkg in $xml.report.package) {
            foreach ($sf in $pkg.sourcefile) {
                $sfName = $sf.name
                $sfLine = $sf.counter | Where-Object { $_.type -eq 'LINE' } | Select-Object -First 1
                if ($sfName -and $sfLine) {
                    $sfMissed = [int]$sfLine.missed
                    $sfCov = [int]$sfLine.covered
                    $sfTotal = $sfMissed + $sfCov
                    if ($sfTotal -gt 0) {
                        $files += [pscustomobject]@{
                            path = "$($pkg.name)/$sfName"
                            lines_pct = [math]::Round(($sfCov / $sfTotal) * 100, 2)
                        }
                    }
                }
            }
        }
    }

    return @{
        covered = $covered
        total = $total
        bcovered = $bcovered
        btotal = $btotal
        files = $files
    }
}

function Parse-IstanbulJson {
    param([string]$path)

    $json = Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json
    $covered = 0; $total = 0
    $files = @()

    if ($json.total -and $json.total.lines) {
        $covered = [int]$json.total.lines.covered
        $total = [int]$json.total.lines.total
    }

    foreach ($prop in $json.PSObject.Properties) {
        if ($prop.Name -eq 'total') { continue }
        $fileObj = $prop.Value
        if ($fileObj.lines) {
            $fc = [int]$fileObj.lines.covered
            $ft = [int]$fileObj.lines.total
            if ($ft -gt 0) {
                $files += [pscustomobject]@{
                    path = $prop.Name
                    lines_pct = [math]::Round(($fc / $ft) * 100, 2)
                }
            }
        }
    }

    return @{
        covered = $covered
        total = $total
        bcovered = 0
        btotal = 0
        files = $files
    }
}

# -----------------------------------------------------------------------------
# Detection des fichiers coverage par format
# -----------------------------------------------------------------------------

$stacksFound = @()

# 1. Cobertura XML (.NET coverlet, Python coverage.py XML, JS various)
if (Test-Path $SrcDir) {
    $coberturaFiles = Get-ChildItem -Path $SrcDir -Recurse -Filter 'coverage.cobertura.xml' -File -ErrorAction SilentlyContinue
    foreach ($f in $coberturaFiles) {
        try {
            $r = Parse-CoberturaXml -path $f.FullName -stackId 'cobertura' -tool 'coverlet-or-coverage.py'

            # Determiner stack par chemin
            $stackId = if ($f.FullName -match '\.Tests') { 'qa-dotnet-xunit' } else { 'qa-cobertura' }
            $tool = if ($stackId -eq 'qa-dotnet-xunit') { 'coverlet' } else { 'cobertura' }

            $stacksFound += [pscustomobject]@{
                stack = $stackId
                tool = $tool
                toolVersion = ''
                tests = [pscustomobject]@{ total = 0; passed = 0; failed = 0; skipped = 0 }
                coverage = [pscustomobject]@{
                    lines = [pscustomobject]@{
                        covered = $r.covered
                        total = $r.total
                        percent = if ($r.total -gt 0) { [math]::Round(($r.covered / $r.total) * 100, 2) } else { 0.0 }
                    }
                    branches = if ($r.btotal -gt 0) {
                        [pscustomobject]@{
                            covered = $r.bcovered
                            total = $r.btotal
                            percent = [math]::Round(($r.bcovered / $r.btotal) * 100, 2)
                        }
                    } else { $null }
                }
                files = $r.files
            }
        } catch {
            Write-Warning "Parse cobertura failed for $($f.FullName): $_"
        }
    }

    # 2. lcov.info (Vitest/c8/Jest/Karma istanbul)
    $lcovFiles = Get-ChildItem -Path $SrcDir -Recurse -Filter 'lcov.info' -File -ErrorAction SilentlyContinue
    foreach ($f in $lcovFiles) {
        try {
            $r = Parse-LcovInfo -path $f.FullName
            $stackId = if ($f.FullName -match 'angular|karma') { 'qa-angular-jasmine' } else { 'qa-node-vitest' }
            $tool = if ($stackId -eq 'qa-angular-jasmine') { 'istanbul' } else { 'c8' }

            $stacksFound += [pscustomobject]@{
                stack = $stackId
                tool = $tool
                toolVersion = ''
                tests = [pscustomobject]@{ total = 0; passed = 0; failed = 0; skipped = 0 }
                coverage = [pscustomobject]@{
                    lines = [pscustomobject]@{
                        covered = $r.covered
                        total = $r.total
                        percent = if ($r.total -gt 0) { [math]::Round(($r.covered / $r.total) * 100, 2) } else { 0.0 }
                    }
                    branches = $null
                }
                files = $r.files
            }
        } catch {
            Write-Warning "Parse lcov failed for $($f.FullName): $_"
        }
    }

    # 3. JaCoCo XML (Kotlin/Java)
    $jacocoFiles = Get-ChildItem -Path $SrcDir -Recurse -Filter 'jacocoTestReport.xml' -File -ErrorAction SilentlyContinue
    $jacocoFiles += Get-ChildItem -Path $SrcDir -Recurse -Filter 'jacoco.xml' -File -ErrorAction SilentlyContinue
    foreach ($f in $jacocoFiles) {
        try {
            $r = Parse-JaCoCoXml -path $f.FullName

            $stacksFound += [pscustomobject]@{
                stack = 'qa-kotlin-junit'
                tool = 'JaCoCo'
                toolVersion = ''
                tests = [pscustomobject]@{ total = 0; passed = 0; failed = 0; skipped = 0 }
                coverage = [pscustomobject]@{
                    lines = [pscustomobject]@{
                        covered = $r.covered
                        total = $r.total
                        percent = if ($r.total -gt 0) { [math]::Round(($r.covered / $r.total) * 100, 2) } else { 0.0 }
                    }
                    branches = if ($r.btotal -gt 0) {
                        [pscustomobject]@{
                            covered = $r.bcovered
                            total = $r.btotal
                            percent = [math]::Round(($r.bcovered / $r.btotal) * 100, 2)
                        }
                    } else { $null }
                }
                files = $r.files
            }
        } catch {
            Write-Warning "Parse JaCoCo failed for $($f.FullName): $_"
        }
    }

    # 4. coverage-summary.json (istanbul Angular/Karma)
    $istanbulFiles = Get-ChildItem -Path $SrcDir -Recurse -Filter 'coverage-summary.json' -File -ErrorAction SilentlyContinue
    foreach ($f in $istanbulFiles) {
        try {
            $r = Parse-IstanbulJson -path $f.FullName

            $stacksFound += [pscustomobject]@{
                stack = 'qa-angular-jasmine'
                tool = 'istanbul'
                toolVersion = ''
                tests = [pscustomobject]@{ total = 0; passed = 0; failed = 0; skipped = 0 }
                coverage = [pscustomobject]@{
                    lines = [pscustomobject]@{
                        covered = $r.covered
                        total = $r.total
                        percent = if ($r.total -gt 0) { [math]::Round(($r.covered / $r.total) * 100, 2) } else { 0.0 }
                    }
                    branches = $null
                }
                files = $r.files
            }
        } catch {
            Write-Warning "Parse istanbul failed for $($f.FullName): $_"
        }
    }
}

if ($stacksFound.Count -eq 0) {
    Write-Output "No coverage files found under $SrcDir (recursive)."
    Write-Output "Looked for: coverage.cobertura.xml, lcov.info, jacocoTestReport.xml, coverage-summary.json"
    exit 1
}

# -----------------------------------------------------------------------------
# Calcul summary (moyenne ponderee par LOC totales)
# -----------------------------------------------------------------------------

$totalCovered = ($stacksFound | ForEach-Object { $_.coverage.lines.covered } | Measure-Object -Sum).Sum
$totalTotal   = ($stacksFound | ForEach-Object { $_.coverage.lines.total }   | Measure-Object -Sum).Sum
$totalTests   = ($stacksFound | ForEach-Object { $_.tests.total }   | Measure-Object -Sum).Sum
$totalPassed  = ($stacksFound | ForEach-Object { $_.tests.passed }  | Measure-Object -Sum).Sum
$totalFailed  = ($stacksFound | ForEach-Object { $_.tests.failed }  | Measure-Object -Sum).Sum
$totalSkipped = ($stacksFound | ForEach-Object { $_.tests.skipped } | Measure-Object -Sum).Sum

$globalPct = if ($totalTotal -gt 0) { [math]::Round(($totalCovered / $totalTotal) * 100, 2) } else { 0.0 }
$passed = ($globalPct -ge $CoverageMin)

# -----------------------------------------------------------------------------
# Construire JSON et ecrire (atomique)
# -----------------------------------------------------------------------------

$specLabel = if ($specName) { "$SpecNumber-$specName" } else { "$SpecNumber" }

$result = [ordered]@{
    spec        = $specLabel
    extractedAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    stacks      = $stacksFound
    summary     = [ordered]@{
        total_tests          = $totalTests
        passed               = $totalPassed
        failed               = $totalFailed
        skipped              = $totalSkipped
        coverage_lines_pct   = $globalPct
        coverage_min         = $CoverageMin
        coverage_passed      = $passed
    }
}

$outPath = Join-Path $QaDir 'coverage.json'
$tmpPath = "$outPath.tmp"

$result | ConvertTo-Json -Depth 10 | Out-File -FilePath $tmpPath -Encoding UTF8 -Force
Move-Item -Path $tmpPath -Destination $outPath -Force

Write-Output "Coverage parsed: $globalPct% (min: $CoverageMin%) passed=$passed"
Write-Output "Stacks: $($stacksFound.Count)"
Write-Output "Output: $outPath"

exit 0
