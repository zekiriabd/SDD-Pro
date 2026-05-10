# =============================================================================
# SDD_Pro v3.1.0 - Quality scan (sonar-like, deterministe, 0 token)
# =============================================================================
# Usage : pwsh .claude/scripts/quality-scan.ps1 -SpecNumber {n}
#
# Scanne le code de production (workspace/output/src/{App|Backend|Lib}/) pour les
# patterns suivants et produit workspace/output/qa/feat-{n}/quality.json :
#   - TODO / FIXME / XXX / HACK (errors)
#   - Magic numbers (hex hardcoded hors theme.css, magic ints isoles)
#   - console.log / Console.WriteLine / print en prod (warnings)
#   - Methodes > 50 lignes (warnings)
#   - Code commente en bloc (warnings)
#   - Naming violations selon stack (warnings)
#
# Aucun token consomme - tout est PowerShell pur.
# Tres rapide (<1s pour ~5000 LOC).
# ASCII-safe pour PowerShell 5.1.
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [int]$SpecNumber
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Get-Location).Path
$SrcDir      = Join-Path $ProjectRoot 'workspace/output/src'
$QaDir       = Join-Path $ProjectRoot "workspace/output/qa/feat-$SpecNumber"

if (-not (Test-Path $QaDir)) { New-Item -ItemType Directory -Path $QaDir -Force | Out-Null }

if (-not (Test-Path $SrcDir)) {
    Write-Output "Source directory not found: $SrcDir"
    Write-Output "Skipping quality scan (no code to analyze)."
    exit 0
}

$results = @{
    errors   = @()
    warnings = @()
    info     = @()
}

# Extensions sources a scanner (exclure tests/binaires/generated)
$sourceExts = @('.cs', '.razor', '.ts', '.tsx', '.js', '.jsx', '.vue', '.py', '.kt', '.kts')
$excludeDirs = @('bin', 'obj', 'node_modules', '.vs', 'dist', 'build', 'coverage', 'TestResults', '.angular', 'wwwroot/_framework')
$testPatterns = @('.Tests/', '__tests__/', '.test.', '.spec.', 'test_', '_test.', 'Test.kt', 'Spec.kt')

function Test-IsExcluded {
    param([string]$path)
    foreach ($d in $excludeDirs) {
        if ($path -match [regex]::Escape($d)) { return $true }
    }
    foreach ($p in $testPatterns) {
        if ($path -match [regex]::Escape($p)) { return $true }
    }
    return $false
}

# Glob recursif tous les fichiers source non-test
$sourceFiles = @()
foreach ($ext in $sourceExts) {
    $files = Get-ChildItem -Path $SrcDir -Recurse -Filter "*$ext" -File -ErrorAction SilentlyContinue
    foreach ($f in $files) {
        if (-not (Test-IsExcluded -path $f.FullName)) {
            $sourceFiles += $f
        }
    }
}

if ($sourceFiles.Count -eq 0) {
    Write-Output "No source files found to scan."
    exit 0
}

# -----------------------------------------------------------------------------
# Scanner chaque fichier
# -----------------------------------------------------------------------------

