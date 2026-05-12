# =============================================================================
# SDD_Pro - Semantic Validation (deterministe, 0 token LLM)
# =============================================================================
# Reintroduit une couche de validation semantique cross-artefacts retiree en v6.0,
# mais sous forme purement deterministe (vocabulaire + regex). Aucun appel LLM.
#
# Usage : pwsh .claude/scripts/validate-semantic.ps1 -SpecNumber {n}
#         pwsh .claude/scripts/validate-semantic.ps1 -SpecNumber {n} -Json
#         pwsh .claude/scripts/validate-semantic.ps1 -SpecNumber {n} -Strictness conservative|standard|strict
#
# Sortie : section §2 du rapport readiness (markdown stdout) ou JSON
# Exit code : toujours 0 (semantique = WARN uniquement, jamais bloquant)
#
# Checks (strictness=standard) :
#   - VAGUE_TERM         : termes vagues dans SPEC / US (fast, easy, scalable, ...)
#   - SECURITY_GAP       : auth/credential keywords sans mention de protection
#   - SENSITIVE_DATA     : PII mentionnees sans mention de privacy
#   - ROUTE_CONTRACT_GAP : /api/* mentionne en SPEC, endpoint absent du code (si code present)
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [int]$SpecNumber,

    [ValidateSet('conservative','standard','strict')]
    [string]$Strictness = 'standard',

    [switch]$Json
)

$ErrorActionPreference = 'Stop'
$script:Warnings = @()
$script:Passes = @()

function Add-Pass($id, $msg) { $script:Passes += [pscustomobject]@{ id = $id; message = $msg } }
function Add-Warn($id, $msg, $context = "") {
    $script:Warnings += [pscustomobject]@{ id = $id; message = $msg; context = $context }
}

$ProjectRoot = (Get-Location).Path
$SpecsDir    = Join-Path $ProjectRoot 'workspace/input/specs'
$UsDir       = Join-Path $ProjectRoot 'workspace/output/us'
$SrcDir      = Join-Path $ProjectRoot 'workspace/output/src'
$StackPath   = Join-Path $ProjectRoot 'workspace/input/stack/stack.md'

# -----------------------------------------------------------------------------
# Vocabulaires (standard strictness par defaut, ~5-15 WARN par SPEC moyenne)
# -----------------------------------------------------------------------------
# Termes vagues : qualite non mesurable. Match en mot complet (boundary).
$vagueStandard = @(
    'fast','quick','rapide','vite','rapidement',
    'easy','facile','intuitive','intuitif',
    'user-friendly','convivial',
    'scalable','performant','responsive',
    'robust','robuste','reliable','fiable',
    'many','several','plusieurs','beaucoup',
    'simple','simply','simplement'
)
$vagueConservative = @(
    'fast','rapide','easy','facile','scalable','user-friendly'
)
$vagueStrict = $vagueStandard + @(
    'appropriate','approprie','adequate','adequat',
    'reasonable','raisonnable','proper','correct',
    'efficient','efficace','optimized','optimise',
    'clean','propre','elegant','elegant',
    'modern','moderne','flexible','dynamic','dynamique',
    'smooth','fluide','seamless'
)

# Cles securite : si mentionnees dans SPEC/US, il faut une mention de protection
$securityKeywords = @(
    'password','mot de passe','motdepasse','mdp',
    'token','jwt','bearer','refresh token',
    'auth','authentication','authentification','login','connexion','signin','sign in',
    'credential','identifiant','secret','api key','cle api','clef api'
)
$protectionKeywords = @(
    'hash','hashed','hashé','bcrypt','argon','argon2','scrypt','pbkdf2','sha-?(?:256|512)',
    'encrypt','encrypted','chiffr','chiffrement','aes','rsa',
    'salt','sel cryptographique',
    'https','tls','ssl',
    'httponly','http-only','samesite','secure cookie','cookie secure',
    'environment variable','variable d''environnement','env var','env variable'
)

# PII : si mentionnees, il faut une mention de privacy/protection
$piiKeywords = @(
    'email','e-mail','courriel',
    'phone','téléphone','telephone','mobile',
    'postal address','adresse postale',
    'birth date','birthday','date de naissance',
    'ssn','social security','sécurité sociale',
    'credit card','carte bancaire','iban','rib'
)
$privacyKeywords = @(
    'encrypt','chiffr','mask','masqu','anonymized','anonymis','redact','redig',
    'gdpr','rgpd','privacy','vie privée','confidential','confidentiel',
    'access control','contrôle d''accès','rbac','role-based',
    'audit log','journal d''audit'
)

