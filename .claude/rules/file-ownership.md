# Règle — Ownership des fichiers partagés

## Principe

SDD_Pro lance les agents `dev-backend` et `dev-frontend` **en parallèle**
sur toutes les US d'une SPEC (cf. `CLAUDE.md §11.5`). Pour éviter les
conflits d'écriture (race conditions) sur des fichiers que plusieurs
agents pourraient toucher, chaque fichier partagé a **un propriétaire
unique** ou un **mode d'écriture sérialisé**.

Cette règle est **load-bearing pour la robustesse industrielle**. Sa
violation peut causer des écrasements silencieux, des fichiers corrompus
ou des résultats non déterministes entre runs identiques.

---

## 1. Matrice d'ownership

| Fichier / Répertoire | Owner exclusif | Mode | Phase |
|---|---|---|---|
| `workspace/output/src/{BackendName}/Program.cs` | `dev-backend` | Edit-augment exclusif | 5 |
| `workspace/output/src/{BackendName}/**` (Services, Endpoints, DTOs, Mappers, Validators, Entities augmentées) | `dev-backend` | Edit-augment exclusif | 5 |
| `workspace/output/src/{AppName}/Program.cs` | `dev-frontend` | Edit-augment exclusif | 5 |
| `workspace/output/src/{AppName}/wwwroot/css/theme.css` | `dev-frontend` | Edit-augment exclusif | 5 |
| `workspace/output/src/{AppName}/**` (Pages, Components, Layouts, Auth, Services, Validators) | `dev-frontend` | Edit-augment exclusif | 5 |
| `workspace/output/src/{AppName}.sln` | `arch` | Create + add-project | 4 |
| `workspace/output/src/{LibName}/**` (DTOs, Models, Inputs, Outputs partagés) | `arch` (création) | First-write wins, autres en read-only passif | 4-5 |
| `workspace/output/db/schema.json` / `schema.md` / `schema.diff.md` | `arch` | Create exclusif | 4 |
| `workspace/output/src/{Project}/CLAUDE.md` (par projet) | `arch` (création + régénération) ; `dev-*` (marquage RESOLVED post-build, cf. §6.bis) | Create + Edit hash exclusif côté arch ; Edit narrow côté dev-* | 4-5 |
| `workspace/output/context/constitution.md` | **séquentiel** : `/spec-generate` (bootstrap) puis `po` (§3) puis `arch` (§4, §6) puis `elicitor` (§7) | Append-only par section, jamais en parallèle | 1, 2, 4, 1.5 |
| `workspace/output/context/adrs/ADR-*.md` | **multi-writers** | Numérotation atomique par timestamp (cf. §3) | 4, 5 |
| `workspace/output/context/adrs/INDEX.md` | `arch` | Create exclusif (régénéré à chaque arch run, idempotent) | 4 |
| `workspace/output/us/{n}-{m}-*.md` | `po` | Create exclusif (1 fichier = 1 US) | 2 |
| `workspace/input/ui/{n}-{m}-*.html` | UX Designer humain | Create / Edit manuel (jamais touché par les agents — read-only stricte côté agents) | 2.5 |
| `workspace/output/plans/{n}-{m}-*.{back\|front}.md` | `dev-backend` (`.back`) ou `dev-frontend` (`.front`) | Create exclusif (mode `:plan`) | 2.7 |
| `workspace/output/validation/{n}-readiness.md` | `/spec-validate` | Create exclusif | 2.6 |
| `workspace/input/specs/{n}-*.md` | `/spec-generate` puis `elicitor` (append-only) | Sérialisé | 1, 1.5 |
| `workspace/console/status.json` | console web (`POST /api/validate`, `POST /api/gate-decide`) **+** `/sdd-full` (via `.claude/scripts/gate-decide.ps1`) | **Atomic write avec lock partagé** `workspace/console/.status.lock` (O_EXCL, TTL 10s, retry 5×) | LOT 2-3, depuis 2026-05-10 |
| `workspace/console/.status.lock` | console web OU `/sdd-full` (un seul à la fois) | Création atomique O_EXCL, supprimé après write | LOT 2-3 |
| `workspace/console/{server.js,app.jsx,index.html,styles.css,data-loader.js,lib/*.js,package.json,README.md}` | dev humain (Tech Lead) | Edit manuel — aucun agent SDD ne touche | hors pipeline |
| `workspace/output/dashboard/README.html` | `dashboard` (Haiku 4.5) | Create overwrite (idempotent) | fin de pipeline |
| `workspace/output/qa/feat-{n}/dashboard.html` | `dashboard` (Haiku 4.5) | Create overwrite (idempotent) | fin de `/qa-generate` |
| `workspace/output/context/adrs/INDEX.md` | `dashboard` (Haiku 4.5, depuis 2026-05-08) ; `arch` continue à pouvoir l'écrire en idempotent | Create overwrite | fin d'`arch` STEP 12.7 ou manuel `/doc-refresh` |

