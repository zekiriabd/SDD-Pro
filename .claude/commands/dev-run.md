# /dev-run — Orchestrateur dev (arch+db → back + front en parallèle) pour 1 FEAT

> ⚠️ **Commande interne v7.0.0** — invoquée par /sdd-full STEP 4.
> Orchestrateur dev (arch+back+API+front) — invoqué par /sdd-full.
> Utilisateur final : préférer la commande orchestrante (`/sdd-full` ou `/dev-run`)
> qui gère pré-conditions, idempotence et état. Conservée comme command pour
> debug/inspection ciblée et préservation des chaînes d'invocation documentées.

> **Dépendance load-bearing au runtime Claude Code** : orchestration
> parallèle via tool `Agent` (alias `Task`) avec N calls indépendants
> dans un même message. Contrat externe garanti par Claude Code.
> Anti-régression : `framework_smoke.py` vérifie la présence de
> « parallèle » + `Agent` + `dev-backend` + `dev-frontend`.

Pour la FEAT `{n}`, en séquence :

1. **Pré-step `arch`** (idempotent) — bootstrap solution/projets selon
   stacks actifs + scaffolding DB Database-First si `DatabaseType ≠ none`
   (les deux phases sont gérées par le même agent `arch`)
2. **`dev-backend` + `dev-frontend` EN PARALLÈLE** sur toutes les US ;
   chaque agent décide s'il a du travail (fullstack/frontend pure/
   backend pure) ou exit silencieux

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
Done` US-level suffit (cf. `file-ownership.md §6`).

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
FEAT {n} — {U} US à matérialiser (back + front en parallèle)
```

---

## STEP 2.bis — Valider le graphe de dépendances `## Dependencies` (v6.8+)

Avant batching, valider et ordonner `US_LIST` selon le graphe de dépendances
déclaré dans les sections `## Dependencies` des US (cf. `templates/us.template.md`).

```bash
python .claude/python/sdd_scripts/validate_us_deps.py --feat {n} --json
```

| Exit | Sens | Action |
|---|---|---|
| 0 | Graphe valide (orphelins tolérés, INFO) | Continuer ; remplacer `US_LIST` par le topo order |
| 3 | `[US_DEPS_CYCLE]` | STOP + ERROR, Tech Lead corrige les `## Dependencies` |
| 4 | `[US_DEPS_MISSING]` | STOP + ERROR, ref vers US inexistante |
| 1/2/5 | erreur infra | STOP + ERROR |

Sur exit 0, récupérer **les batches layered Kahn** (v7.0.0 audit P0 R3) :

```bash
# v7.0.0 strict batching — une ligne par layer, ids US séparés par espaces.
# Garantie : aucun US dans un layer ne dépend d'un autre US du même layer.
US_LAYERS=$(python .claude/python/sdd_scripts/validate_us_deps.py --feat {n} --layered-batches)
```

`US_LAYERS` est consommé en STEP 6.a / 6.c comme suit :
```bash
while IFS= read -r layer; do
    # Chaque layer = US indépendants entre eux → safe parallel
    # Si layer plus grand que MaxParallel, chunk en sous-batches DE LA MÊME LAYER
    # (toujours safe car tous indépendants par construction).
    for sub_batch in chunk("$layer", $max_parallel); do
        invoke_parallel(sub_batch)   # dev-backend OU dev-frontend selon STEP
        wait                          # attendre fin du sous-batch
    done
done <<< "$US_LAYERS"
```

**Fallback compat** : si `--layered-batches` non supporté (script ancien),
fallback sur `--topo` :
```bash
US_LIST=$(python .claude/python/sdd_scripts/validate_us_deps.py --feat {n} --topo)
# Heuristique : chunk(US_LIST, $max_parallel) — risque de collision intra-batch
# si dépendance proche (cf. ancien comportement v6.7–v6.10).
```

**Backward-compat strict** : pour les US legacy sans `## Dependencies` (ou avec
`NONE`), le graphe est vide, le layered Kahn renvoie 1 seul layer contenant
toutes les US (tri alphabétique stable), et le comportement est byte-identique
à `--topo` v6.7. Aucune US v1 n'est cassée.

**Invariant aval (STEP 6.a, 6.c) — v7.0.0 strict** : au sein d'un layer, les
US sont **pairwise indépendantes** (aucune dépendance interne). Donc :

