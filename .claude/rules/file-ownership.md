# Règle — Ownership des fichiers partagés

## Principe

SDD_Pro lance `dev-backend` et `dev-frontend` **en parallèle** sur
toutes les US d'une FEAT. Pour éviter les conflits d'écriture, chaque
fichier partagé a **un propriétaire unique** ou un **mode d'écriture
sérialisé**. **Load-bearing pour la robustesse industrielle** —
violation = écrasements silencieux, fichiers corrompus, résultats
non déterministes.

---

## 1. Matrice d'ownership

| Fichier / Répertoire | Owner exclusif | Mode | Phase |
|---|---|---|---|
| `workspace/output/src/{BackendName}/**` (Program.cs, Services, Endpoints, DTOs, Mappers, Validators, Entities augmentées) | `dev-backend` | Edit-augment exclusif | 5 |
| `workspace/output/src/{AppName}/**` (Program.cs, Pages, Components, Layouts, theme.css, Auth, Services, Validators) | `dev-frontend` | Edit-augment exclusif | 5 |
| `workspace/output/src/{AppName}.sln` | `arch` | Create + add-project | 4 |
| `workspace/output/src/{LibName}/**` (DTOs, Models, Inputs, Outputs partagés) | `arch` (création) | First-write wins + lock (§4) | 4-5 |
| `workspace/output/db/schema.{json,md,diff.md}` | `arch` | Create exclusif | 4 |
| `workspace/output/src/{Project}/CLAUDE.md` (par projet) | `arch` (création/régénération) ; `dev-*` (marquage RESOLVED §6.bis) | Create + Edit hash exclusif (arch) ; Edit narrow (dev-*) | 4-5 |
| `workspace/output/.sys/.context/constitution.md` | **séquentiel** : `/feat-generate` → `po` (§3) → `arch` (§4, §6) → `elicitor` (§7) | Append-only par section | 1, 2, 4, 1.5 |
| `workspace/output/.sys/.context/adrs/ADR-*.md` | **multi-writers** | Numérotation atomique timestamp (§3) | 4, 5 |
| `workspace/output/.sys/.context/adrs/INDEX.md` | `dashboard` (depuis 2026-05-08) ; `arch` continue à pouvoir l'écrire | Create overwrite (idempotent) | fin pipeline / arch STEP 12.7 |
| `workspace/output/us/{n}-{m}-*.md` | `po` | Create exclusif (1 fichier = 1 US) | 2 |
| `workspace/input/ui/{n}-{m}-*.html` | UX Designer humain | Read-only stricte côté agents | 2.5 |
| `workspace/output/plans/{n}-{m}-*.{back\|front}.md` | `dev-backend` (`.back`) / `dev-frontend` (`.front`) | Create exclusif (mode `:plan`) | 2.7 |
| `workspace/output/.sys/.validation/{n}-readiness.md` | `/feat-validate` | Create exclusif | 2.6 |
| `workspace/input/feats/{n}-*.md` | `/feat-generate` puis `elicitor` (append-only) | Sérialisé | 1, 1.5 |
| `workspace/console/status.json` | console web + `/sdd-full` (via `gate_decide.py`) | **Atomic write + lock partagé** `.status.lock` (O_EXCL, TTL 10s, retry 5×) | LOT 2-3 |
| `workspace/console/.status.lock` | console web OU `/sdd-full` (un seul à la fois) | Création atomique O_EXCL, supprimé après write | LOT 2-3 |
| `workspace/console/{server.js,app.jsx,index.html,…}` | dev humain (Tech Lead) | Edit manuel — aucun agent SDD ne touche | hors pipeline |
| ~~`workspace/output/dashboard/README.html`~~ | **retiré v6.10** | métriques dans `console.db` (24 tables) ; rendu graphique par console web | — |
| ~~`workspace/output/qa/feat-{n}/dashboard.html`~~ | **retiré v6.10** | métriques QA dans `console.db` (tables `qa_*`) ; endpoints `/api/feat/:n` | — |

---

## 1.bis Anti-pattern strict — Front/Back isolation (depuis 2026-05-12)

**Bloquant** : un projet frontend ne doit **JAMAIS** être créé,
scaffoldé ou écrit **à l'intérieur** du répertoire d'un projet backend
(et symétriquement). Les projets vivent **au même niveau** sous
`workspace/output/src/`.

### Layout canonique

```
workspace/output/src/
  ├── {BackendName}/        ← projet backend
  ├── {AppName}/            ← projet frontend
  ├── {LibName}/            ← projet lib partagé (si LibStrategy=shared)
  └── *.sln                 ← (stacks .NET)
```

### Anti-pattern interdit

```
{BackendName}/{AppName}/        ❌ INTERDIT
{BackendName}/kotlin/{AppName}/ ❌ INTERDIT (variante runtime)
{BackendName}/front/            ❌ INTERDIT
```

