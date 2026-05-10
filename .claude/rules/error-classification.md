# Règle — Error Classification (vocabulaire d'erreur unifié cross-agent)

## Principe

Tous les agents et scripts du framework SDD_Pro utilisent un **vocabulaire
d'erreur normalisé** dans leurs blocs ERROR. Ce vocabulaire est exposé sous
forme de **préfixes entre crochets** dans le champ `CAUSE:`, permettant à un
parser externe (CI, dashboard, monitoring) ou à `build_loop` de classer les
erreurs sans interprétation textuelle.

Cette règle unifie les classifications historiques dispersées dans :
- `stack-completeness.md` : `[STACK_LIBRARY_MISSING]`
- `file-ownership.md` : `[LIBNAME_LOCK_HELD]`, `[LIBNAME_SIGNATURE_CONFLICT]`
- `qa-coverage.md` : `[QA_TEST_FAILED]`, `[QA_COVERAGE_GAP]`, etc.
- `qa-ownership.md` : `[QA_OWNERSHIP_VIOLATION]`
- `responsibilities.md §12` : `[FRONTEND_BACKEND_CONTRACT_GAP]`
- `ui-mandatory.md` (legacy) : `[UI_*]`

---

## 1. Taxonomie des classes d'erreur

### 1.1 Classes runtime (env, infra, dépendances)

| Préfixe | Quand l'utiliser | Phase concernée |
|---|---|---|
| `[NETWORK]` | Timeout, firewall, VPN, service unreachable | DB scan, smoke check, package fetch |
| `[AUTH]` | Login failed, expired token, invalid credentials | DB scan, gh CLI, npm publish |
| `[PERMISSION]` | User sans droits SELECT, FS read-only, sudo required | DB scan, FS write, init project |
| `[NOT_FOUND]` | Database / file / package / endpoint absent | DB scan, file lookup, dep install |
| `[TIMEOUT]` | Smoke check timeout, build_loop timeout, command timeout | Smoke, build_loop, init |
| `[DISK]` | No space left, disk full, FS error | File write, build artifacts |
| `[ENV_MISSING]` | Required environment variable absent | DB env vars, secrets |

### 1.2 Classes pipeline (logique framework)

| Préfixe | Quand l'utiliser | Phase concernée |
|---|---|---|
| `[STACK_MALFORMED]` | `stack.md` invalide, section manquante, path inexistant | arch STEP 1 |
| `[SCHEMA_MISMATCH]` | Table/colonne absente de `workspace/output/db/schema.json` | dev-backend STEP 4.5 |
| `[SPEC_REJECTED]` | SPEC ne respecte pas le format attendu | po STEP 2 |
| `[GRANULARITY_VIOLATION]` | > 6 US, anti-pattern detecte | po STEP 5.0 |
| `[TRACEABILITY_GAP]` | SFD/AC/BR/FD non couvert par une US | po STEP 5.5 |
| `[READINESS_NO_GO]` | `/spec-validate` retourne NO-GO sans `--force` | spec-validate |

### 1.3 Classes contrat (preserves/adds, layers, ownership)

| Préfixe | Quand l'utiliser | Phase concernée |
|---|---|---|
| `[PRESERVES_VIOLATED]` | Identifier `preserves:` retire apres augmentation | dev-* post-Edit |
| `[ADDS_VIOLATED]` | Identifier `adds:` non present apres ecriture | dev-* post-Edit |
| `[LAYER_VIOLATION]` | Code dans une couche interdite (ex. business in UI) | dev-* STEP build |
| `[FILE_OWNERSHIP]` | Agent écrit dans path interdit par `file-ownership.md §1` | hook SubagentStop |
| `[STATUS_FLIP_FAILED]` | `Status: Done` flip pas persiste sur disque | dev-* post-write |

### 1.4 Classes build (compile / lint / type)

| Préfixe | Quand l'utiliser | Phase concernée | Comportement |
|---|---|---|---|
| `[BUILD_CORRECTIBLE]` | Erreur que `build_loop` peut iterer (import, typo, override, nullability, DI signature) | dev-* STEP build | itère (max `BuildLoopMaxIter`) |
| `[BUILD_BLOCKING]` | Erreur architecturale, non-iterable | dev-* STEP build | **fail-fast immédiat** |
| `[DEP_MISSING]` | Package non installe, requiert intervention Tech Lead | dev-* STEP build | fail-fast |
| `[CIRCULAR_DEP]` | Dependance circulaire entre layers / projets | dev-* STEP build | fail-fast |

**Règle critique** : `build_loop` NE DOIT PAS itérer sur `[BUILD_BLOCKING]`,
`[DEP_MISSING]`, ou `[CIRCULAR_DEP]`. Ces classes signalent un problème
structurel qui ne sera pas résolu par une nouvelle tentative — fail-fast.

### 1.5 Classes anti-derive (scope expansion)

