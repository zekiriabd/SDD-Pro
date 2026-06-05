# SDD_Pro — Working Agreement

> Autorisation de travail de l'assistant Claude dans le workspace SDD_Pro.
> Référencé depuis `@.claude/CLAUDE.md §11` (slim entry point).

## Pleine autorisation accordée

Dans le répertoire SDD_Pro :

- Créer, éditer, supprimer, déplacer des fichiers (sources, docs, US,
  workspace, `.claude/`, etc.)
- Exécuter shell, builds, lints, tests, scripts Python (`.claude/python/`)
- Opérations git locales : `add`, `commit`, `branch`, `checkout`,
  `merge`, `rebase`, `stash`
- Restore de packages : NuGet (`dotnet restore`), npm (`npm install`),
  pip, etc. depuis registres officiels

## Limites strictes

Toute opération dépassant l'un des 3 périmètres suivants déclenche une
demande explicite au Tech Lead :

### 1. Structure de base de données

Aucune modification du schéma DB réelle.

Interdits : `INSERT/UPDATE/DELETE/CREATE/ALTER/DROP/TRUNCATE`,
`dotnet ef migrations add|remove|script`,
`dotnet ef database update|drop`.

L'introspection READ-ONLY (scaffolding Database-First par agent `arch`)
reste autorisée.

### 2. Hors répertoire SDD_Pro

Aucun accès en lecture/écriture aux autres projets du disque, fichiers
système, profils shell, registry Windows.

### 3. Réseau sortant

Seulement ce que requièrent build/test :

- ✅ Restore packages depuis NuGet/npm/PyPI/Maven officiels
- ✅ Appels HTTP `localhost` (tests intégration, dev server)
- ❌ `git push` (toute branche)
- ❌ `curl` vers domaines arbitraires (sauf documentation explicite
  dans une règle / stack)
- ❌ Upload, telemetry, analytics

## Conséquence comportementale

Ne JAMAIS demander confirmation pour des opérations couvertes par cette
autorisation. Demander uniquement si l'opération franchit une des
3 limites ci-dessus.

## Référence settings

`.claude/settings.json`
- `permissions.allow` couvre les patterns shell courants
- `permissions.deny` bloque les opérations DB structurelles et `git push`
