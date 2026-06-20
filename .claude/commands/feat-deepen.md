# /feat-deepen — Élicitation structurée d'une FEAT

<!-- @llm-only-flags-file : tous les flags CLI de cette commande slash sont interprétés par Claude (pas par un argparse Python). -->

> ⚠️ **Commande interne v7.0.0** — invocation manuelle ou via `/feat-generate --deepen`.
> Sera fusionné dans `/feat-generate` post-v7.0.0. Préférer `/sdd-full` ou `/dev-run` en usage normal.

Enrichit une FEAT fonctionnelle existante via une **bibliothèque de
15 techniques d'élicitation** (`@.claude/docs/brainstorming-techniques.md`,
emprunt BMad v7.0.0+). L'agent `elicitor` détecte le contexte de la
FEAT (compliance ? B2C ? IA ? incident ?) et recommande 2-3 techniques
adaptées au lieu d'appliquer mécaniquement les 5 historiques.

**5 techniques historiques (v6.x défaut)** : Pre-mortem, First
Principles, Red Team, Stakeholder Mapping, Inversion.
**Nouvelles v7.0.0+ (10 disponibles)** : SCAMPER, Reverse Brainstorming,
5 Whys, Customer Journey Mapping, Empathy Map, Crazy 8s, Six Thinking
Hats, Cynefin, OKR Decomposition, Lotus Blossom.

**Usage :**
- `/feat-deepen {n}` — mode interactif (agent choisit 2-3 techniques)
- `/feat-deepen {n} --quick` — mode one-shot, 3 techniques par défaut (§1+§3+§5)
- `/feat-deepen {n} --techniques scamper,empathy` — forcer techniques (futur v7.1+)

**Quand l'utiliser ?**
- Après `/feat-generate` pour les features complexes ou critiques
- AVANT `/us-generate` pour maximiser la qualité des US générées
- Optionnel : SDD_Pro fonctionne sans, mais les ACs et le code généré
  sont moins robustes pour les edge cases.

**Hors scope** : ne génère PAS de code, ne modifie PAS les US.
Enrichit uniquement la FEAT parente + constitution §7 (P3 strict).

---

## STEP 0.7 — Parser les flags via le wrapper Python (v7.0.0+ audit P3 D)

**Recommandé** : avant de parser manuellement les arguments, invoquer
le wrapper déterministe qui valide les 15 noms de techniques canoniques :

```bash
echo "{raw user input string}" | python -m sdd_scripts.elicitor_args
# Sortie : workspace/output/.sys/.state/elicitor-{n}.args.json
# stdout : JSON parsé avec techniques résolues (mode + liste finale)
```

Le wrapper :
- Valide `--quick`, `--legacy-5`, `--techniques nom1,nom2[,...]`
- Vérifie les 15 noms canoniques + 6 alias (`scamper`, `empathy-map`, `5-whys`/`five-whys`, etc.)
- Applique la mutual exclusion `--legacy-5` ↔ `--techniques`
- Borne max 5 techniques (fatigue cognitive)
- Résout le `mode` final : `legacy-5` | `explicit` | `quick-default` | `interactive-context-detected`

| Exit | Action |
|---|---|
| `0 SUCCESS` | Lire `.args.json`, l'agent elicitor consomme `techniques` directement |
| `1 FAIL_FAST` | FEAT absent OU technique name inconnu → STOP + ERROR `[INVALID_ARG]` |
| `2 CORRECTIBLE` | `--legacy-5 + --techniques` → STOP + propager stderr |
| `3 INFRA_BLOCKED` | Disk write failure → STOP |

**Fallback legacy** : si le wrapper n'est pas invoqué, l'agent elicitor
parse les flags lui-même via interprétation LLM (cf. marqueur
`@llm-only-flags-file` en tête de fichier).

---

## STEP 1 — Valider l'argument

> Si STEP 0.7 a été exécuté, les valeurs des flags viennent de
> `workspace/output/.sys/.state/elicitor-{n}.args.json` (déterministe).
> Sinon, parsing LLM legacy.

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
🔍 /feat-deepen {n}-{FeatName} — mode interactif (bibliothèque 15 techniques)

L'agent va analyser ta FEAT et recommander 2-3 techniques adaptées à
son contexte (compliance, B2C, IA, incident, etc.). Tu valides la
sélection avant de répondre aux questions.

Bibliothèque complète : @.claude/docs/brainstorming-techniques.md
Catégories : Risques (4) · Hypothèses (2) · Acteurs (3) · Idéation (4) · Décision (2)

Tu peux répondre "passer" pour skip une technique, ou "je ne sais pas"
pour qu'on infère ensemble.

Continuer ? (oui / annuler / choisir manuellement les techniques)
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
