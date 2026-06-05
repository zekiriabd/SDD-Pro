# Règle — Build & Loop (Backend-First gate + Dev-shared patterns, consolidated v7.0.0)

> **v7.0.0 merge** : fusionne `backend-first.md` (API Gate in-memory
> gated workflow back→front) + `dev-shared.md` (patterns dev-backend
> / dev-frontend identiques : context budget, path safety, mode detect,
> LibName lock, plan construction). Stubs `backend-first.md` et
> `dev-shared.md` **supprimés au sweep v7.0.0-alpha 2026-05-20** — tous
> les Read `@.claude/rules/{backend-first,dev-shared}.md` historiques
> dans agents/commands/python pointent désormais directement ici.

## TOC

- **Partie A — Backend-First Gated Workflow** (§1–§5)
  - §1 Phase QA API Gate (cas testés, fixtures in-memory, statuts PASS/WARN/FAIL/SKIPPED/INFRA_BLOCKED)
  - §2 Boucle correction FAIL → PASS
  - §3 Configuration (GatedWorkflow, ApiGateRequired, ApiGateMinPerEndpoint)
  - §4 Localisation des tests
  - §5 Anti-patterns
- **Partie B — Dev-shared patterns cross-agent** (§1–§9)
  - §1 Context budget HARD-GATE (STEP 0.5)
  - §1.bis Path safety Front/Back isolation (STEP 1.bis)
  - §1.ter Mode detection From Plan (STEP 1)
  - §2 LibName lock procédure
  - §2.bis Atomic write — anti-corruption crash mid-write
  - §3 Anti-derive bullets dev-*
  - §3.bis Anti-derive universels cross-agent
  - §4 QA-ownership forbidden patterns
  - §5 Stack-completeness
  - §6 BREAKING CHANGES cleanup post-build
  - §7 Plan construction v1/v2 + dispatch From Plan
  - §8 Read on-demand
  - §9 Enforcement

---

# Partie A — Backend-First Gated Workflow

## Principe

`/dev-run {n}` (et donc `/sdd-full {n}`) exécute `dev-backend` puis
`dev-frontend` **en séquence stricte**, séparés par une **API Gate** :

```
arch + DB → dev-backend ALL US → QA API Gate (in-memory) → dev-frontend ALL US
                                       │
                                       └─ 🔴 RED → STOP, l'humain corrige et relance
```

Frontend consomme les routes backend par contrat. Tant que les endpoints ne
sont pas vérifiés runtime, générer le frontend est prématuré (chaque
mismatch = 4xx/5xx silencieux). Mode **non opt-in** depuis 2026-05-07.

---

## 1. Phase « QA API Gate »

### 1.1 Cas testés (par endpoint)

| Type | Cas |
|---|---|
| Happy | GET liste paginée → 200 ; GET by id → 200 ; POST → 201 + Location ; PUT → 200 ; DELETE → 204 puis GET → 404 |
| Négatif | GET id inexistant → 404 ; body invalide → 400 ProblemDetails ; sans Bearer → 401 ; scope manquant → 403 |

### 1.2 Fixtures (in-memory only, jamais la DB réelle)

| Stack QA | Stratégie |
|---|---|
| `qa/dotnet-xunit` | `WebApplicationFactory` + EF Core InMemory (DbContext remplacé via `services.RemoveAll`) |
| `qa/node-vitest` | `supertest` + Prisma SQLite `:memory:` ou mocks `PrismaClient` |
| `qa/python-pytest` | `httpx.AsyncClient(app=app)` + SQLAlchemy SQLite `:memory:` (override `get_db`) |
| `qa/kotlin-junit` | `MockMvc` + `@DataJpaTest` H2 in-memory |

**Seed** : 3-5 lignes par entité, IDs déterministes (1, 2, 3). **Auth** : JWT
mocké via `TestAuthHandler` (ClaimsPrincipal pré-rempli). **Jamais** d'appel
Azure AD réel.

### 1.3 Statuts normalisés (v7.0.0) et critère de passage

**5 statuts explicites** (canoniques depuis v7.0.0) — remplacent l'ancien
triplet `GREEN/YELLOW/RED` qui était ambigu sur "rien à tester" vs
"runtime cassé". Mapping vieux → nouveau garanti par le template api-tests
(champ `verdict` legacy conservé en parallèle de `status` canonique).

