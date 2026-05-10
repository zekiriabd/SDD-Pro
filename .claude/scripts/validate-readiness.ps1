# =============================================================================
# SDD_Pro v3 - Implementation Readiness Gate (validations deterministes)
# =============================================================================
# Usage : pwsh .claude/scripts/validate-readiness.ps1 -SpecNumber {n}
#         pwsh .claude/scripts/validate-readiness.ps1 -SpecNumber {n} -Json
#
# Sortie : section 1 du rapport readiness (markdown stdout) ; ou JSON si -Json
# Exit code : 0 = toutes validations passent ; 1 = au moins 1 erreur bloquante
#
# ASCII-safe : tous les libellés en ASCII pour compatibilité PowerShell 5.1
# qui lit les fichiers UTF-8 sans BOM via codepage système.
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [int]$SpecNumber,

    [switch]$Json
)

$ErrorActionPreference = 'Stop'
$script:Errors = @()
$script:Warnings = @()
$script:Passes = @()

function Add-Pass($id, $msg) { $script:Passes += [pscustomobject]@{ id = $id; message = $msg } }
function Add-Warn($id, $msg) { $script:Warnings += [pscustomobject]@{ id = $id; message = $msg } }
function Add-Err($id, $cause, $fix) { $script:Errors += [pscustomobject]@{ id = $id; cause = $cause; fix = $fix } }

# Resolution repertoires (script doit tourner depuis racine projet)
$ProjectRoot = (Get-Location).Path
$SpecsDir   = Join-Path $ProjectRoot 'workspace/input/specs'
$UsDir      = Join-Path $ProjectRoot 'workspace/output/us'
$UiInputDir = Join-Path $ProjectRoot 'workspace/input/ui'
$StackPath  = Join-Path $ProjectRoot 'workspace/input/stack/stack.md'
$ConstPath  = Join-Path $ProjectRoot 'workspace/output/context/constitution.md'

# -----------------------------------------------------------------------------
# 0. Localiser la SPEC
# -----------------------------------------------------------------------------
$specFiles = @()
if (Test-Path $SpecsDir) {
    $specFiles = Get-ChildItem -Path $SpecsDir -Filter "$SpecNumber-*.md" -File -ErrorAction SilentlyContinue
}

if ($specFiles.Count -eq 0) {
    Add-Err 'SPEC-MISSING' "Aucun fichier workspace/input/specs/$SpecNumber-*.md trouve" 'Creer la SPEC via /spec-generate ou la deposer manuellement'
} elseif ($specFiles.Count -gt 1) {
    Add-Err 'SPEC-DUPLICATE' "Plusieurs fichiers commencent par $SpecNumber-" "Renommer pour qu'un seul fichier ait le prefixe $SpecNumber-"
}

$specFile = $null
$specName = $null
if ($specFiles.Count -eq 1) {
    $specFile = $specFiles[0]
    if ($specFile.BaseName -match "^$SpecNumber-(.+)$") {
        $specName = $Matches[1]
    }
}