1. Aucune race sur `{LibName}/` ou autre artefact partagé (cf.
   `ownership.md §4` LibName lock O_EXCL).
2. Le chunking par `MaxParallel` à l'intérieur d'un layer **préserve** la
   sécurité (les US d'un sous-batch sont triviallement indépendantes puisque
   c'est un sous-ensemble d'un layer indépendant).
3. Inter-layer : layer K attend la fin du layer K-1 avant de démarrer
   (synchronisation explicite via `wait` shell ou équivalent batched
   sequencing).

→ La concession historique `dev-run.md` v6.10 (« le topo order minimise les
violations mais ne les élimine pas pour des graphes denses ») est **résolue**
en v7.0.0. Le diamant `A→B, A→C, B→D, C→D` est désormais ordonnancé en
3 layers : `{A}`, `{B, C}`, `{D}` — `D` n'est jamais dans le même batch que `B` ni `C`.

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

## STEP 4.bis — Détection short-circuit arch (script-driven, v6.1)

**But** : sur FEATs ≥ 2 (ou re-runs), éviter le coût arch (build,
ré-introspection DB, ré-écriture CLAUDE.md, refresh INDEX.md) quand le
bootstrap est stable. Logique déterministe déléguée au script Python.

### 4.bis.0 — Bypass via flag

Si `$rebuild_arch == true` (flag `--rebuild-arch` passé) → forcer
`$arch_required = true`, skip 4.bis.1 et aller directement à STEP 5.
Émettre 1 ligne :
```
FEAT {n} — arch forcé (--rebuild-arch)
```

### 4.bis.1 — Invocation du script déterministe

```bash
python .claude/python/sdd_scripts/detect_arch_shortcircuit.py \
  --feat-number {n} --json
```

Le script vérifie les 4 conditions (cf. `detect_arch_shortcircuit.py`
docstring) :
1. `workspace/input/stack/stack.md` lisible avec `## Project Config` + `## Active Database` exploitables
2. CLAUDE.md projet présents pour chaque famille active (back, front, lib si LibName)
3. `workspace/output/db/schema.json` présent si `DatabaseType ≠ none` (lu depuis `## Active Database`)
4. mtime stack.md ≤ mtime du plus ancien CLAUDE.md projet

Sortie JSON sur stdout :
```json
{
  "required": false,
  "reason": "bootstrap stable, schema DB présent, CLAUDE.md cohérents",
  "checks": { ... }
}
```

| Exit | Sens | Action |
|---|---|---|
| `0` + `required: false` | Skip arch | Émettre 1 ligne (cf. 4.bis.3 cas skip), aller à STEP 6 |
| `0` + `required: true` | Arch nécessaire | Émettre 1 ligne (cf. 4.bis.3 cas requis), continuer STEP 5 |
| `1` ou `2` | Erreur script | Fallback safe : forcer `$arch_required = true` (arch est idempotent) |

### 4.bis.3 — Émission (1 ligne)

**Cas skip** :
```
FEAT {n} — arch skip ({reason du JSON})
```

**Cas requis** :
```
FEAT {n} — arch requis ({reason du JSON})
```

### 4.bis.4 — Anti-derive

- Ne PAS dupliquer les checks en LLM (laisser le script faire)
- Erreur script (exit ≠ 0) → fallback safe `arch_required: true`
- Skip = raccourci de performance, jamais de correction (arch
  idempotent en interne)

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

## STEP 5.5 — Threat model pré-dev (RETIRÉ v7.0.0)

> **v7.0.0 (governance-major-auditors-trim)** : le mode `threat-model`
> de `security-reviewer` est **supprimé**. Le défaut
> `SecurityThreatModelEnabled` est flippé `true → false` dans
> `config.base.yml`. La STEP est conservée numériquement pour
> préserver la numérotation aval, mais **aucun agent n'est spawné ici**.
>
> **Remplacement** : template humain à instancier par le Tech Lead
> pré-`/arch-init` — `.claude/templates/threat-model.template.md`
> (STRIDE light, ~15-30 min, ~150 LOC structurées : assets / actors /
> surfaces / threats / controls / residual / ADRs / review).
>
> Les classes `[SEC_*]` runtime (post-dev) restent gérées par
> `security-reviewer --mode scan` (STEP 6.4 du batch auditors).
>
> Aucune lecture de `phase_planner.threat_model` — la phase est
> systématiquement `enabled: false` avec `agent_removed: true` dans le JSON.

