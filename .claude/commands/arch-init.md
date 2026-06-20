# /arch-init — Bootstrap idempotent (projets vides + scaffolding DB)

> ⚠️ **Commande interne v7.0.0** — invoquée par `/dev-run` STEP 5.
> Utilisateur final : préférer `/sdd-full` ou `/dev-run` (gèrent pré-conditions, idempotence, état).

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

## STEP 2 — Vérifier les blocs `## Active Database` + `## Active Auth Specs`

Lire `workspace/input/stack/stack.md` → récupérer le bloc
`## Active Database` (depuis 2026-05-14, `DatabaseType` n'est plus
dans `## Project Config`).

- Si `## Active Database` absent OU `DatabaseType: none` → SKIP le
  check DB.
- Sinon → vérifier que les 5 clés sont présentes (valeur non vide) :
  `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`. Si une
  seule manque :
  ```
  ERROR: /arch-init — clé(s) DB manquante(s) dans ## Active Database
  CAUSE: clés non définies : {liste}
  FIX: renseigner les valeurs dans workspace/input/stack/stack.md ## Active Database
  ```

Si un stack auth est listé sous `## Active Auth Specs`, vérifier les
clés `AZ_*` (cf. `auth/azure-ad.md §2`). Manquantes → ERROR similaire.

(Les valeurs ne sont jamais affichées par cette commande. La
validation détaillée est aussi faite par `validate_readiness.py` lors
de `/feat-validate`.)

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

## STEP 3.5 — Spawn `constitutioner` si sentinel posé (no-spawn fix, v7.0.0-alpha audit P0-workflow 2026-06-05)

Lire le sentinel `workspace/output/.sys/.state/arch-ready-for-constitutioner.flag`.

| Cas | Action |
|---|---|
| Sentinel absent | skip silencieusement (arch n'a pas eu besoin de Phase D, ex: projet pré-SDD_Pro v3 sans `constitution.md`) |
| Sentinel présent + parseable | spawn `Agent: constitutioner` (cf. ci-dessous) |
| Sentinel présent + corrompu | WARN 1 ligne, skip (non-bloquant — la commande continue) |

### Invocation `constitutioner`

```
Agent: constitutioner
```

Le sous-agent gère :
- Création ADRs (numérotation atomique timestamp, idempotente) par
  dimension active (backend, frontend, UI, auth, database)
- Update `workspace/output/.sys/.context/constitution.md` : §4 stack
  retenu (Edit ligne), §6 index ADRs (append), §1 date
- Régénération `workspace/output/.sys/.context/adrs/INDEX.md`
- Validation read-back v5.0 (anti Edit silencieux)

### Cleanup sentinel

Après que `constitutioner` ait terminé (succès OU échec), supprimer le
sentinel (idempotence du prochain run) :

```bash
rm -f workspace/output/.sys/.state/arch-ready-for-constitutioner.flag
```

**Sortie attendue** :
`constitutioner: {K} ADRs ({existants}+{nouveaux}), §4/§6/INDEX.md OK`.

Sur ERROR `constitutioner` → propager + STOP (l'INDEX ADRs serait
incohérent en aval).

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
- Pas de modification des FEATs, US, mockups HTML.
- Exécutée typiquement **avant** `/dev-run {n}` (intégrée en pré-step
  par `/dev-run` directement — la commande `/arch-init` est utile pour
  le debug ou la pré-init manuelle).
- **Bootstrap + DB en une seule étape** depuis SDD_Pro v2.1 (Sprint 2).