# -----------------------------------------------------------------------------
# 1.1 Coherence numerotation IDs SPEC
# -----------------------------------------------------------------------------
if ($specFile) {
    $specContent = Get-Content $specFile.FullName -Raw -Encoding UTF8

    function Test-IdSequence {
        param([string]$content, [string]$prefix, [string]$sectionPattern)

        $sectionMatch = [regex]::Match($content, "(?ms)^## $sectionPattern\s*\r?\n(.*?)(?=^## |\z)")
        if (-not $sectionMatch.Success) { return @{ skipped = $true } }
        $section = $sectionMatch.Groups[1].Value

        $idPattern = "^- $prefix-(\d+):"
        $regexMatches = [regex]::Matches($section, $idPattern, [System.Text.RegularExpressions.RegexOptions]::Multiline)

        if ($regexMatches.Count -eq 0) {
            return @{ empty = $true }
        }

        $ids = @($regexMatches | ForEach-Object { [int]$_.Groups[1].Value })
        $duplicates = @($ids | Group-Object | Where-Object Count -gt 1 | ForEach-Object { $_.Name })
        $sortedIds = $ids | Sort-Object
        $expected = 1..($sortedIds[-1])
        $missing = @(Compare-Object -ReferenceObject $expected -DifferenceObject $sortedIds | Where-Object SideIndicator -eq '<=' | ForEach-Object InputObject)

        return @{
            count       = $regexMatches.Count
            ids         = $sortedIds
            duplicates  = $duplicates
            missing     = $missing
            ok          = ($duplicates.Count -eq 0 -and $missing.Count -eq 0)
        }
    }

    foreach ($pair in @(
        @('SFD', 'Functional Needs', $true),
        @('FD',  'Functional Deliverables', $true),
        @('BR',  'Business Rules', $false),
        @('AC',  'Acceptance Criteria', $false)
    )) {
        $prefix   = $pair[0]
        $sec      = $pair[1]
        $required = $pair[2]

        $r = Test-IdSequence -content $specContent -prefix $prefix -sectionPattern $sec
        if ($r.skipped) {
            if ($required) { Add-Err "$prefix-SECTION" "Section ## $sec absente de la SPEC" "Ajouter la section ## $sec dans workspace/input/specs/$($specFile.Name)" }
            continue
        }
        if ($r.empty) {
            if ($required) { Add-Warn "$prefix-EMPTY" "Section ## $sec presente mais vide ou sans IDs $prefix-N" }
            continue
        }
        if (-not $r.ok) {
            if ($r.duplicates.Count -gt 0) {
                $dups = ($r.duplicates -join ', ')
                Add-Err "$prefix-DUPLICATE" "IDs dupliques : $prefix-$dups" "Renumeroter les bullets dupliques dans ## $sec"
            }
            if ($r.missing.Count -gt 0) {
                $mis = ($r.missing -join ', ')
                Add-Warn "$prefix-GAP" "IDs manquants dans ## $sec : $prefix-$mis (numerotation discontinue)"
            }
        } else {
            Add-Pass "$prefix-IDS" "$prefix-N : $($r.count) IDs continus, pas de doublons"
        }
    }
}

# -----------------------------------------------------------------------------
# 1.2 Tracabilite 100% SPEC -> US
# -----------------------------------------------------------------------------
$usFiles = @()
if (Test-Path $UsDir) {
    $usFiles = Get-ChildItem -Path $UsDir -Filter "$SpecNumber-*.md" -File -ErrorAction SilentlyContinue
}

if ($specFile -and $usFiles.Count -eq 0) {
    Add-Err 'US-MISSING' "Aucune US trouvee (workspace/output/us/$SpecNumber-*.md)" "Lancer /us-generate $SpecNumber"
} elseif ($specFile -and $usFiles.Count -gt 0) {
    $allUsContent = ($usFiles | ForEach-Object { Get-Content $_.FullName -Raw -Encoding UTF8 }) -join "`n`n"

    function Get-AllIds {
        param([string]$content, [string]$prefix, [string]$sectionPattern)
        $sectionMatch = [regex]::Match($content, "(?ms)^## $sectionPattern\s*\r?\n(.*?)(?=^## |\z)")
        if (-not $sectionMatch.Success) { return @() }
        $regexMatches = [regex]::Matches($sectionMatch.Groups[1].Value, "^- $prefix-(\d+):", [System.Text.RegularExpressions.RegexOptions]::Multiline)
        return @($regexMatches | ForEach-Object { "$prefix-$($_.Groups[1].Value)" })
    }

    function Get-CoveredIds {
        param([string]$content, [string]$prefix)
        $regexMatches = [regex]::Matches($content, "$prefix-(\d+)")
        return @($regexMatches | ForEach-Object { "$prefix-$($_.Groups[1].Value)" } | Sort-Object -Unique)
    }

    foreach ($pair in @(
        @('SFD', 'Functional Needs', $true),
        @('FD',  'Functional Deliverables', $true),
        @('BR',  'Business Rules', $false),
        @('AC',  'Acceptance Criteria', $false)
    )) {
        $prefix   = $pair[0]
        $sec      = $pair[1]
        $required = $pair[2]

        $declared = Get-AllIds -content $specContent -prefix $prefix -sectionPattern $sec
        if ($declared.Count -eq 0) { continue }

        $covered = Get-CoveredIds -content $allUsContent -prefix $prefix
        $orphans = @($declared | Where-Object { $_ -notin $covered })

        if ($orphans.Count -eq 0) {
            Add-Pass "$prefix-COVERAGE" "Tous les $prefix-N de la SPEC sont couverts par au moins une US ($($declared.Count) IDs)"
        } else {
            $list = ($orphans -join ', ')
            if ($required) {
                Add-Err "$prefix-ORPHAN" "$prefix non couverts par les US : $list" "Ajouter ces IDs au Covers d'une US ou completer les ACs"
            } else {
                Add-Warn "$prefix-ORPHAN" "$prefix non couverts par les US : $list (non bloquant)"
            }
        }
    }
}