Passer directement à STEP 6.

### 5.5.4 — State tracking (legacy, conservé)

```bash
python .claude/python/sdd_scripts/sdd_state.py set-phase \
  --run-id $RUN_ID --phase threat_model --status pass \
  --payload-json '{"threats_count":N,"verdict":"informational"}'
```

---

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

### 6.0.bis Plan staleness check (v7.0.0 simplified)

> **Note v7.0.0** : la phase historique "Routing strict" (v6.2-v6.10) qui
> évaluait `plan-schema-version: 2 + strict-ready: true` pour router vers
> `dev-*-strict` (Sonnet 4.6) a été retirée. Les variants strict sont
> supprimés. La validation déterministe reste utile pour détecter les
> plans stale/invalides — mais ne route plus vers un agent alternatif.

Pour chaque plan détecté en 6.0, vérifier qu'il n'est pas stale via
`validate_plan.py` (0 token LLM) :

```bash
python .claude/python/sdd_scripts/validate_plan.py \
  --plan-path "workspace/output/plans/{n}-{m}-{Name}.{back|front}.md" \
  --us-path "workspace/output/us/{n}-{m}-{Name}.md" \
  --json
```

| Exit script | Action |
|---|---|
| `0` ou `1` | plan valide (avec ou sans Inline Digest) → continuer 6.a |
| `2` (stale/invalid) | STOP + ERROR `[PLAN_STALE]` ou `[PLAN_INVALID]` |

**Exit 2 bloquant** :
```
🔴 /dev-run {n} — plan stale ou invalide
Plan : workspace/output/plans/{n}-{m}-{Name}.{back|front}.md
Cause : [PLAN_STALE | PLAN_INVALID] {détail depuis JSON}
FIX : relancer /dev-plan {n} pour régénérer le plan, puis /dev-run {n}
```

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

Lire le verdict consolidé depuis la DB (le `.json` éphémère a été
ingéré et supprimé par `qa-generate` STEP 6.bis) :

```bash
GATE_JSON=$(python .claude/python/sdd_scripts/query_console_db.py api-gate --feat {n})
STATUS=$(echo "$GATE_JSON" | python -c "import json,sys; print(json.load(sys.stdin).get('status', 'INFRA_BLOCKED'))")
TESTS_FAILED=$(echo "$GATE_JSON" | python -c "import json,sys; print(json.load(sys.stdin).get('tests_failed', 0))")
# legacy fallback si DB pre-v7 sans 'status' :
# GATE_PASSED=$(echo "$GATE_JSON" | python -c "import json,sys; print(json.load(sys.stdin).get('gate_passed', False))")
```

Décision selon `status` (canonique v7.0.0, cf. `build-and-loop.md §1.3`) :

| `status` | Action |
|---|---|
| `PASS`           | continuer 6c (vert) |
| `WARN`           | continuer 6c + propager WARNING au verdict QA global |
| `SKIPPED`        | continuer 6c silencieusement (aucun endpoint OU gate désactivée) |
| `FAIL`           | STOP, voir bloc `6.b.STOP` ci-dessous (mismatch contrat back↔front) |
| `INFRA_BLOCKED`  | STOP + ERROR `[QA_FRAMEWORK_MISSING]` (test runner / fixtures KO — corriger config infra avant retry, **pas** une régression code) |

> Compat : la sortie `gate_passed: true` couvre `PASS`, `WARN`, `SKIPPED`.
> Les callers legacy peuvent continuer à le lire ; les nouveaux callers
> doivent préférer `status` pour distinguer "rien à tester" (`SKIPPED`)
> d'un vrai pass (`PASS`).

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

**Idempotence (re-run après correction backend, v6.10)** : au début de
6a, requêter la DB pour le verdict API Gate le plus récent et son
`extracted_at`. Comparer avec le mtime des fichiers backend. Si le
verdict DB est postérieur **et** `gate_passed: true`, skip 6a + 6b et
passer directement à 6c.