| `status` (canonique) | `verdict` legacy | Sens opérationnel | Action `/dev-run` STEP 6.b |
|---|---|---|---|
| **`PASS`**          | `GREEN`  | tous tests OK + `total >= MIN_PER_ENDPOINT × N_endpoints` | continue 6c (dev-frontend) |
| **`WARN`**          | `YELLOW` | tests OK mais `total < MIN_PER_ENDPOINT × N_endpoints` (couverture endpoints partielle) | continue 6c + WARNING |
| **`FAIL`**          | `RED`    | ≥ 1 test failed (mismatch contrat back↔front) | STOP + boucle correction §2 |
| **`SKIPPED`**       | `n/a`    | aucun endpoint à tester (FEAT frontend-pure) OU `ApiGateRequired: false` ET `GatedWorkflow: false` | continue 6c silencieusement |
| **`INFRA_BLOCKED`** | `n/a`    | test runner absent (`[QA_FRAMEWORK_MISSING]`), fixtures non utilisables (`[QA_INIT_FAILED]`), DB in-memory KO | STOP + ERROR `[QA_FRAMEWORK_MISSING]` (pas une régression code — config infra à corriger) |

**Critère arithmétique de `status`** :
```
status = "INFRA_BLOCKED"  if test runner unusable OR fixtures init failed
status = "SKIPPED"        elif N_endpoints == 0 OR (ApiGateRequired=false AND GatedWorkflow=false)
status = "FAIL"           elif failed >= 1
status = "PASS"           elif total >= MIN_PER_ENDPOINT × N_endpoints
status = "WARN"           else   # tests OK mais couverture partielle
```

`MIN_PER_ENDPOINT = 2` (1 happy + 1 négatif min). Ordre d'évaluation
**fail-fast** : INFRA_BLOCKED court-circuite tout (la qualité du test
runner conditionne tout signal en aval).

**Champ booléen dérivé** (conservé pour callers legacy) :
```
gate_passed = (status in {"PASS", "WARN", "SKIPPED"})
```
Note : `WARN` reste `gate_passed: true` (continue) mais propage l'avertissement
au verdict QA global. `INFRA_BLOCKED` n'est **jamais** considéré PASS — c'est
un gating bloquant distinct d'un FAIL fonctionnel (sémantique : "je n'ai
pas pu tester", pas "le code est cassé"). Cette distinction évite que
build_loop itère inutilement sur un environnement de test cassé.

### 1.4 Rapport

`workspace/output/qa/feat-{n}/api-tests.json` — schéma :
`endpoints[].{verb, route, tests:{total,passed,failed}, cases[]}`
+ `summary.{endpoints_total, tests_total, tests_passed, tests_failed,
min_per_endpoint, min_per_endpoint_required, gate_passed, status, verdict}`.

- `status` (canonique v7.0.0) : `PASS | WARN | FAIL | SKIPPED | INFRA_BLOCKED`
- `verdict` (legacy, conservé) : `GREEN | YELLOW | RED` (mapping §1.3)
- `gate_passed` (booléen dérivé) : `true` ssi status ∈ {PASS, WARN, SKIPPED}

Les callers v7.0.0+ **doivent lire `status`** (sémantique fine).
Les callers legacy peuvent lire `verdict` ou `gate_passed`.

---

## 2. Boucle correction FAIL → PASS

1. Consulter `api-tests.md` (par endpoint en échec)
2. Corriger : (a) `/dev-backend {n}-{m}` (idempotent), (b) édit manuel
   backend, ou (c) édit test (QA ownership, dans `*.Tests/Api/`)
3. Re-tester : `/qa-generate {n} --mode api-tests [--filter {endpoint}]`
4. `status: PASS` → relancer `/dev-run {n}` (idempotent : skip backend si stable)

> Boucle **non applicable** sur `status: INFRA_BLOCKED` — corriger la
> config infra (test runner, fixtures, DB in-memory) avant tout retry.

---

## 3. Configuration

```yaml
GatedWorkflow: true       # default — cette règle
ApiGateRequired: true     # default — false = WARN au lieu de RED
ApiGateMinPerEndpoint: 2  # default
```

`GatedWorkflow: false` = legacy parallèle (audit log
`workspace/output/.sys/.audit/legacy-parallel.log`). Déconseillé.

**Indépendance de `QAMode`** : la gate API (Phase 4) tourne toujours quand
`GatedWorkflow: true`, indépendamment de `QAMode` (qui pilote uniquement la
Phase 5 tests unitaires + coverage). `QAMode: off` ne désactive **pas** la
gate API ; pour la désactiver, utiliser `GatedWorkflow: false`.

