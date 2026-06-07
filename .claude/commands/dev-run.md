# /dev-run — Orchestrateur dev (arch+db → back → API gate → front) pour 1 FEAT

> **Commande user-facing** (cf. CLAUDE.md §3 — 12 user-facing). Phase 4 :
> orchestre arch+DB → dev-backend ALL US → QA API Gate → dev-frontend ALL US.
> Invoquée aussi par `/sdd-full` STEP 4. Pour un pipeline complet A→Z, préférer
> `/sdd-full` qui gère également Phase 2 (US) et Phase 5 (QA + reviews).

> **Dépendance load-bearing au runtime Claude Code** : orchestration
> parallèle via tool `Agent` (alias `Task`) avec N calls indépendants
> dans un même message. Contrat externe garanti par Claude Code.
> Anti-régression : `framework_smoke.py` vérifie la présence de
> « parallèle » + `Agent` + `dev-backend` + `dev-frontend`.

Pour la FEAT `{n}`, en séquence (**workflow gated séquentiel** depuis
v7.0.0, default `GatedWorkflow: true` — cf. STEP 6 et
`.claude/rules/build-and-loop.md` Partie A) :

1. **Pré-step `arch`** (idempotent) — bootstrap solution/projets selon
   stacks actifs + scaffolding DB Database-First si `DatabaseType ≠ none`
   (les deux phases sont gérées par le même agent `arch`)
2. **`dev-backend` sur TOUTES les US** (parallélisme intra-back borné
   par `MaxParallel`, default 3 US simultanées)