| Préfixe | Quand l'utiliser | Phase concernée |
|---|---|---|
| `[DERIVE_VIOLATION]` | Agent ajoute une feature non scopée par US/SPEC | dev-*, qa |
| `[REFACTOR_HORS_SCOPE]` | Rename/move/extract non demandé | dev-* post-Edit |
| `[OPTIMIZATION_PROACTIVE]` | HashSet/index/async non déclaré | dev-* post-Edit |
| `[UNDECLARED_DECISION]` | Pattern/lib/convention non déclaré dans stack | dev-* STEP 5 |
| `[STACK_LIBRARY_MISSING]` | Lib hors §2.4 du stack actif (cf. `stack-completeness.md`) | dev-*, qa |

### 1.6 Classes UI (fidélité HTML mockup → code)

| Préfixe | Quand l'utiliser | Phase concernée |
|---|---|---|
| `[UI_FIDELITY_GAP]` | Libellé/structure du HTML source absent du markup généré | dev-frontend STEP 11 |
| `[UI_TOKEN_VIOLATION]` | Hex hardcode dans CSS isolé au lieu de `var(--*)` | dev-frontend post-Edit |
| `[FRONTEND_BACKEND_CONTRACT_GAP]` | Route HTTP frontend vise un endpoint backend inexistant | dev-frontend STEP 5 |

### 1.7 Classes QA (tests unitaires + coverage + API gate + quality)

| Préfixe | Quand l'utiliser | Phase concernée |
|---|---|---|
| `[QA_TEST_FAILED]` | Au moins un test unitaire échoue → décision RED | qa STEP 5 |
| `[QA_COVERAGE_GAP]` | `coverage_lines_pct < CoverageMin` → décision YELLOW | qa STEP 6 |
| `[QA_FRAMEWORK_MISSING]` | Test runner CLI absent OU `## Active QA Specs` vide | qa STEP 2 / 5 |
| `[QA_INIT_FAILED]` | Bootstrap test project échoue | qa STEP 2.5 |
| `[QA_TEST_INVALID]` | Forbidden patterns détectés (sleep, DB réelle, état partagé) | qa STEP 3 / 4 |
| `[QA_OUTPUT_INVALID]` | `coverage.json` ou `quality.json` non-parseable | qa STEP 7 |
| `[QA_PRECONDITION_FAILED]` | SPEC/US/code production absents | qa STEP 0.4 |
| `[QA_OWNERSHIP_VIOLATION]` | Agent dev-* écrit fichier de test, OU agent qa écrit code prod | dev-*, qa |
| `[API_GATE_RED]` | API Gate (cf. `backend-first.md`) retourne RED, frontend bloqué | dev-run phase 4c |

Ordre de priorité d'émission (une seule classe primaire émise) :
```
[QA_TEST_FAILED] > [QA_COVERAGE_GAP]
[API_GATE_RED] > tout autre QA_*
```

### 1.8 Classes parallélisme (file ownership / locks)

| Préfixe | Quand l'utiliser | Phase concernée |
|---|---|---|
| `[LIBNAME_LOCK_HELD]` | Lock file LibName détenu par autre agent (cf. `file-ownership.md §4`) | dev-* STEP write LibName |
| `[LIBNAME_SIGNATURE_CONFLICT]` | DTO/Model partagé avec signatures divergentes entre agents | dev-* STEP write LibName |

### 1.9 Classe inconnue

| Préfixe | Quand l'utiliser | Phase concernée |
|---|---|---|
| `[UNKNOWN]` | Erreur non classifiable (stderr brut, exception non gérée) | Tous |

---

## 2. Format obligatoire dans le bloc ERROR

### Format chat (compressé, cf. `chat-output.md`)
```
🔴 {agent} {n}-{m} — {résumé}
CAUSE: [{CLASS}] {détail concis 1 ligne} → {pointer fichier rapport}
```

### Format rapport (3 lignes, dans `workspace/output/qa/...`, `validation/...`)
```
ERROR: {feat/us/task or pipeline-step} failed
CAUSE: [{CLASS}] {detail concis 1 ligne}
FIX: {action 1 ligne}
```

### Exemples

**`[BUILD_CORRECTIBLE]`** (build_loop itère) :
```
ERROR: dev-backend 1-2 build failed (iter 1/3)
CAUSE: [BUILD_CORRECTIBLE] missing import 'SIM.Backend.Services.IBebeService' in BebesEndpoints.cs:1
FIX: add 'using SIM.Backend.Services;' OR re-run after dep task fixes namespace
```

**`[BUILD_BLOCKING]`** (fail-fast) :
```
ERROR: dev-frontend 2-1 build failed (iter 1/3)
CAUSE: [BUILD_BLOCKING] business logic detected in Pages/Login.razor (DbContext usage in UI layer)
FIX: move data access to Services/AuthService.cs, inject via DI in code-behind
```