---

## 4. Localisation des tests

```
workspace/output/src/{BackendName}.Tests/
├── Unit/                  # tests unitaires (qa-coverage.md)
└── Api/                   # tests intégration HTTP (cette règle)
    ├── Fixtures/          # TestWebApplicationFactory, TestAuthHandler, SeedData
    └── *EndpointsTests.cs
```

Dossier `Api/` généré uniquement si endpoints HTTP existent.

---

## 5. Anti-patterns

- ❌ dev-frontend avant que la gate passe
- ❌ Tester contre la DB réelle (toujours in-memory/mock)
- ❌ Bypass gate (`--no-validate` couvre `/feat-validate`, pas la gate API)
- ❌ Fixtures hors entités scaffoldées par arch
- ❌ Auth Azure AD réelle dans les tests

---

# Partie B — Dev-shared patterns (dev-backend / dev-frontend)

## Principe

Patterns opérationnels strictement identiques entre `agents/dev-backend.md`
et `agents/dev-frontend.md`. Hérités par référence
(`@.claude/rules/build-and-loop.md`) plutôt que dupliqués. Évolution centrée ici.

**Périmètre** : fragments **vraiment identiques** (exit codes, scripts,
format ERROR). Fragments asymétriques (paths front/back, preflight,
mapping HTML→DS) restent inlinés dans chaque agent.

---

## 1. Pattern context budget (HARD-GATE STEP 0.5)

**SSoT pour les 11 agents** (`po`, `arch`, `dev-backend`, `dev-frontend`,
`qa`, `elicitor`, `code-reviewer`, `security-reviewer`,
`spec-compliance-reviewer`, `arch-reviewer`, `adversarial-reviewer`).
`constitutioner` hérite du budget de `arch` (Phase B). Avant tout `Read`
hors preflight, exécuter :

```bash
python .claude/python/sdd_scripts/context_budget.py \
  --agent {agent-id} \
  [--feat-number {n}] [--us-id {n}-{m}]
```

| Agent | Flags requis |
|---|---|
| `arch` | `--agent arch` (pas de `--feat-number` — niveau projet) |
| `dev-backend`, `dev-frontend` | `--agent {dev-*} --feat-number {n} --us-id {n}-{m}` |
| `po`, `qa`, `elicitor`, *-reviewer | `--agent {agent-id} --feat-number {n}` |

Exit non-zero → STOP. Le ledger est écrit dans
`console.db` (table `context_budget`, v6.10 SSoT). Hoist v7.0.0-alpha
(audit CRIT-9, 2026-06-04) — chacun des 9 agents non-dev se contentait
de dupliquer cette substance (~9 L × 9 = ~80 L). Désormais ils
référencent ce §1 directement avec leur `--agent` en dur.

---

## 1.bis Pattern path safety — Front/Back isolation (STEP 1.bis)

**Bloquant avant tout Write/Edit sous `workspace/output/src/`.** Récupérer
`AppName` et `BackendName` depuis `## Project Config` (lu par preflight).

Pour **chaque** path à écrire, appliquer la matrice selon la famille :

| Agent | Path autorisé (root) | Segments interdits |
|---|---|---|
| `dev-backend` | `workspace/output/src/{BackendName}/` ou `workspace/output/src/{LibName}/` (si `LibStrategy=shared`) | `/{AppName}/` imbriqué ; `{BackendName}/Kotlin/{AppName}/`, `{BackendName}/web/`, `{BackendName}/front/`, `{BackendName}/spa/` |
| `dev-frontend` | `workspace/output/src/{AppName}/` (littéral, case-sensitive) | `/{BackendName}/` imbriqué ; `{BackendName}/Kotlin/`, `{BackendName}/web/`, `{BackendName}/front/` |

Si violation → STOP + ERROR :
```
ERROR: {agent} {n}-{m} — path interdit
CAUSE: [FILE_OWNERSHIP_NESTED] tentative d'écrire {path} (front imbriqué dans back ou inverse)
FIX: écrire sous workspace/output/src/{AppName|BackendName}/ AU MÊME NIVEAU, jamais imbriqué
```

**Création répertoire** : si le parent n'existe pas, `mkdir -p`
implicite — APRÈS validation du pré-check.

Détail règle : `@.claude/rules/ownership.md §1.bis`.

---

## 1.ter Pattern mode detection (STEP 1)

