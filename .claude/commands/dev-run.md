# /dev-run — Orchestrateur dev (arch+db → back + front en parallèle) pour 1 SPEC

Pour la SPEC `{n}`, exécute en séquence :

1. **Pré-step `arch`** (idempotent) — bootstrap solution / projets vides
   selon les stacks actifs **+** scaffolding DB Database-First si
   `DatabaseType ≠ none` (les deux phases sont gérées par le même agent
   `arch` depuis SDD_Pro v2.1)
2. **`dev-backend` et `dev-frontend` EN PARALLÈLE** sur toutes les US
   de la SPEC ; chaque agent décide lui-même s'il a du travail (US
   fullstack, frontend pure, backend pure) ou exit silencieux

Mode **autonome** : pas de Q/R utilisateur.

**Usage :** `/dev-run {n}` — où `{n}` est le numéro de la SPEC.

**Hors scope :** la phase plan (`/us-generate`) doit avoir tourné
avant. Cette commande consomme `workspace/output/us/` (US) et `workspace/input/ui/`
(mockups HTML statiques optionnels).

---

## STEP 1 — Valider l'argument

Arguments :
- `{n}` (entier ≥ 1, **obligatoire**)
- `--force` (optionnel, depuis SDD_Pro v3) — bypass un éventuel rapport
  readiness existant en NO-GO. À utiliser en connaissance de cause.
- `--max-parallel N` (optionnel, depuis v3.1.3) — nombre maximum d'US
  traitées simultanément (1 US = jusqu'à 2 invocations dev-* en
  parallèle). Default : valeur de `MaxParallel` dans `## Project Config`
  de `workspace/input/stack/stack.md`, sinon **3** (heuristique conservatrice
  pour 4-6 US fullstack). Range : 1-12. Hors range → ERROR.

  Exemples :
  - `/dev-run 1` → utilise default (3 US à la fois → max 6 invocations
    parallèles).
  - `/dev-run 1 --max-parallel 1` → mode séquentiel (1 US, 2 invocations
    simultanées back+front, puis suivante).
  - `/dev-run 1 --max-parallel 6` → 6 US parallèles (max 12 invocations,
    comportement legacy v3.0.x).

  Stocker la valeur résolue dans `$max_parallel` consommé par STEP 6.2.

Si `{n}` absent → demander :
```
Quel est le numéro de la SPEC à matérialiser ? (ex. : 1)
```

Si `{n}` non numérique →
```
ERROR: /dev-run — argument invalide
CAUSE: "{argument}" n'est pas un entier
FIX: relancer /dev-run {n} (ex. /dev-run 1)
```

---

## STEP 1.5 — Vérification du rapport readiness (depuis SDD_Pro v3)

Read `workspace/output/validation/{n}-readiness.md` **si présent**.