# -----------------------------------------------------------------------------
# 1.3 Coherence stack
# -----------------------------------------------------------------------------
if (-not (Test-Path $StackPath)) {
    Add-Err 'STACK-MISSING' "workspace/input/stack/stack.md absent" 'Creer workspace/input/stack/stack.md avec sections Active Tech Specs / Project Config'
} else {
    $stackContent = Get-Content $StackPath -Raw -Encoding UTF8

    $hasBackend = $stackContent -match '(?ms)^## Active Tech Specs[^#]*?(\bbackend/[^.]+\.md\b)'
    $hasFrontend = $stackContent -match '(?ms)^## Active Tech Specs[^#]*?(\bfrontend/[^.]+\.md\b)'

    if (-not $hasBackend -and -not $hasFrontend) {
        Add-Err 'STACK-EMPTY' "Aucun stack backend ni frontend actif dans Active Tech Specs" 'Activer au moins un stack (backend/* ou frontend/*) dans workspace/input/stack/stack.md'
    } else {
        Add-Pass 'STACK-ACTIVE' "Stacks actifs : backend=$($hasBackend), frontend=$($hasFrontend)"
    }

    if ($stackContent -match '(?ms)^## Project Config\s*\r?\n.*?AppName\s*:\s*\S') {
        Add-Pass 'PROJECT-CONFIG' 'Project Config rempli (AppName defini)'
    } else {
        Add-Err 'PROJECT-CONFIG-MISSING' 'Project Config absent ou AppName non defini' 'Ajouter ## Project Config avec AppName: <NomProjet>'
    }

    if ($stackContent -match '(?ms)DatabaseType\s*:\s*(\S+)') {
        $dbType = $Matches[1].Trim()
        $validDb = @('none', 'postgres', 'sqlserver', 'mysql', 'sqlite', 'oracle', 'mariadb')
        if ($dbType.ToLower() -in $validDb) {
            Add-Pass 'DB-TYPE' "DatabaseType valide : $dbType"
        } else {
            Add-Warn 'DB-TYPE-UNKNOWN' "DatabaseType '$dbType' non reconnu (attendu : $($validDb -join ', '))"
        }
    } else {
        Add-Warn 'DB-TYPE-MISSING' 'DatabaseType non defini dans Project Config (assume : none)'
    }
}

# -----------------------------------------------------------------------------
# 1.4 Coherence US <-> HTML mockups (v4.0.0)
# -----------------------------------------------------------------------------
$htmlFiles = @()
if (Test-Path $UiInputDir) {
    $htmlFiles = Get-ChildItem -Path $UiInputDir -Filter "$SpecNumber-*.html" -File -ErrorAction SilentlyContinue
}

if ($htmlFiles.Count -gt 0 -and $usFiles.Count -gt 0) {
    $usBasenames = @($usFiles | ForEach-Object { $_.BaseName })
    $htmlOrphans = @()
    foreach ($html in $htmlFiles) {
        if ($html.BaseName -notin $usBasenames) {
            $htmlOrphans += $html.Name
        }
    }
    if ($htmlOrphans.Count -eq 0) {
        Add-Pass 'HTML-US-MATCH' "Tous les mockups HTML ($($htmlFiles.Count)) ont une US correspondante"
    } else {
        $list = ($htmlOrphans -join ', ')
        Add-Warn 'HTML-ORPHAN' "Mockups HTML sans US correspondante : $list (renommer ou retirer)"
    }
}

