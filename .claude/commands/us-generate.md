# /us-generate — Découpe une SPEC en User Stories

Invoque l'agent PO pour découper une SPEC fonctionnelle en User
Stories structurées (cible 1-3, warning 4-6, hard cap 6) dans `workspace/output/`.

**Usage :** `/us-generate {n}` — où `{n}` est le numéro de la SPEC

---

## STEP 1 — Valider l'argument

L'argument `{n}` est obligatoire et doit être un entier ≥ 1.

Si absent → demander :
```
Quel est le numéro de la SPEC à découper ? (ex. : 1 pour workspace/input/specs/1-Auth.md)
```

Si non numérique → ERROR :
```
ERROR: /us-generate — argument invalide
CAUSE: "{argument}" n'est pas un entier
FIX: relancer /us-generate {n} avec n entier (ex. /us-generate 1)
```

---

## STEP 2 — Vérifier la SPEC existe

Glob `workspace/input/specs/{n}-*.md`.
- 0 fichier → ERROR :
  ```
  ERROR: /us-generate — SPEC introuvable
  CAUSE: aucun fichier workspace/input/specs/{n}-*.md
  FIX: créer la SPEC via /spec-generate ou la déposer manuellement
  ```
- > 1 fichier → ERROR :
  ```
  ERROR: /us-generate — numérotation invalide
  CAUSE: plusieurs fichiers commencent par {n}- dans workspace/input/specs/
  FIX: renommer pour qu'un seul fichier ait le préfixe {n}-
  ```

---

## STEP 3 — Invoquer l'agent PO

Lancer l'agent `po` (défini dans `.claude/agents/po.md`) avec le numéro
`{n}` en argument. L'agent gère le découpage, la traçabilité et l'écriture
des fichiers US dans `workspace/output/`.

Attendre la fin de l'agent. Relayer sa sortie telle quelle (ligne de succès
ou bloc ERROR 3 lignes).

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
✅ SPEC {n}-{SpecName} — planification terminée

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
- Pas de modification de la SPEC parente
- Pas de génération de code (réservé à `/dev-backend`, `/dev-frontend`, `/dev-run`)
- Pas de lecture des mockups HTML ou du stack (réservé aux agents dev-*)
