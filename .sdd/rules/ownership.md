---
# TOK-C1 (audit 2026-06-12) : chargement paresseux (path-scoped rule). Lue on-demand par
# dev-*/arch/po/constitutioner ; auto-injection au contact des artefacts workspace listés.
# TOK-C2 (audit tokens 2026-08-30) : narrowing — l'ex-glob `workspace/**` injectait ces
# ~25 KB au contact de N'IMPORTE QUEL fichier workspace (ui/, console/, db/, .sys/.audit…)
# et rendait l'entrée `workspace/feats/**` redondante. Portée = les artefacts que la
# matrice §1 arbitre ET dont un writer ne lit pas la rule explicitement.
# `workspace/plans/**` ajouté : les writers (dev-* en mode `:plan`) ne la lisent que par
# pointeur « cf. », pas en STEP contexte. Non repris : ui/ (writer = humain, agents
# read-only), db/ + .sys/.audit (writers arch/hooks — substance inlinée / déterministe),
# console/ (console web + scripts, hors agents).
paths:
  - "workspace/src/**"
  - "workspace/us/**"
  - "workspace/feats/**"
  - "workspace/plans/**"
  - "workspace/.sys/.context/**"
---

# Règle — Ownership (File matrix + Constitution + ADRs, consolidated v7.0.0)

> **v7.0.0 merge** : fusionne `file-ownership.md` (matrice path → owner
> + serialization parallèle) + `constitution.md` (constitution projet +
> ADRs governance + numérotation atomique timestamp). Stubs originaux
> **supprimés au sweep v7.0.0-alpha 2026-05-20** — tous les Read historiques
> pointent désormais directement ici.

## TOC

- **Partie A — File ownership matrix** : qui écrit où, mode d'écriture
  (Edit-augment exclusif / Create exclusif / Sérialisation / First-write+lock),
  procédure LibName lock, anti-pattern front/back isolation, marquage
  BREAKING RESOLVED.
- **Partie B — Constitution & ADRs** : SSoT cross-FEAT, écriture
  append-only par section, numérotation atomique timestamp ADRs, qui
  peut écrire dans la constitution selon la phase.

---

# Partie A — File Ownership matrix

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
| `workspace/src/{BackendName}/**` (Program.cs, Services, Endpoints, DTOs, Mappers, Validators, Entities augmentées) | `dev-backend` | Edit-augment exclusif | 5 |
| `workspace/src/{AppName}/**` (Program.cs, Pages, Components, Layouts, theme.css, Auth, Services, Validators) | `dev-frontend` | Edit-augment exclusif | 5 |
| `workspace/src/{AppName}.sln` | `arch` | Create + add-project | 4 |
| `workspace/src/{LibName}/**` (DTOs, Models, Inputs, Outputs partagés) | `arch` (création) | First-write wins + lock (§4) | 4-5 |
| `workspace/db/schema.{json,md,diff.md}` | `arch` | Create exclusif | 4 |
| `workspace/src/{Project}/CLAUDE.md` (par projet) | `arch` (création/régénération) ; `dev-*` (marquage RESOLVED §6.bis) | Create + Edit hash exclusif (arch) ; Edit narrow (dev-*) | 4-5 |
| `workspace/.sys/.context/constitution.md` | **séquentiel** : `/feat-generate` (bootstrap §1-§3) → `po` (§3 acteurs) → `elicitor` (§7) → `constitutioner` (§1 date, §4 stack, §6 ADRs index) | Append-only par section | 1, 2, 1.5, 3.5 |
| `workspace/.sys/.context/adrs/ADR-*.md` | `constitutioner` (owner EXCLUSIF depuis 2026-05-13) | Numérotation atomique timestamp (§3) | 3.5 |
| `workspace/.sys/.context/adrs/INDEX.md` | `constitutioner` (régénère, owner) ; `sdd_scripts/index_adrs.py` (rebuild 0-token déterministe hors pipeline) | Create overwrite (idempotent) | 3.5 / fin pipeline |
| `workspace/us/{n}-{m}-*.md` | `po` | Create exclusif (1 fichier = 1 US) | 2 |
| `workspace/ui/{n}-{m}-*.html` | UX Designer humain | Read-only stricte côté agents | 2.5 |
| `workspace/plans/{n}-{m}-*.{back\|front}.md` | `dev-backend` (`.back`) / `dev-frontend` (`.front`) | Create exclusif (mode `:plan`) | 2.7 |
| `workspace/src/{BackendName}.Tests/**`, `workspace/src/{AppName}.Tests/**` + patterns test adjacents (`**/__tests__/**`, `*.test.ts`, `*.FEAT.ts`, `test_*.py`, `*Test.kt`) | `qa` | Create/Edit exclusif (territoire test — jamais le code production, cf. `[QA_OWNERSHIP_VIOLATION]`) | 5 |
| `workspace/.sys/.validation/{n}-readiness.md` | `/feat-validate` | Create exclusif | 2.6 |
| `workspace/.sys/.audit/` | hooks framework (`*.log`/`*.jsonl`, rotation `rotate_audit_logs.py`) **+** rapports d'audit code holistiques `AUDIT-*.md` (emplacement canonique, 2026-07-06 — ex-`output/audit/` ; `rotate_audit_logs` ne touche pas les `.md`) | Append (logs) / Create (audits) | hooks / ad-hoc |
| `workspace/feats/{n}-*.md` | `/feat-generate` puis `elicitor` (append-only) | Sérialisé | 1, 1.5 |
| `workspace/console/status.json` | console web + `/sdd-full` (via `gate_decide.py`) | **Atomic write + lock partagé** `.status.lock` (O_EXCL, TTL 10s, retry 5×) | LOT 2-3 |
| `workspace/console/.status.lock` | console web OU `/sdd-full` (un seul à la fois) | Création atomique O_EXCL, supprimé après write | LOT 2-3 |
| `workspace/console/{server.js,app.jsx,index.html,…}` | dev humain (Tech Lead) | Edit manuel — aucun agent SDD ne touche | hors pipeline |

