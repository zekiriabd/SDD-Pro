---
description: Diagnostic du workflow reverse engineering (pendant de /sdd-status). Liste les projets legacy sous workspace/old/ avec leur phase status, et les FEATs reverse dans workspace/feats/ avec marker [REV]/[REV⚠️] (ADV-6). Read-only, jamais bloquant. Script déterministe, aucun agent spawné.
---
# /sdd-reverse-status [--project {LegacyProject}] [--json]

## Rôle

Diagnostic read-only du workflow reverse engineering. Pendant du `/sdd-status` SDD_Pro standard, scoped reverse.

## Args

| Arg | Type | Description |
|---|---|---|
| `--project {LegacyProject}` | optionnel | Filtre sur un projet spécifique. Par défaut : tous les projets sous `workspace/old/` |
| `--json` | flag | Sortie JSON machine-readable |

## Actions

Invoque le script déterministe (aucun agent) :

```bash
python .sdd/python/sdd_reverse_scripts/reverse_status.py [--project ...] [--json]
```

Le script :
1. Liste tous les sous-dossiers de `workspace/old/` (sauf `.`)
2. Pour chacun, détecte la phase atteinte :
   - **init** : `.sys/` existe
   - **inventory** : `.sys/inventory.json` existe
   - **audit** : `.sys/tech-audit.md` existe
   - **db_merged** : `.sys/db-schema.merged.json` existe
3. Calcule pour chaque projet : `feats_extracted / units_total` (depuis `_featAllocations` vs `units[]`)
4. Liste les FEATs `generated-by: sdd-reverse` dans `workspace/feats/` avec :
   - Marker `[REV]` (confidence=high) ou `[REV⚠️]` (medium/low)
   - `allow_sdd_full` depuis le commentaire `<!-- REVERSE-GATE -->`
   - source-unit, confidence, language-detected

## Sortie humaine

```
═══ Reverse Engineering Status ═══

Projets legacy : 2

  • HelloWebForms
      init✓ → inventory✓ → audit✓ → merged✓
      FEATs : 2/2 unités extraites (100%)

  • LegacyJava
      init✓ → inventory✓ → audit✗ → merged✗
      FEATs : 1/5 unités extraites (20%)


FEATs reverse dans workspace/feats/ : 3

  [REV] 1-Login  (confidence=high, U=U-1)
        → /sdd-full OK
  [REV⚠️] 2-Home  (confidence=medium, U=U-2)
        → REVUE HUMAINE OBLIGATOIRE avant /sdd-full
  [REV⚠️] 3-Dashboard  (confidence=low, U=U-3)
        → REVUE HUMAINE OBLIGATOIRE avant /sdd-full
```

## Sortie JSON

```json
{
  "ok": true,
  "projects": [
    {"name": "HelloWebForms", "phases": {...}, "units_total": 2, "feats_extracted": 2, ...},
    ...
  ],
  "feats": [
    {"file": "...", "name": "1-Login", "confidence": "high", "marker": "[REV]", "allow_sdd_full": true, ...},
    ...
  ]
}
```

## Anti-derive

- **Read-only strict** : aucune écriture, aucun side-effect
- **No-spawn** : aucun agent
- **Jamais bloquant** : exit 0 toujours (exit 1 uniquement si `workspace/old/` absent — info)
- Pas de gate, pas de FAIL — diagnostic pur

Voir `.sdd/docs/reverse-engineering-workflow.md` §6.1 + §6.2 (marker [REV] + check_reverse_feat_for_full gate).
