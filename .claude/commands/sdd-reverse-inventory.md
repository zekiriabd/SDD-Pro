---
description: Phase 1 du workflow reverse — cartographie déterministe d'un projet legacy. Spawn agent reverse-inventory (Sonnet 4.6) qui délègue au script reverse_inventory.py + enrichit inventory.md. Output bloquant pour Phase 3 (/sdd-reverse {U-N}).
---
# /sdd-reverse-inventory {LegacyProject} [--use-cache] [--json]

## Rôle

Lancer la **Phase 1** : produire `inventory.{md,json}` + `db-schema.{md,json}` + `language-detected.json` sous `workspace/old/{LegacyProject}/.sys/`. Bloquant pour `/sdd-reverse {U-N}` (Phase 3).

## Args

| Arg | Type | Description |
|---|---|---|
| `{LegacyProject}` | string requis | Nom du sous-dossier sous `workspace/old/` |
| `--use-cache` | flag | Saute le scan si `inventory.json` existant + valide ADV-23 (schemaVersion + `_allocatedNames`) |
| `--json` | flag | Émet le rapport final en JSON sur stdout (machine-readable) |

## Pré-conditions

1. `workspace/old/{LegacyProject}/.sys/` doit exister (sinon → `/sdd-reverse-init {P}` d'abord)
2. `workspace/old/{LegacyProject}/` contient des fichiers source non-binaires
3. `.sdd/python/sdd_reverse/language_signatures.yml` présent (sinon → erreur framework, problème d'install)

Si manquant → STOP + ERROR `[REVERSE_NO_SOURCE]` ou `[INFRA_BLOCKED]`.

## Actions

1. **Spawn unique** `Agent(reverse-inventory)` avec args = `{LegacyProject}`
2. L'agent vérifie préconditions + invoque `python .sdd/python/sdd_reverse_scripts/reverse_inventory.py --project workspace/old/{LegacyProject}` (+ `--use-cache` / `--refresh` / `--json` si transmis — invocation canonique par chemin de fichier, C6)
3. Le script écrit les 5 artefacts `.sys/*`
4. L'agent enrichit `inventory.md` FR avec résumé exécutif + regroupements sémantiques
5. Émission ligne chat finale `[REVERSE] {LegacyProject} : N unités, M entités, langage primaire {lang}. (15%)`

## Mode `--use-cache`

Si `inventory.json` existant et passe la gate ADV-23 (`schemaVersion == 1` ET `_allocatedNames` ET `_featAllocations` présents) → le script saute le scan complet et l'agent régénère uniquement le markdown FR. Sinon refresh forcé + INFO `[REVERSE_INVENTORY_SCHEMA_STALE]`.

## Sortie

```
workspace/old/{LegacyProject}/.sys/
├── inventory.{md,json}
├── db-schema.{md,json}
└── language-detected.json
```

Voir `.sdd/docs/reverse-engineering-workflow.md` §4.1 + §5 + §6 (contrats inter-phases).

## Anti-derive

- Aucun spawn d'autre agent que `reverse-inventory`
- Read-only sur le legacy, write uniquement sous `.sys/`
- Phase 3 NE DOIT PAS être lancée automatiquement (le Tech Lead arbitre quelles unités extraire et dans quel ordre)

## Idempotence

Re-lancer écrase les `.json` (overwrite via atomic_write_local). U-N IDs préservés via fingerprint full+core (ADV-1).
