# Arch — Phase B : DB connection + introspection + scaffolding

> Module conditionnel de l'agent `arch`. Read seulement si
> `DatabaseType ≠ none` (cf. `arch.md` STEP 7 décision DB).
>
> Contient STEP 8-11 : composition connection string en RAM, introspection
> schema (READ-ONLY), écriture `workspace/output/db/schema.{json,md,diff.md}`,
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
- JAMAIS dans `schema.json`/`schema.md`/`workspace/output/db/`
- JAMAIS logger `DB_PASSWORD` ni la chaîne complète
- JAMAIS de concaténation strings — builder canonique uniquement

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

## STEP 10 — Écrire `workspace/output/db/schema.json` + `schema.md`

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
4. Écrire `workspace/output/db/schema.diff.md` (frontmatter
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
| `dotnet-minimalapi`  | `dotnet ef dbcontext scaffold` | `workspace/output/src/{BackendName}/Entities/` |
| `node-express`       | `prisma db pull` + `prisma generate` | `workspace/output/src/{BackendName}/prisma/schema.prisma` + client |
| `python-fastapi`     | `sqlacodegen` (sync) / `sqlacodegen-v2` (async SQLAlchemy 2.x) | `workspace/output/src/{BackendName}/entities/db/models.py` |
| `kotlin-spring-boot` | `hibernate-tools` / `jOOQ codegen` / `Flyway` + template Kotlin | `workspace/output/src/{BackendName}/src/main/kotlin/{pkg}/entities/` |

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
