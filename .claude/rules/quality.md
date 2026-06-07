# Règle — Quality (Coverage + UI Tokens consolidée, v7.0.0)

> **v7.0.0 merge** : fusionne `qa-coverage.md` (QA test coverage seuil 80 %)
> + `ui-tokens.md` (variables CSS, anti-hex-hardcode). Stubs `qa-coverage.md` et `ui-tokens.md` **supprimés au sweep v7.0.0-alpha 2026-05-20** — tous les Read historiques pointent désormais directement ici.

## TOC

- **Partie A — QA Coverage** (§A.1-§A.8) : agent QA, seuil `CoverageMin`,
  schéma `coverage.json` normalisé, classes d'erreur `[QA_*]`.
- **Partie B — UI Tokens** (§B.1-§B.7) : agent dev-frontend, variables
  CSS, anti-hex-hardcode, classe `[UI_TOKEN_VIOLATION]`.
- **Partie C — Acceptance Gate** (§C.1-§C.7) : checks bloquants par projet
  (test/lint/build/coverage/smoke/E2E), hook `SubagentStop` matcher=qa,
  classe `[ACCEPTANCE_GATE_FAILED]`.

---

# Partie A — QA Coverage (seuil 80 %, schéma normalisé)

## A.1 Principe

L'agent QA mesure la couverture de tests de chaque feature livrée
contre un seuil déclaré dans `## Project Config` de `workspace/input/stack/stack.md`.
La métrique principale est le **pourcentage de lignes couvertes** sur
le périmètre de la feature courante.

Cette règle est **cross-stack** : elle s'applique de manière identique
que le projet utilise `coverlet` (.NET), `c8` (Node), `coverage.py`
(Python), `JaCoCo` (Kotlin), ou `istanbul` (Angular). La normalisation
se fait au niveau du schéma `coverage.json`.

## A.2 Configuration projet — `## Project Config`

```markdown
## Project Config
QAMode: full              # off | quality-only | tests-only | tests+coverage | full | manual
CoverageMin: 80           # OBLIGATOIRE, entier 0-100 — pas de défaut
```

| Clé | Obligatoire | Défaut | Range | Hors range / Absent |
|---|---|---|---|---|
| `QAMode` | non | `manual` | `off | quality-only | tests-only | tests+coverage | full | manual` | ERROR `[STACK_MALFORMED]` |
| `CoverageMin` | **OUI** | — (pas de défaut) | `0-100` | ERROR `[STACK_MALFORMED]` (absent OU hors range) |

`CoverageMin: 0` est valide (= seuil désactivé, métrique reportée mais
non bloquante même en WARNING) — c'est une **décision explicite** du
Tech Lead, pas un état par défaut.

**Décision SDD_Pro v6.1 (hardening)** : `coverage_lines_pct < CoverageMin`
produit un **🔴 RED bloquant** (`[QA_COVERAGE_GAP]`). La règle
antérieure v3.1.0 (WARN non bloquant) est révoquée — atteindre la
couverture est désormais une condition d'acceptation, pas un
"nice-to-have".

**Durcissement v6.10.1 (présence obligatoire)** : `CoverageMin` doit
figurer **explicitement** dans `## Project Config` (ou la couche
team/base si layered config activée). Absent → STOP + ERROR
`[STACK_MALFORMED]` dès la lecture du stack.md par `read_layered_config`.
Aucun défaut framework — l'omission ne peut plus passer pour un
"j'ai oublié, donc 80 par défaut". Le Tech Lead **décide et trace**
la valeur (y compris `0` pour bypass).

**Bypass explicite** :
- baisser `CoverageMin` dans `## Project Config` (décision tracée en git blame)
- mettre `CoverageMin: 0` (seuil désactivé, équivalent au mode v3.1.0)
- ne **JAMAIS** utiliser `--force` pour contourner — le bypass passe par
  la configuration

Précédence (cf. `error-classification.md §1.7`) :
```
[QA_TEST_FAILED] > [QA_COVERAGE_GAP]    (les deux RED, tests d'abord)
```

## A.3 Format `coverage.json`

L'agent QA écrit `workspace/output/qa/feat-{n}/coverage.json` :