```bash
GATE=$(python .claude/python/sdd_scripts/query_console_db.py api-gate --feat {n})
GATE_PASSED=$(echo "$GATE" | python -c "import json,sys; print(json.load(sys.stdin).get('gate_passed', False))")
GATE_TS=$(echo "$GATE" | python -c "import json,sys; print(json.load(sys.stdin).get('extracted_at', ''))")
```

Émettre :
```
FEAT {n} — backend stable (console.db qa_api_tests GREEN @ {GATE_TS}), skip 6a+6b → 6c frontend
```

### Mode legacy parallèle (`GatedWorkflow: false`)

Si `GatedWorkflow: false` dans Project Config OU flag `--unsequenced`
sur la ligne de commande : revenir au workflow v3.x (back+front
parallèles dans un même batch). Logger dans
`workspace/output/.sys/.audit/legacy-parallel.log`. Émettre WARN dans le
récap STEP 7. Supporté uniquement pour projets simples sans contrat
backend fragile.

---

## STEP 6.4 — Auditor batch parallèle (code-review + security-scan + spec-compliance, v7.0.0)

**Conditionnel** : invoque les 3 agents auditor **EN PARALLÈLE** (un
seul message Agent multi-tool-use) pour les phases enabled selon
`phase_planner.py` (cf. STEP 5.5.1 — réutiliser `$PHASE_PLAN`).
Lecture mode + verdicts post-exécution. Le verdict consolidé pilote
le passage à STEP 6.5 ou STOP.

> **Anti-régression `framework_smoke.py`** : les invocations parallèles
> ci-dessous utilisent le tool `Agent` (alias `Task`) avec multiples
> calls indépendants dans un même message. Pattern identique à STEP 6.a
> et 6.c. Ne pas casser.

