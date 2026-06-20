# `sdd_lib/migrations/` — console.db schema migrations

> Forward-only schema migrations for `workspace/output/db/console.db`.

## Convention

Fichier : `{NNNN}_{slug}.sql`
- `NNNN` = version **cible** (4 chiffres zero-padded, ex. `0002`)
- `{slug}` = kebab-case court, descriptif (ex. `add-feat-tags`, `index-runs-feat-n`)

Exemples valides :
- `0002_add-feat-tags.sql`
- `0003_index-runs-feat-n.sql`
- `0004_add-spec-compliance-table.sql`

## Sémantique

- **Forward-only** : aucun rollback automatique. Si une migration est mauvaise, écrire une migration corrective `{N+1}`.
- **Idempotent recommandé** : préférer `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN` (SQLite refuse l'ajout de colonne existante, donc protéger par check `PRAGMA table_info`).
- **Atomique** : chaque fichier `.sql` est exécuté dans une seule transaction implicite (`executescript()` wrappe). Si échec mid-script, rollback automatique → la version `schema_version` n'est PAS incrémentée.
- **Append-only** : ne jamais éditer un fichier de migration déjà mergé. Écrire une nouvelle migration corrective.

## Workflow (auteur)

1. Bumper `SCHEMA_VERSION` dans `console_db.py` (`SCHEMA_VERSION = 2`).
2. Créer le fichier `{NNNN}_{slug}.sql` dans ce répertoire.
3. Écrire des tests dans `tests/test_console_db_migrations.py` qui vérifient :
   - le round-trip v(N-1) → v(N) sur une DB vide
   - l'idempotence (réappliquer ne casse rien)
   - les données préservées si la migration touche des tables existantes
4. ADR `governance-schema-migration-{slug}` documentant la décision.

## Workflow (runtime)

`ensure_initialized()` :
1. Lit la version courante via `current_schema_version()`.
2. Si `None` → DB fresh, charge `console_db_schema.sql` complet (init v1).
3. Si `current < SCHEMA_VERSION` → `apply_pending_migrations()` exécute toutes les migrations `> current ET ≤ SCHEMA_VERSION` dans l'ordre.
4. Si `current > SCHEMA_VERSION` → DB en avance sur le framework (autre checkout/branche), aucune migration appliquée, WARN stderr.
5. Si `current == SCHEMA_VERSION` → no-op.

## Garanties

- Pas de data loss sur upgrade (les anciennes colonnes/tables restent).
- Pas de `--force-recreate` requis pour évoluer.
- Reproductibilité cross-machine : même séquence de migrations → même schéma final.

## Tests

Couverture obligatoire dans `tests/test_console_db_migrations.py` (introduit en v7.0.0).
