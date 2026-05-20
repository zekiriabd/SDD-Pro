# /us-generate — Découpe une FEAT en User Stories

> ⚠️ **Commande interne v7.0.0** — invoquée par /sdd-full STEP 2.
> Découpage FEAT → US — invoqué automatiquement.
> Utilisateur final : préférer la commande orchestrante (`/sdd-full` ou `/dev-run`)
> qui gère pré-conditions, idempotence et état. Conservée comme command pour
> debug/inspection ciblée et préservation des chaînes d'invocation documentées.

Invoque l'agent PO pour découper une FEAT fonctionnelle en User
Stories structurées (cible 1-3, warning 4-6, hard cap 6) dans `workspace/output/`.

**Usage :** `/us-generate {n}` — où `{n}` est le numéro de la FEAT

---

## STEP 1 — Valider l'argument

L'argument `{n}` est obligatoire et doit être un entier ≥ 1.

Si absent → demander :
```
Quel est le numéro de la FEAT à découper ? (ex. : 1 pour workspace/input/feats/1-Auth.md)
```

Si non numérique → ERROR :
```
ERROR: /us-generate — argument invalide
CAUSE: "{argument}" n'est pas un entier
FIX: relancer /us-generate {n} avec n entier (ex. /us-generate 1)
```

---

## STEP 2 — Vérifier la FEAT existe

Glob `workspace/input/feats/{n}-*.md`.
- 0 fichier → ERROR :
  ```
  ERROR: /us-generate — FEAT introuvable
  CAUSE: aucun fichier workspace/input/feats/{n}-*.md
  FIX: créer la FEAT via /feat-generate ou la déposer manuellement
  ```
- > 1 fichier → ERROR :
  ```
  ERROR: /us-generate — numérotation invalide
  CAUSE: plusieurs fichiers commencent par {n}- dans workspace/input/feats/
  FIX: renommer pour qu'un seul fichier ait le préfixe {n}-
  ```

---

## STEP 2.5 — Checkpoint skip (v6.6.4, opt-in)

Si `CheckpointMode: resume` dans Project Config (défaut `off` =
comportement v6.6.3 strict) :

```python
from sdd_lib.checkpoint import is_phase_resumable

inputs = [
    f"workspace/input/feats/{n}-*.md",      # FEAT parent
    "workspace/input/stack/stack.md",       # Project Config + stacks actifs
]
resumable, reason = is_phase_resumable(
    feat=n, phase="us-generate", input_paths=resolved_inputs,
)
if resumable:
    print(f"⊘ /us-generate {n}: skipped (checkpoint hit)")
    # STOP avec succès, ne pas re-déléguer à l'agent PO
```

Si `CheckpointMode ∈ {off, record}` → skip ce STEP, continuer.

Émissions possibles : `[CHECKPOINT_HASH_MISMATCH]`, `[CHECKPOINT_INPUT_MISSING]`,
`[CHECKPOINT_STATE_UNREADABLE]`. Cf. `error-classification.md §1.16`.

---

## STEP 3 — Invoquer l'agent PO

Lancer l'agent `po` (défini dans `.claude/agents/po.md`) avec le numéro
`{n}` en argument. L'agent gère le découpage, la traçabilité et l'écriture
des fichiers US dans `workspace/output/`.

Attendre la fin de l'agent. Relayer sa sortie telle quelle (ligne de succès
ou bloc ERROR 3 lignes).

### STEP 3.bis — Checkpoint record (v6.6.4, opt-in)

Si l'agent PO a réussi (US écrites) ET `CheckpointMode ∈ {record, resume}` :

```python
from sdd_lib.checkpoint import record_input_hash

record_input_hash(
    run_id=$RUN_ID,
    phase="us-generate",
    input_paths=resolved_inputs,    # FEAT + stack.md
)
```

Erreur silencieuse si state.json absent → WARN, non bloquant.

---

## STEP 4 — Inventaire des mockups HTML (depuis v4)

Glob `workspace/input/ui/{n}-*.html` pour détecter les mockups déjà déposés.

Glob `workspace/output/us/{n}-*.md` pour récupérer les basenames d'US.

Cross-check :
- HTML dont basename matche une US → couvert
- HTML dont basename ne matche aucune US → orphelin (WARN)
- US sans HTML → info (frontend possible sans mockup OU backend-only)

Émettre la liste compactement (1 ligne par US et 1 ligne par orphelin).

Si aucun HTML détecté ET au moins une US a une composante UI attendue,
émettre une info non bloquante invitant à déposer les mockups
(convention `{n}-{m}-{Name}.html`).

---

## STEP 5 — Confirmation finale

Si l'agent PO réussit, ajouter le récap final :
```
✅ FEAT {n}-{FeatName} — planification terminée

US générées      : {U} fichiers dans workspace/output/us/
Mockups HTML     : {H} fichiers dans workspace/input/ui/ (ou "aucun")
HTML orphelins   : {O} (à corriger ou retirer)
US sans mockup   : {U-H}

Prochaine étape :
  - (optionnel) déposer/réviser les mockups HTML (workspace/input/ui/{n}-{m}-{Name}.html)
  - /dev-run {n} pour matérialiser le code (arch + db + back + front en parallèle)
  - ou /sdd-full {n} pour pipeline complet
```

Si l'agent échoue, ne rien ajouter (l'ERROR 3 lignes de l'agent suffit).

---

## Règles de cette commande

- Pas de Q/R utilisateur après le STEP 1 (l'agent est autonome)
- Pas de modification de la FEAT parente
- Pas de génération de code (réservé à `/dev-backend`, `/dev-frontend`, `/dev-run`)
- Pas de lecture des mockups HTML ou du stack (réservé aux agents dev-*)