Détecte le mode d'exécution dev-* via Glob unique. Variables `PLAN_ONLY`
et `{Name}` (et `HTML_PATH` côté frontend) déjà définies par STEP 0
HARD-GATE Phase A.

### 1.ter.1 Suffixe Glob par famille

| Agent | Glob | Description |
|---|---|---|
| `dev-backend` | `workspace/output/plans/{n}-{m}-*.back.md` | Plan backend pré-généré par `/dev-plan` |
| `dev-frontend` | `workspace/output/plans/{n}-{m}-*.front.md` | Plan frontend pré-généré par `/dev-plan` |

### 1.ter.2 Résolution

- 1 fichier match → `FROM_PLAN_PATH = chemin matché`
- 0 fichier → `FROM_PLAN_PATH = null`
- ≥ 2 fichiers (collision basename) → STOP + ERROR `[INVALID_MODE]`

### 1.ter.3 Exclusion mutuelle avec `PLAN_ONLY`

Si `FROM_PLAN_PATH != null` ET `PLAN_ONLY = true` → STOP + ERROR :
```
ERROR: {agent} {n}-{m} — modes incompatibles
CAUSE: [INVALID_MODE] mode :plan invoqué alors qu'un plan {n}-{m}-*.{back|front}.md existe déjà
FIX: soit drop le suffixe `:plan`, soit supprimer le plan existant
```

### 1.ter.4 Modes en sortie

| Condition | Mode | Comportement aval |
|---|---|---|
| `PLAN_ONLY = false`, `FROM_PLAN_PATH = null` | **Normal (inline)** | plan inline + génération code + build (+ fidelity check côté frontend) |
| `PLAN_ONLY = true` | **Plan Only** | produit `workspace/output/plans/{n}-{m}-{Name}.{back\|front}.md` et STOP avant génération code (utilisé par `/dev-plan`) |
| `FROM_PLAN_PATH != null` | **From Plan** | lecture du plan existant au lieu de re-planifier inline (utilisé automatiquement par `/dev-run` après `/dev-plan`) |

### 1.ter.5 Invariant

L'agent ne traite **jamais** plusieurs US dans la même invocation —
un seul `{n}-{m}` par run.

---

## 2. Pattern LibName lock (avant tout Write sous `workspace/output/src/{LibName}/`)

```bash
python .claude/python/sdd_scripts/acquire_libname_lock.py \
  --lib-path "workspace/output/src/{LibName}" \
  --entity "{Entity}" \
  --agent-id "{dev-backend|dev-frontend}-{n}-{m}"
```

| Exit | Sens | Action agent |
|---|---|---|
| `0` | ACQUIRED (création ou re-entrant même agent) ou RELEASED | écrire le fichier puis release du lock |
| `1` | LOCK_HELD par autre agent | STOP + ERROR `[LIBNAME_LOCK_HELD]` |
| `2` | stale lock (>30min) écrasé OU lock corrompu/illisible écrasé | continuer (recovery automatique) |
| `3` | erreur fichier (`--lib-path` invalide, permission denied, release sur lock d'un autre agent) | STOP + ERROR `[INFRA_BLOCKED]` (pas un conflit lock — corriger l'arg ou la perm) |

Détail matrice ownership et procédure complète :
`@.claude/rules/ownership.md §1, §4`.

---

## 2.bis Pattern atomic write — anti-corruption crash mid-write (v7.0.0 R4)

**Bloquant pour tout Write/Edit sous `{LibName}/` ET `{BackendName}/Services|Endpoints|DTOs`
ET `{AppName}/src/components|src/pages`** — les artefacts partagés entre US
de la même FEAT.

### Problème mitigé

Sans pattern atomique, un crash mid-write (Ctrl-C, OOM, kill -9, panne
réseau si write sur FS distant) laisse un fichier **tronqué partiellement**.
Le prochain agent qui :
1. Acquiert le LibName lock après recovery stale (§2 ci-dessus, TTL 30min)
2. Read le fichier corrompu (50 lignes écrites sur 100)
3. Edit dessus

…va produire un mélange de deux entités, compiler (warning) ou échouer
obscurément sans signal clair. Post-mortem CMS-Back identifié 2× ce
pattern en production avant le fix R4.

### Procédure obligatoire dev-* (Python helper)

```python
from sdd_lib.atomic_write import atomic_write_text

# Au lieu de :
#   Path(target).write_text(content)        # NON ATOMIQUE
# Faire :
atomic_write_text(Path(target), content)    # .sddtmp + os.replace()
```