### Pré-check obligatoire (avant tout Write/Edit/mkdir)

Path cible P doit matcher EXACTEMENT l'un de :
- `workspace/output/src/{BackendName}/...` (owner = arch | dev-backend)
- `workspace/output/src/{AppName}/...` (owner = arch | dev-frontend)
- `workspace/output/src/{LibName}/...` (owner = arch | dev-* via lock)
- `workspace/output/src/{*.sln}` (owner = arch)

`{AppName}`/`{BackendName}`/`{LibName}` = valeurs LITTÉRALES de
`## Project Config`, pas un dérivé (`kotlin/{AppName}`, `/front`, `/web`).

> **Alias v6.10.2+** : la clé préférée côté `stack.md` est désormais
> **`FrontendName`** (alias de `AppName`, ex. `FrontendName: CMSPrintFront`).
> Le token canonique du framework reste `{AppName}` — la normalisation
> est faite par `sdd_lib.project_config.normalize_project_aliases()`. Pour
> un projet **fullstack** (single-project), drop le suffixe `Front` côté
> nom (ex. `CMSPrintFront` → `CMSPrint`). Les clés `AppNamespace` /
> `BackendNamespace` ne sont **plus requises** dans `stack.md` : elles
> sont auto-dérivées (`AppNamespace = AppName`, `BackendNamespace = BackendName`).

Si P ne matche pas OU `{AppName}` imbriqué dans `{BackendName}` →
STOP + ERROR `[FILE_OWNERSHIP_NESTED]` :
```
ERROR: {agent} — projet front imbriqué dans le projet back
CAUSE: [FILE_OWNERSHIP_NESTED] tentative d'écrire {path} (AppName={AppName} imbriqué sous BackendName={BackendName})
FIX: créer/scaffolder sous workspace/output/src/{AppName}/ AU MÊME NIVEAU que {BackendName}/, jamais imbriqué
```

### Post-mortem CMS-Back 2026-05-11

Dossier `cmsback/Kotlin/cms-front/` créé par confusion runtime →
build backend casse (Gradle ramasse les `.tsx`), QA pollué, migration
monorepo impossible.

### Création répertoires output

Tout agent qui écrit sous `workspace/output/...` doit créer le parent
absent (`mkdir -p` implicite), **après** validation du pré-check. Aucun
agent ne doit échouer sur `parent directory not found`.

---

## 2. Constitution.md — sérialisation stricte

Écrit séquentiellement, **jamais en parallèle** :

```
PHASE 1   : /feat-generate    → §1 + §2 + §3 (création/extension)
PHASE 1.5 : agent elicitor    → §7 (risques + hypothèses)
PHASE 2   : agent po          → §3 (acteurs cumulés) — UN à la fois
PHASE 4   : agent arch        → §4 (stack final) + §6 (ADRs index) — sérialisé
PHASE 5   : agents dev-*      → ❌ INTERDITS d'écrire dans constitution.md
```

**Pourquoi dev-\* exclus** : `/dev-run` lance dev-backend + dev-frontend
en parallèle sur N US. 2×N éditions concurrentes de §6 = race garantie.

**Solution** : les dev-* créent uniquement des **fichiers ADR
individuels** (numérotation atomique §3). L'index §6 est rebuild
post-hoc par arch à la prochaine invocation. Source de vérité = `Glob
workspace/output/.sys/.context/adrs/*.md`.

---

## 3. ADR — numérotation atomique par timestamp

**Format** : `ADR-{YYYYMMDDTHHmmss}-{slug}.md`
- `{YYYYMMDDTHHmmss}` = timestamp UTC seconde (ex. `20260505T143022`)
- Collision (deux agents même seconde) → suffixe `-{rand4}`
- `{slug}` = kebab-case, lowercase, max 5 mots

```
ADR-20260505T143022-stack-backend-dotnet.md
ADR-20260605T091533-1234-pagination-strategy.md
```

Tri par filename = ordre temporel stable cross-team/cross-machine.

L'index §6 de `constitution.md` (mis à jour par arch uniquement)
ré-indexe alphabétiquement (= ordre chronologique). Alias courts
(`ADR-001`) **non-load-bearing** acceptables dans le H1 du fichier mais
identifiant réel = nom de fichier timestamp.

---

## 4. Mode d'écriture par type

### Edit-augment exclusif
Fichier créé par arch (phase 4), un seul agent l'édite en phase 5.
Augmentations seulement. Ex. `Program.cs` backend : arch crée
squelette, dev-backend append `services.AddScoped<...>()`.

### Create exclusif
1 fichier par invocation, pas de conflit (1 fichier = 1 entité). Ex.
`workspace/output/us/{n}-{m}-*.md`, ADR par timestamp.

### First-write wins + lock file (LibName, durci v5.0)

