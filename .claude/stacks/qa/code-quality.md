# QA Stack — Code Quality (Sonar-like cross-stack)

Status: ✅ Available
Validation: 🟢 reference (cross-stack, 0 token, déterministe)

## 1. Scope

Stack **non-LLM** : règles d'analyse statique appliquées par le script
`python .claude/python/sdd_scripts/quality_scan.py` sur le code de
production de la FEAT ciblée.

**0 token** consommé. Très rapide (< 1s pour ~5000 LOC).

S'applique cross-stack (.NET, Node, Python, Kotlin, Angular). Active dès
qu'au moins un autre QA stack est listé.

---

## 2. Activation

Dans `workspace/input/stack/stack.md` :

```markdown
## Active QA Specs
- .claude/stacks/qa/dotnet-xunit.md
- .claude/stacks/qa/code-quality.md      # active le scan sonar-like
```

Cette stack est **non-prescriptive sur le test runner** — elle complète
les autres QA stacks par un audit de qualité du code de production.

---

## 3. Catégories analysées

### 3.1 TODO / FIXME / XXX / HACK (errors)

Détecte les commentaires de dette technique :
- `// TODO: ...`, `// FIXME: ...`, `// XXX: ...`, `// HACK: ...`
- `# TODO: ...` (Python)
- `<!-- TODO: ... -->` (HTML/Razor)

**Sévérité** : `error` (à résoudre avant prod).

### 3.2 Debug output (warnings)

Détecte les sorties de debug oubliées :

| Pattern | Contexte |
|---|---|
| `console.log(`, `console.error(`, `console.warn(` | JS/TS |
| `Console.WriteLine(`, `Debug.Print(` | C# |
| `print(` (en début de ligne) | Python |
| `System.out.println(` | Java/Kotlin |
| `println!(` | Rust |

**Sévérité** : `warning`.

### 3.3 Hardcoded hex (warnings)

