# /sdd-reverse-inventory — Phase 1 du reverse engineering

> ⚠️ **Commande du workflow reverse engineering** (séparé du pipeline SDD_Pro principal).
> Master prompt : `@.claude/docs/reverse-engineering-master-prompt.md`
> Design doc : `@.claude/docs/reverse-engineering-workflow.md`
> Loader : `@.claude/loader.reverse.yml` section `reverse-inventory`
> Règle : `@.claude/rules/reverse-engineering.md`

Exécute la Phase 1 complète :
1. **Scan déterministe** (Python, 0 token) : `scan_legacy.py` + `inventory_builder.py` + `ui_unit_detector.py`
   → produit `inventory-raw.json` + `units-candidates.json`
2. **Synthèse humaine + arbitrage** (agent LLM `reverse-inventory`) : lit les JSONs et un échantillon de fichiers
   → produit `inventory.md` (lisible Tech Lead) + `inventory.json` (source de vérité Phase 3)

**Usage** : `/sdd-reverse-inventory {ProjectName}` *ou* `/sdd-reverse-inventory {path-to-legacy}`

---

## STEP 1 — Résolution du chemin projet

Argument `{ProjectName_or_path}` :
- Si `workspace/old/{ProjectName_or_path}/` existe → `LEGACY_PATH = workspace/old/{ProjectName_or_path}`
- Sinon si le chemin passé existe directement → `LEGACY_PATH = {arg}`
- Sinon → ERROR :
  ```
  ERROR: /sdd-reverse-inventory — projet introuvable
  CAUSE: [REVERSE_PRECONDITION] ni workspace/old/{arg}/ ni {arg} n'existe
  FIX: lancer /sdd-reverse-init {Name} d'abord, OU vérifier le chemin
  ```

---

## STEP 2 — Phase 1a : Scan déterministe Python

Invocation directe du CLI orchestrateur (Bash, pas de LLM) :

```bash
python -m sdd_reverse_scripts.reverse_inventory \
  --project-path "{LEGACY_PATH}" \
  2>&1
```

Le script émet ses propres updates 1L au format `[REVERSE] ... (X%)`.

Codes de sortie :
- `0` : succès — passer à STEP 3
- `1` : `[REVERSE_PRECONDITION]` — propager l'erreur, STOP
- `2` : `[REVERSE_SCAN_FAILED]` — propager, STOP
- `3` : `[REVERSE_NO_LANGUAGE]` — propager, STOP

Outputs attendus après succès :
- `{LEGACY_PATH}/.sys/inventory-raw.json`
- `{LEGACY_PATH}/.sys/units-candidates.json`

---

## STEP 3 — Phase 1b : Spawn de l'agent reverse-inventory

```
Agent: reverse-inventory
  args: {LEGACY_PATH}
  task: |
    Lis workspace/old/{LegacyProject}/.sys/inventory-raw.json et units-candidates.json
    déjà produits par scan_legacy.py + ui_unit_detector.py.

    Applique le STEP 1-5 de @.claude/agents/reverse-inventory.md :
    1. Lecture sélective (max 10 fichiers représentatifs en échantillon)
    2. Arbitrage merge/split/omit des unités candidates
    3. Numérotation FEAT proposée par ordre de complexité croissante
    4. Génération workspace/old/{P}/.sys/inventory.md (lisible humain)
    5. Génération workspace/old/{P}/.sys/inventory.json (source de vérité Phase 3)

    Output français. Confidence cap par langage (cf. rules/reverse-engineering.md §2).
    Anti-derive REVERSE (cf. §4) : strictement exécutif.
```

L'agent émet ses updates `[REVERSE-INVENTORY] ... (X%)` puis un verdict 1L `[DONE]`.

---

## STEP 4 — Validation post-execution

Vérifier la présence des outputs :
- `{LEGACY_PATH}/.sys/inventory.md`
- `{LEGACY_PATH}/.sys/inventory.json`

Si l'un manque → l'agent a STOP avec ERROR : propager l'erreur, exit ≠ 0.

---

## STEP 5 — Verdict final

```
[DONE] Reverse inventory {ProjectName} — {N} unités fonctionnelles candidates, {M} modules.
       Confidence globale : {high|medium|low}.
       Outputs : workspace/old/{ProjectName}/.sys/inventory.{md,json}

Prochaines étapes :
  1. Relire workspace/old/{ProjectName}/.sys/inventory.md
  2. Optionnel : éditer inventory.md pour ajuster fusions/splits (puis re-run pour ré-aligner inventory.json)
  3. Lancer /sdd-reverse {unit-id} pour extraire la 1ère FEAT (recommandé : commencer par les unités les plus simples)
```

---

## Anti-derive

- La commande est **strictement orchestrante** : elle ne lit aucun fichier legacy, ne génère aucune FEAT.
- Toute la logique métier est dans l'agent `reverse-inventory` + les scripts Python.
- Idempotent : re-run écrase `inventory-raw.json`, `units-candidates.json`, `inventory.md`, `inventory.json`.
- Si l'humain a édité `inventory.md` manuellement entre 2 runs, un WARN signale l'écrasement avant action.

## Exit codes

- `0` : success
- `1` : précondition échouée (projet introuvable, .sys non créé)
- `2` : scan failed (Phase 1a)
- `3` : no language detected
- `4` : agent reverse-inventory a STOP avec ERROR