---

## 1.bis Anti-pattern strict — Front/Back isolation (depuis 2026-05-12)

**Règle bloquante** : un projet frontend ne doit **JAMAIS** être créé,
scaffoldé ou écrit **à l'intérieur** du répertoire d'un projet backend
(et symétriquement). Les projets vivent **au même niveau** sous
`workspace/output/src/`.

### Layout canonique

```
workspace/output/src/
  ├── {BackendName}/        ← projet backend (cmsback, SIMBackend, …)
  │     └── src/main/kotlin/  (ou Services/, Endpoints/, etc. selon stack)
  ├── {AppName}/            ← projet frontend (cmsfront, SIM, …)
  │     └── src/  (ou Pages/, Components/, etc.)
  ├── {LibName}/            ← projet lib partagé (si LibStrategy=shared)
  └── *.sln                 ← (stacks .NET) référence les 3 projets
```

### Anti-pattern interdit

```
workspace/output/src/
  └── {BackendName}/
        └── {AppName}/      ← ❌ INTERDIT
        └── kotlin/{AppName}/ ← ❌ INTERDIT (même variante avec préfixe runtime)
        └── front/          ← ❌ INTERDIT
```

### Pré-check obligatoire (avant tout Write/Edit/Bash mkdir)

Tout agent (`arch`, `dev-backend`, `dev-frontend`) qui s'apprête à écrire
sous `workspace/output/src/` exécute mentalement :

```
1. Soit P = path absolu cible
2. P doit matcher EXACTEMENT l'un de :
   - workspace/output/src/{BackendName}/...   (owner = arch | dev-backend)
   - workspace/output/src/{AppName}/...       (owner = arch | dev-frontend)
   - workspace/output/src/{LibName}/...       (owner = arch | dev-* via lock)
   - workspace/output/src/{*.sln}            (owner = arch)
3. {AppName} et {BackendName} et {LibName} doivent être les valeurs LITTÉRALES
   de `## Project Config` de `workspace/input/stack/stack.md`,
   pas un dérivé (kotlin/{AppName}, /front, /web, etc.)
4. Si P ne matche aucun pattern OU contient {AppName} imbriqué dans
   {BackendName} (ou inverse) → STOP + ERROR [FILE_OWNERSHIP_NESTED]
