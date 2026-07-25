# Arch — Phase B : DB connection + introspection + scaffolding

> Module conditionnel de l'agent `arch`. Read seulement si
> `DatabaseType ≠ none` (cf. `arch.md` STEP 7 décision DB).
>
> Contient STEP 8-11 : composition connection string en RAM, introspection
> schema (READ-ONLY), écriture `workspace/db/schema.{json,md,diff.md}`,
> scaffolding Database-First cross-stack.
>
> Source de vérité : ce fichier. `arch.md` route ici sans dupliquer.

---

## STEP 8 — Composer la connection string en RAM (cross-stack)

Lire 5 clés depuis `db_config` (STEP 2.ter, validation déjà faite) :

| Clé | Rôle |
|---|---|
| `DB_HOST` | hôte / serveur SQL |
| `DB_PORT` | port (1433 SqlServer, 5432 PostgreSQL, …) |
| `DB_NAME` | nom de la base |
| `DB_USER` | utilisateur |
| `DB_PASSWORD` | mot de passe (jamais loggé, jamais sur disque) |

> **Pas d'env vars** : valeurs exclusivement depuis `stack.md ## Active
> Database`. `$env:VAR`, `${VAR}`, `process.env`, `os.environ`,
> `System.getenv` interdits côté arch et code applicatif.

### 8.1 Composition selon le langage backend

Délégué au pattern `§8.2 Connection String Pattern` du stack actif :

| Langage | Section | Outil canonique |
|---|---|---|
| .NET   | `dotnet-minimalapi.md §8.2` | `SqlConnectionStringBuilder` (variants par DatabaseType) |
| Node   | `node-express.md §8.2`      | objet `{host,port,database,user,password}` ou Prisma `DATABASE_URL` (`encodeURIComponent`) |
| Python | `python-fastapi.md §8.2`    | `sqlalchemy.engine.URL.create()` |

Arch :
1. Lit §8.2 du stack
2. Génère un **bridge runtime ad-hoc** dans le langage cible
   (`_bridge.cs/.js/.py` temporaire compose puis invoque scaffold)
3. Bridge supprimé après usage (idempotent)

**Garde-fous absolus** :
- Connection string composée → JAMAIS écrite hors STEP 4.5
- JAMAIS dans `schema.json`/`schema.md`/`workspace/db/`
- JAMAIS logger `DB_PASSWORD` ni la chaîne complète
- JAMAIS de concaténation strings — builder canonique uniquement

---

## STEP 8.5 — Migration Flyway sanctionnée (conditionnel)

> **Seule dérogation à « DB READ-ONLY »** — `library-and-stack.md §C.6`.
> Exécuté **uniquement** si l'orchestrateur (`/sdd-full`/`/sdd-poc`) a détecté
> une FEAT dont le nom de fichier contient « Flyway » et posé le sentinel.

### 8.5.1 Lire le sentinel

```bash
FLAG=workspace/.sys/.state/flyway-migrate-requested.flag
```

- Sentinel **absent** → skip STEP 8.5 (cas nominal, on passe à STEP 9).
- Sentinel **présent** ET `DatabaseType = none` → ignorer + WARN (rien à migrer),
  consommer le flag, passer à STEP 12 (pas de Phase B).
- Sentinel **présent** ET `DatabaseType ≠ none` → exécuter 8.5.2.

arch ne lit **jamais** la FEAT pour décider — il se fie au sentinel posé par
l'orchestrateur (anti-derive « Jamais lire FEATs » préservé).

### 8.5.2 Exécuter `flyway migrate`

1. **Localiser le runner Flyway** du stack backend actif (section
   `Scaffolding tool` / `Migration tool` du `.md` stack, ou `flyway` CLI / plugin
   Gradle-Maven). Runner introuvable / non exécutable → STOP
   `CAUSE: [INFRA_BLOCKED]` (« je n'ai pas pu exécuter », pas de fallback DDL).
2. **Localiser les scripts** versionnés `V{version}__{desc}.sql` :
   - Spring Boot : `src/main/resources/db/migration/`
   - sinon : `workspace/db/migration/`
   - Aucun script trouvé → WARN (rien à appliquer), consommer le flag, STEP 9.
3. **Invoquer** `flyway migrate` via le bridge ad-hoc STEP 8.1 (connection string
   en RAM, jamais persistée ni loggée). Flyway saute les versions déjà inscrites
   dans `flyway_schema_history` (idempotence native).
4. Exit ≠ 0 → STOP `CAUSE: [SCHEMA_MISMATCH]` : `flyway migrate exit {N} :
   {message condensé}` (script invalide, conflit de version, base injoignable).
   Aucune ré-écriture partielle masquée.

### 8.5.3 Forçage re-scaffold + consommation du flag

- Après migrate réussi, **forcer** STEP 9 (ré-introspection) + STEP 11 (re-scaffold
  `--force` incrémental) **même si `schema.json` existe** — le schéma a changé,
  les entities doivent refléter la base migrée (défait tout short-circuit arch).
- **Consommer** le sentinel (`rm -f $FLAG`) après migrate réussi → per-run, une
  FEAT Flyway re-déclenche le migrate au prochain `/sdd-full`/`/sdd-poc`
  (sûr car idempotent).

arch **n'écrit ni ne modifie** les scripts `V*__*.sql` — ce sont des artefacts de
la FEAT (Tech Lead / dev-backend). arch **exécute** seulement le runner.

```
[ARCH] Migration Flyway appliquée ({k} versions), schéma re-scaffoldé. (28%)
```

---

## STEP 9 — Introspection du schéma (READ-ONLY)

Selon `DatabaseType`, exécuter une requête d'introspection des métadonnées :

| DatabaseType | Source |
|---|---|
| `SqlServer`  | `INFORMATION_SCHEMA.TABLES` + `INFORMATION_SCHEMA.COLUMNS` |
| `PostgreSQL` | `information_schema.tables` + `information_schema.columns` |
| `MySql`      | `information_schema.tables` + `information_schema.columns` |
| `Sqlite`     | `sqlite_master` + `pragma table_info` |

Récolter par table : nom + schéma, colonnes (nom, type SQL, nullable,
default, position), PK + FK, index (au moins les uniques).

**Anti-derive** : aucune requête au-delà de l'introspection. Aucun
`SELECT` sur tables de données.

---

## STEP 10 — Écrire `workspace/db/schema.json` + `schema.md`

Format `schema.json` :
```json
{
  "extracted_at": "{ISO-8601}",
  "database_type": "SqlServer",
  "tables": [
    {
      "schema": "dbo",
      "name": "Users",
      "primary_key": ["Id"],
      "columns": [
        {"name": "Id", "type": "int", "nullable": false, "default": null},
        {"name": "Email", "type": "nvarchar(256)", "nullable": false, "default": null}
      ],
      "foreign_keys": [{"column": "RoleId", "ref_table": "Roles", "ref_column": "Id"}],
      "indexes": [{"name": "IX_Users_Email", "columns": ["Email"], "unique": true}]
    }
  ]
}
```

Format `schema.md` : tableau Markdown lisible, une section par table
(PK, FK, colonnes).

### 10.1 Versionnage et diff

Avant écrasement :
1. `schema.json` présent → copier vers `schema.prev.json`
2. Écrire nouveau `schema.json`
3. Diff léger : tables added/removed, colonnes added/removed, types
   changés, FK added/removed
4. Écrire `workspace/db/schema.diff.md` (frontmatter
   `prev_extracted_at`/`curr_extracted_at` + sections "Tables added/
   removed/modified" avec détail colonnes + types + FK par table).

Premier run (pas de baseline) → diff skip, récap mentionne `Diff: first
run`. Aucune différence → `schema.diff.md` contient `No changes since
{prev_extracted_at}.`

Mode `create` idempotent : écraser `schema.json`/`schema.diff.md` si
existants. `schema.prev.json` non-committé en force.

---

## STEP 11 — Scaffolding Database-First (cross-stack, stack-driven)

**Source de vérité** : section `Scaffolding tool` du stack backend
actif (numéro §-variable, grep `^### .* Scaffolding tool`). Introuvable
→ STOP + ERROR `[STACK_SCAFFOLDING_MISSING]`.