# Selection vocabulaire selon strictness
$vagueTerms = switch ($Strictness) {
    'conservative' { $vagueConservative }
    'strict'       { $vagueStrict }
    default        { $vagueStandard }
}

# -----------------------------------------------------------------------------
# 0. Localiser la SPEC
# -----------------------------------------------------------------------------
$specFile = $null
$specName = $null
if (Test-Path $SpecsDir) {
    $specFiles = @(Get-ChildItem -Path $SpecsDir -Filter "$SpecNumber-*.md" -File -ErrorAction SilentlyContinue)
    if ($specFiles.Count -eq 1) {
        $specFile = $specFiles[0]
        if ($specFile.BaseName -match "^$SpecNumber-(.+)$") { $specName = $Matches[1] }
    }
}

if (-not $specFile) {
    if ($Json) {
        ([pscustomobject]@{
            spec_number = $SpecNumber
            spec_name = $null
            strictness = $Strictness
            decision = 'SKIP'
            warnings = @()
            passes = @()
            note = 'SPEC introuvable - validation semantique skip'
        } | ConvertTo-Json -Depth 5)
    } else {
        Write-Output "## 2. Validations semantiques (deterministes)"
        Write-Output ""
        Write-Output "**Skip** : SPEC introuvable (workspace/input/specs/$SpecNumber-*.md)"
    }
    exit 0
}

$specContent = Get-Content $specFile.FullName -Raw -Encoding UTF8

# Charger les US pour scan etendu
$usContent = ""
if (Test-Path $UsDir) {
    $usFiles = @(Get-ChildItem -Path $UsDir -Filter "$SpecNumber-*.md" -File -ErrorAction SilentlyContinue)
    foreach ($f in $usFiles) {
        $usContent += "`n--- US: $($f.Name) ---`n"
        $usContent += (Get-Content $f.FullName -Raw -Encoding UTF8)
    }
}

$fullText = $specContent + "`n" + $usContent

# Helpers
function Get-LineNumber([string]$text, [int]$index) {
    if ($index -lt 0) { return 0 }
    $prefix = $text.Substring(0, [math]::Min($index, $text.Length))
    return ($prefix.Split("`n")).Count
}

function Get-Snippet([string]$text, [int]$index, [int]$radius = 60) {
    $start = [math]::Max(0, $index - $radius)
    $end = [math]::Min($text.Length, $index + $radius)
    $snip = $text.Substring($start, $end - $start)
    $snip = $snip -replace '\s+', ' '
    return $snip.Trim()
}

function Test-AnyMatch([string]$text, [string[]]$patterns) {
    foreach ($p in $patterns) {
        if ($text -match $p) { return $true }
    }
    return $false
}

# Section text extractor (sans cross-section bleed)
function Get-SectionBody([string]$text, [string]$heading) {
    $pat = "(?ms)^##\s+" + [regex]::Escape($heading) + "\s*\r?\n(.+?)(?=^##\s+|\z)"
    $m = [regex]::Match($text, $pat)
    if ($m.Success) { return $m.Groups[1].Value }
    return ""
}

# -----------------------------------------------------------------------------
# Check 1 - VAGUE_TERM : termes vagues dans Acceptance Criteria + Business Rules + Functional Needs
# -----------------------------------------------------------------------------
$vagueCount = 0
$scanSections = @('Acceptance Criteria','Business Rules','Functional Needs','Objective','Functional Deliverables')
foreach ($sec in $scanSections) {
    $body = Get-SectionBody $specContent $sec
    if (-not $body) { continue }
    foreach ($term in $vagueTerms) {
        $pat = '(?i)\b' + [regex]::Escape($term) + '\b'
        $matches = [regex]::Matches($body, $pat)
        foreach ($m in $matches) {
            $absoluteIndex = $specContent.IndexOf($body) + $m.Index
            $lineNo = Get-LineNumber $specContent $absoluteIndex
            $snippet = Get-Snippet $specContent $absoluteIndex 50
            Add-Warn 'VAGUE_TERM' "'$term' dans ## $sec L${lineNo} - terme non mesurable" "L${lineNo}: $snippet"
            $vagueCount++
        }
    }
}
if ($vagueCount -eq 0) {
    Add-Pass 'VAGUE_TERM' "Aucun terme vague detecte (vocabulaire $Strictness, $($vagueTerms.Count) termes scannes)"
}

