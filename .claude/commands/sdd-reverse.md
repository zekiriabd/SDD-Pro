# /sdd-reverse — Phase 3 : extraction fonctionnelle d'une unité legacy → FEAT.md

> ⚠️ **Commande du workflow reverse engineering** (séparé du pipeline SDD_Pro principal).
> Master prompt : `@.claude/docs/reverse-engineering-master-prompt.md`
> Design doc : `@.claude/docs/reverse-engineering-workflow.md`
> Loader : `@.claude/loader.reverse.yml` section `reverse-functional-extractor`
> Règle : `@.claude/rules/reverse-engineering.md`

Extrait UNE unité fonctionnelle du legacy en UNE FEAT.md au format SDD_Pro standard.

La FEAT générée est strictement compatible avec :
- `/feat-validate {n}` (Readiness Gate)
- `/sdd-full {n}` (pipeline complet existant)
- `/sdd-poc {n}` (pipeline minimaliste existant)

**Usage** :
- `/sdd-reverse {ProjectName} {unit-id}` (ex. `/sdd-reverse AcmeCRM unit-001`)
- `/sdd-reverse {LEGACY_PATH} {unit-id}` (chemin explicite)

---

## STEP 1 — Valider les arguments

Arguments :
- `{ProjectName_or_path}` (obligatoire)
- `{unit_id}` (obligatoire, format `unit-NNN`)

Résolution `LEGACY_PATH` :
- Si `workspace/old/{arg1}/` existe → `LEGACY_PATH = workspace/old/{arg1}`
- Sinon si `{arg1}` est un chemin valide → `LEGACY_PATH = {arg1}`
- Sinon → ERROR `[REVERSE_PRECONDITION]`

Vérifier que `{unit_id}` matche le pattern `^unit-\d{3}(\+unit-\d{3})*$` (support fusion explicite `unit-001+unit-002` même si non recommandé — préférer fusion via inventory.json).

---

## STEP 2 — Précondition : inventory.json présent

```bash
INVENTORY_JSON="${LEGACY_PATH}/.sys/inventory.json"
```

Si absent → ERROR :
```
ERROR: /sdd-reverse — Phase 1 inventory manquant
CAUSE: [REVERSE_PRECONDITION] {LEGACY_PATH}/.sys/inventory.json absent
FIX: lancer /sdd-reverse-inventory {ProjectName} d'abord (Phase 1)
```

Parser le JSON, chercher l'unité `{unit_id}`. Si absente → ERROR `[REVERSE_UNIT_NOT_FOUND]`.

Récupérer :
- `feat_number_proposed` → `{n}`
- `feat_name_proposed` → `{Name}`
- `evidence[]` (fichiers cités)
- `language_detected` (pour cookbook fiche)
- `confidence_hint`

---

## STEP 3 — Précondition : FEAT.md cible disponible

```bash
TARGET_FEAT="workspace/input/feats/{n}-{Name}.md"
```

Si déjà existante :
1. Lire son frontmatter
2. Si `generated-by: sdd-reverse` ET `unit_id` identique ET `unit-hash` identique au hash calculé maintenant
   → **SKIP silencieux** (idempotence). Émettre :
   ```
   [REVERSE] FEAT {n}-{Name} déjà extraite (hash inchangé). SKIP. (100%)
   ```
   exit 0.
3. Si `generated-by: sdd-reverse` ET `unit-hash` différent → continuer mais émettre WARN :
   ```
   🟡 [REVERSE/WARN] FEAT {n}-{Name} existe (hash différent — legacy modifié). Re-extraction en cours.
   ```
4. Si `generated-by != sdd-reverse` → ERROR :
   ```
   ERROR: /sdd-reverse {unit-id} — collision FEAT
   CAUSE: [REVERSE_FEAT_NUMBER_TAKEN] {n}-{Name}.md existe (créé par /feat-generate)
   FIX: renuméroter via inventory.json OU déplacer la FEAT existante avant relance
   ```

---

## STEP 4 — Spawn de l'agent reverse-functional-extractor

```
Agent: reverse-functional-extractor
  args: {LEGACY_PATH} {unit_id}
  task: |
    Lis workspace/old/{P}/.sys/inventory.json (passage unit-{id} uniquement).
    Applique le STEP 0-9 de @.claude/agents/reverse-functional-extractor.md :
    1. Préflight + hash unité
    2. Lecture sélective MAX 15 fichiers (evidence + db-schema + cookbook)
    3. Analyse intention métier (Actors, SFDs, FDs, BRs, ACs)
    4. Génération frontmatter complet
    5. Génération corps FEAT.md (6 sections SDD_Pro obligatoires)
    6. Auto-validation interne (schéma, IDs, evidence, confidence, covers)
    7. Write atomique workspace/input/feats/{n}-{Name}.md
    8. Validation post-write via /feat-validate {n} --json
    9. Verdict 1L

    Output français (D6). Confidence cap par langage (cf. règle §2).
    Anti-derive REVERSE strict (cf. règle §4). Evidence sur chaque item.
```

L'agent émet ses updates `[REVERSE] ... (X%)` puis un verdict 1L `[DONE]`.

---

## STEP 5 — Vérification post-execution

Vérifier :
1. `workspace/input/feats/{n}-{Name}.md` créé/mis à jour
2. `workspace/old/{P}/.sys/modules/{module-id}/extraction-{unit-id}.md` créé (rapport agent)

Si manquant → l'agent a STOP avec ERROR. Propager.

---

## STEP 6 — Verdict final

```
[DONE] /sdd-reverse {unit-id} — FEAT {n}-{Name} extraite (confidence: {high|medium|low}).
       FEAT : workspace/input/feats/{n}-{Name}.md
       Rapport : workspace/old/{ProjectName}/.sys/modules/{module-id}/extraction-{unit-id}.md

Prochaines étapes :
  - Si confidence : high → exploitable immédiatement par /sdd-full {n}
  - Si confidence : medium/low → relire la FEAT, vérifier les items <!-- confidence: low -->
  - Pour extraire l'unité suivante : /sdd-reverse {ProjectName} {next-unit-id}
```

---

## Anti-derive

- 1 invocation = 1 unité = 1 FEAT. Pas de batch.
- Idempotent : re-run avec hash inchangé = skip silencieux.
- Strictement orchestrante : aucune logique métier ici, tout dans l'agent + scripts Python.
- Aucun fichier SDD_Pro existant n'est modifié (la commande lit `validate_readiness.py` en read-only).

## Exit codes

- `0` : success (FEAT extraite OU skip idempotent)
- `1` : précondition échouée (project introuvable, unit-id invalide)
- `2` : inventory.json absent (Phase 1 pas exécutée)
- `3` : collision FEAT (numéro déjà pris par non-reverse)
- `4` : agent reverse-functional-extractor STOP avec ERROR