| Stack backend | Outil canonique | Output entities |
|---|---|---|
| `dotnet-minimalapi`  | `dotnet ef dbcontext scaffold` | `workspace/src/{BackendName}/Entities/` |
| `node-express`       | `prisma db pull` + `prisma generate` | `workspace/src/{BackendName}/prisma/schema.prisma` + client |
| `python-fastapi`     | `sqlacodegen` (sync) / `sqlacodegen-v2` (async SQLAlchemy 2.x) | `workspace/src/{BackendName}/entities/db/models.py` |
| `kotlin-spring-boot` | `hibernate-tools` / `jOOQ codegen` / `Flyway` + template Kotlin | `workspace/src/{BackendName}/src/main/kotlin/{pkg}/entities/` |

Format §8.3 attendu dans chaque stack : `Outil` / `Output` / `Idempotence` /
`Filtres` (support §11.1).

Arch invoque l'outil via le bridge ad-hoc STEP 8.1 (connection string
en RAM, jamais sur disque).

### 11.1 Filtre tables

Bloc `## DB Scaffolding` optionnel dans `stack.md` :

```markdown
## DB Scaffolding
Mode: list                       # all | list | exclude
Tables: Users, Employees, Bebes  # si Mode=list (CSV)
ExcludeTables: AspNet*, __EF*    # si Mode=exclude (wildcards)
```

Modes : `all` (défaut/absent), `list`, `exclude` (`*` wildcards).
Traduction CLI : `--table` (.NET), `--filter` (Prisma 5+), `--tables`
(sqlacodegen). Outil sans support → WARNING + `all` + post-process
suppression.

### 11.2 Préservation des customs

Scaffolding **incrémental** : `partial class` adjacentes (.NET, préservées
par `--force`), `prisma/extensions/` (Prisma), `entities/db/extensions/`
(SQLAlchemy). Convention détaillée dans `CLAUDE.md` projet (STEP 12).

### 11.3 Erreur

Exit ≠ 0 → ERROR `[SCHEMA_MISMATCH]` : `{outil} exit {N} : {message
condensé}`. FIX : vérifier connectivité DB, matrice §8.1, présence
outil §8.3.

Mémoriser `DB_RESULT = { tables: N, columns: N, fks: N, entities: N }`
pour récap STEP 13.

---