# -----------------------------------------------------------------------------
# Check 2 - SECURITY_GAP : keywords securite sans mention de mecanisme de protection
# -----------------------------------------------------------------------------
# Strategie : si SPEC mentionne >= 1 securityKeyword, verifier que >= 1 protectionKeyword
# est mentionne dans le SPEC global. Sinon WARN une seule fois (pas par occurrence).
$hasSecurity = Test-AnyMatch $specContent ($securityKeywords | ForEach-Object { '(?i)\b' + [regex]::Escape($_) + '\b' })
$hasProtection = Test-AnyMatch $fullText ($protectionKeywords | ForEach-Object { '(?i)' + $_ })

if ($hasSecurity) {
    if (-not $hasProtection) {
        $found = @()
        foreach ($kw in $securityKeywords) {
            if ($specContent -match ('(?i)\b' + [regex]::Escape($kw) + '\b')) {
                $found += $kw
                if ($found.Count -ge 3) { break }
            }
        }
        $foundStr = ($found -join ', ')
        Add-Warn 'SECURITY_GAP' "SPEC mentionne $foundStr mais aucun mecanisme de protection (hash/bcrypt/encrypt/tls/httponly) declare en SPEC ou US" ""
    } else {
        Add-Pass 'SECURITY_OK' "Keywords securite presentes ET au moins un mecanisme de protection mentionne"
    }
}

# -----------------------------------------------------------------------------
# Check 3 - SENSITIVE_DATA : PII mentionnees sans mention de privacy
# -----------------------------------------------------------------------------
$piiFound = @()
foreach ($kw in $piiKeywords) {
    if ($specContent -match ('(?i)\b' + [regex]::Escape($kw) + '\b')) {
        $piiFound += $kw
    }
}

if ($piiFound.Count -gt 0) {
    $hasPrivacy = Test-AnyMatch $fullText ($privacyKeywords | ForEach-Object { '(?i)' + [regex]::Escape($_) })
    if (-not $hasPrivacy) {
        $piiList = (($piiFound | Select-Object -First 3) -join ', ')
        Add-Warn 'SENSITIVE_DATA' "PII detectees ($piiList) mais aucune mention de privacy/chiffrement/anonymisation/RGPD en SPEC ou US" ""
    } else {
        Add-Pass 'PII_OK' "PII mentionnees ET au moins un mecanisme de privacy declare"
    }
}