# -----------------------------------------------------------------------------
# 1.5 Constitution (SDD_Pro v3)
# -----------------------------------------------------------------------------
if (Test-Path $ConstPath) {
    Add-Pass 'CONST-EXISTS' 'Constitution presente (workspace/output/context/constitution.md)'

    $constContent = Get-Content $ConstPath -Raw -Encoding UTF8
    if ($specFile) {
        if ($constContent -match [regex]::Escape("$SpecNumber-$specName")) {
            Add-Pass 'CONST-SPEC-LINKED' "SPEC $SpecNumber-$specName referencee dans la constitution"
        } else {
            Add-Warn 'CONST-SPEC-NOTLINKED' "SPEC $SpecNumber-$specName non referencee dans constitution.md section 3 - l'agent PO devrait l'ajouter au prochain run"
        }
    }
} else {
    Add-Warn 'CONST-MISSING' "Constitution absente (workspace/output/context/constitution.md) - projet pre-v3 ou /spec-generate non utilise. Non bloquant."
}

# -----------------------------------------------------------------------------
# 1.6 Spec-deepen recommande sur SPECs complexes (SDD_Pro v3.1.3, audit A4)
# -----------------------------------------------------------------------------
# Une SPEC "complexe" est detectee via 5 criteres de seuil. Si elle depasse
# >= 2 de ces seuils ET que /spec-deepen n'a pas tourne (constitution §7 vide
# ou absente), un WARN est emis. Combine avec le mode strict /sdd-full v3.1.2,
# cela rend /spec-deepen de facto obligatoire pour les SPECs complexes (sauf
# --force explicite).
#
# Seuils de complexite (l'un de ces criteres = +1 point) :
#   1. SFD-N >= 10
#   2. BR-N  >= 8
#   3. AC-N  >= 15
#   4. DatabaseType != none (signal de complexite donnees)
#   5. Out of Scope >= 5 items (signal de complexite perimetre)
# Score >= 2 => SPEC complexe.