> v7.0.0-alpha (audit MIN-5, 2026-06-04) — les 2 lignes historiques sur
> `dashboard/README.html` + `qa/feat-{n}/dashboard.html` (retirés v6.10)
> ont été supprimées du tableau (l'historique vit dans CHANGELOG). Le
> rendu graphique des métriques `console.db` est désormais owned par
> `workspace/console/` (console web).

---

## 1.bis Anti-pattern strict — Front/Back isolation (depuis 2026-05-12)

**Bloquant** : un projet frontend ne doit **JAMAIS** être créé,
scaffoldé ou écrit **à l'intérieur** du répertoire d'un projet backend
(et symétriquement). Les projets vivent **au même niveau** sous
`workspace/src/`.

### Layout canonique

```
workspace/src/
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
- `workspace/src/{BackendName}/...` (owner = arch | dev-backend)
- `workspace/src/{AppName}/...` (owner = arch | dev-frontend)
- `workspace/src/{LibName}/...` (owner = arch | dev-* via lock)
- `workspace/src/{*.sln}` (owner = arch)

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
FIX: créer/scaffolder sous workspace/src/{AppName}/ AU MÊME NIVEAU que {BackendName}/, jamais imbriqué
```

### Post-mortem CMS-Back 2026-05-11

Dossier `cmsback/Kotlin/cms-front/` créé par confusion runtime →
build backend casse (Gradle ramasse les `.tsx`), QA pollué, migration
monorepo impossible.

### Création répertoires output

Tout agent qui écrit sous `workspace/...` doit créer le parent
absent (`mkdir -p` implicite), **après** validation du pré-check. Aucun
agent ne doit échouer sur `parent directory not found`.

---

## 2. Constitution.md — sérialisation stricte

Écrit séquentiellement, **jamais en parallèle** :

```
PHASE 1   : /feat-generate    → §1 + §2 + §3 (création/extension)
PHASE 1.5 : agent elicitor    → §7 (risques + hypothèses)
PHASE 2   : agent po          → §3 (acteurs cumulés) — UN à la fois
PHASE 3.5 : agent constitutioner → §1 (date) + §4 (stack final) + §6 (ADRs index) — sérialisé
PHASE 4   : agent arch        → ❌ pose seulement le sentinel disque, n'écrit PLUS §4/§6 (Phase D déléguée)
PHASE 5   : agents dev-*      → ❌ INTERDITS d'écrire dans constitution.md
```

**Pourquoi arch + dev-\* exclus** (CR-2, externalisation Phase D 2026-05-13) :
les ADRs + constitution §1/§4/§6 + INDEX sont owned **exclusivement** par
`constitutioner`, spawné par `/arch-init` STEP 3.5 après que `arch` ait posé
le sentinel disque `workspace/.sys/.state/arch-ready-for-constitutioner.flag`
(no-spawn préservé). `arch` ne fait plus la Phase D. `/dev-run` lance par ailleurs
dev-backend + dev-frontend en parallèle sur N US → 2×N éditions concurrentes de §6
seraient une race garantie.

**Solution** : `arch` et les dev-* créent au plus des **fichiers ADR
individuels** (numérotation atomique §3) mais ne touchent JAMAIS §6 ;
l'index §6 + INDEX.md sont (re)build par `constitutioner` (Phase 3.5) ou
par `sdd_scripts/index_adrs.py` (déterministe, hors pipeline). Source de
vérité = `Glob workspace/.sys/.context/adrs/*.md`.

---

## 3. ADR — numérotation atomique par timestamp + rand4

**Format canonique v7.0.0 (audit 2026-06-06 RUPT-6, grâce 2026-06-08)** :
`ADR-{YYYYMMDDTHHmmss}-{rand4}-{slug}.md`
- `{YYYYMMDDTHHmmss}` = timestamp UTC seconde (ex. `20260606T143022`)
- `{rand4}` = **4 hex chars random SYSTÉMATIQUE depuis 2026-06-08**
  (`secrets.token_hex(2)`, 16 bits entropie). Anti-collision même seconde
  garantie > 99.998 %. Les ADRs créés **avant 2026-06-08** restent
  acceptés sans rand4 (tolérance compat — regex `(?:-[a-z0-9]+)?` middle
  segment optionnel).
- `{slug}` = kebab-case, lowercase, max 5 mots / 40 caractères

```
ADR-20260606T143022-a1f2-stack-backend-dotnet.md
ADR-20260606T143022-b3c4-pagination-cursor-based.md   ← même seconde, no collision
```

**Helper Python obligatoire** (au lieu de générer le filename dans le
prompt LLM) :
```python
from sdd_lib.adr_id import mint_adr_filename
filename = mint_adr_filename("stack-backend-dotnet")
# -> "ADR-20260606T143022-a1f2-stack-backend-dotnet.md"
```

Pour les agents (arch / dev-* / constitutioner) qui ont accès au tool
`Bash`, invocation via :
```bash
python -c "from sdd_lib.adr_id import mint_adr_filename; print(mint_adr_filename('stack-backend-dotnet'))"
```

Compat regex : `sdd_scripts/index_adrs.py` accepte les 2 formats
(`(?:-[a-z0-9]+)?` middle segment optionnel) — les ADRs v6.x sans rand4
restent indexables, les ADRs v7.0.0+ avec rand4 aussi.

Tri par filename = ordre temporel stable cross-team/cross-machine
(timestamp ISO 8601 compact lexicographiquement croissant).

L'index §6 de `constitution.md` (mis à jour par `constitutioner` uniquement — CR-2, cf. §2 et Partie B §4.4)
ré-indexe alphabétiquement (= ordre chronologique). Alias courts
(`ADR-001`) **non-load-bearing** acceptables dans le H1 du fichier mais
identifiant réel = nom de fichier timestamp+rand4.

---

## 4. Mode d'écriture par type

### Edit-augment exclusif
Fichier créé par arch (phase 4), un seul agent l'édite en phase 5.
Augmentations seulement. Ex. `Program.cs` backend : arch crée
squelette, dev-backend append `services.AddScoped<...>()`.

### Create exclusif
1 fichier par invocation, pas de conflit (1 fichier = 1 entité). Ex.
`workspace/us/{n}-{m}-*.md`, ADR par timestamp.

### First-write wins + lock file (LibName, durci v5.0)

`workspace/src/{LibName}/` peut être touché par dev-backend ET
dev-frontend (DTOs/Models partagés). **Verrou explicite par entité.**

**Procédure** — avant tout Write/Edit sous `{LibName}/` :

1. Tenter création atomique du lock (no-clobber) :
   ```bash
   mkdir -p workspace/src/{LibName}/.locks
   ( set -C; echo "$AGENT_ID:$(date -u +%s)" > "workspace/src/{LibName}/.locks/{Entity}.lock" ) 2>/dev/null
   ```
   - Succès (rc=0) → écrire `{Entity}.cs`
   - Échec (fichier existe) → lire le `.lock` :
     - Même `AGENT_ID` → idempotent, continuer
     - Autre `AGENT_ID` → STOP + ERROR `[LIBNAME_LOCK_HELD]`
2. Après écriture : `rm -f "workspace/src/{LibName}/.locks/{Entity}.lock"`
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

---

# Partie B — Constitution projet + ADRs governance

## Principe

Le fichier `workspace/.sys/.context/constitution.md` est la **source de vérité
partagée** entre tous les agents SDD_Pro. Il garantit la cohérence
sémantique cross-FEAT (glossaire, acteurs, conventions) et trace les
décisions architecturales (ADRs).

Chaque ADR (`workspace/.sys/.context/adrs/ADR-{nnn}-{slug}.md`) trace **une
décision structurante** au format Context / Decision / Consequences.

---

## 1. Création initiale

`/feat-generate` (premier appel sur un projet) bootstrap la constitution
avec :
- §1 Identité (`ProjectName` = `AppName` du `workspace/stack/stack.md` si
  défini, sinon nom du dossier projet)
- §2 Glossaire (vide initialement, étendu par les agents)
- §3 Acteurs (extraits de la FEAT créée)
- §4 Stack technique (`<à compléter par /arch-init>`)
- §5 Conventions (références CLAUDE.md §3-§4, vide pour 5.3)
- §6 ADRs (vide initialement)
- §7 Risques (vide tant que `/feat-deepen` n'a pas tourné)
- §8 Index des écrivains (statique)

**Idempotent** : si `workspace/.sys/.context/constitution.md` existe déjà, ne
JAMAIS l'écraser. Étendre seulement les acteurs (§3) et termes (§2)
de la nouvelle FEAT.

---

## 2. Read-only par défaut

Tous les agents **lisent** la constitution en début d'exécution
(intégrée dans leur STEP de chargement). Elle compte ~2 KB → coût
négligeable.

**Personne ne réécrit** le fichier intégralement. Les modifications
sont :
- **Append-only** sur les listes (ajout d'une ligne acteur, terme,
  ADR)
- **Update-in-place** sur 1 ligne de tableau (ex. : MAJ statut ADR de
  Proposed → Accepted)

---

## 3. Qui peut écrire dans la constitution

| Agent / Commande | Sections autorisées | Mode | Phase |
|---|---|---|---|
| `/feat-generate` | §1 (bootstrap), §2-3 (init) | Création ou extend | 1 |
| Agent `elicitor` (`/feat-deepen`) | §7 (risques, hypothèses) | Append-only | 1.5 |
| Agent `po` | §2 (nouveaux termes), §3 (nouveaux acteurs) | Append-only | 2 |
| Agent `constitutioner` | §1 (date), §4 (stack final + DatabaseType), §6 (ADRs index) + ADRs + INDEX.md | Update §1/§4 / Append §6 | 3.5 |

**Modifié CR-2 (externalisation Phase D, 2026-05-13)** : l'agent `arch`
**n'écrit PLUS** dans `constitution.md` (ni §4 ni §6) ni les ADRs. Il pose
seulement le sentinel disque
`workspace/.sys/.state/arch-ready-for-constitutioner.flag` en fin de
Phase B ; `/arch-init` STEP 3.5 spawn alors `constitutioner` qui est **owner
exclusif** de §1/§4/§6 + ADRs + INDEX (no-spawn préservé : le spawn vit dans
la commande, pas dans l'agent arch).

**Modifié en v3.0.1** : les **agents `dev-*` sont STRICTEMENT
read-only** sur `constitution.md`. Ils créent au plus leurs ADRs en fichiers
indépendants (`workspace/.sys/.context/adrs/ADR-{timestamp}-{slug}.md` —
numérotation atomique, voir §4) **sans toucher §6**. L'index §6 est
rebuild par `constitutioner` (Phase 3.5) ou ignoré (la source de vérité = les
fichiers ADR eux-mêmes).

**Pourquoi ?** `/dev-run` lance dev-backend + dev-frontend en
parallèle sur N US (jusqu'à 2×N invocations). Si chacun éditait §6,
on aurait des race conditions garanties sur le même fichier. La
matrice ci-dessus (Partie A §1) formalise cette sérialisation.

**Tout autre agent ou phase** = read-only strict (lecture passive
pour glossaire, acteurs, ADRs existants).

### 3.bis Procédure append-only durcie pour §3 Acteurs (depuis v3.1.3)

L'agent PO suit cette procédure **obligatoire** au STEP 8.5
(cf. `agents/po.md`) — toute version antérieure (skip silencieux,
append simple) est dépréciée :

1. **Détection placeholder bootstrap** : la ligne
   `| `<a completer par agent PO>` | <role> | - |` (issue de
   `templates/constitution.template.md`) est détectée et **remplacée**
   par le 1er acteur (Edit, pas append).
2. **Append normal** pour les acteurs suivants ou si pas de placeholder.
3. **Edit in-place** sur la 3ᵉ colonne (`FEATs concernées`) si l'acteur
   est déjà listé pour une autre FEAT.
4. **Validation read-back obligatoire** : à la fin du STEP, l'agent
   re-Read constitution.md et vérifie que **tous** les acteurs de la
   section `## Actors` de la FEAT parente apparaissent en colonne 1
   du tableau §3, ET qu'il n'y a plus de ligne placeholder.
5. **STOP + ERROR si validation échoue** : un STEP 8.5 ne peut plus
   se terminer silencieusement vide.

**Cas réel ayant motivé ce durcissement** (run 1-pvlist, audit A1) :
le STEP 8.5 v3 d'origine acceptait un skip silencieux quand le pattern
Edit append ne matchait pas le placeholder. Résultat : §3 est resté
avec `<a completer par agent PO>` pendant toute la durée du projet.
La v3.1.3 supprime cette possibilité de défaillance silencieuse.

---

## 4. Création d'un ADR

Un ADR est créé quand :

- **constitutioner (Phase 3.5)** : pour chaque décision majeure (choix
  backend, frontend, UI DS, auth, DatabaseType, stratégie scaffolding). Au
  moins 1 ADR par dimension active du stack. (arch pose le sentinel ; il
  ne crée plus les ADRs lui-même — CR-2.)
- **Dev-* en cours d'exécution** : si un choix d'implémentation
  important n'est pas couvert par un ADR existant ET ne découle pas
  directement du stack actif (ex. : choix d'une stratégie de
  pagination, d'une convention de naming spécifique au projet).
  Sinon, suivre le stack sans tracer.

### 4.1 Identifiant — timestamp atomique (v3.0.1)

**Ne PAS utiliser** `ADR-{nnn}-{slug}.md` avec numérotation
incrémentale (`Glob + max + 1`) — racy quand plusieurs agents
créent un ADR en parallèle (`/dev-run` lance dev-backend +
dev-frontend simultanément).

**Utiliser** : `ADR-{YYYYMMDDTHHmmss}-{rand4}-{slug}.md`

- `{YYYYMMDDTHHmmss}` : timestamp UTC à la seconde
  - Format compact ISO 8601 sans séparateurs de date/heure
  - Exemples : `20260505T143022`, `20260605T091533`
- `{rand4}` : **4 hex chars random SYSTÉMATIQUE depuis 2026-06-08**
  (`secrets.token_hex(2)`, 16 bits entropie). Anti-collision même seconde
  garantie > 99.998 %. Les ADRs créés **avant 2026-06-08** sont acceptés
  sans rand4 (compat ; cf. Partie A §3 et `sdd_scripts/index_adrs.py`
  regex tolérante). La fonction `mint_adr_filename` supporte aussi un
  `adrs_dir=...` optionnel pour retry-on-collision (jusqu'à 5 tentatives)
  qui couvre le tail de 0.0015 % de proba collision résiduelle.
- `{slug}` = kebab-case, lowercase, max 5 mots significatifs

### 4.2 Tri et lecture

Les ADRs se trient **chronologiquement** par tri alphabétique du
filename (le timestamp ISO le garantit). Aucune ambiguïté entre
agents parallèles.

Exemples :
- `ADR-20260505T143022-stack-backend-dotnet.md`
- `ADR-20260505T143025-database-first-approach.md`
- `ADR-20260605T091533-pagination-cursor-based.md`

Optionnellement, le H1 du fichier peut conserver un alias court
(`# ADR-001 — Backend stack`) pour la lisibilité humaine, mais cet
alias **n'est PAS l'identifiant** — il peut être renuméroté
post-hoc sans casser de lien (les liens utilisent le filename).

### 4.3 Format

Read `.sdd/templates/adr.template.md`. Remplir tous les champs.
Status initial = `Accepted` (les ADRs SDD_Pro tracent des décisions
déjà prises, pas des propositions à débattre).

### 4.4 Index dans constitution.md §6

⚠️ **Modifié CR-2 (2026-05-13)** : seul l'agent `constitutioner`
(phase 3.5, séquentielle) peut écrire dans §6 + INDEX.md. `arch` (Phase B)
**ne touche PLUS** §6 — il pose le sentinel disque et délègue. Les agents
`dev-*` (phase 5, parallèles) **ne touchent PAS** constitution.md — ils
créent au plus le fichier ADR individuel.

**Comportement par phase** :
- **constitutioner (phase 3.5)** : après scan des ADRs sur disque, (re)build
  intégralement le tableau §6 de `workspace/.sys/.context/constitution.md` :
  ```markdown
  | ADR-{YYYYMMDDTHHmmss}-{rand4}-{slug} | <titre> | Accepted | 3.5-CONSTITUTION |
  ```
- **Dev-* (phase 5)** : crée uniquement le fichier ADR. Pour les ADRs phase
  5, la source de vérité = `Glob workspace/.sys/.context/adrs/*.md`.

Pour reconstruire l'index §6 manuellement après une session
`/dev-run` qui aurait produit des ADRs : prochaine invocation
`constitutioner` (idempotente) re-scanne et reconstruit, OU régénération
directe via `python .sdd/python/sdd_scripts/index_adrs.py`
(déterministe, 0 token).

---

## 5. Quand créer un ADR vs ne pas en créer

**Créer un ADR** :
- Choix entre 2+ options techniques avec trade-off (ex. Database-First
  vs Code-First)
- Convention projet inhabituelle ou non triviale (ex. naming
  endpoints, stratégie pagination, format DTOs)
- Décision qui affecte plusieurs US ou plusieurs agents
- Décision qui invalide ou supersede une décision antérieure

**Ne PAS créer d'ADR** :
- Choix entièrement imposé par le stack actif (ex. utiliser Razor
  pour Blazor — c'est inhérent au stack)
- Détail d'implémentation interne à 1 service (ex. nom d'une variable
  privée)
- Décision triviale (ex. ordre des `using`)

---

## 6. Anti-derive

- Aucun ADR ne contient de code applicatif (uniquement décision +
  rationale)
- Aucun ADR ne supersede sans le mentionner explicitement (`Superseded
  by ADR-XXX` dans l'ADR antérieur)
- Aucun ADR ne dépend d'une FEAT ou US qui n'existe pas
- La constitution n'est jamais réécrite intégralement par un agent —
  uniquement étendue
- En cas de conflit entre constitution.md et un ADR plus récent, l'ADR
  fait foi

---

## 7. Localisation des fichiers

```
workspace/.sys/.context/
├── constitution.md                    # 1 fichier projet, partagé
└── adrs/
    ├── ADR-001-{slug}.md
    ├── ADR-002-{slug}.md
    └── ...
```

Aucun autre emplacement n'est valide.