`workspace/output/src/{LibName}/` peut être touché par dev-backend ET
dev-frontend (DTOs/Models partagés). **Verrou explicite par entité.**

**Procédure** — avant tout Write/Edit sous `{LibName}/` :

1. Tenter création atomique du lock (no-clobber) :
   ```bash
   mkdir -p workspace/output/src/{LibName}/.locks
   ( set -C; echo "$AGENT_ID:$(date -u +%s)" > "workspace/output/src/{LibName}/.locks/{Entity}.lock" ) 2>/dev/null
   ```
   - Succès (rc=0) → écrire `{Entity}.cs`
   - Échec (fichier existe) → lire le `.lock` :
     - Même `AGENT_ID` → idempotent, continuer
     - Autre `AGENT_ID` → STOP + ERROR `[LIBNAME_LOCK_HELD]`
2. Après écriture : `rm -f "workspace/output/src/{LibName}/.locks/{Entity}.lock"`
3. **Stale lock** : `.lock` > 30min (timestamp UNIX) → écraser (recovery
   crash agent / interruption).

**Conflit signature** (cas conceptuel, pas timing) : 2ème agent
détecte `{Entity}.cs` existant (lock libéré), compare signature avec
sa propre intention. Divergence → STOP + ERROR `[LIBNAME_SIGNATURE_CONFLICT]` :
```
ERROR: dev-{backend|frontend} {n}-{m} — conflit signature LibName
CAUSE: [LIBNAME_SIGNATURE_CONFLICT] {LibName}/Models/{Entity}.cs existe avec signature différente ({existing} vs {intended})
FIX: harmoniser via /dev-plan + review humaine, modifier l'US ou unifier le DTO en amont
```

Le dossier `.locks/` n'est **jamais commité** (à ajouter au
`.gitignore` du projet généré, géré par arch en Phase A).

### Sérialisation par phase
constitution.md, schema.json, .sln : un seul agent autorisé par phase,
phases séquentielles dans le pipeline.

---

## 5. Application à `/dev-run`

`/dev-run {n}` lance `2 × U` invocations parallèles (dev-backend +
dev-frontend pour chaque US `{n}-{m}`). Le respect de cette règle
garantit :
- dev-backend de `{n}-1` et de `{n}-2` écrivent dans des services/endpoints
  différents (scope par-US, fichier nouveau)
- dev-backend `{n}-1` et dev-frontend `{n}-1` ne touchent pas les mêmes
  fichiers (familles back vs front séparées)
- ADRs créés sans collision (numérotation timestamp)
- Aucun ne touche constitution.md

**Borne parallélisme (v3.1.3)** : `--max-parallel N` ou `MaxParallel: N`
dans Project Config (défaut 3 US fullstack par batch = max 6
invocations dev-* simultanées, range 1-12). Cf. `commands/dev-run.md
§STEP 1` (Args) et §STEP 6.2 (algorithme batches).

---

## 6. Anti-derive

- Aucun Edit sur un fichier hors ownership
- Aucune réécriture intégrale quand mode = Edit-augment ou append-only
- Doute → STOP + ERROR avec hint vers cette règle

---

## 6.bis Exception narrow — Marquage RESOLVED post-build (v3.1.2)

**Exception encadrée** : à la fin du STEP build (vert, exit 0), dev-*
peut Edit la section `## BREAKING CHANGES` du `CLAUDE.md` de son
projet **uniquement** pour :
1. Renommer le H2 en `## BREAKING CHANGES — RESOLVED {YYYY-MM-DD}`
2. Préfixer le bloc d'un encart de statut RESOLU
3. Optionnellement condenser la liste détaillée en résumé

**Interdits** :
- ❌ Supprimer la section (arch la supprimera à la régénération)
- ❌ Modifier d'autres sections (Layer Mapping, Forbidden, §2.4 libs)
- ❌ Ajouter de nouvelles sections
- ❌ Marquer RESOLVED si build échoue ou warnings d'erreur résiduels

**Régénération définitive (arch)** : prochain `/arch-init` détecte les
sections `RESOLVED {date}` et supprime intégralement si l'écart est
réellement résolu (entités scaffold inchangées), sinon conserve
(signal régression).

**Pourquoi** : sans cette exception, les blocs BREAKING CHANGES
restent visibles longtemps après résolution. Les invocations dev-*
suivantes les relisent comme directives actives → faux signaux,
actions redondantes (post-mortem run 1-pvlist : build SIM.Api vert
mais CLAUDE.md indiquait "43 erreurs CS1061" résiduelles).

---

## 7. Évolutions prévues

- Validateur `loader.yml` ↔ agents (vérifier que `writes:` déclarés
  matchent les Write/Edit réels)
- Audit post-batch : diff git après `/dev-run` pour détecter modifs
  hors-périmètre