L'helper :
1. Crée le parent dir si absent (`mkdir -p`).
2. Écrit en `{target}.sddtmp` (suffix dédié, ne collide pas avec `.tmp` user).
3. `f.flush() + os.fsync()` (best-effort — durabilité kernel-panic).
4. `os.replace(tmp, target)` — atomique POSIX + Windows ≥ NT.
5. Cleanup `.sddtmp` automatique si rename échoue.

### Procédure pour les outils Edit Claude Code (non-Python)

Quand l'agent dev-* invoque le tool `Write` ou `Edit` natif Claude Code,
le runtime fait déjà une écriture atomique côté harness (Write garantit
file integrity au niveau VFS). **Aucun changement requis côté agent prompt**
pour ces tools — le pattern Python ci-dessus s'applique uniquement aux
scripts auxiliaires (`acquire_libname_lock.py` callers, etc.).

### Détection orphan tmps (forensic)

```python
from sdd_lib.atomic_write import find_orphan_tmps
for orphan in find_orphan_tmps("workspace/output/src"):
    log(f"WARN orphan tmp from crash : {orphan}")
```

Invoqué par `framework_smoke.py` (à câbler v7.1). Aucun cleanup
automatique — l'orphan est une **trace forensique** indiquant un crash
non-récupéré. Tech Lead inspecte, archive ou supprime manuellement.

### Anti-patterns rejetés

- ❌ `f.write(content)` direct sur le target
- ❌ `Path(target).write_text(...)` sans fsync
- ❌ Suffix custom autre que `.sddtmp` (collision avec `.tmp` user / `.swp` vim)
- ❌ Catch + swallow de l'exception de rename (laisse `.sddtmp` orphan invisible)

---

## 3.bis Anti-derive universels (cross-agent, v7.0.0-alpha audit MAJ-1)

Bullets génériques applicables à **TOUS les 12 agents** (dev-*, support, auditors).
Référencés via `@.claude/rules/build-and-loop.md §3.bis` ; chaque agent y ajoute
ses propres bullets **domain-specific** (DB read-only pour arch, périmètre QA
pour qa, no-duplicate-quality-scan pour code-reviewer, etc.).

1. **Autonomous** : ne JAMAIS poser de question à l'utilisateur en cours
   d'exécution. L'agent décide ou STOP, pas de dialogue.
2. **Ambiguïté → STOP** : sur ambiguïté irrécupérable → STOP + ERROR 3
   lignes (ERROR / CAUSE / FIX avec préfixe `[CLASS]` cf.
   `error-classification.md §2`). Pas de devinette, pas de fallback créatif.
3. **No-spawn** : ne JAMAIS appeler / spawn un autre agent depuis ce
   prompt. Les invocations cross-agent vivent dans les commandes
   orchestrantes (`/sdd-full`, `/dev-run`, `/sdd-review`), pas dans
   les agents-feuilles. Exception : `constitutioner` qui est lui-même
   spawné par `arch` Phase B.

---

## 3. Anti-derive bullets dev-* (backend / frontend)

Interdictions strictes partagées dev-backend / dev-frontend (conservées
dans leur "Anti-derive strict" pour lisibilité ; **source de vérité ici**) :

1. Ne JAMAIS lire d'autres US, ni les FEATs.
2. Ne JAMAIS écrire de fichier hors plan inline (STEP 5/6) ou hors
   mapping du stack actif.
3. Ne JAMAIS introduire une lib non déclarée dans `.claude/stacks/{cat}/*.md`
   actifs (§2.4.a CORE ou §2.4.b ON-DEMAND triggered).
4. Ne JAMAIS générer de tests, fixtures, mocks, fichiers de test
   matchant les patterns QA (cf. §4 ci-dessous — QA hors scope).
5. Ne JAMAIS modifier l'US (read-only) ni le mockup HTML (lecture
   passive uniquement pour dev-frontend).
6. Ne JAMAIS poser de question à l'utilisateur (autonomous).
7. Si ambiguïté irrécupérable → STOP + ERROR 3 lignes (ERROR/CAUSE/FIX
   avec préfixe `[CLASS]` cf. `error-classification.md`).

---

## 4. Pattern QA-ownership (interdits côté dev-*)

Tentative d'écrire un fichier matchant ces patterns → STOP + ERROR
`[QA_OWNERSHIP_VIOLATION]` :