**`[STACK_LIBRARY_MISSING]`** :
```
ERROR: dev-backend 1-3 — librairie manquante
CAUSE: [STACK_LIBRARY_MISSING] besoin de EPPlus pour AC-3 (export Excel) absent §2.4
FIX: ajouter EPPlus 7.4.0 dans .claude/stacks/backend/dotnet-minimalapi.libs.json + sync-stack-md.ps1
```

**`[FILE_OWNERSHIP]`** (détecté par hook) :
```
ERROR: dev-backend 1-2 — violation ownership
CAUSE: [FILE_OWNERSHIP] dev-backend a écrit workspace/output/src/{AppName}/Pages/Login.razor (territoire dev-frontend)
FIX: déplacer la génération vers dev-frontend OU corriger le plan de la US
```

---

## 3. Comportement de `build_loop` selon classe

| Classe | Itération | Action |
|---|---|---|
| `[BUILD_CORRECTIBLE]` | OUI (max `BuildLoopMaxIter`, défaut 3) | Re-dispatcher l'agent avec stderr en input |
| `[BUILD_BLOCKING]` | NON | STOP immédiat, ERROR au Tech Lead |
| `[DEP_MISSING]` | NON | STOP, FIX = installer la dep côté Tech Lead |
| `[CIRCULAR_DEP]` | NON | STOP, FIX = arbitrage architectural |
| `[LAYER_VIOLATION]` | NON | STOP, FIX = repenser la US |
| `[PRESERVES_VIOLATED]` | NON | STOP, FIX = re-dispatcher en révisant le plan |
| `[STACK_LIBRARY_MISSING]` | NON | STOP, FIX = mettre à jour `.libs.json` du stack |
| `[FILE_OWNERSHIP]` | NON | STOP, FIX = corriger le plan |
| `[UI_FIDELITY_GAP]` | NON (un seul retry après revue plan) | WARNING ou STOP selon score |

---

## 4. Enforcement

- **Tous les agents** (po, arch, dev-backend, dev-frontend, qa, elicitor,
  dashboard) chargent cette règle en STEP de chargement contexte.
- **Tous les scripts** (`preflight.ps1`, `validate-readiness.ps1`,
  `parse-coverage.ps1`, `quality-scan.ps1`, `validate-fidelity.ps1`,
  `validate-augment-contract.ps1`, `audit-file-ownership.ps1`) émettent
  des préfixes `[CLASS]` dans leurs sorties.
- **Hooks** (`PostToolUse`, `SubagentStop`, `Stop`) lisent les classes
  pour décider de l'action (continuer / append warning / STOP).
- Une erreur sans préfixe `[CLASS]` est tolérée (backward-compat) mais
  considérée comme `[UNKNOWN]` par les parsers.

---

## 5. Agents qui chargent cette règle

| Agent | STEP de chargement | Usage principal |
|---|---|---|
| `po` | STEP 3 contexte | Émission `[SPEC_REJECTED]`, `[GRANULARITY_VIOLATION]`, `[TRACEABILITY_GAP]` |
| `arch` | STEP 0 contexte | Émission `[STACK_MALFORMED]`, `[SCHEMA_MISMATCH]`, `[NETWORK]`, `[AUTH]`, `[PERMISSION]`, `[ENV_MISSING]` |
| `dev-backend` | STEP 3 contexte | Émission `[BUILD_*]`, `[LAYER_VIOLATION]`, `[STACK_LIBRARY_MISSING]`, `[DERIVE_*]`, `[LIBNAME_*]`, `[QA_OWNERSHIP_VIOLATION]` |
| `dev-frontend` | STEP 3 contexte | Émission `[BUILD_*]`, `[UI_*]`, `[FRONTEND_BACKEND_CONTRACT_GAP]`, `[STACK_LIBRARY_MISSING]`, `[DERIVE_*]` |
| `qa` | STEP 3 contexte | Émission `[QA_*]`, `[API_GATE_RED]`, `[STACK_LIBRARY_MISSING]` |
| `elicitor` | (read passif) | Pas d'émission propre |
| `dashboard` | (read passif) | Lit les classes dans les rapports pour visualisation |

---

## 6. Ce que cette règle n'impose PAS

- Une syntaxe stricte de localisation (`file:line:col`) — laissée au choix
  de chaque agent selon le toolchain de la stack.
- Une trace stack complète dans le `CAUSE:` — interdit (1 ligne max).
- Une classification multi-classes (une erreur = UNE classe principale).
- Une remontée structurée JSON — out of scope (le framework reste lite).

---

## 7. Règle mentale

**"Avant d'émettre un ERROR, je vérifie qu'il a un préfixe `[CLASS]` dans
le `CAUSE:`. Si aucune classe ne matche, j'utilise `[UNKNOWN]` plutôt
que rien."**

La discipline des préfixes permet à `build_loop` de décider
mécaniquement, aux scripts de classer sans LLM, et au dashboard de
visualiser les pannes par cause-racine.