# -----------------------------------------------------------------------------
# Check 4 - ROUTE_CONTRACT_GAP : routes /api/* mentionnees vs endpoints reels
# -----------------------------------------------------------------------------
# Strategie : scan SPEC+US pour les routes /api/...; pour chaque route, verifier
# qu'un MapGet/MapPost/MapPut/MapDelete (ou [HttpGet]/[HttpPost]) existe dans
# workspace/output/src/{BackendName}/. Si le backend n'est pas encore genere,
# skip silencieusement (le check tournera apres /dev-run).
$routePattern = '(?i)["`/]?(/api/[a-z0-9_\-/.{}:]+)'
$routesInSpec = @{}
$ms = [regex]::Matches($fullText, $routePattern)
foreach ($m in $ms) {
    $route = $m.Groups[1].Value.TrimEnd('.',',',';',':','"','''','`',')')
    # Normaliser : enlever query/fragments
    $route = $route -replace '[\?#].*$',''
    if ($route -and $route.Length -gt 4) {
        $routesInSpec[$route] = $true
    }
}

if ($routesInSpec.Count -gt 0) {
    # Resoudre BackendName depuis stack.md
    $backendName = $null
    if (Test-Path $StackPath) {
        $stackRaw = Get-Content $StackPath -Raw -Encoding UTF8
        if ($stackRaw -match '(?im)^\s*BackendName\s*:\s*(\S+)') {
            $backendName = $Matches[1].Trim()
        }
    }

    $backendCodeDir = $null
    if ($backendName) {
        $candidate = Join-Path $SrcDir $backendName
        if (Test-Path $candidate) { $backendCodeDir = $candidate }
    }

    if (-not $backendCodeDir) {
        # Skip silencieux : on relancera apres /dev-run
        Add-Pass 'ROUTE_CONTRACT_DEFERRED' "Routes /api/* detectees ($($routesInSpec.Count)) mais code backend pas encore genere - check differe apres /dev-run"
    } else {
        # Collecter toutes les routes declarees dans le code backend
        $declaredRoutes = @{}
        $codeFiles = Get-ChildItem -Path $backendCodeDir -Recurse -File -Include *.cs,*.ts,*.js,*.py,*.kt,*.java -ErrorAction SilentlyContinue
        $declPattern = '(?im)(?:Map(?:Get|Post|Put|Delete|Patch)|\[Http(?:Get|Post|Put|Delete|Patch)(?:\(|\])|@(?:Get|Post|Put|Delete|Patch)Mapping|app\.(?:get|post|put|delete|patch)|@app\.(?:get|post|put|delete|patch))\s*\(?\s*["`'']([^"`'')]+)["`'']'
        foreach ($f in $codeFiles) {
            $code = Get-Content $f.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if (-not $code) { continue }
            $rmatches = [regex]::Matches($code, $declPattern)
            foreach ($rm in $rmatches) {
                $r = $rm.Groups[1].Value.TrimEnd('/')
                if ($r) { $declaredRoutes[$r] = $true }
            }
        }

        $missing = @()
        foreach ($r in $routesInSpec.Keys) {
            $normalized = $r.TrimEnd('/')
            $found = $false
            foreach ($d in $declaredRoutes.Keys) {
                # Match exact OU pattern parametre ({id} matche /123)
                $dPat = '^' + ([regex]::Escape($d) -replace '\\\{[^}]+\\\}','[^/]+') + '$'
                if ($normalized -match $dPat) { $found = $true; break }
                $rPat = '^' + ([regex]::Escape($normalized) -replace '\\\{[^}]+\\\}','[^/]+') + '$'
                if ($d -match $rPat) { $found = $true; break }
            }
            if (-not $found) { $missing += $normalized }
        }

        if ($missing.Count -gt 0) {
            $list = (($missing | Select-Object -First 5) -join ', ')
            $more = if ($missing.Count -gt 5) { " (+$($missing.Count - 5) autres)" } else { "" }
            Add-Warn 'ROUTE_CONTRACT_GAP' "Routes mentionnees en SPEC/US sans endpoint backend declare : $list$more - cf. responsibilities.md §12 [FRONTEND_BACKEND_CONTRACT_GAP]" ""
        } else {
            Add-Pass 'ROUTE_CONTRACT_OK' "Toutes les routes /api/* SPEC ($($routesInSpec.Count)) ont un endpoint backend declare"
        }
    }
}

# -----------------------------------------------------------------------------
# Decision (semantique = jamais bloquant : WARN max)
# -----------------------------------------------------------------------------
$decision = if ($script:Warnings.Count -gt 0) { 'WARN' } else { 'GO' }

# -----------------------------------------------------------------------------
# Sortie
# -----------------------------------------------------------------------------
if ($Json) {
    $result = [pscustomobject]@{
        spec_number = $SpecNumber
        spec_name   = $specName
        strictness  = $Strictness
        decision    = $decision
        warnings    = $script:Warnings
        passes      = $script:Passes
        timestamp   = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    }
    $result | ConvertTo-Json -Depth 5
} else {
    Write-Output "## 2. Validations semantiques (deterministes)"
    Write-Output ""
    Write-Output "**Strictness** : $Strictness"
    Write-Output "**Decision semantique** : $decision (non bloquant)"
    Write-Output "**Passes** : $($script:Passes.Count) | **Warnings** : $($script:Warnings.Count)"
    Write-Output ""
    if ($script:Passes.Count -gt 0) {
        Write-Output "### Validations passees"
        foreach ($p in $script:Passes) { Write-Output "- [PASS] $($p.id) : $($p.message)" }
        Write-Output ""
    }
    if ($script:Warnings.Count -gt 0) {
        Write-Output "### Warnings semantiques"
        foreach ($w in $script:Warnings) {
            Write-Output "- [WARN] $($w.id) : $($w.message)"
            if ($w.context) { Write-Output "  - Contexte : $($w.context)" }
        }
        Write-Output ""
    }
    Write-Output "_Note : validation semantique deterministe (vocabulaire $Strictness). Pour escalation petit modele sur WARN, voir SemanticValidationMode dans stack.md._"
}

exit 0