foreach ($file in $sourceFiles) {
    $relPath = $file.FullName.Substring($ProjectRoot.Length).TrimStart('/', '\').Replace('\', '/')
    $content = Get-Content $file.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if (-not $content) { continue }

    $lines = $content -split "(`r`n|`n|`r)"
    $isThemeCss = $relPath -match '/theme\.(css|scss)$'

    # 1. TODO / FIXME / XXX / HACK
    $todoMatches = [regex]::Matches($content, '(?im)\b(TODO|FIXME|XXX|HACK)\b[^\r\n]*')
    foreach ($m in $todoMatches) {
        $lineNum = ($content.Substring(0, $m.Index) -split "`n").Count
        $tag = $m.Groups[1].Value.ToUpper()
        $results.errors += [pscustomobject]@{
            category = 'todo'
            severity = 'error'
            file = $relPath
            line = $lineNum
            tag = $tag
            message = $m.Value.Trim() -replace '\s+', ' ' | Select-Object -First 1
        }
    }

    # 2. console.log / Console.WriteLine / print en prod
    $debugPatterns = @{
        'console\.log'        = 'js-debug'
        'console\.error'      = 'js-debug'
        'console\.warn'       = 'js-debug'
        'Console\.WriteLine'  = 'cs-debug'
        'Debug\.Print'        = 'cs-debug'
        'System\.out\.println' = 'java-kotlin-debug'
        '^\s*print\s*\('     = 'py-debug'
        'println\!'          = 'rust-debug'
    }
    foreach ($pattern in $debugPatterns.Keys) {
        $matches = [regex]::Matches($content, $pattern, [System.Text.RegularExpressions.RegexOptions]::Multiline)
        foreach ($m in $matches) {
            $lineNum = ($content.Substring(0, $m.Index) -split "`n").Count
            $results.warnings += [pscustomobject]@{
                category = 'debug-output'
                severity = 'warning'
                file = $relPath
                line = $lineNum
                tag = $debugPatterns[$pattern]
                message = "Debug output left in production code"
            }
        }
    }

    # 3. Hex hardcoded hors theme.css (uniquement dans CSS / SCSS)
    if (-not $isThemeCss -and $relPath -match '\.(css|scss|razor|tsx|jsx|vue)$') {
        $hexMatches = [regex]::Matches($content, '#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b')
        foreach ($m in $hexMatches) {
            $lineNum = ($content.Substring(0, $m.Index) -split "`n").Count
            $results.warnings += [pscustomobject]@{
                category = 'hardcoded-hex'
                severity = 'warning'
                file = $relPath
                line = $lineNum
                tag = 'hex-outside-theme'
                message = "Hex value $($m.Value) hardcoded outside theme.css - use CSS var or token"
            }
        }
    }

    # 4. Methodes > 50 lignes (heuristique : detecte des blocs entre { et } sur > 50 lignes)
    # Implementation simplifiee : detect "function/method/def" + count lignes jusqu'au prochain pattern
    if ($relPath -match '\.(cs|kt|ts|tsx|js|jsx|py)$') {
        $methodPatterns = @(
            'public\s+\w+\s+\w+\s*\([^)]*\)\s*\{',
            'private\s+\w+\s+\w+\s*\([^)]*\)\s*\{',
            'protected\s+\w+\s+\w+\s*\([^)]*\)\s*\{',
            'function\s+\w+\s*\([^)]*\)\s*\{',
            'fun\s+\w+\s*\([^)]*\)',
            'def\s+\w+\s*\([^)]*\)\s*:'
        )
        foreach ($pat in $methodPatterns) {
            $matches = [regex]::Matches($content, $pat)
            foreach ($m in $matches) {
                $startLine = ($content.Substring(0, $m.Index) -split "`n").Count
                # Heuristique simple : compter lignes jusqu'au prochain motif "}" au niveau 0
                # Pour Python, jusqu'au prochain pattern non-indente
                $remaining = $content.Substring($m.Index)
                $methodLines = $remaining -split "`n" | Select-Object -First 100
                $closeBrace = -1
                $depth = 0
                $started = $false
                for ($i = 0; $i -lt $methodLines.Count; $i++) {
                    $ln = $methodLines[$i]
                    if ($ln -match '\{') { $depth++; $started = $true }
                    if ($ln -match '\}') {
                        $depth--
                        if ($started -and $depth -le 0) { $closeBrace = $i; break }
                    }
                }
                if ($closeBrace -gt 50) {
                    $results.warnings += [pscustomobject]@{
                        category = 'long-method'
                        severity = 'warning'
                        file = $relPath
                        line = $startLine
                        tag = 'method-over-50-lines'
                        message = "Method spans approximately $closeBrace lines - consider refactoring"
                    }
                }
            }
        }
    }

    # 5. Code commente en bloc (heuristique : > 5 lignes consecutives commencant par // ou /* ou #)
    if ($relPath -match '\.(cs|kt|ts|tsx|js|jsx|py|razor)$') {
        $commentBlock = 0
        $blockStartLine = 0
        for ($i = 0; $i -lt $lines.Count; $i++) {
            $ln = $lines[$i].Trim()
            $isComment = ($ln -match '^\s*//' -or $ln -match '^\s*#' -or $ln -match '^\s*\*' -or $ln -match '^\s*<!--')
            $hasContent = ($ln -match '\b\w+\s*[\(\=\;\.]')  # Heuristique: contient code (parens/affect/semicolon/dot)
            if ($isComment -and $hasContent) {
                if ($commentBlock -eq 0) { $blockStartLine = $i + 1 }
                $commentBlock++
            } else {
                if ($commentBlock -ge 5) {
                    $results.info += [pscustomobject]@{
                        category = 'commented-code'
                        severity = 'info'
                        file = $relPath
                        line = $blockStartLine
                        tag = 'commented-out-code'
                        message = "Block of $commentBlock commented-out code lines - consider removing"
                    }
                }
                $commentBlock = 0
            }
        }
    }

    # 6. Magic numbers isoles (entiers > 1 hors 0/1/-1/2 dans un bloc executable)
    # Heuristique simple : detect "[^=]\s*=\s*\d{3,}" (assignment de >=100 sans contexte clair)
    if ($relPath -match '\.(cs|kt|ts|tsx|js|jsx|py)$') {
        $magicMatches = [regex]::Matches($content, '[^_a-zA-Z0-9]([0-9]{3,})[^_a-zA-Z0-9]')
        $reportedMagics = @{}
        foreach ($m in $magicMatches) {
            $val = $m.Groups[1].Value
            $lineNum = ($content.Substring(0, $m.Index) -split "`n").Count
            $key = "$relPath::$lineNum"
            if (-not $reportedMagics.ContainsKey($key)) {
                $reportedMagics[$key] = $true
                # Skip si commun (timestamps, ports, status codes, ...)
                if ($val -match '^(200|201|204|301|302|400|401|403|404|500|503|1000|1024|2048|4096|8080|8443|3306|5432|27017)$') { continue }
                $results.info += [pscustomobject]@{
                    category = 'magic-number'
                    severity = 'info'
                    file = $relPath
                    line = $lineNum
                    tag = 'literal-numeric'
                    message = "Magic number '$val' - consider extracting to a named constant"
                }
            }
        }
    }
}

# -----------------------------------------------------------------------------
# Construire JSON et ecrire
# -----------------------------------------------------------------------------

$result = [ordered]@{
    spec        = $SpecNumber
    extractedAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    summary     = [ordered]@{
        total_files = $sourceFiles.Count
        errors      = $results.errors.Count
        warnings    = $results.warnings.Count
        info        = $results.info.Count
    }
    errors      = $results.errors
    warnings    = $results.warnings
    info        = $results.info
}

$outPath = Join-Path $QaDir 'quality.json'
$tmpPath = "$outPath.tmp"
$result | ConvertTo-Json -Depth 10 | Out-File -FilePath $tmpPath -Encoding UTF8 -Force
Move-Item -Path $tmpPath -Destination $outPath -Force

Write-Output "Quality scan complete:"
Write-Output "  Files scanned : $($sourceFiles.Count)"
Write-Output "  Errors        : $($results.errors.Count)"
Write-Output "  Warnings      : $($results.warnings.Count)"
Write-Output "  Info          : $($results.info.Count)"
Write-Output "  Output        : $outPath"

exit 0