| Stack runtime | Patterns interdits |
|---|---|
| .NET | `*.Tests/**`, `**/*Tests.cs` |
| Node/TS | `**/__tests__/**`, `**/*.test.{ts,tsx,js,jsx}`, `**/*.FEAT.{ts,tsx,js,jsx}` |
| Python | `**/test_*.py`, `**/*_test.py` |
| Kotlin | `**/*Test.kt`, `**/*FEAT.kt`, `**/src/test/kotlin/**` |

Pas de deps test (`xUnit`, `Vitest`, `Moq`, `pytest`, `MockK`,
`@testing-library/*`) dans `.csproj`/`package.json`/`pyproject.toml`/
`build.gradle.kts` du **code production**. Ces deps vivent exclusivement
dans les projets de test (`*.Tests/`) propriété de l'agent QA.

Substance inlinée dans `qa.md` (§Ownership) et `dev-backend.md` /
`dev-frontend.md` (§Anti-derive strict).

---

## 5. Pattern stack-completeness

Toute lib utilisée DOIT figurer §2.4.a (CORE — installée par arch) ou
§2.4.b (ON-DEMAND — triggered par capability detection STEP 5.bis pour
dev-backend ; côté dev-frontend, les composants DS doivent figurer
dans mapping §2/§7 du stack `ui-*`).

Absent → STOP + ERROR `[STACK_LIBRARY_MISSING]` (cf. §3 de
`stack-completeness.md` pour le format ERROR + HINT canonique).

**Built-in OK** sans entrée §2.4 :
- .NET : `System.*` (BCL)
- Node : `fs`, `path`, `crypto`, `http`, `url`, `events` (natifs)
- Python : stdlib (`datetime`, `json`, `pathlib`, `os`, `re`, `typing`)
- Java/Kotlin : `java.*`, `javax.*`, `kotlin.*` (stdlib)
- Dépendances transitives auto-installées par le package manager
- Types fournis nativement par le framework (`IConfiguration`,
  `ILogger<T>`, `IJSRuntime`, `useState`, `Component`)

Pas d'install ad-hoc (`npm install <pkg>`, `dotnet add package <pkg>`)
hors §2.2.1 du stack. Réservé `arch` Phase A. Pour ajouter une lib :
éditer le stack puis relancer `/arch-init` (idempotent).

---

## 6. Pattern BREAKING CHANGES cleanup post-build

Après build vert au STEP build (`exit 0`, dev-backend STEP 8 /
dev-frontend STEP 9), invoquer le script de marquage RESOLVED :

```bash
python .claude/python/sdd_scripts/mark_breaking_resolved.py \
  --claude-md "workspace/output/src/{BackendName|AppName}/CLAUDE.md" \
  --modified-files "{liste fichiers modifiés cette US, séparés virgule}" \
  --build-command "{commande build du stack}"
```

| Exit | Sens | Action agent |
|---|---|---|
| `0` (`SUCCESS`) | opération complétée (marked OU skipped — pipeline continue) | log la valeur de `SDD_MARK_BREAKING_ACTION` si export demandé |
| `3` (`INFRA_BLOCKED`) | erreur fichier (parse, write, missing) | ERROR `[BREAKING_CLEANUP_FAILED]` |

> ✅ **Standardisé v7.0.0** (cf. docstring du script) — convention
> `sdd_lib/exit_codes.py` respectée. **Breaking** vs v6.x : marked et
> skipped retournaient autrefois 1 et 0 ; les deux sont désormais `0`.
> Discrimination via stdout pattern `[OK]` / `[SKIP]` / `[DRY-RUN]` ou
> env-export `SDD_MARK_BREAKING_CAPTURE=1` → `SDD_MARK_BREAKING_ACTION=
> marked|skipped|dryrun`. Pattern bash standard `cmd || handle_error`
> fonctionne désormais.

Détail procédure + cas interdits : `@.claude/rules/ownership.md §6.bis`.

---

## 7. Pattern Plan Construction (dev-backend STEP 5 / dev-frontend STEP 6)

### 7.1 Mode dispatch (identique BE/FE)

- `FROM_PLAN_PATH != null` → **mode From Plan** : Read le fichier plan,
  parser sa section `## Files`, reconstruire la liste en mémoire.
  Skip la construction inline, aller directement au write-through
  des fichiers code.
- `PLAN_ONLY = true` → **mode Plan Only** : produire le plan
  (§7.4) puis **STOP** avant la génération de code.
- Sinon → **mode Inline** : construire le plan + générer le code dans
  la même invocation.