```

### Format ERROR sur violation

```
ERROR: {agent} — projet front imbriqué dans le projet back
CAUSE: [FILE_OWNERSHIP_NESTED] tentative d'écrire {path} (AppName={AppName} imbriqué sous BackendName={BackendName})
FIX: créer/scaffolder le projet frontend sous workspace/output/src/{AppName}/ AU MÊME NIVEAU que {BackendName}/, jamais imbriqué
```

### Pourquoi (post-mortem CMS-Back 2026-05-11)

Observé sur un projet réel : dossier `cmsback/Kotlin/cms-front/` créé
par confusion runtime. Symptômes :
- Build backend casse (Gradle ramasse les `.tsx` du front)
- QA scope pollué (tests front exécutés dans la suite back)
- File-ownership §1 violé silencieusement (dev-frontend écrit dans
  territoire dev-backend)
- Migration impossible vers monorepo type Nx/Turborepo (déjà mal placé)

### Création automatique des répertoires output

Tout agent qui s'apprête à écrire sous `workspace/output/...` doit
**créer le répertoire parent** s'il est absent (`mkdir -p` équivalent),
**après** avoir validé le pré-check ci-dessus. Aucun agent ne doit
échouer sur `parent directory not found` — la création est implicite,
mais elle est subordonnée à la validation du pattern canonique.

---

## 2. Constitution.md — sérialisation stricte

`workspace/output/context/constitution.md` est écrit séquentiellement, **jamais
par deux agents simultanés** :

```
PHASE 1   : /spec-generate    → §1 + §2 + §3 (création OU extension)
PHASE 1.5 : agent elicitor    → §7 (risques + hypothèses)
PHASE 2   : agent po          → §3 (acteurs cumulés) — UN agent à la fois
PHASE 4   : agent arch        → §4 (stack final) + §6 (ADRs index) — sérialisé
PHASE 5   : agents dev-*      → ❌ INTERDITS d'écrire dans constitution.md
                                 (les ADRs vont dans workspace/output/context/adrs/
                                  via numérotation atomique §3)
