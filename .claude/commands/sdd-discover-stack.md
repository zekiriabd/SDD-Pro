# /sdd-discover-stack — Détection automatique du stack d'un repo existant

Scanne un repo (brownfield ou nouveau) et produit
`workspace/input/stack/stack.md.candidate` avec les stack-ids SDD_Pro
candidats + une `## Project Config` pré-remplie. Le Tech Lead arbitre
les ambiguïtés et renomme `.candidate` → `stack.md` quand validé.

**Usage :** `/sdd-discover-stack [--scope <path>] [--force]`

**Garanties non-régression** :
- Cette commande **ne touche jamais** au moteur SDD_Pro (build_loop, API
  Gate, phases auditor, file ownership). Elle ne fait que lire des
  fichiers manifestes et écrire un `.candidate` à côté.
- Si `stack.md` existe déjà → écrit dans `stack.md.candidate` (jamais
  d'overwrite direct sauf `--force`).
- Scripts Python déterministes (0 token LLM jusqu'à STEP 5).

---

## STEP 1 — Args

| Arg | Défaut | Sens |
|---|---|---|
| `--scope <path>` | `.` | Répertoire à scanner (relatif au repo root) |
| `--force` | absent | Autorise overwrite de `workspace/input/stack/stack.md` existant |

Si l'arg `--scope` est absent → scan du repo root.

---

## STEP 2 — Pré-check existence stack.md

```bash
STACK_MD = workspace/input/stack/stack.md
STACK_CANDIDATE = workspace/input/stack/stack.md.candidate
```

- Si `STACK_MD` existe ET `--force` absent → cible de sortie = `STACK_CANDIDATE`
- Si `STACK_MD` existe ET `--force` présent → cible de sortie = `STACK_MD` (overwrite)
- Si `STACK_MD` absent → cible de sortie = `STACK_MD` directement

Informer l'utilisateur de la cible choisie :
```
🔍 /sdd-discover-stack: scanne {scope}, écrira → {target_path}
```

---

## STEP 3 — Scan déterministe

Invoquer :
```bash
python .claude/python/sdd_scripts/scan_repo.py \
  --scope {scope} \
  --output workspace/output/.sys/.audit/scan-report.json \
  --quiet
```

Le script écrit `scan-report.json` avec :
- `manifests[]` : fichiers détectés (csproj, package.json, etc.) + leur contenu parsé
- `languages[]`, `frameworks[]`, `ui_indicators[]`, `database_indicators[]`, `auth_indicators[]`
- `warnings[]` : éventuels `[SCAN_PARSE_ERROR]`

Si exit ≠ 0 → STOP + ERROR `[DISCOVER_SCAN_FAILED]`.

---

## STEP 4 — Matching contre catalogue SDD_Pro

Invoquer :
```bash
python .claude/python/sdd_scripts/match_stack_catalog.py \
  --scan-report workspace/output/.sys/.audit/scan-report.json \
  --output workspace/output/.sys/.audit/match-report.json
```

Le script écrit `match-report.json` avec :
- `candidates.{backend,frontend,ui}[]` : stack-ids triés par score (0-100) avec confidence (high/medium/low)
- `database` : valeur Project Config `DatabaseType:` (`SqlServer`/`PostgreSql`/`MySql`/`Sqlite`/`MongoDb` ou `null`)
- `auth` : stack auth id (`azure-ad`/`auth-local` ou `null`)
- `warnings[]` : `[DISCOVER_NO_MATCH]` / `[DISCOVER_PARTIAL]` / `[DISCOVER_AMBIGUOUS]`

---

## STEP 5 — Lecture des résultats et décision

Read `workspace/output/.sys/.audit/match-report.json`.

### 5.1 Cas DISCOVER_NO_MATCH

Si `candidates.backend == []` ET `candidates.frontend == []` :
```
❌ /sdd-discover-stack: aucun stack SDD_Pro reconnu dans {scope}

Stacks supportés (🟢 reference) :
  - Backend  : dotnet-minimalapi, kotlin-spring-boot, python-fastapi, node-express
  - Frontend : react, vue, angular, blazor-webassembly
  - UI       : shadcn, vuetify, radzen-blazor

Indicateurs détectés (insuffisants pour matcher) :
  languages           : {languages}
  frameworks          : {frameworks}

FIX: vérifier que le repo contient bien un manifest reconnu
     (csproj, package.json, pyproject.toml, build.gradle.kts, pom.xml)
     OU compléter manuellement workspace/input/stack/stack.md
```
STOP + ERROR `[DISCOVER_NO_MATCH]`.

### 5.2 Cas DISCOVER_AMBIGUOUS (≥ 2 candidats même catégorie)

Si `len(candidates.backend) > 1` OU `len(candidates.frontend) > 1` :
afficher les candidats avec leur score et demander au Tech Lead de choisir :

```
⚠️ Ambiguïté détectée — plusieurs backends matchés :

  1. dotnet-minimalapi (score 95, confidence high)
     Evidence: languages:dotnet, frameworks:aspnetcore-minimal
  2. python-fastapi (score 80, confidence high)
     Evidence: languages:python, frameworks:fastapi

Lequel utiliser ? (réponds par le numéro ou "both" pour générer un combo)
```

Attendre la réponse. `both` n'est pas supporté en v6.6.1 → afficher message :
"Combo backend non supporté en v6.6.1, choisis un seul."

Idem pour frontend si ambiguïté.

### 5.3 Cas standard (1 candidat par catégorie)

Continuer directement vers STEP 6.

---

## STEP 6 — Compléter les valeurs Project Config

Pour les champs non détectables automatiquement (noms de projet,
namespaces, MaxParallel, etc.), utiliser des valeurs sensibles par
défaut **avec un commentaire `# TODO`** pour signaler au Tech Lead :

| Clé | Source | Default si non détectable |
|---|---|---|
| `AppName` | package.json `name` (frontend) | `<AppName>` + `# TODO renseigner` |
| `BackendName` | csproj filename / Spring artifactId | `<BackendName>` + `# TODO` |
| `AppNamespace` | détection csharp namespace | défaut = `AppName` |
| `BackendNamespace` | détection csharp namespace | défaut = `BackendName` |
| `LibStrategy` | toujours `openapi-codegen` par défaut | `openapi-codegen` |
| `QAMode` | toujours `manual` par défaut sécuritaire | `manual` |
| `CoverageMin` | **obligatoire** (pas de défaut framework — décision explicite à inscrire dans Project Config, cf. `quality.md §A.2`) | `80` (recommandation pour candidate) |
| `MaxParallel` | défaut `3` | `3` |
| `PlanReviewDefault` | défaut `true` | `true` |

Pour les modes auditors v7.0.0 : laisser commentés
```yaml
# CodeReviewMode: full
# SecurityMode: full
# SpecComplianceMode: full
# ArchReviewMode: full
# AdversarialReviewMode: full   # opt-in, informational
```
> ⚠️ `A11yMode`/`PerfMode` retirés v7.0.0 (agents `accessibility-auditor`
> et `performance-auditor` supprimés — `governance-major-auditors-trim`).
> Remplacement : ingest CI v7.2.0 via `ingest_axe.py` / `ingest_lighthouse.py`.

---

## STEP 7 — Écrire stack.md.candidate

Format du fichier généré :

```markdown
# Project Stack — généré par /sdd-discover-stack le {ISO date}

> ⚠️ Fichier candidat. Revoir les sections marquées `# TODO` avant de
> renommer en `stack.md`. Toutes les valeurs détectées automatiquement
> sont sourcées dans `workspace/output/.sys/.audit/match-report.json`.

## Project Config
AppName: <AppName>                # TODO ajuster (détecté : "{detected_name}")
AppNamespace: <AppName>
BackendName: <BackendName>        # TODO ajuster
BackendNamespace: <BackendName>
LibStrategy: openapi-codegen
PlanReviewDefault: true
QAMode: manual                    # passer à "full" quand prêt
CoverageMin: 80                   # obligatoire — voir quality.md §A.2 ; 0 = désactivé (décision tracée)
MaxParallel: 3

# Auditors v7.0.0 — uncomment pour activer
# CodeReviewMode: full
# SecurityMode: full
# SpecComplianceMode: full
# ArchReviewMode: full

## Active Tech Specs
 - .claude/stacks/backend/{backend-stack-id}.md      # score {score}, {confidence}
 - .claude/stacks/frontend/{frontend-stack-id}.md    # score {score}, {confidence}

## Active UI Specs
 - .claude/stacks/ui/{ui-stack-id}.md                # score {score}, {confidence}

## Active QA Specs
 - .claude/stacks/qa/{matched-qa-stack}.md           # TODO confirmer
 - .claude/stacks/qa/code-quality.md

## Active Auth Specs
 - .claude/stacks/auth/{auth}.md
 # TODO ajouter les secrets : AUTH_JWT_SECRET, AUTH_JWT_ISSUER, AUTH_JWT_AUDIENCE, AUTH_JWT_EXPIRATION

## Active Database
 - DatabaseType: {database}        # détecté
 # TODO ajouter : DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT

# ## Active SMTP Server     # uncomment + remplir si l'app envoie des emails
```

**Mapping QA stack automatique** (selon backend détecté) :
- `dotnet-minimalapi` → `qa/dotnet-xunit.md` + `qa/node-vitest.md` (si frontend node)
- `kotlin-spring-boot` → `qa/kotlin-junit.md`
- `python-fastapi` → `qa/python-pytest.md`
- `node-express` → `qa/node-vitest.md`
- Frontend `react`/`vue` → `qa/node-vitest.md`
- Frontend `angular` → `qa/angular-jasmine.md`
- Frontend `blazor-webassembly` → `qa/blazor-bunit.md`

Si combo non supporté → laisser `# TODO confirmer QA stack`.

---

## STEP 8 — Émission succès

```
✓ /sdd-discover-stack: stack candidat écrit

Cible       : {target_path}
Détecté     :
  Backend   : {backend_stack_id} (score {score}, {confidence})
  Frontend  : {frontend_stack_id} (score {score}, {confidence})
  UI        : {ui_stack_id} (score {score}, {confidence})
  Database  : {database}
  Auth      : {auth}

Warnings    : {liste warnings DISCOVER_PARTIAL/DISCOVER_AMBIGUOUS}

Prochaines étapes :
  1. Revoir les lignes `# TODO` dans {target_path}
  2. Renommer en stack.md (si .candidate)
  3. /feat-generate <FeatName>
```

Si une warning `[DISCOVER_PARTIAL]` ou `[DISCOVER_AMBIGUOUS]` est
présente, **l'afficher en jaune** dans le résumé pour attirer
l'attention du Tech Lead.

---

## STEP 9 — Anti-derive

- Cette commande ne modifie **JAMAIS** :
  - Le code de prod (`workspace/output/src/`)
  - Les FEATs/US (`workspace/input/feats/`, `workspace/output/us/`)
  - Les rapports (`workspace/output/qa/`, `.sys/.validation/`)
  - Les agents, rules, stacks (`.claude/`)
- Outputs uniquement :
  - `workspace/output/.sys/.audit/scan-report.json` (forensic)
  - `workspace/output/.sys/.audit/match-report.json` (forensic)
  - `workspace/input/stack/stack.md.candidate` (ou `stack.md` si `--force`)
- Idempotente : re-invocation = ré-écrit les mêmes fichiers candidates.
- Pas de network : tous les scans sont locaux.

---

## STEP 10 — Limitations connues v6.6.1

- **Pas de mode combo** : si 2 backends détectés (monorepo polyglot), il
  faut choisir 1 seul. Combo multi-backend prévu v6.6.2+.
- **Pas de détection auto AppName/BackendName** : 90% des cas nécessitent
  un ajustement manuel post-génération.
- **Stacks 🟡 expérimentaux non détectés** : seuls les 11 stacks 🟢
  reference sont reconnus en v6.6.1.
- **Pas de détection des secrets** : `DB_PASSWORD`, `AUTH_JWT_SECRET`,
  etc. doivent être ajoutés manuellement (sécurité — on ne lit pas les
  `appsettings.json` pour ça).

---

## Chat Output Protocol

> Cette commande applique strictement `@.claude/rules/output-protocol.md`.
> Substance non dupliquée — la règle est SSoT.

**Labels canoniques émis** : `[ANALYSIS]` (cf. output-protocol.md §3)
**Plage de progression couverte** : `0-100%` (scan onboarding mono-shot)

**Granularité cible** : 3-4 updates (scan manifests, match catalogue,
écriture `stack.md.candidate`, verdict).

**Interdits stricts** (cf. §5 du protocole) :
- chemins de fichiers internes (`workspace/...`, `.claude/...`)
- liste détaillée des manifests parsés (compteur suffit)
- stdout/stderr de scan_repo.py / match_stack_catalog.py
- JSON dumps

**Verdict final** : 1 ligne avec compteur stacks détectés + pointeur
fichier généré. Exemple : `[ANALYSIS] 1 combo backend×frontend×ui
détecté → workspace/input/stack/stack.md.candidate. (100%)`. En cas
d'absence de match : `🟡 [ANALYSIS/WARN] Manifests présents mais
[DISCOVER_NO_MATCH]. (100%)`.

**Bypass debug** : `SDD_CHAT_VERBOSE=1` → mode legacy verbose (§10).