> **v7.0.0** : `accessibility-auditor` **retiré** du batch
> (governance-major-auditors-trim). Remplacé par axe-core CI dans le
> projet généré. Si `$PHASE_PLAN.a11y_audit.enabled == true` (legacy
> Project Config qui n'a pas flippé `A11yMode: off`), l'entrée du batch
> est **ignorée silencieusement** côté caller — pas d'agent à spawn.

### 6.4.1 — Construction du batch

```python
BATCH = []  # liste d'invocations à dispatcher en parallèle
if phases.code_review.enabled:
    BATCH.append(Agent("code-reviewer", args="{n}"))
if phases.security_scan.enabled:
    BATCH.append(Agent("security-reviewer", args="{n}"))   # --mode scan supprimé v7.0.0
if phases.spec_compliance.enabled:
    BATCH.append(Agent("spec-compliance-reviewer", args="{n}"))
# v7.0.0 : phases.a11y_audit ignored — agent removed.
# Replacement : axe-core in the generated project's CI step.
```

Si `BATCH == []` (toutes phases skipped) → skip STEP 6.4 entier,
passer à STEP 6.5 (dashboard).

Sinon, dispatcher **toutes les invocations en parallèle dans un seul
message**. Attendre la fin de l'ensemble. Pattern identique aux batches
dev-* (STEP 6.a, 6.c) — toutes les invocations sont indépendantes
(paths d'écriture disjoints, cf. `agents/*.md §Idempotence` et matrice
`file-ownership.md §1`).

### 6.4.2 — Lecture des verdicts

Après réception des 3 (ou moins) agents, lire les rapports JSON :

| Agent | Verdict path | Champ |
|---|---|---|
| code-reviewer | `workspace/output/.sys/.validation/{n}-code-review.json` | `summary.verdict` |
| security-reviewer | `workspace/output/.sys/.validation/{n}-security-scan.json` | `summary.verdict` |
| spec-compliance-reviewer | `workspace/output/.sys/.validation/{n}-spec-compliance.json` | `summary.verdict` |

Si un fichier attendu est absent (agent a STOP en erreur runtime) →
agent considéré comme `🔴 RED` avec cause `[AUDITOR_RUNTIME_ERROR]`.

### 6.4.3 — Verdict consolidé

```
verdict_overall = max_severity({verdicts non-skipped})
# ordering : 🔴 RED > 🟡 WARN > 🟢 GREEN
```

| Verdict | Action |
|---|---|
| 🟢 GREEN | continue STEP 6.5 (dashboard) |
| 🟡 WARN  | continue STEP 6.5 + log WARN dans STEP 7 récap |
| 🔴 RED   | STOP — afficher 6.4.STOP ci-dessous, ne pas exécuter dashboard |

### 6.4.STOP — Format STOP sur RED

```
🔴 /dev-run {n} — auditor batch RED ({N_red} agents en échec)

Verdicts :
  - code-reviewer       : {🟢|🟡|🔴} (blocking: {class si applicable})
  - security-scan       : {🟢|🟡|🔴}
  - spec-compliance     : {🟢|🟡|🔴}

Rapports :
  - workspace/output/.sys/.validation/{n}-code-review.md
  - workspace/output/.sys/.validation/{n}-security-scan.md
  - workspace/output/.sys/.validation/{n}-spec-compliance.md

Pour débloquer :
  1. Lire les rapports en 🔴 RED (issues critical/serious + suggestions FIX)
  2. Corriger (relancer /dev-{backend|frontend} {n}-{m} ciblé OU édit manuel)
  3. Relancer /dev-run {n} (idempotent : skip 6.a/6.b/6.c si stables, rerun 6.4)

Bypass (à utiliser en connaissance de cause) :
  - Baisser CodeReviewFailOn / SecurityFailOn / SpecComplianceFailOn dans Project Config
  - Override hard-blocking impossible (secrets, SQL injection, contract drift)
```

### 6.4.4 — Émission succès (verdict 🟢 ou 🟡)

1 ligne par agent invoqué + 1 ligne consolidée :

```
✓ code-reviewer       : {🟢 GREEN | 🟡 WARN} — {C}/{S}/{M}/{m} issues
✓ security-scan       : {🟢 GREEN | 🟡 WARN} — {C}/{S}/{M}/{m} issues
✓ spec-compliance     : {🟢 GREEN | 🟡 WARN} — {V}/{T} ACs verified
FEAT {n} — auditor batch {🟢 GREEN | 🟡 WARN} (continue → dashboard)
```

Pour les agents skippés (phase disabled) :
```
⊘ {agent_name} : skipped ({skip_reason du phase_planner})
```

### 6.4.5 — State tracking

```bash
python .claude/python/sdd_scripts/sdd_state.py set-phase \
  --run-id $RUN_ID --phase auditor_batch --status {pass|warn|fail} \
  --payload-json '{"code_review":"{verdict}","security_scan":"{verdict}","spec_compliance":"{verdict}"}'
```

### 6.4.6 — Anti-derive

- Les 4 agents sont **idempotents** (cf. `agents/*.md §Idempotence`) —
  relancer `/dev-run` les fera ré-tourner et écraser leurs rapports.
- **Pas de fallback** sur 🔴 RED : le Tech Lead corrige, pas l'agent.
- Phases auditor n'ont **PAS** de `build_loop` (cf.
  `error-classification.md §3` — classes `[REVIEW_*]`, `[A11Y_*]`,
  `[SEC_*]`, `[SPEC_*]` toutes "Itère: NON").
- Le `phase_planner.py` lui-même n'invoque aucun LLM (Python pur,
  déterministe, 0 token).
- **spec-compliance-reviewer ne fait pas confiance** au rapport des
  autres agents — lit le code indépendamment AC-par-AC (pattern
  superpowers v5.1, cf. `agents/spec-compliance-reviewer.md §Rôle`).

---

## STEP 6.5 — Refresh INDEX ADRs (auto, depuis 2026-05-08 ; déterministe en v7.0.0)

> **v7.0.0** : agent `dashboard` retiré (cf. STEP 4.7 de `/sdd-full`
> pour la migration). Remplacé par script Python `index_adrs.py`.

Exécuter **systématiquement** après le gated workflow pour régénérer :

```bash
python .claude/python/sdd_scripts/index_adrs.py
```

Sortie : `workspace/output/.sys/.context/adrs/INDEX.md` (utile : `dev-*`
ont peut-être créé des ADRs phase 5 que `arch` n'a pas indexés).

> **v6.10 BREAKING (préservé)** : les rendus HTML
> (`dashboard/README.html`, `qa/feat-{n}/dashboard.html`) restent
> retirés. Les métriques vivent dans `console.db` ; le rendu graphique
> est délégué à la console web.

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