- Fichier absent → continuer normalement (la gate n'a pas tourné — cas
  d'usage direct `/dev-run` sans passer par `/sdd-full`). Émettre un
  WARNING informationnel :
  ```
  WARNING: /dev-run — gate readiness non exécutée
  HINT: lancer /spec-validate {n} avant pour détecter les trous SPEC en amont
  ```
  puis continuer.

- Fichier présent + décision `🟢 GO` ou `🟡 WARN` → continuer.

- Fichier présent + décision `🔴 NO-GO` :
  - Si `--force` fourni → continuer + émettre :
    ```
    WARNING: /dev-run — bypass NO-GO via --force
    Rapport : workspace/output/validation/{n}-readiness.md (consulter §3)
    ```
  - Sinon → STOP :
    ```
    🔴 /dev-run {n} — bloqué par rapport readiness (NO-GO)
    Rapport : workspace/output/validation/{n}-readiness.md
    FIX :
      1. corriger les erreurs §3 du rapport
      2. relancer /spec-validate {n}
      3. relancer /dev-run {n} une fois GO ou WARN
    Bypass : /dev-run {n} --force (à utiliser en connaissance de cause)
    ```

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
SPEC {n} — {U} US à matérialiser (back + front en parallèle)
```

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

## STEP 4 — Validation des variables d'environnement requises

La liste des env vars attendues est **dérivée des stacks actifs**, pas
listée dans `stack.md`. Chaque stack documente ses propres env vars
canoniques :

| Source                                            | Env vars déclarées (référence)                   |
|---------------------------------------------------|--------------------------------------------------|
| `## Project Config: DatabaseType ≠ none` + stack backend actif | `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (cf. `dotnet-minimalapi.md §5.1`) |
| `## Active Auth Specs ⊇ auth/azure-ad`             | `AZ_TENANTID`, `AZ_CLIENTID`, `AZ_DOMAIN`, `AZ_AUDIENCES`, `AZ_BE_CALLBACKPATH`, `AZ_FE_CALLBACKPATH` (cf. `auth/azure-ad.md §3`) |

Lire la valeur (`$env:VAR` PowerShell, `${VAR}` bash) **sans afficher**
les valeurs. Si une ou plusieurs sont vides →
```
ERROR: /dev-run — variable(s) d'environnement manquante(s)
CAUSE: variables non définies : {liste exacte des noms manquants}
FIX: définir les variables dans l'environnement avant de relancer
```

**STOP** l'orchestration. Aucun agent n'est invoqué tant que les
prérequis ne sont pas en place.

---

## STEP 5 — Pré-step arch (bootstrap + scaffolding DB idempotents)

Invoquer l'agent `arch` (équivalent `/arch-init`). L'agent gère
intégralement :
- l'idempotence du bootstrap (skip si projets déjà initialisés)
- l'introspection DB et le scaffolding Database-First si
  `DatabaseType ≠ none` (skip silencieux sinon)

- Si `arch` réussit → continuer au STEP 6
- Si `arch` échoue → propager l'ERROR et **STOP**
  (les agents dev ne peuvent pas tourner sur un projet non initialisé
  ni sur des entities manquantes quand DB requise)

---

## STEP 6 — Workflow gated séquentiel (depuis 2026-05-07, cf. `.claude/rules/backend-first.md`)

**Nouveau défaut** : back→QA API gate→front, plus de parallélisme back+front.

```
6a. dev-backend ALL US (parallèle bornée par MaxParallel)
        ↓
6b. QA API Gate (tests d'intégration HTTP, in-memory DB)
        ↓
   ├── 🟢 GREEN → 6c. dev-frontend ALL US (parallèle bornée)
   └── 🔴 RED   → STOP + rapport, l'humain corrige et relance /dev-run
```

Lire `## Project Config` :
- `GatedWorkflow` (default `true`) : si `false`, fallback legacy
  parallèle (logger dans `workspace/output/.audit/legacy-parallel.log`).
  Déconseillé.
- `ApiGateRequired` (default `true`) : si `false`, gate produit WARN
  au lieu de RED (continue malgré tests rouges, déconseillé).

### 6.0 Détection automatique du mode From Plan

Avant d'invoquer les agents, Glob `workspace/output/plans/{n}-*-*.{back,front}.md`.
Chaque agent dev-* détecte lui-même la présence de son plan au
démarrage et bascule automatiquement en mode From Plan.

Émettre 1 ligne :
```
SPEC {n} — {U} US : {P_back} plans backend + {P_front} plans frontend détectés (mode From Plan)
```

### 6.a Phase Backend — invocations dev-backend bornées

Pour chaque US `{n}-{m}-{Name}`, invoquer `dev-backend {n}-{m}` en
batches de `$max_parallel`. Les invocations frontend sont **différées
à 6c**.

```
$batches = chunk(US_LIST, size = $max_parallel)
for batch in $batches:
    invoquer en parallèle :
      pour chaque US dans batch :
        Agent(dev-backend {n}-{m})
    attendre fin du batch
```

Émettre 1 ligne par batch :
```
SPEC {n} — backend batch {i}/{B} : US {liste-{m}} → {U_batch} invocations dev-backend
```

Chaque dev-backend :
- US backend ou fullstack → génère le code serveur
- US frontend pure → exit `skipped (frontend-only US)` (la phase 6c
  prendra le relais sans backend pour cette US)

**Échec d'une US backend** : continue les autres invocations du batch
(comme avant), mais à la fin de 6a si **au moins 1 US backend en
échec** → émettre :
```
🔴 /dev-run {n} — phase backend incomplète ({F_back} US en échec sur {U})

Échecs :
  - dev-backend {n}-{m}-{Name} : {raison condensée}
  ...

L'API gate ne peut pas tourner sur un backend incomplet. Corriger les
erreurs (cf. logs dev-backend) puis relancer /dev-run {n}.
```
**STOP**, ne pas exécuter 6b ni 6c.

### 6.b Phase QA API Gate (tests d'intégration HTTP)

Si toutes les US backend sont OK (incl. skipped frontend-only), invoquer
`/qa-generate {n} --mode api-tests` (cf. `.claude/rules/backend-first.md §1`).

Contenu de l'invocation :
- Génération de tests d'intégration HTTP par endpoint backend exposé
  (style Postman) avec **in-memory DB** ou mocks selon stack QA actif
- Couverture minimale `ApiGateMinPerEndpoint` (default 2 — 1 happy + 1
  négatif)
- Auth mockée (test handler), jamais Azure AD réel
- Rapport : `workspace/output/qa/feat-{n}/api-tests.{md,json}`

Lire `workspace/output/qa/feat-{n}/api-tests.json` après exécution.
Décision selon `summary.gate_passed` :

| Verdict gate | Action |
|---|---|
| 🟢 `gate_passed: true`, 0 failed, coverage min OK | continuer 6c |
| 🟡 `gate_passed: true` mais coverage endpoints partielle | continuer 6c + WARN |
| 🔴 `gate_passed: false` (≥1 failed OR coverage minimale non atteinte) | STOP, voir bloc ci-dessous |

### 6.b.STOP — Format STOP sur RED

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
`dev-frontend {n}-{m}` en batches de `$max_parallel`.

```
$batches = chunk(US_LIST, size = $max_parallel)
for batch in $batches:
    invoquer en parallèle :
      pour chaque US dans batch :
        Agent(dev-frontend {n}-{m})
    attendre fin du batch
```

Émettre 1 ligne par batch :
```
SPEC {n} — frontend batch {i}/{B} : US {liste-{m}} → {U_batch} invocations dev-frontend
```

Chaque dev-frontend bénéficie maintenant de la **certitude que les
endpoints backend honorent leur contrat** (vérifié par 6b). Les
mismatches `responsibilities.md §12` ne peuvent plus se produire en
silence.

**Idempotence (re-run après correction backend)** : au début de 6a,
comparer le mtime de `workspace/output/qa/feat-{n}/api-tests.json` avec
le mtime des fichiers backend. Si le rapport est postérieur **et**
`gate_passed: true`, skip 6a + 6b et passer directement à 6c.
Émettre :
```
SPEC {n} — backend stable (api-tests.json GREEN), skip 6a+6b → 6c frontend
```

### Mode legacy parallèle (`GatedWorkflow: false`)

Si `GatedWorkflow: false` dans Project Config OU flag `--unsequenced`
sur la ligne de commande : revenir au workflow v3.x (back+front
parallèles dans un même batch). Logger dans
`workspace/output/.audit/legacy-parallel.log`. Émettre WARN dans le
récap STEP 7. Supporté uniquement pour projets simples sans contrat
backend fragile.

---

## STEP 6.5 — Refresh dashboards (auto, depuis 2026-05-08)

Invoquer **systématiquement** `Agent: dashboard` (Haiku 4.5) après
exécution du gated workflow pour régénérer :

- `workspace/output/dashboard/README.html`
- `workspace/output/context/adrs/INDEX.md` (utile : `dev-*` ont peut-être
  créé des ADRs phase 5 que `arch` n'a pas indexés)

Non bloquant : sur échec, WARNING + continuer vers STEP 7.

---

## STEP 7 — Récap final

Émettre **un seul bloc final** consolidé (≤ 6 lignes en cas nominal,
cf. `.claude/rules/chat-output.md §4`) :

```
✅ SPEC {n} — phase dev terminée (gated)

Workflow      : gated back→API gate→front (MaxParallel={$max_parallel})
Bootstrap + DB : {init|skipped} ({N_tables} tables | DB=none)
Backend       : {Tb_ok}/{U} US ({Tb_skip} skipped, {F_back} échec)
API Gate      : {Tg_passed}/{Tg_total} tests · {N_endpoints} endpoints couverts → {🟢 GREEN | 🟡 YELLOW | 🔴 RED}
Frontend      : {Tf_ok}/{U} US ({Tf_skip} skipped, {F_front} échec) | not run (gate RED)
```

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