```json
{
  "FEAT": "{n}-{FeatName}",
  "extractedAt": "2026-05-05T14:32:18Z",
  "stacks": [
    {
      "stack": "qa-dotnet-xunit",
      "tool": "coverlet",
      "toolVersion": "6.0.2",
      "tests": { "total": 47, "passed": 47, "failed": 0, "skipped": 0 },
      "coverage": {
        "lines":    { "covered": 1234, "total": 1500, "percent": 82.27 },
        "branches": { "covered": 100,  "total": 150,  "percent": 66.67 }
      },
      "files": [
        { "path": "workspace/output/src/SIMBackend/Services/AuthService.cs", "lines_pct": 90.00 }
      ]
    }
  ],
  "summary": {
    "total_tests": 47,
    "passed": 47,
    "failed": 0,
    "skipped": 0,
    "coverage_lines_pct": 82.27,
    "coverage_min": 80,
    "coverage_passed": true
  }
}
```

### A.3.1 Champs obligatoires

| Champ | Type | Description |
|---|---|---|
| `FEAT` | string | `{n}-{FeatName}` |
| `extractedAt` | ISO-8601 UTC | Timestamp de la mesure |
| `stacks[]` | array ≥ 1 | Une entrée par stack QA actif |
| `stacks[].stack` | string | Stack ID (`qa-dotnet-xunit`, etc.) |
| `stacks[].tool` | string | Tool de coverage (`coverlet`, `c8`, `JaCoCo`, …) |
| `stacks[].tests.{total,passed,failed,skipped}` | int | Compteurs de tests |
| `stacks[].coverage.lines.{covered,total,percent}` | nombres | Couverture lignes |
| `summary.total_tests` | int | Σ tests cross-stack |
| `summary.coverage_lines_pct` | float | Couverture globale (moyenne pondérée par LOC totales) |
| `summary.coverage_min` | int | Reflète `CoverageMin` du Project Config |
| `summary.coverage_passed` | bool | `coverage_lines_pct >= coverage_min` |

### A.3.2 Champs optionnels

| Champ | Quand présent |
|---|---|
| `stacks[].coverage.branches` | Si le tool supporte branches |
| `stacks[].files[]` | Si le tool fournit le détail per-fichier |

### A.3.3 Calcul de `summary.coverage_lines_pct`

Multi-stack : moyenne pondérée par LOC totales :
```
coverage_lines_pct = round(Σ(stack.lines.covered) / Σ(stack.lines.total) × 100, 2)
```

Mono-stack : `coverage_lines_pct = stacks[0].coverage.lines.percent`.

### A.3.4 Validation avant écriture

1. JSON parsable
2. Tous les champs §A.3.1 présents
3. Pour chaque stack, `coverage.lines.percent ≈ covered / total × 100` (tolérance ±0.1)
4. `summary.coverage_passed = (coverage_lines_pct >= coverage_min)`

Toute violation → ERROR `[QA_OUTPUT_INVALID]`. Le fichier coverage.json
N'EST PAS écrit (pas de fichier corrompu).

## A.4 Règles d'évaluation

### A.4.1 Métrique principale

```
summary.coverage_passed = (summary.coverage_lines_pct >= CoverageMin)
```

Si `false` → flag `[QA_COVERAGE_GAP]` **bloquant** dans le rapport.
Décision globale = `RED` (depuis v6.1 hardening).

### A.4.2 Threshold = 0

`CoverageMin: 0` skip le check (`coverage_passed = true` toujours).
Les autres classes (`[QA_TEST_FAILED]`) peuvent toujours flagger.

## A.5 Classes d'erreur QA

> **SSoT** : la taxonomie complète des 8 classes `[QA_*]` + l'ordre de
> priorité d'émission vit dans `@.claude/rules/error-classification.md §1.7`
> (audit MAJ-8, 2026-06-04 — dé-duplication entre les 2 rules pour
> éliminer le risque de drift sémantique). Cette section §A.5 conserve
> uniquement le **focus QA-spécifique** : les 2 classes que `qa` émet en
> propre (`[QA_TEST_FAILED]`, `[QA_COVERAGE_GAP]`) avec leur format ERROR
> illustré ci-dessous (§A.6).

## A.6 Format ERROR — exemples

### `[QA_COVERAGE_GAP]` (RED bloquant, depuis v6.1 hardening)

```
ERROR: feat 1-Auth — coverage gap
CAUSE: [QA_COVERAGE_GAP] lines coverage 62.45% below threshold 80% (8 files measured)
FIX: ajouter des tests dans workspace/output/src/SIMBackend.Tests/Services/ ciblant AuthService.RefreshToken
     OU baisser CoverageMin dans workspace/input/stack/stack.md ## Project Config (décision tracée)
```

### `[QA_TEST_FAILED]` (rouge)

