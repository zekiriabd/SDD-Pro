# /sdd-bootstrap — Initialisation d'un projet SDD_Pro (greenfield)

Bootstrap interactif d'un nouveau projet SDD_Pro : génère
`workspace/input/stack/stack.md` à partir du template, crée le squelette
`workspace/` (`feats/`, `ui/`, `output/.sys/`, etc.), installe les
dépendances Python du framework, et lance un smoke check final.

**Usage :** `/sdd-bootstrap [--combo c1|c2|custom] [--dry-run] [--skip-install] [--force]`

**Quand l'utiliser** :
- **Greenfield** : repo cloné depuis GitHub Template SDD_Pro, aucun
  `workspace/input/stack/stack.md` encore généré.
- **Re-init** : repo déjà initialisé mais on souhaite repartir de zéro
  (passe `--force` après confirmation).

**Quand NE PAS l'utiliser** :
- Repo **brownfield** existant avec code historique → préférer
  `/sdd-discover-stack` qui scanne les manifests existants et produit
  un `stack.md.candidate` à arbitrer.

---

## STEP 1 — Détection préalable

L'opération `bootstrap.py` est **interactive** (Python `input()`) et ne
peut pas tourner depuis un sub-agent Claude. Cette commande informe
l'utilisateur de la marche à suivre + valide les prérequis lisibles.

Pré-checks (déterministes, 0 token) :

1. `bootstrap.py` existe à la racine du repo (`Glob bootstrap.py`)
2. `.claude/templates/stack.md.template` existe
3. Python 3.10+ disponible (`python --version`)

Si l'un échoue → STOP + ERROR :
```
ERROR: /sdd-bootstrap — prerequis manquant
CAUSE: [INFRA_BLOCKED] {detail}
FIX: cloner le repo depuis GitHub Template SDD_Pro (intact), verifier Python 3.10+
```

---

## STEP 2 — Détection état projet

Glob `workspace/input/feats/*.md` et test `workspace/input/stack/stack.md` :

| État | Conditions | Action |
|---|---|---|
| **greenfield** | aucun stack.md, aucune FEAT | informer l'utilisateur, propose `python bootstrap.py` |
| **partial** | stack.md absent, mais FEATs présentes | WARN incoherence — informer puis propose `--force` |
| **initialisé** | stack.md ≥ 100 octets ET pas de `{{` | informer "deja initialise", propose `/feat-generate` ou `--force` |
| **template brut** | stack.md contient des `{{Placeholder}}` | informer "template non rendu", propose `python bootstrap.py --force` |

---

## STEP 3 — Sortie utilisateur (1 ligne par cas)

**Cas greenfield** :
```
[BOOTSTRAP] Projet vierge detecte. Lancer dans un terminal :
    python bootstrap.py [--combo c1|c2|custom]

  Combo recommande :
    c1 = .NET Minimal API + React + shadcn + Azure AD (defaut)
    c2 = Kotlin Spring Boot + React + shadcn + Azure AD

  Options :
    --combo c1|c2|custom   skip la question stack (preset)
    --dry-run              affiche actions sans ecrire
    --skip-install         passe pip/npm install (CI)
    --force                overwrite workspace/input/ existant

  Apres bootstrap : /feat-generate {Name} puis /sdd-full 1
```

**Cas initialisé** :
```
[BOOTSTRAP] Projet deja initialise (workspace/input/stack/stack.md present).
Prochaine etape : /feat-generate {Name}
Pour repartir de zero : python bootstrap.py --force
```

**Cas template brut** :
```
[BOOTSTRAP] stack.md contient des placeholders {{...}} non substitues.
Lancer : python bootstrap.py --force
(le template a ete copie tel quel sans rendu — bootstrap fait la substitution)
```

---

## STEP 4 — Anti-derive

- Cette commande **ne lance jamais** `bootstrap.py` directement (pas de
  `Bash python bootstrap.py`) — il est interactif et nécessite l'input
  terminal de l'utilisateur, pas du sub-agent.
- Cette commande **ne touche jamais** à `workspace/input/stack/stack.md`
  ni au reste du `workspace/`. C'est `bootstrap.py` (lancé par
  l'utilisateur depuis son terminal) qui écrit.
- Read-only stricte côté framework.

---

## STEP 5 — Lien avec autres commandes

- **Pré-requis pour** : `/feat-generate`, `/sdd-full`, `/dev-run`,
  `/qa-generate`, `/feat-validate`, `/sdd-status`, `/sdd-review`,
  `/sdd-serve` — toutes ces commandes émettent
  `[STACK_MISSING]` ou `[STACK_MALFORMED]` si `bootstrap.py` n'a pas
  tourné.
- **Alternative brownfield** : `/sdd-discover-stack --scope .` scanne
  un repo existant (manifests, package.json, .csproj, pom.xml) et
  produit `stack.md.candidate`. Le Tech Lead arbitre puis renomme.

---

## STEP 6 — Documentation référencée

- `bootstrap.py` (racine repo) — script Python, ~600 lignes, stdlib only
- `.claude/templates/stack.md.template` — template source
- `.claude/CLAUDE.md §9` — démarrage rapide (mentionne Step 0)
- `.claude/docs/quickstart.md` — walkthrough complet
