# `sdd_lib/migrations/` — console.db schema migrations

> Forward-only schema migrations for `workspace/db/console.db`.

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
- **Idempotent** : préférer `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`. Les `ALTER TABLE ... ADD COLUMN` sont **automatiquement gardés** par le runner (`PRAGMA table_info` : colonne déjà présente → statement sauté) depuis l'audit 2026-11-07 — un rejeu concurrent ne produit plus `duplicate column name`.
- **Atomique** (audit 2026-11-07) : chaque fichier `.sql` est exécuté statement par statement dans **une transaction explicite `BEGIN IMMEDIATE`** qui contient AUSSI l'INSERT `schema_version`. Échec mid-script → `ROLLBACK` : ni DDL partiel ni version. (Avant : `executescript()` committait puis l'INSERT de version partait dans une 2e transaction.) La version est re-vérifiée à l'intérieur du verrou → deux writers concurrents sérialisent, le second voit la migration faite et la saute.
- **Interdit dans un fichier de migration** : `BEGIN`/`COMMIT`/`ROLLBACK` explicites (le runner possède la transaction).
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
1. Lit la version courante via `current_schema_version()` (DB relocalisable via `$SDD_CONSOLE_DB_PATH`).
2. Si `None` → DB fresh, charge `console_db_schema.sql` complet (init v1).
3. Si `current < SCHEMA_VERSION` → `apply_pending_migrations()` exécute toutes les migrations `> current ET ≤ SCHEMA_VERSION` dans l'ordre.
4. Si `current > SCHEMA_VERSION` → DB en avance sur le framework (autre checkout/branche), aucune migration appliquée, WARN stderr.
5. Si `current == SCHEMA_VERSION` → no-op.
6. Dans tous les cas (sauf DB en avance) : migration de données légère `mark_stale_runs()` — tout run `running` sans activité depuis > 24 h passe `stale` (idempotent).

## Garanties

- Pas de data loss sur upgrade (les anciennes colonnes/tables restent).
- Pas de `--force-recreate` requis pour évoluer.
- Reproductibilité cross-machine : même séquence de migrations → même schéma final.

## Tests

Couverture obligatoire dans `tests/test_console_db_migrations.py` (introduit en v7.0.0).