```
ERROR: feat 1-Auth — tests failed
CAUSE: [QA_TEST_FAILED] 3 tests failed of 47 total — first failure at AuthServiceTests.cs:84 (Assert.Equal expected:200 actual:401)
FIX: inspect workspace/output/qa/feat-1/report.md, fix code via /dev-run 1 ou ajuster les tests
```

### `[QA_FRAMEWORK_MISSING]` (rouge)

```
ERROR: feat 1-Auth — framework missing
CAUSE: [QA_FRAMEWORK_MISSING] command 'dotnet test' failed (dotnet CLI not in PATH)
FIX: install .NET SDK from https://dot.net OR set dotnet in PATH
```

## A.7 Invariants

### A.7.1 `coverage.json` overwritten chaque run

Pas de merge avec un fichier précédent. Pas d'historique. Le fichier
reflète EXACTEMENT le dernier run. Historisation = service externe
(out of scope).

### A.7.2 Écriture atomique

Le fichier est écrit en `.coverage.json.tmp` puis renommé. Cela évite
qu'un kill du process laisse un JSON tronqué.

### A.7.3 Encodage et formatting

- UTF-8 sans BOM
- Indentation 2 espaces
- Clés ordonnées selon §A.3.1 (déterministe pour les diffs)

### A.7.4 Timestamps

`extractedAt` en UTC ISO-8601 avec `Z` final.

## A.8 Enforcement + non-scope

**Enforcement** :
- Agent QA charge cette règle en STEP 3 (chargement contexte)
- Script `parse_coverage.py` applique le format §A.3 et le calcul
  §A.3.3 sans intervention LLM (déterministe, 0 token)
- Commande `/qa-generate` propage le statut feature selon §A.4 + §A.5

**Ce que cette partie n'impose PAS** :
- Quel test runner / coverage tool utiliser (cf. `.claude/stacks/qa/*.md`)
- Le format intermédiaire produit par le tool (cobertura XML, lcov,
  json native) — `parse_coverage.py` normalise
- L'historisation (out of scope)
- L'intégration avec services externes (Codecov, SonarQube Cloud) — hors scope

---

# Partie B — UI Tokens (variables CSS, anti-hex-hardcode)

## B.1 Principe

Toute couleur, espacement, rayon ou typo de l'UI générée **DOIT** passer
par des **tokens CSS** (variables) et **JAMAIS** par des valeurs hex
hardcodées dans les composants. Cette discipline garantit :

1. **Fidélité au design** : la palette FEAT.md §8 et les mockups HTML
   se traduisent en un set fini de variables que tous les composants
   consomment.
2. **Theming multi-mode** : light/dark/HC via override des tokens à la
   racine `:root` / `[data-theme="dark"]`.
3. **Maintenance** : un changement de marque édite N tokens, pas N×100
   composants.

Cette règle est **load-bearing** pour l'agent `dev-frontend` et le
build_loop (un hex hardcode trouvé en STEP build → STOP +
`[UI_TOKEN_VIOLATION]`).

## B.2 Vocabulaire des tokens

Tokens normés (compatibles shadcn + Vuetify + Radzen) :

### B.2.1 Couleurs sémantiques
- `--background`, `--foreground` (page entière)
- `--card`, `--card-foreground`
- `--popover`, `--popover-foreground`
- `--primary`, `--primary-foreground`
- `--secondary`, `--secondary-foreground`
- `--accent`, `--accent-foreground`
- `--muted`, `--muted-foreground`
- `--destructive`, `--destructive-foreground`
- `--success`, `--warning`, `--info` (extensions projet)
- `--border`, `--input`, `--ring`

### B.2.2 Espacements
- `--radius` (rayon de base, dérivés `calc(var(--radius) - 2px)` etc.)
- Espacements via Tailwind scale (`gap-4`, `px-6`, …) — **pas de tokens
  dédiés** sauf cas exceptionnel.

### B.2.3 Typo
- `--font-sans`, `--font-mono` (déclarés `:root`, consommés par
  `font-family`)
- Tailles via Tailwind scale (`text-sm`, `text-lg`, …)

## B.3 Structure des fichiers (stack frontend)

| Stack | Fichier tokens | Convention |
|---|---|---|
| `react` + `shadcn` | `src/index.css` | `@layer base { :root { --background: 0 0% 100%; ... } }` (HSL space-separated, format shadcn) |
| `vue` + `vuetify` | `src/styles/theme.ts` | Object `{ light: { colors: { primary: "#...", ... } } }` consommé par `createVuetify` |
| `angular` + radzen | `src/styles.css` | `:root { --rz-primary: #...; }` (préfixes radzen) |
| `blazor-webassembly` + `radzen-blazor` | `wwwroot/css/site.css` | idem radzen |