### 7.2 AC coverage (vérification interne)

Chaque AC de l'US (backend AC ou AC-UI selon famille) doit être
traçable vers ≥ 1 fichier du plan. Si non → STOP + ERROR :
```
ERROR: agent {dev-backend|dev-frontend} — couverture AC{|-UI} incomplète
CAUSE: AC{-UI}-{X} de l'US {n}-{m} non matérialisée par aucun fichier
FIX: clarifier l'AC dans l'US OU compléter le stack actif
```

### 7.3 Exit silencieux "aucun travail"

Si l'US n'implique aucun fichier de la famille (US frontend pure côté
dev-backend / US backend pure côté dev-frontend) → 1 ligne et STOP,
sans écrire ni builder :
```
{dev-backend|dev-frontend} {n}-{m}-{Name}: skipped ({frontend|backend}-only US)
```

### 7.4 Structure générique du plan v1 (legacy, backward-compat)

Format historique, accepté en mode From Plan classique (Opus). Écrire
`workspace/output/plans/{n}-{m}-{Name}.{back|front}.md` :

```markdown
---
us: {n}-{m}-{Name}
family: {backend|frontend}
generated-at: {ISO-8601}
generated-by: agent {dev-backend|dev-frontend} (mode :plan)
stack-{backend|frontend}: {active stack id}
# (frontend ajoute aussi stack-ui, html-source)
---

# Plan technique {backend|frontend} — {n}-{m}-{Name}

## Files

- path: {chemin}
  operation: {create|augment}
  layer: {layer-de-la-famille}      # Service/DTO/… (back) ou Page/Component/… (front)
  preserves: [{ids}]                 # uniquement si augment
  adds: [{ids}]                      # uniquement si augment
  covers_acs: [AC-1, AC-3]
  # (frontend ajoute aussi ds_components, source_html_elements)

(N entrées au total)

## ACs Coverage Summary
| AC | Files |
|----|-------|
| AC-1 | path1 |

# (frontend ajoute sections "## Theme overrides" et "## UI Assets pending")

## Notes
(Décisions notables, texte libre, optionnel)
```

Ligne de confirmation :
```
{dev-backend|dev-frontend} {n}-{m}-{Name}: plan written → workspace/output/plans/{n}-{m}-{Name}.{back|front}.md ({F} fichiers)
```

### 7.4.bis Structure plan v2 (strict-ready, depuis v6.2)

Format requis pour le mode **From-Plan Strict** (cf. §7.6, §7.7). Le plan
v2 enrichit le frontmatter et ajoute une section `## Inline Digest` qui
rend le plan **auto-suffisant** : `dev-*-strict` (Sonnet 4.6) peut
matérialiser sans Read additionnel des stacks ou de la `CLAUDE.md`.

Frontmatter v2 (champs additionnels en gras) :

```yaml
---
us: {n}-{m}-{Name}
family: {backend|frontend}
generated-at: {ISO-8601}
generated-by: agent {dev-backend|dev-frontend} (mode :plan)
stack-{backend|frontend}: {active stack id}

# Champs v2 obligatoires
plan-schema-version: 2
us-hash: sha256:{hash SHA-256 du fichier US au moment de la planification}
strict-ready: true

# Champs v2 optionnels
claude-md-hash: sha256:{hash CLAUDE.md projet au moment de la planification}
capabilities-triggered: cap-a,cap-b,...
---
```

Nouvelle section markdown obligatoire en v2 :

```markdown
## Inline Digest

### Stack §1.3 mapping ({stack-id})
- {Layer} → {répertoire canonique}/
- ...

### CLAUDE.md projet (extrait pertinent)
- AppNamespace : ...
- Entities scaffoldées : ...
- BREAKING CHANGES : (none|...)

### Schema.json (entités touchées par cette US)
- {EntityName} { id, ..., ... }
- ...

# (frontend ajoute aussi un "### UI Design System mapping" : RadzenButton↔Button, etc.)
```

Sections `## Files`, `## ACs Coverage Summary` et `## Notes` inchangées.

**Pourquoi v2** : `dev-*-strict` ne re-Read PAS les stacks (15-30 KB),
ni CLAUDE.md, ni schema.json. Digest centralise les infos pour
matérialiser. Économie ~20-50 KB/invocation + cache hit accru.

### 7.5 Anti-derive plan (commun, v1 et v2)

