# /feat-deepen — Élicitation structurée d'une FEAT

Enrichit une FEAT fonctionnelle existante via 5 techniques d'élicitation
avancée (Pre-mortem, First Principles, Red Team, Stakeholder Mapping,
Inversion). Délègue à l'agent `elicitor`.

**Usage :**
- `/feat-deepen {n}` — mode interactif (5×1-2 questions ciblées)
- `/feat-deepen {n} --quick` — mode one-shot (inférence depuis FEAT)

**Quand l'utiliser ?**
- Après `/feat-generate` pour les features complexes ou critiques
- AVANT `/us-generate` pour maximiser la qualité des US générées
- Optionnel : SDD_Pro fonctionne sans, mais les ACs et le code généré
  sont moins robustes pour les edge cases.

**Hors scope** : ne génère PAS de code, ne modifie PAS les US.
Enrichit uniquement la FEAT parente + constitution §7 (P3 strict).

---

## STEP 1 — Valider l'argument

Argument **obligatoire** : `{n}` (entier ≥ 1).

Si absent → demander :
```
Quelle FEAT veux-tu approfondir ? (numéro, ex. : 1)
```

Si non numérique →
```
ERROR: /feat-deepen — argument invalide
CAUSE: "{argument}" n'est pas un entier
FIX: relancer /feat-deepen {n}
```

Détecter le flag `--quick` dans les arguments. Stocker `quick = true|false`.

---

## STEP 2 — Vérifier la FEAT

Glob `workspace/input/feats/{n}-*.md`.

- 0 fichier → ERROR :
  ```
  ERROR: /feat-deepen — FEAT introuvable
  CAUSE: aucun fichier workspace/input/feats/{n}-*.md
  FIX: créer la FEAT via /feat-generate avant
  ```
- > 1 fichier → ERROR (numérotation invalide).

Émettre 1 ligne :
```
FEAT {n}-{FeatName} — élicitation {interactive|one-shot} démarrée
```

---

## STEP 3 — Avertissement utilisateur (mode interactif uniquement)

Si `quick == false` :
```
🔍 /feat-deepen {n}-{FeatName} — mode interactif

5 techniques d'élicitation vont être appliquées en séquence :
  1. Pre-mortem (risques projet)
  2. First Principles (hypothèses implicites)
  3. Red Team (edge cases)
  4. Stakeholder Mapping (RACI)
  5. Inversion (modes de défaillance)

Chaque technique posera 1-2 questions ciblées (~10 questions au total).
Tu peux répondre "passer" pour skip une technique, ou "je ne sais pas"
pour qu'on infère ensemble.

Continuer ? (oui / annuler)
```

Si annulation → STOP propre.

---

## STEP 4 — Déléguer à l'agent `elicitor`

Invoquer l'agent `elicitor` avec :
- Argument : `{n}`
- Mode : `quick` ou `interactive`

L'agent gère :
- Les 5 techniques (interactive ou one-shot)
- L'écriture des 5 sections en fin de FEAT
- La mise à jour de `workspace/output/.sys/.context/constitution.md` §7

L'agent émet son propre récap à la fin (STEP 11 de l'agent).

---

## STEP 5 — Confirmation

Si l'agent termine avec succès → ne rien afficher de plus (le récap
de l'agent suffit).

Si l'agent ERROR → propager l'ERROR telle quelle et STOP.

---

## Règles de cette commande

- **Idempotente** : relancer `/feat-deepen {n}` re-déclenche
  l'élicitation. L'agent gère le cas "sections déjà présentes" en
  proposant écraser / annuler / étendre.
- **Optionnel dans le pipeline** : pas invoqué automatiquement par
  `/sdd-full` ni `/us-generate`. À déclencher manuellement par le PO
  humain quand pertinent.
- **Append-only sur la FEAT** : ne modifie JAMAIS les sections
  existantes (`## Functional Needs`, `## Business Rules`, etc.).
  Seules les 5 sections enrichies sont ajoutées en fin de fichier.
- **Pas de génération de code** : strictement P3 (élicitation pure).