3. **QA API Gate** (tests d'intégration HTTP in-memory) — STOP si
   `status=FAIL|INFRA_BLOCKED`, continue sur `PASS|WARN|SKIPPED`
4. **`dev-frontend` sur TOUTES les US** (parallélisme intra-front
   borné par `MaxParallel`) ; chaque agent décide s'il a du travail
   (frontend pure / backend pure) ou exit silencieux

> **Anti-régression** : `framework_smoke.py` valide la présence de
> `Agent` + `parallèle` + `dev-backend` + `dev-frontend` dans ce fichier
> (le parallélisme intra-phase reste un contrat load-bearing du runtime
> Claude Code). Le sequencing inter-phase back→gate→front est la
> nouveauté v7.0.0 vs v6.x parallèle. Legacy v6 disponible via
> `GatedWorkflow: false` (audit-log `legacy-parallel.log`).

Mode **autonome** : pas de Q/R utilisateur.

**Usage :** `/dev-run {n}` (`{n}` = numéro FEAT).

**Hors scope :** `/us-generate` doit avoir tourné avant. Consomme
`workspace/output/us/` (US) et `workspace/input/ui/` (mockups HTML optionnels).

---

## STEP 1 — Valider l'argument

Arguments :
- `{n}` (entier ≥ 1, **obligatoire**)
- `--force` (optionnel) — bypass un rapport readiness NO-GO existant.
- `--max-parallel N` (optionnel) — nombre max d'US simultanées (1 US =
  jusqu'à 2 invocations dev-*). Default : `MaxParallel` dans `## Project
  Config` de `workspace/input/stack/stack.md`, sinon **3**. Range 1-12.
  Hors range → ERROR.

  Exemples :
  - `/dev-run 1` → default (3 US → max 6 invocations parallèles).
  - `/dev-run 1 --max-parallel 1` → séquentiel (1 US back+front, puis suivante).
  - `/dev-run 1 --max-parallel 6` → 6 US parallèles (max 12 invocations).

  Stocker dans `$max_parallel` (STEP 6.2).

- `--rebuild-arch` (optionnel) — force l'invocation `arch` (STEP 5)
  même si STEP 4.bis détecte un bootstrap stable. À utiliser quand :
  - schéma DB changé (nouvelles tables/colonnes)
  - lib ajoutée à `.libs.json` d'un stack actif
  - `## Project Config` modifié (AppName, BackendName, DatabaseType…)
  - projet supprimé manuellement et à re-bootstrapper

  Sans ce flag, FEATs ≥ 2 (ou re-runs) sautent arch dès que les
  artefacts de bootstrap sont cohérents (STEP 4.bis).

  Stocker `$rebuild_arch ∈ {true, false}` (STEP 4.bis et 5).

- `--resume` (optionnel) — reprend depuis le dernier checkpoint (cf.
  `CheckpointMode: resume` Project Config). Skip les STEPs déjà PASS
  selon `sdd_state.py should-skip-step`. Idempotent. Stocker `$resume`.

- `--unsequenced` (optionnel) — désactive la gate API back→front, lance
  dev-backend + dev-frontend en parallèle (mode legacy v6.x). Équivalent
  à `GatedWorkflow: false` dans Project Config. Audit-loggué dans
  `workspace/output/.sys/.audit/legacy-parallel.log`. Déconseillé.

- ~~`PlanCacheStrict`~~ — **retiré v7.0.0** (les variants `dev-*-strict`
  ont été supprimés ; clé tolérée mais sans effet runtime).

Si `{n}` absent → demander :
```
Quel est le numéro de la FEAT à matérialiser ? (ex. : 1)
```

Si `{n}` non numérique →
```
ERROR: /dev-run — argument invalide
CAUSE: "{argument}" n'est pas un entier
FIX: relancer /dev-run {n} (ex. /dev-run 1)
```

---

## STEP 1.5 — Vérification du rapport readiness

Read `workspace/output/.sys/.validation/{n}-readiness.md` **si présent**.

- Fichier absent → continuer (gate non exécutée, cas `/dev-run` direct
  sans `/sdd-full`). WARNING informationnel :
  ```
  WARNING: /dev-run — gate readiness non exécutée
  HINT: lancer /feat-validate {n} avant pour détecter les trous FEAT en amont
  ```
  puis continuer.

- Fichier présent + décision `🟢 GO` ou `🟡 WARN` → continuer.

- Fichier présent + décision `🔴 NO-GO` :
  - Si `--force` fourni → continuer + émettre :
    ```
    WARNING: /dev-run — bypass NO-GO via --force
    Rapport : workspace/output/.sys/.validation/{n}-readiness.md (consulter §3)
    ```
  - Sinon → STOP :
    ```
    🔴 /dev-run {n} — bloqué par rapport readiness (NO-GO)
    Rapport : workspace/output/.sys/.validation/{n}-readiness.md
    FIX :
      1. corriger les erreurs §3 du rapport
      2. relancer /feat-validate {n}
      3. relancer /dev-run {n} une fois GO ou WARN
    Bypass : /dev-run {n} --force (à utiliser en connaissance de cause)
    ```

---

## STEP 1.75 — Checkpoint skip (v6.6.5, opt-in)

Si `CheckpointMode: resume` dans Project Config (défaut `off` =
comportement v6.6.4 strict) :

```python
from sdd_lib.checkpoint import is_phase_resumable

inputs = [
    f"workspace/input/feats/{n}-*.md",        # FEAT parent
    *glob(f"workspace/output/us/{n}-*.md"),   # toutes les US
    *glob(f"workspace/input/ui/{n}-*.html"),  # mockups HTML (si présents)
    "workspace/input/stack/stack.md",         # Project Config + stacks
]
resumable, reason = is_phase_resumable(
    feat=n, phase="dev-run", input_paths=resolved_inputs,
)
if resumable:
    print(f"⊘ /dev-run {n}: skipped (checkpoint hit — code already materialized, inputs unchanged)")
    # STOP avec succès, ne pas re-dispatcher arch + dev-* + auditors
```

Si `CheckpointMode ∈ {off, record}` → skip ce STEP, continuer.

**Granularité dev-run** : checkpoint au niveau **dev-run complet** (skip
arch + dev-back + dev-front + API Gate + auditors d'un coup), pas au
niveau phase interne. Pour la granularité phase, l'idempotence `Status:
Done` US-level suffit (cf. `ownership.md §6`, was file-ownership.md §6).

Émissions possibles : `[CHECKPOINT_HASH_MISMATCH]` (US ou mockup modifié),
`[CHECKPOINT_INPUT_MISSING]` (US supprimée), `[CHECKPOINT_STATE_UNREADABLE]`
(première exécution).

---

## STEP 2 — Lister les US à matérialiser

Glob `workspace/output/us/{n}-*.md` → liste `US_LIST` (basenames sans extension).

Si `US_LIST` est vide →
```
ERROR: /dev-run — aucune US à matérialiser
CAUSE: aucun fichier workspace/output/us/{n}-*.md
FIX: lancer /us-generate {n} pour générer les US d'abord
```

Émettre 1 ligne récap :
```
FEAT {n} — {U} US à matérialiser (back → API gate → front, parallélisme intra-phase borné par MaxParallel)
```

---

## STEP 2.bis — Valider le graphe `## Dependencies`

Valider et ordonner `US_LIST` selon le graphe de dépendances des US.

```bash
python .claude/python/sdd_scripts/validate_us_deps.py --feat {n} --json
DEPS_EXIT=$?
case $DEPS_EXIT in
  0) ;;  # OK
  3) echo "ERROR: [US_DEPS_CYCLE]" >&2; exit 1 ;;
  4) echo "ERROR: [US_DEPS_MISSING] ref vers US inexistante" >&2; exit 1 ;;
  5) echo "ERROR: [US_DEPS_PARSE_ERROR] frontmatter ## Dependencies malformé" >&2; exit 1 ;;
  1) echo "ERROR: [INVALID_ARG] args malformés" >&2; exit 2 ;;
  *) echo "ERROR: [INFRA_BLOCKED] exit $DEPS_EXIT" >&2; exit 3 ;;
esac
```

Sur exit 0, récupérer **les batches layered Kahn** (v7.0.0) :

```bash
# Garantie : aucun US dans un layer ne dépend d'un autre US du même layer.
US_LAYERS=$(python .claude/python/sdd_scripts/validate_us_deps.py --feat {n} --layered-batches)

# Consommé en STEP 6.a / 6.c :
while IFS= read -r layer; do
    for sub_batch in chunk("$layer", $max_parallel); do
        invoke_parallel(sub_batch); wait
    done
done <<< "$US_LAYERS"
```

**Fallback compat** : si `--layered-batches` indisponible →
`--topo` (risque collision intra-batch sur graphe dense, comportement v6.7).

**Backward-compat** : US legacy sans `## Dependencies` → 1 seul layer
tri alphabétique stable, byte-identique `--topo` v6.7.

**Invariant v7.0.0 strict** : intra-layer = pairwise indépendantes →
(1) aucune race `{LibName}/` (LibName lock O_EXCL, `ownership.md §4`),
(2) chunking `MaxParallel` préserve sécurité, (3) layer K attend layer K-1.
Le diamant `A→B, A→C, B→D, C→D` → 3 layers : `{A}`, `{B, C}`, `{D}`.

---

## STEP 3 — Vérifier les stacks actifs

Lire `workspace/input/stack/stack.md`.

- Si aucun `## Active Tech Specs` `backend-*` ET aucun `frontend-*` →
  ```
  ERROR: /dev-run — aucun stack tech sélectionné
  CAUSE: ## Active Tech Specs vide ou seul ui/auth présents
  FIX: décommenter au moins un backend ou un frontend
  ```

(Un stack manquant côté backend OU frontend n'est pas bloquant ici :
les agents dev-* feront leur propre check et exit silencieux si
inapplicable.)

---

## STEP 4 — Validation des blocs `## Active Database` + `## Active Auth Specs` de stack.md

Les valeurs DB et Auth sont des **clés dans `stack.md`** (Tech Lead)
propagées par `arch` Phase A — STEP 4.5 vers les fichiers de configuration
applicatifs natifs.

| Source dans stack.md                              | Clés requises (valeur non vide)                 |
|---------------------------------------------------|--------------------------------------------------|
| `## Active Database` (si `DatabaseType ≠ none`)   | `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (cf. `dotnet-minimalapi.md §5.1`) |
| `## Active Auth Specs ⊇ auth/azure-ad`            | `AZ_TENANTID`, `AZ_CLIENTID`, `AZ_DOMAIN`, `AZ_AUDIENCES`, `AZ_BE_CALLBACKPATH`, `AZ_FE_CALLBACKPATH` (cf. `auth/azure-ad.md §2`) |

Parser ces blocs (cf. `agents/arch.md §2.ter.1`) **sans afficher** les
valeurs. Si ≥ 1 clé absente/vide →
```
ERROR: /dev-run — clé(s) manquante(s) dans stack.md
CAUSE: clés non définies : {liste exacte} dans {## Active Database | ## Active Auth Specs}
FIX: renseigner les valeurs dans workspace/input/stack/stack.md (bloc concerné)
```

**STOP**. Aucun agent invoqué tant que prérequis absents.

---

## STEP 4.bis — Short-circuit arch (déterministe)

Évite le coût arch sur FEATs ≥ 2 / re-runs quand bootstrap stable.
`--rebuild-arch` force `arch_required = true` (1 ligne `FEAT {n} — arch forcé`).

```bash
python .claude/python/sdd_scripts/detect_arch_shortcircuit.py --feat-number {n} --json
```

Script vérifie 4 conditions (cf. docstring) : stack.md lisible / CLAUDE.md
projets présents / schema.json présent si DB / mtime stack.md ≤ CLAUDE.md.

| Exit | Action |
|---|---|
| `0` + `required: false` | Émettre `FEAT {n} — arch skip ({reason})`, → STEP 6 |
| `0` + `required: true` | Émettre `FEAT {n} — arch requis ({reason})`, → STEP 5 |
| `≠ 0` | Fallback safe : `arch_required = true` (arch idempotent) |

**Anti-derive** : pas de checks LLM dupliqués, fallback safe sur erreur
script, skip = perf jamais correction.

---

## STEP 5 — Pré-step arch (bootstrap + scaffolding DB idempotents)

**Conditionnel** : si `$arch_required == false` (STEP 4.bis), skip et
passer à STEP 6.

Sinon, invoquer agent `arch` (équivalent `/arch-init`). L'agent gère :
- idempotence du bootstrap (skip si projets initialisés)
- introspection DB et scaffolding Database-First si `DatabaseType ≠ none`
  (skip silencieux sinon)

- `arch` OK → STEP 5.5
- `arch` échoue → propager ERROR et **STOP** (dev-* ne peut tourner
  sans projet initialisé / entities scaffold si DB requise)

---

## STEP 5.5 — Phase plan initialization (SSoT)

**Owner unique du calcul `$PHASE_PLAN`** consommé par STEP 6.4 (auditor batch).
Sans guard, `if phases.X.enabled` faute silencieusement → batch dégénère.

Atomic write (`.tmp.{PID}` + fsync + rename) anti-corruption mid-write
(post-mortem : JSON tronqué = décision auditor corrompue silencieusement).

```bash
mkdir -p workspace/output/.sys/.state
TMP=workspace/output/.sys/.state/phase-plan-{n}.json.tmp.$$
python .claude/python/sdd_scripts/phase_planner.py --feat-number {n} --json > "$TMP"
PP_EXIT=$?
if [ "$PP_EXIT" -ne 0 ]; then
  rm -f "$TMP"
  echo "ERROR: [PHASE_PLAN_INIT_FAILED] phase_planner.py exit $PP_EXIT (FEAT {n})"
  echo "FIX: vérifier workspace/input/feats/{n}-*.md + Project Config + /sdd-status {n}"
  exit 2
fi
sync "$TMP" 2>/dev/null || true
mv "$TMP" workspace/output/.sys/.state/phase-plan-{n}.json
PHASE_PLAN=$(cat workspace/output/.sys/.state/phase-plan-{n}.json)
```

`phase_planner.py` : Python pur, 0 LLM, ~50 ms. JSON persisté disque +
`state.json.phases.planning.payload` (via `sdd_state.py set-phase`) pour
récap `/sdd-full §5`.

**Lecture STEP 6.4** (cross-tool-call) : `cat workspace/output/.sys/.state/phase-plan-{n}.json`
(la bash var $PHASE_PLAN ne survit pas aux tool-call boundaries).

## STEP 6 — Workflow gated séquentiel (cf. `.claude/rules/build-and-loop.md`)

**Défaut** : back → QA API gate → front, plus de parallélisme back+front.

```
6a. dev-backend ALL US (parallèle bornée par MaxParallel)
        ↓
6b. QA API Gate (tests d'intégration HTTP, in-memory DB)
        ↓
   ├── PASS / WARN / SKIPPED → 6c. dev-frontend ALL US (parallèle bornée)
   ├── FAIL                  → STOP + rapport, l'humain corrige et relance /dev-run
   └── INFRA_BLOCKED         → STOP + ERROR [QA_FRAMEWORK_MISSING] (config infra)
```

Statuts canoniques API Gate (v7.0.0) : `PASS | WARN | FAIL | SKIPPED | INFRA_BLOCKED`.
Détail sémantique + critère arithmétique : `.claude/rules/build-and-loop.md §1.3`.

Lire `## Project Config` :
- `GatedWorkflow` (default `true`) : si `false`, fallback legacy parallèle
  (log `workspace/output/.sys/.audit/legacy-parallel.log`). Déconseillé.
- `ApiGateRequired` (default `true`) : si `false` ET `GatedWorkflow: false`,
  status devient `SKIPPED` (gate désactivée).

### 6.0 Détection automatique du mode From Plan

Avant invocation, Glob `workspace/output/plans/{n}-*-*.{back,front}.md`.
Chaque dev-* détecte son plan au démarrage et bascule en mode From Plan.

Émettre 1 ligne :
```
FEAT {n} — {U} US : {P_back} plans backend + {P_front} plans frontend détectés (mode From Plan)
```

### 6.0.bis Plan staleness check

Pour chaque plan détecté en 6.0, vérifier non-stale via `validate_plan.py`
(0 token) :

```bash
python .claude/python/sdd_scripts/validate_plan.py \
  --plan-path "workspace/output/plans/{n}-{m}-{Name}.{back|front}.md" \
  --us-path "workspace/output/us/{n}-{m}-{Name}.md" --json
```

| Exit | Action |
|---|---|
| `0` / `1` | plan valide → 6.a |
| `2` | STOP + ERROR `[PLAN_STALE]` ou `[PLAN_INVALID]` (FIX : `/dev-plan {n}`) |

### 6.a Phase Backend — invocations dev-backend bornées

Pour chaque US `{n}-{m}-{Name}`, invoquer en batches de `$max_parallel`.

```
$batches = chunk(US_LIST, size = $max_parallel)
for batch in $batches:
    invoquer en parallèle :
      pour chaque US dans batch :
        Agent(dev-backend, args="{n}-{m}")         # Opus 4.7
    attendre fin du batch
```

Émettre 1 ligne par batch :
```
FEAT {n} — backend batch {i}/{B} : US {liste-{m}} → {U_batch} invocations
```

Chaque agent :
- US backend/fullstack → génère code serveur
- US frontend pure → exit `skipped (frontend-only US)`

**Échec US backend** : continue les autres invocations du batch. À la
fin de 6a si ≥ 1 US backend en échec → émettre :
```
🔴 /dev-run {n} — phase backend incomplète ({F_back} US en échec sur {U})

Échecs :
  - dev-backend {n}-{m}-{Name} : {raison condensée}
  ...

L'API gate ne peut pas tourner sur un backend incomplet. Corriger les
erreurs (cf. logs dev-backend) puis relancer /dev-run {n}.
```
**STOP**, pas de 6b ni 6c.

### 6.b Phase QA API Gate (tests d'intégration HTTP)

Si toutes US backend OK (incl. skipped frontend-only), invoquer
`/qa-generate {n} --mode api-tests` (cf. `.claude/rules/build-and-loop.md §1`).

Contenu :
- Tests d'intégration HTTP par endpoint backend (style Postman) avec
  **in-memory DB** ou mocks selon stack QA actif
- Couverture min `ApiGateMinPerEndpoint` (default 2 — 1 happy + 1 négatif)
- Auth mockée (test handler), jamais Azure AD réel
- Rapport humain : `workspace/output/qa/feat-{n}/api-tests.md`
- Données interrogeables : `workspace/output/db/console.db`
  (tables `qa_api_tests` + `qa_api_endpoints`, depuis v6.10)

Lire le verdict consolidé depuis la DB (`.json` éphémère ingéré et supprimé
par `qa-generate` STEP 6.bis) :

```bash
GATE_JSON=$(python .claude/python/sdd_scripts/query_console_db.py api-gate --feat {n})
# v7+ schema: `status` PASS|WARN|FAIL|SKIPPED|INFRA_BLOCKED ; v6: `gate_passed` bool.
STATUS=$(echo "$GATE_JSON" | python -c "
import json, sys
d = json.load(sys.stdin)
if 'status' in d:
    print(d['status'])
elif 'gate_passed' in d:
    print('PASS' if d['gate_passed'] else 'FAIL')  # legacy v6 derive
    sys.stderr.write('[QA/WARN] api-gate v6 schema — migration console.db pending\n')
else:
    print('INFRA_BLOCKED')
    sys.stderr.write('[QA/FAIL] api-gate schema unknown — fail-safe INFRA_BLOCKED\n')
")
TESTS_FAILED=$(echo "$GATE_JSON" | python -c "import json,sys; print(json.load(sys.stdin).get('tests_failed', 0))")
```

Décision (canonique v7.0.0, cf. `build-and-loop.md §1.3`) :

| `status` | Action |
|---|---|
| `PASS` | → 6c (vert) |
| `WARN` | → 6c + propager WARNING verdict QA global |
| `SKIPPED` | → 6c silent (0 endpoint OU gate désactivée) |
| `FAIL` | STOP — bloc `6.b.STOP` (mismatch contrat back↔front) |
| `INFRA_BLOCKED` | STOP + ERROR `[QA_FRAMEWORK_MISSING]` (runner KO — fix infra, **pas** régression code) |

> Compat : `gate_passed: true` couvre PASS/WARN/SKIPPED. Préférer `status`
> pour distinguer "rien à tester" (SKIPPED) d'un vrai pass.

### 6.b.STOP — Format STOP sur FAIL

```
🔴 /dev-run {n} — API Gate RED ({F_api} test(s) échoué(s) sur {T_api})

Rapport : workspace/output/qa/feat-{n}/api-tests.md
Endpoints en échec :
  - {VERB} {route} : {N_failed}/{N_total} cases ko
    cause : {message condensé du 1er échec}
  ...

Frontend NON généré pour cette session.

Pour débloquer :
  1. corriger le code backend (workspace/output/src/{BackendName}/...) OU
     régénérer une US backend cassée : /dev-backend {n}-{m}
  2. re-tester (rapide) : /qa-generate {n} --mode api-tests --filter {endpoint}
  3. quand 🟢 GREEN → relancer /dev-run {n} (la phase 6a saute,
     6b re-confirme, 6c démarre)
```

### 6.c Phase Frontend — invocations dev-frontend bornées

**Uniquement si 6b a passé en 🟢 ou 🟡.** Pour chaque US, invoquer
en batches de `$max_parallel` :

```
$batches = chunk(US_LIST, size = $max_parallel)
for batch in $batches:
    invoquer en parallèle :
      pour chaque US dans batch :
        Agent(dev-frontend, args="{n}-{m}")         # Opus 4.7
    attendre fin du batch
```

Émettre 1 ligne par batch :
```
FEAT {n} — frontend batch {i}/{B} : US {liste-{m}} → {U_batch} invocations
```

Chaque agent bénéficie de la **certitude que les endpoints backend
honorent leur contrat** (vérifié par 6b). Les mismatches
`[FRONTEND_BACKEND_CONTRACT_GAP]` ne peuvent plus se produire en
silence.

**Idempotence re-run après correction backend** : au début de 6a, requêter
la DB. Si verdict postérieur au mtime backend ET `status ∈ {PASS, WARN}` →
skip 6a + 6b → 6c. `SKIPPED` ne déclenche pas le skip ("0 endpoint testé"
≠ preuve stabilité).

```bash
GATE=$(python .claude/python/sdd_scripts/query_console_db.py api-gate --feat {n})
GATE_STATUS=$(echo "$GATE" | python -c "
import json,sys; d=json.load(sys.stdin)
print(d.get('status') or ('PASS' if d.get('gate_passed') else 'FAIL'))
")
GATE_TS=$(echo "$GATE" | python -c "import json,sys; print(json.load(sys.stdin).get('extracted_at', ''))")
```

Skip 6a+6b si `GATE_STATUS in {PASS, WARN}` ET `GATE_TS > mtime(backend)`.
Émettre `FEAT {n} — backend stable, skip 6a+6b → 6c`.

### Mode legacy parallèle (`GatedWorkflow: false`)

Fallback workflow v3.x (back+front parallèles même batch). Logger
`workspace/output/.sys/.audit/legacy-parallel.log`, WARN au récap STEP 7.
Réservé projets simples sans contrat backend fragile.

---

## STEP 6.4 — Auditor batch parallèle (4 auditors)

**Conditionnel** : jusqu'à **4 agents auditor EN PARALLÈLE** (un seul message
multi-tool-use) selon `phase_planner.py` (réutiliser `$PHASE_PLAN` STEP 5.5)
+ `ArchReviewMode` Project Config. Verdict consolidé pilote STEP 6.5 ou STOP.

**Pourquoi pas pré-déclenché en parallèle avec 6.c (dev-frontend)** : les 4
agents exigent **code complet back + front** : spec-compliance vérifie ACs
sur src/{BackendName,AppName}/**, arch-reviewer lit plans + code, code-reviewer
détecte `[FRONTEND_BACKEND_CONTRACT_GAP]` cross-fichier, security scan CORS
allowlist + JWT flow client↔serveur. Séquence 6.a→6.b→6.c→6.4→6.5 optimale.

### 6.4.1 — Construction du batch

```python
# RE-READ phase plan depuis disque (shell var $PHASE_PLAN STEP 5.5 ne survit
# pas aux tool-call boundaries — chaque Bash = subshell indépendant).
import json, pathlib
plan_path = pathlib.Path(f"workspace/output/.sys/.state/phase-plan-{n}.json")
if not plan_path.is_file():
    STOP + ERROR("[PHASE_PLAN_INIT_FAILED] state file missing",
                 f"FIX: re-run STEP 5.5 OR phase_planner.py --feat {n}")
phase_plan = json.loads(plan_path.read_text(encoding="utf-8"))
phases = phase_plan.get("phases", {})

# Hard-fail si phase_planner.py JSON malformé (sinon 3/4 reviewers skip silencieux).
# RUPT-4 : phases est dict Python → mapping `phases["X"]`, PAS attribute access.
if not phases or not all(k in phases for k in ("code_review", "security_scan", "spec_compliance")):
    STOP + ERROR("[PHASE_PLAN_INIT_FAILED] phases dict unusable",
                 f"FIX: rerun phase_planner.py --feat {n} et inspecter output")

arch_review_mode = read_layered_config(keys=("ArchReviewMode",)).get("ArchReviewMode", "manual")

BATCH = []
if phases["code_review"].get("enabled"):       BATCH.append(Agent("code-reviewer", args="{n}"))
if phases["security_scan"].get("enabled"):     BATCH.append(Agent("security-reviewer", args="{n}"))
if phases["spec_compliance"].get("enabled"):   BATCH.append(Agent("spec-compliance-reviewer", args="{n}"))
if arch_review_mode == "full":                 BATCH.append(Agent("arch-reviewer", args="{n}"))
```

Si `BATCH == []` → skip STEP 6.4, passer à STEP 6.5.

Sinon dispatcher **en parallèle dans un seul message**. Paths d'écriture
disjoints (cf. `ownership.md §1`).

> `accessibility-auditor` retiré v7.0.0 (`governance-major-auditors-trim`,
> remplacé par axe-core CI). Entrée legacy ignorée silencieusement.

### 6.4.2 — Lecture des verdicts

| Agent | Verdict path | Champ |
|---|---|---|
| code-reviewer | `{n}-code-review.json` | `summary.verdict` |
| security-reviewer | `{n}-security-scan.json` | `summary.verdict` |
| spec-compliance-reviewer | `{n}-spec-compliance.json` | `summary.verdict` |
| arch-reviewer | `{n}-arch-review.json` | `summary.verdict` |

Tous sous `workspace/output/.sys/.validation/`. Fichier absent (agent STOP
runtime) → `🔴 RED [AUDITOR_RUNTIME_ERROR]`. **Exception arch-reviewer** :
échec runtime → WARN seulement (jamais hard-blocking par design,
`ArchReviewFailOn: serious` défaut).

### 6.4.3 — Verdict consolidé

`verdict_overall = max_severity({non-skipped})` (🔴 > 🟡 > 🟢).

| Verdict | Action |
|---|---|
| 🟢 GREEN | → STEP 6.5 |
| 🟡 WARN | → STEP 6.5 + log WARN STEP 7 récap |
| 🔴 RED | STOP — bloc 6.4.STOP, pas de STEP 6.5 |

### 6.4.STOP — Format STOP sur RED

```
🔴 /dev-run {n} — auditor batch RED ({N_red} agents en échec)

Verdicts :
  - code-reviewer    : {🟢|🟡|🔴} (blocking: {class si applicable})
  - security-scan    : {🟢|🟡|🔴}
  - spec-compliance  : {🟢|🟡|🔴}
  - arch-reviewer    : {🟢|🟡|⚪ skipped}

Rapports : workspace/output/.sys/.validation/{n}-*.md

Débloquer :
  1. Lire rapports 🔴 (issues critical/serious + suggestions FIX)
  2. Corriger (/dev-{backend|frontend} {n}-{m} ou édit manuel)
  3. Relancer /dev-run {n} (idempotent : skip 6.a/6.b/6.c si stables)

Bypass : baisser CodeReviewFailOn / SecurityFailOn / SpecComplianceFailOn
en Project Config. Hard-blocking (secrets, SQL injection, contract drift)
non-overridable.
```

### 6.4.4 — Émission succès

```
✓ code-reviewer    : {🟢|🟡} — {C}/{S}/{M}/{m} issues
✓ security-scan    : {🟢|🟡} — {C}/{S}/{M}/{m} issues
✓ spec-compliance  : {🟢|🟡} — {V}/{T} ACs verified
✓ arch-reviewer    : {🟢|🟡} — {P} pattern violations  (si ArchReviewMode=full)
FEAT {n} — auditor batch {🟢|🟡} (→ STEP 6.5 INDEX ADRs)
```

Agents skippés : `⊘ {agent} : skipped ({reason})`.

### 6.4.5 — State tracking

```bash
python .claude/python/sdd_scripts/sdd_state.py set-phase \
  --run-id $RUN_ID --phase auditor_batch --status {pass|warn|fail} \
  --payload-json '{"code_review":"{v}","security_scan":"{v}","spec_compliance":"{v}","arch_review":"{v|skipped}"}'
```

### 6.4.6 — Anti-derive

- 4 agents **idempotents** (relancer écrase rapports)
- **Pas de fallback** sur 🔴 : Tech Lead corrige
- Auditors n'ont **PAS** de `build_loop` (`[REVIEW_*]`/`[SEC_*]`/`[SPEC_*]` "Itère: NON")
- `phase_planner.py` = 0 token LLM
- spec-compliance lit le code indépendamment AC-par-AC (pattern superpowers v5.1)

---

## STEP 6.5 — Refresh INDEX ADRs (déterministe)

Exécuter **systématiquement** après le gated workflow pour régénérer
`workspace/output/.sys/.context/adrs/INDEX.md` (dev-* ont peut-être créé
des ADRs phase 5 que `arch` n'a pas indexés) :

```bash
python .claude/python/sdd_scripts/index_adrs.py
```

Coût : **0 token**, latence < 100 ms. Non bloquant : sur exit ≠ 0,
émettre WARNING + continuer vers STEP 6.6 puis STEP 7.

---

## STEP 6.6 — Checkpoint record (v6.6.5, opt-in)

Si toute la phase dev terminée (build vert, API Gate non-RED, auditeurs
non-RED) ET `CheckpointMode ∈ {record, resume}` :

```python
from sdd_lib.checkpoint import record_input_hash

record_input_hash(
    run_id=$RUN_ID,
    phase="dev-run",
    input_paths=resolved_inputs,   # même liste que STEP 1.75
)
```

Stocke `input_hash` dans `state.json.phases.dev-run.payload.input_hash`.
Permet un futur `--resume` (avec `CheckpointMode: resume`) de skip
l'intégralité de `/dev-run {n}` si les inputs (FEAT + US + mockups +
stack.md) n'ont pas changé.

Erreur silencieuse si state.json absent → WARN dans stderr, non bloquant.

**Non émis si** :
- Phase dev a échoué (build_loop exhausted, API Gate RED, auditor RED)
- `CheckpointMode: off` (défaut)

---

## STEP 6.bis — Status flip US (v6.10.5, fix CRIT-2)

Pour chaque US dont **les builds backend ET frontend** ont réussi (ou
ont été skippés sans erreur — US frontend-only ou backend-only), flipper
`InProgress → Review`. Skip si API Gate RED ou build_loop exhausted
(US reste `InProgress`, signalant le besoin de correction).

```bash
for us_file in workspace/output/us/{n}-*.md; do
  us_id=$(basename "$us_file" .md | grep -oE '^[0-9]+-[0-9]+')
  # Flip uniquement si la phase dev n'a pas échoué pour cette US
  # (Tb_ok + Tf_ok inclut cette US OU elle est skipped sans erreur)
  python .claude/python/sdd_scripts/set_us_status.py \
    --us "$us_id" --status Review 2>/dev/null || true
done
```

Idempotent et non-bloquant. Si API Gate RED → SKIP cette phase
entièrement (le STOP §6.b prend le relais, les US restent `InProgress`).

---

## STEP 7 — Récap final

Émettre **un seul bloc final** consolidé (≤ 7 lignes en cas nominal) :

```
✅ FEAT {n} — phase dev terminée (gated)

Workflow      : gated back→API gate→front (MaxParallel={$max_parallel})
Bootstrap + DB : {init | skipped (short-circuit) | invoked} ({N_tables} tables | DB=none)
Backend       : {Tb_ok}/{U} US ({Tb_skip} skipped, {F_back} échec)
API Gate      : {Tg_passed}/{Tg_total} tests · {N_endpoints} endpoints couverts → {🟢 GREEN | 🟡 YELLOW | 🔴 RED}
Frontend      : {Tf_ok}/{U} US ({Tf_skip} skipped, {F_front} échec) | not run (gate RED)
```

Notation `Bootstrap + DB` :
- `skipped (short-circuit)` : STEP 4.bis a détecté un bootstrap stable
  (cf. depuis 2026-05-10) — l'agent arch n'a pas été invoqué
- `invoked` : agent arch invoqué, idempotence interne (skip Init
  Commands, scaffolding incrémental)
- `init` : premier run (projets créés depuis zéro)

Cas succès complet :
```
✅ /dev-run {n} — {U} US · gated GREEN · code dans workspace/output/src/
```

Cas API Gate RED → format §6.b.STOP (seul rapport affiché).

---

## Règles de cette commande

- **Autonome** — pas de Q/R utilisateur.
- **STEP 6 parallèle bornée** (depuis v3.1.3) : invocations groupées
  en batches de `$max_parallel` US (= jusqu'à `2 × $max_parallel`
  invocations simultanées par batch). Au sein d'un batch, toutes les
  invocations sont dans **un seul message Agent en parallèle** (pas
  de boucle séquentielle). Les batches sont enchaînés séquentiellement
  (le batch `i+1` démarre quand TOUTES les invocations du batch `i`
  sont terminées). Default `$max_parallel = 3`. Configurable via
  `--max-parallel N` ou `MaxParallel: N` dans `## Project Config`.
- **Pas de modification** des US, mockups HTML ou stack.
- **Idempotent** : relancer `/dev-run {n}` regénère le code (chaque
  agent dev gère lui-même l'écrasement). Bootstrap + scaffolding DB
  sont idempotents par construction.
- **Erreur isolée par US** : un échec sur 1 US ne casse pas les autres.
- **Séparation des familles** : dev-backend ne lit jamais les stacks
  frontend/ui (le mockup HTML est lu en passif uniquement pour
  identifier les endpoints implicites) ; dev-frontend ne lit jamais
  les stacks backend hors patterns d'injection auth.
- **Pas de pré-step DB séparé** : le scaffolding Database-First est
  intégré à l'agent `arch` depuis SDD_Pro v2.1.

---

## Chat Output Protocol

> Cette commande applique strictement `@.claude/rules/output-protocol.md`.
> Substance non dupliquée — la règle est SSoT.

**Labels canoniques émis** : `[PLAN]`, `[ARCH]`, `[CONSTITUTION]`,
`[DEV-BACKEND]`, `[QA]` (API Gate), `[DEV-FRONTEND]`, `[CODE-REVIEW]`,
`[SPEC-REVIEW]`, `[ARCH-REVIEW]`, `[SECURITY]`, `[DONE]` (cf. output-protocol.md §3)
**Plage de progression couverte** : `15-78%` (sans review/QA finale,
cf. output-protocol.md §4)

**Granularité cible** : 1 update par phase orchestrée (typiquement
8-10 updates : plan → arch → backend ALL US → API Gate → frontend
ALL US → verdict). Chaque sub-agent émet ses updates dans sa plage.

**Interdits stricts** (cf. §5 du protocole) :
- chemins de fichiers internes (`workspace/...`, `.claude/...`)
- listes d'US par batch (compteur par batch suffit, ex. `2/3 US livrées`)
- détail des invocations parallèles dev-backend + dev-frontend
- stdout/stderr de bash, JSON dumps phase_planner.py

**API Gate** : 1 ligne dédiée transitionnelle entre dev-backend ALL US
et dev-frontend ALL US, avec statut canonique
PASS/WARN/FAIL/SKIPPED/INFRA_BLOCKED (cf. `build-and-loop.md §1.3`).
Exemple : `[QA] API Gate: 16/16 endpoints couverts, status PASS. (66%)`.

**Verdict final** : 1 ligne `[DONE]` (🟢) / `[DONE/WARN]` (🟡) /
`[DONE/FAIL]` (🔴) (cf. §9.1). Pas de "next steps" après (cf. §9.3).

**Erreurs intermédiaires** : chat 1L avec classe `[CLASS]` + pointeur
fichier rapport (cf. §7.2). Format 3L disque préservé.

**Bypass debug** : `SDD_CHAT_VERBOSE=1` → mode legacy verbose (§10).
