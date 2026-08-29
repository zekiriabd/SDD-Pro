---
description: Phase 2 du workflow reverse — audit informational. Spawn reverse-tech-auditor (Sonnet 4.6) après exécution du script déterministe reverse_audit.py (deps-graph + merge db-schema). Output non bloquant pour Phase 3.
---
# /sdd-reverse-audit {LegacyProject} [--force-enrichment-on Entity.field] [--json]

## Rôle

Lancer la **Phase 2** : audit architecture / anti-patterns / dépendances EOL + enrichissement DB schema. **Optionnel** : Phase 3 ne dépend PAS de Phase 2 (cf. design doc §4.2).

## Args

| Arg | Type | Description |
|---|---|---|
| `{LegacyProject}` | string requis | Sous-dossier de `workspace/old/` (Phase 1 préalable obligatoire) |
| `--force-enrichment-on Entity.field` | flag répétable | ADV-12 : permet à `enrichment.json` d'override le base sur ce field (en cas de conflit type) |
| `--json` | flag | Émet rapport audit en JSON |

## Pré-conditions

- `workspace/old/{LegacyProject}/.sys/inventory.json` doit exister (Phase 1)
- `workspace/old/{LegacyProject}/.sys/db-schema.json` doit exister (Phase 1)

Sinon → STOP + ERROR `[REVERSE_NO_SOURCE]` + suggérer `/sdd-reverse-inventory {LegacyProject}` d'abord.

## Actions

1. **Script déterministe d'abord** :
   ```bash
   python .sdd/python/sdd_reverse_scripts/reverse_audit.py \
       --project workspace/old/{LegacyProject} \
       [--force-enrichment-on ...]
   ```
   Produit `deps-graph.json` + skeleton `db-schema.enrichment.json` + `db-schema.merged.json`.
2. **Spawn unique** `Agent(reverse-tech-auditor)` qui enrichit `tech-audit.md` (FR) + remplit `db-schema.enrichment.json` avec relations/fields/indexes déduits.
3. **Re-merge** : le merge_db_schema.py est re-déclenché par l'agent post-enrichment (idempotent).
4. Émission ligne chat finale `[REVERSE] Audit complet. {anti-patterns} anti-patterns, {eol} EOL deps. (28%)`

## Sortie

```
workspace/old/{LegacyProject}/.sys/
├── tech-audit.md                    (FR narratif, par agent)
├── deps-graph.json                  (script, design doc §5.4)
├── db-schema.enrichment.json        (enrichi par agent, ADV-3)
└── db-schema.merged.json            (union déterministe via merge_db_schema)
```

## Skippable

Phase 2 est **purement informational**. Phase 3 fonctionne sans elle (lit `db-schema.json` base si `db-schema.merged.json` absent). Skip avec `/sdd-reverse-full --skip-audit` (V2).

## ADV-12 — Type conflicts

Si l'enrichment propose un field type différent du base, `merge_db_schema.py` par défaut **garde le base** et émet `[REVERSE_ENRICHMENT_TYPE_CONFLICT]` informational. Override avec `--force-enrichment-on Entity.field` (audit-loggué).

## Anti-derive

- Aucun spawn d'autre agent que `reverse-tech-auditor`
- Lecture bornée 20 fichiers (l'agent)
- Output Phase 2 ne bloque jamais Phase 3
- `db-schema.json` (base) reste intouchable par l'agent — seul le script `merge_db_schema.py` peut produire le `.merged.json`

Voir `.sdd/docs/reverse-engineering-workflow.md` §4.2 + §15.3 (ADV-12 V2 closure).