Détecte les valeurs hex hardcodées (#RRGGBB ou #RGB) **hors** de
`theme.css` / `theme.scss`.

Concerne : `.css`, `.scss`, `.razor`, `.tsx`, `.jsx`, `.vue`.

Le seul endroit autorisé pour les hex est le fichier theme global
référencé par `rules/quality.md` (héritage SDD_Lite philosophie).

**Sévérité** : `warning`.

### 3.4 Méthodes longues (warnings)

Détecte les méthodes / fonctions / classes > 50 lignes (heuristique
basée sur les accolades pour C#/Kotlin/TS, indentation pour Python).

**Sévérité** : `warning`.

### 3.5 Code commenté en bloc (info)

Détecte les blocs de ≥ 5 lignes consécutives de commentaires qui
ressemblent à du code (présence de parenthèses, points-virgules, points,
affectations).

**Sévérité** : `info`.

### 3.6 Magic numbers (info)

Détecte les littéraux numériques ≥ 100 chiffres en contexte
exécutable (hors annotations, hors strings). Exclut les codes communs
(200, 401, 1024, 8080, …).

**Sévérité** : `info`.

### 3.7 Scan supply-chain — CVE / SBOM / licences (v6.1)

Trois sous-checks lancés par `quality_scan.py` selon le `buildSystem`
détecté dans le catalogue stack actif. Tous trois écrivent leurs
artefacts sous `workspace/output/qa/feat-{n}/supply-chain/`.

#### 3.7.a CVE scan (errors si gravité ≥ moderate)

Cible : packages installés avec vulnérabilité connue dans la base
publique GitHub Advisory / NVD.

| BuildSystem | Commande |
|---|---|
| `dotnet`        | `dotnet list package --vulnerable --include-transitive --format json` |
| `npm`/`pnpm`/`yarn` | `npm audit --omit=dev --audit-level=moderate --json` |
| `uv`/`pip`/`poetry` | `pip-audit --format=json` (depuis `pyproject.toml` ou `requirements.txt`) |
| `maven`/`gradle`    | `mvn org.owasp:dependency-check-maven:check -DfailBuildOnCVSS=4 -f pom.xml -Dformat=JSON` ou plugin Gradle `org.owasp.dependencycheck` |
| `cargo`             | `cargo audit --json` |

**Sévérité** : `error` si CVSS ≥ 4.0 (moderate), `warning` si < 4.0.

Sortie consolidée : `workspace/output/qa/feat-{n}/supply-chain/cve.json`
schéma minimal :
```json
{
  "scanner": "dotnet|npm|pip-audit|cargo-audit|...",
  "extractedAt": "ISO",
  "vulnerabilities": [
    { "package": "Foo.Bar", "version": "1.2.3", "advisory": "GHSA-...", "severity": "high", "cvss": 7.5, "url": "https://..." }
  ],
  "summary": { "errors": 1, "warnings": 0 }
}
```

#### 3.7.b SBOM generation (info, archive)

Génère un **Software Bill of Materials** au format CycloneDX (standard
OWASP). Pas de pass/fail — artefact requis pour audit / compliance /
SLSA niveau 1+.

| BuildSystem | Outil canonique |
|---|---|
| `dotnet`        | `dotnet CycloneDX` (NuGet `CycloneDX` global tool) → `bom.xml` ou `bom.json` |
| `npm`/`pnpm`/`yarn` | `@cyclonedx/cyclonedx-npm` |
| `pip`/`uv`/`poetry` | `cyclonedx-py` |
| `maven`/`gradle`    | plugin `org.cyclonedx:cyclonedx-maven-plugin` / `org.cyclonedx.bom` |
| Universel (fallback) | `syft` (Anchore) — détecte automatiquement le buildSystem |

Sortie : `workspace/output/qa/feat-{n}/supply-chain/sbom.cyclonedx.json`.

#### 3.7.c Licences (warnings sur licences non autorisées)

Cible : détecter des licences copyleft virales (GPL-3.0, AGPL-3.0), des
licences "Polyform Noncommercial" (ex. EPPlus ≥ 5), ou des licences
absentes/inconnues qui empêchent la distribution.

| BuildSystem | Outil |
|---|---|
| `dotnet`        | `dotnet nuget-license` (NuGet `dotnet-project-licenses` global tool) |
| `npm`           | `license-checker --json` |
| `pip`           | `pip-licenses --format=json` |
| `maven`/`gradle` | plugin `org.gaul:modernizer-maven-plugin` ou `com.github.jk1.dependency-license-report` |

**Liste blanche par défaut** (configurable via `## Project Config` →
`LicensesAllowed`) :
- `MIT`, `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`,
  `MPL-2.0`, `LGPL-2.1`, `0BSD`, `Unlicense`, `CC0-1.0`,
  `MS-EULA` (Microsoft pour packages officiels)

**Sévérité** :
- `warning` : licence hors liste blanche (ex. `GPL-3.0`, `AGPL-3.0`,
  `Polyform-Noncommercial-1.0.0`, `SSPL-1.0`)
- `error` : aucune licence détectée (package sans manifest licence —
  bloquant pour distribution)

Sortie : `workspace/output/qa/feat-{n}/supply-chain/licenses.json`.

#### 3.7.d Activation et bypass

Activation pilotée par `## Project Config` :
```yaml
SupplyChainScan: full           # full | cve-only | sbom-only | licenses-only | off
LicensesAllowed: MIT,Apache-2.0,BSD-3-Clause   # override liste blanche (séparé par virgules)
CveMaxSeverity: moderate        # moderate (CVSS 4) | high (7) | critical (9) — défaut moderate
```

`off` = skip total (NON recommandé en prod). `CveMaxSeverity: high`
laisse passer les CVE moderate sans bloquer.

**Pré-requis outillage** : si l'outil canonique d'un sous-check n'est
pas installé (ex. `dotnet CycloneDX` global tool), `quality_scan.py`
émet WARN `[SUPPLY_CHAIN_TOOL_MISSING]` et skip le sous-check (pas
bloquant — l'install se fait `dotnet tool install --global CycloneDX`).

---

## 4. Exclusions

Le script exclut automatiquement :

| Type | Patterns |
|---|---|
| Dossiers de build | `bin/`, `obj/`, `dist/`, `build/` |
| Dépendances | `node_modules/`, `.angular/`, `wwwroot/_framework/` |
| Tests | `*.Tests/`, `__tests__/`, `*.FEAT.*`, `*.test.*`, `test_*`, `_test.*` |
| Coverage | `coverage/`, `TestResults/` |
| IDE | `.vs/`, `.idea/` |

Le quality scan s'applique **uniquement au code de production**.

---

## 5. Output

Le script produit `workspace/output/qa/feat-{n}/quality.json` :

```json
{
  "FEAT": 1,
  "extractedAt": "2026-05-05T14:32:18Z",
  "summary": {
    "total_files": 42,
    "errors": 3,
    "warnings": 12,
    "info": 7
  },
  "errors": [
    {
      "category": "todo",
      "severity": "error",
      "file": "workspace/output/src/SIMBackend/Services/AuthService.cs",
      "line": 42,
      "tag": "TODO",
      "message": "TODO: implement token refresh"
    }
  ],
  "warnings": [...],
  "info": [...]
}
```

---

## 6. Règle d'évaluation

Le quality scan **traditionnel** (§3.1-§3.6) ne bloque jamais le
pipeline. Le scan supply-chain (§3.7) **peut bloquer** selon la
sévérité CVE détectée.

| Catégorie | Source | Sévérité | Effet sur décision globale `/qa-generate` |
|---|---|---|---|
| Quality traditionnel | §3.1-§3.6 | `errors` 0 | GREEN (si tests + coverage OK) |
| Quality traditionnel | §3.1-§3.6 | `errors` ≥ 1 | YELLOW |
| Quality traditionnel | §3.1-§3.6 | `warnings` / `info` | informatif, pas de changement |
| Supply-chain CVE | §3.7.a | CVSS ≥ `CveMaxSeverity` | **RED bloquant** (depuis v6.1) |
| Supply-chain CVE | §3.7.a | CVSS < `CveMaxSeverity` | warning, pas de bloquage |
| Supply-chain licenses | §3.7.c | licence absente | **RED bloquant** (pas de licence = pas de distribution) |
| Supply-chain licenses | §3.7.c | licence hors whitelist | YELLOW (revue humaine recommandée) |
| Supply-chain SBOM | §3.7.b | toujours info | jamais bloquant (artefact compliance) |

**Bypass CVE** : baisser `CveMaxSeverity: critical` dans `## Project
Config` (la décision est tracée en git blame). JAMAIS via `--force`.

---

## 7. Personnalisation (futur)

Cette stack est volontairement **non-personnalisable** dans v3.1.0
(pas de fichier de config par projet). Si un projet souhaite désactiver
une catégorie :

- **Workaround actuel** : retirer la ligne
  `- .claude/stacks/qa/code-quality.md` de `## Active QA Specs`
  → désactive le scan complet
- **Cible v3.2** : fichier de config par projet pour désactiver
  catégorie par catégorie (`disable: [magic-number, commented-code]`)

---

## 8. Pourquoi pas un LLM-based code review ?

Choix architectural fort de SDD_Pro v3.1.0 :

| Approche | Coût tokens | Faux positifs | Détecte vrais bugs |
|---|---|---|---|
| **Quality scan PowerShell** (cette stack) | **0** | bas | non (mais smells) |
| LLM code review "trouve les bugs" | ~30-50k / feature | ~30% | partiellement |
| Tests unitaires (autre stack QA) | ~5-8k / US | bas | **oui** |
| Linter / Type checker (stack-native) | 0 | bas | **oui** (compile-time) |

Les **vrais bugs** sont mieux détectés par :
1. **Tests unitaires** (exécution)
2. **Type checker** (compile-time, déterministe)
3. **Linter stack-native** (eslint, dotnet format, ruff, ktlint)

Les **code smells** sont mieux détectés par :
1. **Quality scan PowerShell** (déterministe, 0 token)
2. **SonarQube / Sonar Cloud** (intégration externe, hors scope)

Pas d'overlap inutile, pas de duplication de coût.

---

## 9. Performance

Sur un projet ~5000 LOC réparti en ~50 fichiers, le scan complet :
- **Durée** : < 1 seconde (PowerShell + regex)
- **Tokens** : 0
- **CPU** : faible (~1 cœur, pas de concurrence)
- **I/O** : 1 lecture par fichier source, 1 écriture quality.json

Coût négligeable comparé à un test runner (`dotnet test` ~10-30s).