if ($specFile) {
    # Compter les bullets effectifs (lignes "- {ID}-N: ...") dans la SPEC
    $specRaw = Get-Content $specFile.FullName -Raw -Encoding UTF8

    function Count-Section {
        param($text, $heading, $idPrefix)
        # Match la section + capture le bloc jusqu'au prochain heading H2
        $pattern = '(?ms)^##\s+' + [regex]::Escape($heading) + '\s*(.+?)(?=^##\s+|\z)'
        if ($text -match $pattern) {
            $body = $matches[1]
            $bulletPattern = '^\s*-\s+' + $idPrefix + '-\d+\s*:'
            return ([regex]::Matches($body, $bulletPattern, 'Multiline')).Count
        }
        return 0
    }

    $sfdCount = Count-Section $specRaw 'Functional Needs' 'SFD'
    $brCount  = Count-Section $specRaw 'Business Rules'   'BR'
    $acCount  = Count-Section $specRaw 'Acceptance Criteria' 'AC'

    # Out of Scope : compter les bullets "- ..." dans la section
    $oosCount = 0
    $oosPattern = '(?ms)^##\s+Out of Scope\s*(.+?)(?=^##\s+|\z)'
    if ($specRaw -match $oosPattern) {
        $oosCount = ([regex]::Matches($matches[1], '^\s*-\s+\S', 'Multiline')).Count
    }

    # DatabaseType depuis stack.md
    $hasDb = $false
    if (Test-Path $StackPath) {
        $stackRaw = Get-Content $StackPath -Raw -Encoding UTF8
        if ($stackRaw -match '(?im)^\s*DatabaseType\s*:\s*(\S+)') {
            $dbType = $matches[1].Trim()
            $hasDb = ($dbType -ne 'none' -and $dbType -ne '')
        }
    }

    $score = 0
    $reasons = @()
    if ($sfdCount -ge 10) { $score++; $reasons += "$sfdCount SFD" }
    if ($brCount  -ge 8)  { $score++; $reasons += "$brCount BR" }
    if ($acCount  -ge 15) { $score++; $reasons += "$acCount AC" }
    if ($hasDb)           { $score++; $reasons += "DatabaseType=$dbType" }
    if ($oosCount -ge 5)  { $score++; $reasons += "$oosCount Out-of-Scope" }

    $isComplex = ($score -ge 2)

    # Detecter si /spec-deepen a tourne : §7 contient au moins un bullet
    # factuel hors phrase d'amorce template
    $deepenRun = $false
    if (Test-Path $ConstPath) {
        $constRaw = Get-Content $ConstPath -Raw -Encoding UTF8
        $section7Pattern = '(?ms)^##\s+7\.\s+Risques.+?(?=^##\s+8\.|\z)'
        if ($constRaw -match $section7Pattern) {
            $section7 = $matches[0]
            # Chercher des bullets reels (pas seulement la phrase d'amorce)
            $realBullets = [regex]::Matches($section7, '^\s*-\s+(?!\s*(?:<|Etendu par|Vide tant))', 'Multiline')
            $deepenRun = ($realBullets.Count -ge 1)
        }
    }

    if ($isComplex) {
        if ($deepenRun) {
            Add-Pass 'SPEC-DEEPEN-DONE' "SPEC complexe (score $score/5: $($reasons -join ', ')) et /spec-deepen execute (constitution §7 peuplee)"
        } else {
            Add-Warn 'SPEC-DEEPEN-RECOMMENDED' "SPEC complexe (score $score/5: $($reasons -join ', ')) mais /spec-deepen non execute - constitution §7 vide. Lancer /spec-deepen $SpecNumber pour identifier risques/hypotheses avant /dev-run (audit A4 SDD_Pro v3.1.3). Bypass : /sdd-full --force."
        }
    } else {
        # SPEC simple : pas de check
        Add-Pass 'SPEC-COMPLEXITY-LOW' "SPEC simple (score $score/5) - /spec-deepen optionnel"
    }
}

# -----------------------------------------------------------------------------
# Decision finale
# -----------------------------------------------------------------------------
$decision = if ($script:Errors.Count -gt 0) { 'NO-GO' } elseif ($script:Warnings.Count -gt 0) { 'WARN' } else { 'GO' }
$exitCode = if ($script:Errors.Count -gt 0) { 1 } else { 0 }

# -----------------------------------------------------------------------------
# Sortie
# -----------------------------------------------------------------------------
if ($Json) {
    $result = [pscustomobject]@{
        spec_number = $SpecNumber
        spec_name   = $specName
        decision    = $decision
        errors      = $script:Errors
        warnings    = $script:Warnings
        passes      = $script:Passes
        timestamp   = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    }
    $result | ConvertTo-Json -Depth 5
} else {
    Write-Output "## 1. Validations deterministes (PowerShell)"
    Write-Output ""
    Write-Output "**Spec** : $SpecNumber-$specName"
    Write-Output "**Decision deterministe** : $decision"
    Write-Output "**Passes** : $($script:Passes.Count) | **Warnings** : $($script:Warnings.Count) | **Errors** : $($script:Errors.Count)"
    Write-Output ""
    if ($script:Passes.Count -gt 0) {
        Write-Output "### Validations passees"
        foreach ($p in $script:Passes) { Write-Output "- [PASS] $($p.id) : $($p.message)" }
        Write-Output ""
    }
    if ($script:Warnings.Count -gt 0) {
        Write-Output "### Warnings"
        foreach ($w in $script:Warnings) { Write-Output "- [WARN] $($w.id) : $($w.message)" }
        Write-Output ""
    }
    if ($script:Errors.Count -gt 0) {
        Write-Output "### Erreurs bloquantes"
        foreach ($e in $script:Errors) {
            Write-Output "- [FAIL] $($e.id)"
            Write-Output "  - CAUSE : $($e.cause)"
            Write-Output "  - FIX   : $($e.fix)"
        }
        Write-Output ""
    }
}

exit $exitCode