- Aucun fichier hors périmètre US/HTML
- Aucune lib hors `.claude/stacks/{cat}/*.md` actifs
- Aucune optimisation proactive (caching, retry, logging verbeux,
  feature flags) non demandée par l'US ou le stack
- Aucun `TODO`, `FIXME`, stub, placeholder, secret hardcodé
  (sauf `data-ui-asset` autorisé côté frontend)

### 7.6 Validation du plan (script déterministe)

`validate_plan.py` (sdd_scripts/) valide structure + détection staleness
sans coût LLM. Invoqué par :
- `/dev-plan` STEP 5 (post-génération, validation cohérence)
- `/dev-run` STEP 6.0.bis (gate staleness avant matérialisation)
- `/sdd-status` (diagnostic plan-readiness)

```bash
python .claude/python/sdd_scripts/validate_plan.py \
  --plan-path workspace/output/plans/{n}-{m}-*.{back|front}.md \
  --us-path workspace/output/us/{n}-{m}-*.md \
  --json
```

| Exit | Sens | Comportement caller |
|---|---|---|
| `0` | plan valide avec `## Inline Digest` (plan v2) | OK → matérialiser |
| `1` | plan valide sans digest (plan v1 legacy) | OK → matérialiser |
| `2` | **invalide / corrompu / stale** | STOP + ERROR `[PLAN_STALE]` ou `[PLAN_INVALID]` |

> **v7.0.0 change** : exit 0/1 ne route plus vers des agents différents
> (les variants `dev-*-strict` ont été supprimés). Les deux exit codes
> mènent au même agent `dev-*` (Opus). Le flag historique `--strict`
> reste accepté en CLI (no-op) pour backward-compat scripts.

Classes d'erreur retournées (cf. `error-classification.md`) :
- `PLAN_NOT_FOUND`, `PLAN_UNREADABLE`, `PLAN_NO_FRONTMATTER`
- `PLAN_MISSING_REQUIRED_FIELD`, `PLAN_FILES_SECTION_MISSING`
- `PLAN_FILE_ENTRY_INVALID`, `PLAN_AUGMENT_CONTRACT_MISSING`
- `PLAN_AC_COVERAGE_GAP`, `PLAN_STALE`
- ~~`PLAN_NOT_STRICT_READY`~~ — déprécié (plus de routing strict)

### 7.7 Mode dispatch (simplifié v7.0.0)

Extension de §1.ter.4. Quand `FROM_PLAN_PATH != null`, le caller (`/dev-run`)
lance toujours `dev-*` classique (Opus 4.7). Avant le spawn, gate de
staleness via `validate_plan.py` (exit 2 → STOP) :

```
FROM_PLAN_PATH != null :
  ├─ validate_plan.py --plan-path $PATH --us-path $US
  │   ├─ exit 0 ou 1 → MODE = FROM_PLAN (classique)
  │   │                → spawn dev-* (Opus 4.7)
  │   └─ exit 2      → STOP + ERROR [PLAN_STALE] ou [PLAN_INVALID]
  │                    Tech Lead doit relancer /dev-plan
```

### 7.8 Invariants From-Plan

Le mode From-Plan préserve ces propriétés (inchangées v6→v7) :

- ✅ Source-first : plan MD = SSOT exécutable (pas de mémoire opaque)
- ✅ Idempotence : même plan + même US → même code
- ✅ Reproductibilité cross-machine : tout est dans le plan
- ✅ File ownership : `dev-*` hérite des mêmes règles
- ✅ Anti-derive : STOP si plan stale, pas de fallback créatif
- ✅ Build loop : inchangé (max `BuildLoopMaxIter`)

---

## 8. Read on-demand (cas-limite uniquement)

Les agents dev-* ne lisent PAS systématiquement ces règles (substance
inlinée). À Read uniquement si ambiguïté irrécupérable :

- `@.claude/rules/library-and-stack.md` (workflow Tech Lead + format
  ERROR HINT)
- `@.claude/rules/ownership.md §1-§2, §4, §6.bis`
- `@.claude/docs/principles/source-first.md` (si bug récurrent dans build_loop —
  questionner quelle source MD a manqué)

---

## 9. Enforcement

- **Agents `dev-backend` et `dev-frontend`** : charger cette règle en
  STEP 3 (dev-backend) ou STEP 4 (dev-frontend) au même moment que
  `error-classification.md`. Coût : ~4 KB.
- Toute évolution d'un pattern §1-§7 ci-dessus doit être faite ici
  d'abord, puis vérifiée dans chaque agent (ne pas diverger).