L'agent `arch` génère le squelette de tokens lors du scaffold. L'agent
`dev-frontend` n'édite que `theme.css` / `index.css` pour matérialiser
la palette FEAT.md §8 — **jamais** les composants individuels.

## B.4 Override projet (FEAT-driven)

Quand FEAT.md §8 déclare une palette spécifique (couleurs marque,
typo, rayon), l'agent `dev-frontend` :

1. Mappe chaque token logique vers une valeur de la palette
2. Édite **uniquement** le fichier de tokens (cf. tableau §B.3)
3. Préserve les tokens shadcn/vuetify/radzen standards (override, pas
   remplacement intégral)
4. Documente le mapping dans un commentaire en tête de fichier

Exemple `src/index.css` (combo react+shadcn) :

```css
@layer base {
  :root {
    /* Tokens projet — override FEAT.md §8 palette "Nounou Care" */
    --background: 210 40% 98%;
    --foreground: 222 47% 11%;
    --primary: 217 91% 60%;          /* Bleu marque #2563eb */
    --primary-foreground: 0 0% 100%;
    --radius: 0.5rem;
    /* ... rest préservé du shadcn init standard */
  }

  [data-theme="dark"] {
    --background: 222 47% 11%;
    --foreground: 210 40% 98%;
    --primary: 217 91% 65%;
    /* ... */
  }
}
```

## B.5 Anti-patterns rejetés

| Anti-pattern | Détection | Fix |
|---|---|---|
| `style={{ color: "#2563eb" }}` inline | grep `#[0-9a-fA-F]{3,8}` dans composants | utiliser `text-primary` ou `bg-primary` |
| `className="bg-[#2563eb]"` Tailwind arbitrary value | grep `\[#[0-9a-fA-F]{3,8}\]` | déclarer token + utiliser `bg-primary` |
| `rgba(37, 99, 235, 0.5)` hardcode | grep `rgba?\(` dans composants | utiliser `bg-primary/50` Tailwind ou token alpha |
| Token redéfini par composant (`--my-blue: ...`) | grep `--[a-z-]+:` hors fichier tokens | déclarer au niveau `:root` global |
| CSS-in-JS (styled-components, emotion) avec hex | architecture | hors scope SDD_Pro — utiliser Tailwind + tokens |
| `!important` pour bypass cascade | grep `!important` | resoudre via spécificité ou token dédié |

## B.6 Vérification dev-frontend (STEP build / post-Edit)

```bash
# Cherche hex hardcode dans composants (hors fichier tokens)
grep -rE '#[0-9a-fA-F]{6}\b' workspace/output/src/{AppName}/src/components/ workspace/output/src/{AppName}/src/pages/ \
  | grep -v 'src/index.css\|src/styles/theme\|src/styles.css' \
  && ERROR [UI_TOKEN_VIOLATION]

# Cherche arbitrary values Tailwind avec hex
grep -rE 'bg-\[#|text-\[#|border-\[#' workspace/output/src/{AppName}/src/ \
  && ERROR [UI_TOKEN_VIOLATION]
```

### Format ERROR `[UI_TOKEN_VIOLATION]`

```
ERROR: dev-frontend {n}-{m} — hex hardcode dans composant
CAUSE: [UI_TOKEN_VIOLATION] {path}:{line} contient {hex} au lieu d'un token
FIX: déclarer le token dans src/index.css :root (ou theme.ts) puis
     remplacer par bg-primary / text-foreground / etc. (cf. quality.md §B.2)
```

## B.7 Test d'acceptation + liens

Toute FEAT §8 (palette projet) doit produire un PR diff visible **uniquement**
dans le fichier de tokens (§B.3) + éventuellement quelques composants qui
référencent de nouveaux tokens projet. Si le diff touche > 3 composants
avec des hex différents → violation §B.5.

**Liens avec autres règles** :
- `docs/principles/source-first.md` : tout bug de fidélité visuelle →
  patcher cette règle (si gap) AVANT le composant.
- `ownership.md §1` (Partie A) : seul `dev-frontend` édite `theme.css` /
  `index.css` (réservé en augment, pas réécriture intégrale).
- Stacks UI : `stacks/ui/shadcn.md §3`, `vuetify.md §3`,
  `radzen-blazor.md §3` inlinent la syntaxe spécifique. Cette partie
  est la spec cross-stack.

