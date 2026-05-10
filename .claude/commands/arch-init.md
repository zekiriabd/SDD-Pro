# /arch-init — Bootstrap idempotent (projets vides + scaffolding DB)

Invoque l'agent `arch` pour préparer l'**ossature complète** du projet
à partir des stacks actifs :

- **Phase A** : création de la solution, des projets vides, des
  références inter-projets, et installation des dépendances racine
- **Phase B** : si `DatabaseType ≠ none`, introspection READ-ONLY de
  la base + scaffolding Database-First (entities + DbContext)

**Idempotent** : relancer la commande ne casse rien — les projets
déjà initialisés sont skippés. Le scaffolding DB `--force` est
incrémental.

**Usage :** `/arch-init` (aucun argument).

---

## STEP 1 — Vérifier le stack

Vérifier que `workspace/input/stack/stack.md` existe et contient au moins une
entrée non commentée sous `## Active Tech Specs`.

Si absent ou vide →
```
ERROR: /arch-init — stack non sélectionné
CAUSE: workspace/input/stack/stack.md manque ou ## Active Tech Specs vide
FIX: créer workspace/input/stack/stack.md et activer au moins un backend ou frontend
```

---

## STEP 2 — Vérifier les env vars DB (si applicable)

Lire `workspace/input/stack/stack.md` → récupérer `DatabaseType` du
`## Project Config`.

- Si `DatabaseType: none` ou absent → SKIP le check env vars
- Sinon → vérifier que les 5 variables sont définies : `DB_HOST`,
  `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`. Si une seule manque :
  ```
  ERROR: /arch-init — variable(s) d'environnement DB manquante(s)
  CAUSE: variables non définies : {liste}
  FIX: définir les variables avant de relancer (ex. PowerShell : $env:DB_HOST="...")
  ```

(Les valeurs ne sont jamais affichées par cette commande.)

---

## STEP 3 — Invoquer l'agent arch

Lancer l'agent `arch` (défini dans `.claude/agents/arch.md`). L'agent
gère :
- la lecture sélective du stack actif et des Init Commands §2.2.1
- la détection d'idempotence (projet déjà présent → skip)
- l'exécution des Init Commands de chaque stack à initialiser
- la création de la solution `.sln` si stacks .NET multiples
- le build de validation (exit 0 obligatoire)
- (si `DatabaseType ≠ none`) l'introspection DB + le scaffolding
  Database-First (entities + DbContext)

Attendre la fin de l'agent. Relayer sa sortie telle quelle.

---

## STEP 4 — Confirmation finale

Si l'agent réussit, ajouter UNE SEULE ligne après sa sortie :
```
Prochaine étape : /dev-run {n} pour générer le code (back + front en parallèle).
```

Si l'agent échoue, ne rien ajouter.

---

## Règles de cette commande

- **Idempotent** — relancer ne casse rien.
- Pas de Q/R utilisateur.
- Pas de génération de code applicatif (responsabilité des agents
  dev-backend / dev-frontend).
- Pas de modification des SPECs, US, mockups HTML.
- Exécutée typiquement **avant** `/dev-run {n}` (intégrée en pré-step
  par `/dev-run` directement — la commande `/arch-init` est utile pour
  le debug ou la pré-init manuelle).
- **Bootstrap + DB en une seule étape** depuis SDD_Pro v2.1 (Sprint 2).