```

**Pourquoi `dev-*` n'écrivent pas dans constitution.md** : `/dev-run`
lance `dev-backend` et `dev-frontend` en parallèle sur N US. Si chaque
agent éditait constitution.md §6 pour indexer un nouvel ADR, on aurait
2×N écritures concurrentes sur le même fichier → race condition
garantie.

**Solution** : les `dev-*` créent uniquement des **fichiers ADR
individuels** (numérotation atomique). L'index §6 dans constitution.md
peut être **rebuild post-hoc** par `arch` à la prochaine invocation,
ou par une commande dédiée `/sdd-rebuild-index` (futur). En attendant,
§6 est consultable mais peut être incomplet pour les ADRs créés par
`dev-*` — la **source de vérité = `Glob workspace/output/context/adrs/*.md`**.

---

## 3. ADR — numérotation atomique par timestamp (anti race condition)

### Format de nom de fichier

**Pas de** `ADR-{nnn}-{slug}.md` avec `{nnn}` = `Glob + max + 1`
(racy quand `dev-backend` + `dev-frontend` créent simultanément).

**Utiliser** `ADR-{YYYYMMDDHHmmss}-{slug}.md` :
- `{YYYYMMDDHHmmss}` = timestamp UTC à la seconde au moment de la
  création (ex. `20260505T143022`)
- Si deux agents créent au même moment exact, ajouter un suffixe
  `-{rand4}` (4 chiffres aléatoires)
- `{slug}` = kebab-case, lowercase, max 5 mots

Exemples :
```
ADR-20260505T143022-stack-backend-dotnet.md
ADR-20260505T143022-stack-frontend-blazor-wasm.md
ADR-20260605T091533-1234-pagination-strategy.md
```

### Tri et indexation

Les ADRs sont triés **par timestamp** dans le filename → ordre
chronologique stable, même cross-team / cross-machine.

L'index §6 de `constitution.md` (mis à jour par `arch` uniquement)
ré-indexe en ordre alphabétique (= ordre temporel) :

```markdown
| ADR | Titre | Statut | Phase |
|---|---|---|---|
| ADR-20260505T143022-stack-backend-dotnet | Backend stack — .NET | Accepted | 4-ARCH |
| ADR-20260605T091533-pagination-strategy  | Pagination par curseur | Accepted | 5-CODE |
```

Pour préserver la lisibilité dans la doc, on peut conserver des **alias
courts** (`ADR-001`, `ADR-002`) **non-load-bearing** dans le titre H1
de chaque fichier, mais le **vrai identifiant = nom de fichier
timestamp**.

---

## 4. Mode d'écriture par type de fichier

### Edit-augment exclusif
Le fichier existe (créé par `arch` en phase 4), un seul agent peut
l'éditer en phase 5. Augmentations seulement, pas de réécriture
intégrale.

Exemple : `Program.cs` du backend :
- `arch` crée le squelette (phase 4)
- `dev-backend` ajoute des `services.AddScoped<...>()` lignes (phase 5)
- `dev-frontend` ne le touche jamais (autre projet)

### Create exclusif
Un nouveau fichier par invocation, pas de conflit possible (1
fichier = 1 entité).

Exemples : `workspace/output/us/{n}-{m}-*.md`, ADR par timestamp.

### First-write wins + lock file (LibName, durci v5.0)

`workspace/output/src/{LibName}/` peut être touché par dev-backend ET dev-frontend
qui partagent les DTOs / Models. **Mécanisme anti-race v5.0** : verrou
fichier explicite par entité.

#### Procédure d'écriture sur `{LibName}/Models/{Entity}.cs`

Avant tout `Write` ou `Edit` sur un fichier sous `workspace/output/src/{LibName}/` :

1. **Tenter de créer le lock file** atomique :
   ```bash
   mkdir -p workspace/output/src/{LibName}/.locks
   # Création atomique via redirection no-clobber (échoue si existe déjà)
   ( set -C; echo "$AGENT_ID:$(date -u +%s)" > "workspace/output/src/{LibName}/.locks/{Entity}.lock" ) 2>/dev/null
   ```
   - **Succès** (return code 0) → l'agent détient le verrou, peut écrire
     `{Entity}.cs`
   - **Échec** (return code ≠ 0, fichier existe) → un autre agent détient
     le verrou. **Lire le contenu** du `.lock` pour identifier l'agent
     propriétaire :
     - Si même `AGENT_ID` → idempotent, continuer (re-write OK)
     - Si autre `AGENT_ID` → **STOP** + ERROR `[LIBNAME_LOCK_HELD]` :
       ```
       ERROR: dev-{backend|frontend} {n}-{m} — verrou LibName détenu
       CAUSE: [LIBNAME_LOCK_HELD] {LibName}/Models/{Entity}.cs verrouillé par {other-agent}
       FIX: harmoniser via /dev-plan (les deux agents génèrent leur plan,
            review humaine consolide), puis relancer /dev-run
       ```

2. **Après écriture réussie**, libérer le verrou :
   ```bash
   rm -f "workspace/output/src/{LibName}/.locks/{Entity}.lock"
   ```

3. **Garde-fou stale lock** : si un `.lock` est plus vieux que `30 minutes`
   (timestamp UNIX dans le fichier), considérer comme abandonné et
   l'écraser. Concerne les cas de crash agent / interruption Claude Code.

#### Conflit signature (différent du verrou)

Si les deux agents veulent ajouter **le même DTO avec signatures
différentes** (cas conceptuel, pas timing) :
1. Le second à arriver détecte que `{Entity}.cs` existe déjà (lock libéré)
2. Read le contenu existant et compare la signature (champs, types) avec
   sa propre intention
3. Si divergence → STOP + ERROR `[LIBNAME_SIGNATURE_CONFLICT]` :
   ```
   ERROR: dev-{backend|frontend} {n}-{m} — conflit signature LibName
   CAUSE: [LIBNAME_SIGNATURE_CONFLICT] {LibName}/Models/{Entity}.cs existe avec
          signature différente (champs : {existing} vs {intended})
   FIX: harmoniser via /dev-plan puis review humaine. Modifier l'US ou
        unifier le DTO en amont.
   ```

#### Préservation du dossier `.locks/`

Toute purge manuelle de `workspace/output/src/{LibName}/**` doit inclure
`.locks/` — chaque run repart de zéro côté verrous. Le dossier `.locks/` n'est
**jamais commité** (à ajouter au `.gitignore` du projet généré, géré
par arch en Phase A).

### Sérialisation par phase
constitution.md, schema.json, .sln : un seul agent autorisé par phase,
phases séquentielles dans le pipeline.

---

## 5. Application à `/dev-run`

`/dev-run {n}` lance `2 × U` invocations parallèles (dev-backend +
dev-frontend pour chaque US `{n}-{m}`). Le respect de cette règle
garantit que :

- `dev-backend` de l'US `{n}-1` et `dev-backend` de l'US `{n}-2`
  écrivent dans des **services / endpoints différents** (pas de
  conflit, car le scope est par-US et par-fichier nouveau)
- `dev-backend {n}-1` et `dev-frontend {n}-1` ne touchent pas les
  mêmes fichiers (familles backend vs frontend séparées)
- Tous peuvent créer des ADRs **sans collision** grâce à la
  numérotation timestamp
- **Aucun** ne touche constitution.md

✅ **Résolu en v3.1.3** : `/dev-run` borne désormais le parallélisme
via `--max-parallel N` (CLI) ou `MaxParallel: N` (Project Config),
default `3` US fullstack par batch (= max `2 × 3 = 6` invocations
dev-* simultanées). Range `1-12`. Voir
`commands/dev-run.md §STEP 1` (Args) et `§STEP 6.2` (algorithme
batches). Combiné à la matrice ownership ci-dessus, cela réduit les
races potentielles sur les fichiers partagés (LibName, ADRs) à
≤ 3 par batch.

---

## 6. Anti-derive

- Aucun agent ne contourne cette matrice (pas d'Edit sur un fichier
  qu'il ne possède pas)
- Aucun agent ne réécrit un fichier intégralement quand le mode
  spécifié est "Edit-augment" ou "append-only"
- En cas de doute → STOP + ERROR avec hint "consulter
  `.claude/rules/file-ownership.md`"

---

## 6.bis Exception narrow — Marquage RESOLVED post-build (v3.1.2)

Une **exception strictement encadrée** au principe "arch est seul
propriétaire de `workspace/output/src/{Project}/CLAUDE.md`" est autorisée pour
les agents `dev-backend` / `dev-frontend`.

### Cas autorisé

À la fin du STEP build (build vert, exit code 0), l'agent `dev-*` peut
Edit la section `## BREAKING CHANGES` du `CLAUDE.md` de son projet
**uniquement** pour :

1. Renommer le H2 en `## BREAKING CHANGES — RESOLVED {YYYY-MM-DD}`
2. Préfixer le bloc d'un encart de statut RESOLU
3. Optionnellement, condenser la liste détaillée en résumé "intégré
   au code"

Aucune autre section ne peut être touchée.

### Cas interdits

- ❌ Supprimer la section (laisser arch le faire à la régénération
  selon §6.bis ci-dessous)
- ❌ Modifier d'autres sections du CLAUDE.md (Layer Mapping, Forbidden
  Patterns, Librairies §2.4, etc.)
- ❌ Ajouter de nouvelles sections
- ❌ Marquer RESOLVED si le build échoue (statut mensonger)
- ❌ Marquer RESOLVED s'il reste des warnings d'erreur (pas seulement NuGet/format)

### Régénération définitive (côté arch)

Le prochain `/arch-init` détecte les sections marquées
`BREAKING CHANGES — RESOLVED {date}` et :
- Si l'écart de schéma a effectivement été résolu (entités scaffold
  inchangées) → **supprime intégralement la section**
- Sinon → conserve telle quelle (signal qu'une régression a réintroduit
  l'écart)

### Pourquoi cette exception

Sans elle, les blocs BREAKING CHANGES rédigés par arch (Phase B/C)
restent visibles tels quels longtemps après résolution, et les
invocations dev-* suivantes les relisent comme des **directives encore
actives** → faux signaux, actions redondantes ou incorrectes.

Cas réel : run 1-pvlist (audit C3) — le build SIM.Api était vert mais
CLAUDE.md continuait à indiquer "43 erreurs CS1061, action requise par
dev-backend" car personne n'avait l'autorisation de marquer la section
résolue, et arch n'avait pas re-tourné depuis.

---

## 7. Évolutions prévues (v3.1+)

- **Validateur loader.yml ↔ agents** : script qui vérifie que les
  `writes:` déclarés en `loader.yml` matchent ce que les agents écrivent
  réellement (Read leur prompt, parse les chemins de Write/Edit)
- **Lock files** : pour la libname partagée, fichier de lock par
  entité (ex. `Models/Foo.cs.lock`) pour éviter les premières
  écritures simultanées
- **Audit post-batch** : après `/dev-run`, vérifier qu'aucun fichier
  hors-périmètre n'a été modifié (diff git ou hash compare)