---

# Partie C — Acceptance Gate obligatoire (v7.0.0-alpha audit P5 — 2026-06-05)

## C.1 Principe

Tout projet généré (`workspace/output/src/{AppName|BackendName}`) **DOIT** respecter une **acceptance gate** finale avant tag "FEAT delivered". Cette gate est :

- **Bloquante** : si un check échoue, le verdict global passe 🔴 RED et la FEAT n'est pas validée.
- **Belt + braces** : (a) règle documentée ci-dessous (lecture humaine, prompt agents) + (b) hook enforcement (`SubagentStop` matcher `qa`) automatique.

## C.2 Checks obligatoires par type de projet

### Pour TOUT projet (4 checks minimum)

| Check | Commande (Node) | Commande (.NET) | Commande (Kotlin) | Commande (Python) |
|---|---|---|---|---|
| `test` | `npm test` | `dotnet test` | `./gradlew test` | `pytest` |
| `lint` | `npm run lint` | `dotnet format --verify-no-changes` | `./gradlew ktlintCheck` | `ruff check` |
| `build` | `npm run build` | `dotnet build --nologo` | `./gradlew build` | `python -m build` ou `python -c "import app.main"` |
| `coverage ≥ threshold` | `npm run test:coverage` | `dotnet test /p:CollectCoverage=true` | `./gradlew jacocoTestReport` | `pytest --cov` |

### Pour projet UI (front SPA ou fullstack rendant du HTML)

**+2 checks** obligatoires :

| Check | Description |
|---|---|
| `smoke browser` | démarrage `npm run dev` + `curl http://localhost:{port}/ → 200 size>500` (preuve UI servie) |
| `E2E Playwright ≥ 1` par FEAT UI | au moins 1 spec `*.spec.ts` qui simule un utilisateur réel (click Calculate, vérifier C affiché) |

## C.3 Configuration `## Project Config` (stack.md)

```yaml
AcceptanceGate: strict        # strict (default v7.0.0) | warn | off
AcceptanceGate.RequireE2E: true   # E2E Playwright obligatoire pour UI
AcceptanceGate.SmokeTimeout: 10   # secondes pour curl smoke
AcceptanceGate.MinCoverage: 80    # même seuil que CoverageMin (alias)
```

## C.4 Verdict + ERROR format

```
🔴 RED AcceptanceGate
CAUSE: [ACCEPTANCE_GATE_FAILED] {projet} échec sur {check}
  - npm test : {N failed tests} OR exit ≠ 0
  - npm run lint : {N errors} OR script absent
  - npm run build : exit ≠ 0
  - smoke browser : http {code} OR timeout
  - E2E Playwright : {N specs OR 0} (RequireE2E=true)
FIX: corriger le check fail listé, OU baisser AcceptanceGate strict→warn dans Project Config (décision tracée)
```

## C.5 Hook enforcement (`SubagentStop` matcher `qa`)

Le script `.claude/python/sdd_hooks/validate_acceptance_gate.py` (créé audit P5) tourne automatiquement après l'agent `qa`. Lit `stack.md` Project Config, parcourt tous les projets sous `workspace/output/src/*`, applique les checks par type détecté (`package.json` → Node, `*.csproj` → .NET, `build.gradle.kts` → Kotlin, `pyproject.toml` ou `requirements.txt` → Python).

Bypass : `SDD_ALLOW_ACCEPTANCE_BYPASS=1` (debug uniquement, audit-loggué).

## C.6 Anti-patterns rejetés

- ❌ `package.json` sans script `test` ni `lint` (le projet doit déclarer ses gates même si vides)
- ❌ Tests qui passent mais 0 assertions (couvert par `--coverage`)
- ❌ Lint avec règles désactivées massivement (audit `.eslintignore` / `pyproject.toml` lint config)
- ❌ E2E Playwright bidons (mock 100%, aucun click réel) — règle `RequireE2E.AssertsRealUserPath`
- ❌ Build green mais runtime fail (smoke browser couvre)

## C.7 Lien avec autres règles

- `quality.md §A` (coverage seuil) : déjà couvert, AcceptanceGate inclut `coverage_passed`
- `build-and-loop.md §A` (API Gate) : couvre déjà les tests d'intégration HTTP runtime, **AcceptanceGate inclut API Gate** sur back+front projects
- `library-and-stack.md §7` (5 pièges runtime documentés) : à vérifier en lint OU en review humaine (pas auto)

