---
command: sdd-reverse
phase: 3
description: Phase 3 du workflow reverse — extraction fonctionnelle d'UNE unité U-N en FEAT SDD_Pro standard. Spawn agent reverse-functional-extractor (Opus 4.8). Output workspace/input/feats/{n}-{Name}.md consommable par /sdd-full ou /sdd-poc.
loader: .claude/loader.reverse.yml
---

# /sdd-reverse {U-N} [--allow-low] [--json]

## Rôle

Lancer la **Phase 3** : transformer une unité fonctionnelle identifiée par la Phase 1 en FEAT SDD_Pro standard. Une seule unité par invocation (séquentiel strict, ADV-2).

## Args

| Arg | Type | Description |
|---|---|---|
| `{U-N}` | string requis | Identifiant U-N stable (ex. `U-3`) — résolu via `inventory.json.units[]` |
| `--allow-low` | flag | Autorise génération d'une FEAT `confidence: low` sans bannière de blocage. Audit-loggué. **@llm-only-flag** (lu par l'agent reverse-functional-extractor, pas par un script Python — la commande spawn l'agent directement). |
| `--json` | flag | Émet le rapport extraction en JSON |

## Pré-conditions

1. `workspace/old/{P}/.sys/inventory.json` existe ET passe gate ADV-23 :
   - `schemaVersion == 1`
   - `_allocatedNames` et `_featAllocations` présents (dicts, même vides)
   - Sinon → ERROR `[REVERSE_INVENTORY_SCHEMA_STALE]` + suggérer `/sdd-reverse-inventory --refresh`
2. `units[id="{U-N}"]` existe dans `inventory.json`. Sinon → ERROR `[REVERSE_UNIT_NOT_FOUND]`
3. `.claude/python/sdd_reverse/feat.reverse.template.md` présent (ADV-9). Sinon → ERROR `[REVERSE_TEMPLATE_MISSING]`
4. (Optionnel) Lock `workspace/input/feats/.alloc.lock` libre OU stale > 30s. Sinon → ERROR `[REVERSE_LOCK_HELD]` (Phase 3 séquentielle stricte, ADV-2)

## Actions

1. **Résoudre le projet legacy** : lire `workspace/old/*/.sys/inventory.json` pour trouver lequel contient `units[id={U-N}]`. Si plusieurs matchent → ERROR ambiguité, demander `--project {P}` explicite.
2. **Spawn unique** `Agent(reverse-functional-extractor)` avec args = `{U-N}` (+ `--allow-low` si transmis)
3. L'agent suit le flux STEP 1 à 8 documenté dans `.claude/agents/reverse-functional-extractor.md`
4. Validation interne via `validate_reverse_feat.py` (max 3 itérations, ADV-5)
5. Émission ligne chat finale `[REVERSE] {U-N} → FEAT {n}-{Name} (confidence={cap}, {N} ACs). (PROGRESS%)`

## Sortie

```
workspace/input/feats/{n}-{Name}.md            (FEAT SDD_Pro conforme)
workspace/old/{P}/.sys/modules/{Name}/extraction.md   (log décision)
workspace/old/{P}/.sys/inventory.json          (update _featAllocations + _allocatedNames)
```

## Mode `--allow-low`

Sans ce flag : si extraction conclut `confidence: low` (DB schema absent, evidence insuffisante, validation 3 itérations échouée), la FEAT est quand même écrite mais avec bannière `⚠️ revue humaine obligatoire avant /sdd-full` + commentaire REVERSE-GATE `allow-sdd-full=false`.

Avec `--allow-low` : même écriture, mais le commentaire REVERSE-GATE devient `allow-sdd-full=true` ; bannière reste présente. Audit-loggué dans extraction.md.

**Important** : `--allow-low` ne contourne PAS `check_reverse_feat_for_full.py` qui reste opt-in côté `/sdd-full` (cf. ADV-6, §6.1 design doc).

## Voie d'usage standard

1. `/sdd-reverse-inventory MyLegacy` (Phase 1) → identifier les U-N pertinents
2. Lire `workspace/old/MyLegacy/.sys/inventory.md` (résumé exécutif)
3. Pour chaque unité voulue : `/sdd-reverse U-1`, puis `/sdd-reverse U-2`, etc. (séquentiel)
4. Tech Lead revue Phase 5 (compléter `## Project Config` dans chaque FEAT)
5. `python -m sdd_reverse_scripts.check_reverse_feat_for_full --feat-path workspace/input/feats/1-*.md`
6. `/sdd-full 1` (pipeline SDD_Pro standard)

Voir `.claude/docs/reverse-engineering-workflow.md` §1, §3, §4.3, §6.1.

## Anti-derive

- **Une seule unité par invocation** — jamais batch multi-U-N (ADV-2 Phase 3 séquentielle stricte)
- Lock atomique élargi à la transaction complète (read max_n → write FEAT → update inventory → release)
- No-spawn d'agent autre que `reverse-functional-extractor`
- Idempotence : re-lancer `/sdd-reverse U-3` réécrit la même FEAT (mêmes `n` et `Name` via `_featAllocations`)
