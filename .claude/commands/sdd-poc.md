# /sdd-poc — Pipeline minimaliste POC (FEAT → arch → back → front)

<!-- @llm-only-flags-file : tous les flags CLI de cette commande slash sont interprétés par Claude. -->

> **Mode POC** — pipeline raccourci pour prototypes, démos, ou exemples.
> **NE PAS utiliser en production.** Cette commande **saute** :
> `/us-generate`, `/feat-validate`, `/dev-plan` (sauf opt-in), API Gate,
> `/qa-generate`, `/sdd-review`.
>
> v7.0.0-alpha (audit MAJ-2, 2026-06-04) — refactor « thin wrapper » :
> 330 L → ~140 L. Les STEPs `arch`/`dev-backend`/`dev-frontend` qui
> dupliquaient `/sdd-full` sont désormais de simples `@-ref` vers les
> agents canoniques. Sémantique préservée byte-for-byte.

Enchaîne uniquement les phases strictement nécessaires :

```
PHASE 1 — Pseudo-US        (script feat_to_pseudo_us.py, déterministe)
PHASE 2 — Plans (opt-in)   (--with-plans → /dev-plan en mode :plan)
PHASE 3 — Bootstrap + DB   (/arch-init, idempotent)
PHASE 4 — Backend code     (agent dev-backend sur {n}-1)
PHASE 5 — Frontend code    (agent dev-frontend sur {n}-1, SANS API Gate)
PHASE 6 — Verdict POC      (bannière "ne pas déployer en prod")
```

**Délégation pure** : aucun agent invoqué directement (chaîne
`feat_to_pseudo_us.py` → `/arch-init` → `dev-backend` → `dev-frontend`).

**Migration POC → standard** : `/us-generate {n} --replace-pseudo` puis
`/sdd-full {n}` (idempotent : skip arch, augmente, ajoute QA + review).

---

## Utilisation

```
/sdd-poc {n}                  # mode POC standard (plans inline)
/sdd-poc {n} --with-plans     # opt-in plans externalisés .back.md/.front.md
/sdd-poc {n} --force          # écrase une US réelle existante
```

Flags combinables. Si tu veux strict prod-ready → `/sdd-full {n}`.

> `/arch-init` est idempotent par construction (skip silencieux si stable).
> Pour forcer un re-bootstrap, supprimer manuellement `workspace/output/src/`
> + `workspace/output/db/` puis relancer `/sdd-poc {n}`.

---

## STEP 1 — Argument + flags

Argument **obligatoire** : `{n}` (entier ≥ 1). Absent → demander. Non
numérique → ERROR `[INVALID_ARG]` (cf. `error-classification.md §1.2`).

Stocker `$force`, `$with_plans` (booléens, présence des flags).

---

## STEP 2 — Vérifier la FEAT + détecter US réelles existantes (M8 closure)

### 2.1 FEAT existence

Glob `workspace/input/feats/{n}-*.md` :
- 0 → ERROR `[FEAT_NOT_FOUND]` (créer via `/feat-generate`)
- > 1 → ERROR `[FEAT_AMBIGUOUS]` (renommer)
- 1 → OK, stocker `{FeatName}`

### 2.2 US réelles existantes — guard anti-écrasement (audit M8 closure 2026-06-07)

Avant d'invoquer `feat_to_pseudo_us.py`, détecter si des US **réelles** (générées par `po` via `/us-generate` ou `/sdd-full`) existent déjà sous `workspace/output/us/{n}-*.md`. Distinguer pseudo-US vs réelles par le frontmatter `Status: Pseudo` (ajouté par `feat_to_pseudo_us.py`) :

```bash
REAL_US=$(grep -L "Status: Pseudo" workspace/output/us/{n}-*.md 2>/dev/null | head -5)
PSEUDO_US=$(grep -l "Status: Pseudo" workspace/output/us/{n}-*.md 2>/dev/null | head -5)

if [ -n "$REAL_US" ] && [ "$force" != "true" ]; then
  cat <<EOF >&2
ERROR: /sdd-poc {n} — US réelles existantes détectées (non-Pseudo)
CAUSE: [POC_OVERWRITE_REAL_US] $REAL_US a été généré par /us-generate (po agent),
       pas par /sdd-poc. Lancer /sdd-poc --force écraserait du travail PO légitime.
FIX: 1. Lancer /sdd-full {n} (pipeline complet avec ces US réelles)
     2. OU déplacer/archiver les US réelles puis relancer /sdd-poc
     3. OU passer --force EN CONNAISSANCE DE CAUSE (US réelles archivées
        en workspace/output/.sys/.archive/us-{TS}/ avant écrasement)
EOF
  exit 1
fi

# Si --force ET REAL_US présents : archiver avant écrasement
if [ -n "$REAL_US" ] && [ "$force" = "true" ]; then
  ARCHIVE_DIR="workspace/output/.sys/.archive/us-$(date -u +%Y%m%dT%H%M%S)"
  mkdir -p "$ARCHIVE_DIR"
  echo "$REAL_US" | xargs -I{} mv {} "$ARCHIVE_DIR/"
  echo "[POC/WARN] {n} — $(echo "$REAL_US" | wc -l) US réelles archivées en $ARCHIVE_DIR avant écrasement. (3%)" >&2
fi
```

Symétrie : `feat_to_pseudo_us.py --force` archive maintenant **aussi** côté script (defense-in-depth). Le bloc shell ci-dessus s'exécute **avant** l'invocation script, le script protège **a posteriori**.

Émettre : `[ANALYSIS] FEAT {n}-{FeatName} — pipeline POC démarré. (2%)`

---

## STEP 3 — Bannière d'avertissement POC (LOAD-BEARING)

**Émettre obligatoirement** :
```
⚠️ Mode POC — pas de QA, pas de tests, pas de review. NE PAS déployer en prod.
```

Cette ligne protège l'utilisateur contre l'oubli du mode dans lequel il
tourne. **Ne jamais la supprimer ou la condenser.**

---

## STEP 4 — Générer la pseudo-US

```bash
python .claude/python/sdd_scripts/feat_to_pseudo_us.py \
  --feat-number {n} {--force si $force} --json
```

| Exit | Sens | Action |
|---|---|---|
| `0` SUCCESS | pseudo-US écrite ou déjà à jour | parser stdout JSON → `us_name`, continuer STEP 5 |
| `1` FAIL_FAST | FEAT introuvable/ambiguë OU US réelle existante sans `--force` | STOP, propager ERROR |
| `3` INFRA_BLOCKED | erreur écriture, permission denied | STOP, propager ERROR |

Stocker `$us_name`, `$us_id = "{n}-1"`. Émettre :
`[PO] Pseudo-US {n}-1-{us_name} générée (POC mode). (10%)`

---

## STEP 4.5 — Plans techniques (opt-in `--with-plans`)

**Skip silencieux** si `$with_plans = false`.

Sinon, exécuter `/dev-plan {n}` (mode `:plan`, PLAN_ONLY=true) — produit
`workspace/output/plans/{n}-1-{us_name}.{back|front}.md` puis STOP avant
génération code. **Pas de checkpoint humain** (contrairement à
`/sdd-full --plan`). Cf. `commands/dev-plan.md` pour le détail.

Les agents dev-* en STEP 6/7 détectent automatiquement les plans
(cf. `dev-shared-preflight.md §3` mode From Plan).

Émettre : `[PLAN] Plans écrits → workspace/output/plans/. (18%)`

---

## STEP 5 — Bootstrap (`/arch-init`)

Exécuter intégralement `/arch-init` (idempotent — skip silencieux si
projets + DB déjà à jour). Détail : `@.claude/commands/arch-init.md`.

Émettre selon résultat :
- Succès : `[ARCH] Bootstrap projets + DB terminés. (32%)`
- Idempotent skip : `[ARCH/SKIP] Bootstrap déjà en place. (32%)`
- ERROR → propager + STOP

---

## STEP 6 — Backend (`dev-backend` sur la pseudo-US)

Invoquer l'agent `dev-backend` avec `{n}-1`. Substance complète :
`@.claude/agents/dev-backend.md` (lecture US, plan inline ou From Plan
selon STEP 4.5, build loop, idempotence).

**Spécificité POC** : pseudo-US sans `## Dependencies` (toujours `NONE`)
→ 1 seule invocation, pas de batching parallèle.

| Sortie | Action |
|---|---|
| Succès code généré | continuer STEP 7 |
| Succès skipped (frontend-only) | continuer + WARN 1 ligne |
| ERROR | propager + STOP (pas de retry au-delà du build_loop interne) |

Émettre : `[DEV-BACKEND] Code backend {n}-1 livré, build vert. (66%)`

---

## STEP 7 — Frontend (`dev-frontend`, SANS API Gate)

> **Différence majeure vs `/dev-run`** : aucun API Gate in-memory n'est
> exécuté entre backend et frontend. Le mode POC accepte que le
> contrat back↔front puisse être désynchronisé sans signal runtime.
> Pour cette vérification → `/sdd-full {n}`.

Invoquer l'agent `dev-frontend` avec `{n}-1`. Substance complète :
`@.claude/agents/dev-frontend.md`. Le mockup HTML est auto-copié par
`feat_to_pseudo_us.py` depuis `{n}-{FeatName}.html` si présent.

| Sortie | Action |
|---|---|
| Succès code généré | continuer STEP 8 |
| Succès skipped (backend-only) | continuer + WARN 1 ligne |
| ERROR | propager + STOP |

Émettre : `[DEV-FRONTEND] Code frontend {n}-1 livré, build vert. (90%)`

---

## STEP 8 — Verdict POC (LOAD-BEARING bannière finale)

Émettre **un seul bloc final** :

```
[DONE/POC] FEAT {n}-{FeatName} livrée en mode POC. (100%)

⚠️ POC mode — pas de tests, pas de review, pas d'API Gate.
   NE PAS déployer en prod sans repasser par /sdd-full {n}.

Pour passer en granularité fine :
  1. /us-generate {n} --replace-pseudo   (remplace pseudo-US par 1-N vraies US)
  2. /sdd-full {n}                       (pipeline standard avec QA + review)

Pour explorer le code :
  - workspace/output/src/                (backend + frontend générés)
  - /sdd-serve                           (lance backend + frontend + console)
```

Si une phase a `[…/SKIP]` ou `[…/WARN]` → inclure 1 ligne par phase
dans le récap. Si une phase a `FAIL` → verdict final `[DONE/FAIL]`
avec préfixe `[CLASS]` préservé (cf. `error-classification.md §1`).

---

## Différences vs `/sdd-full`

| Phase | `/sdd-full` | `/sdd-poc` (default) | `/sdd-poc --with-plans` |
|---|:---:|:---:|:---:|
| `/us-generate` | ✅ | ❌ (pseudo-US auto) | ❌ (pseudo-US auto) |
| `/feat-validate` | ✅ | ❌ | ❌ |
| `/dev-plan` | conditionnel + review | ❌ (plan inline) | ✅ (sans review) |
| Bootstrap + DB | ✅ | ✅ | ✅ |
| `dev-backend` | ✅ (ALL US, parallèle) | ✅ (1 pseudo-US) | ✅ (From-Plan) |
| **API Gate in-memory** | ✅ | ❌ | ❌ |
| `dev-frontend` | ✅ (ALL US, parallèle) | ✅ (1 pseudo-US) | ✅ (From-Plan) |
| `/qa-generate` | ✅ (conditionnel) | ❌ | ❌ |
| `/sdd-review` | ✅ (default) | ❌ | ❌ |

---

## Règles de cette commande

- **Délégation pure** : aucun agent invoqué directement.
- **Idempotente** : relancer écrase la pseudo-US (si auto-générée) et
  re-lance dev-* (idempotents par contrat agent).
- **Pas de Q/R utilisateur** après STEP 1.
- **Bannières POC obligatoires** au STEP 3 et STEP 8 (load-bearing
  safety — supprimer l'une = violation).
- **Aucun gate** : pas de plan-review, readiness, API Gate, QA, sdd-review.
- **Pas d'audit log** : `/sdd-poc` n'est pas un bypass de gate (comme
  `--force`) — c'est un **profile** distinct, choisi explicitement.

---

## Chat Output Protocol

Applique `@.claude/rules/output-protocol.md`. Labels canoniques :
`[ANALYSIS]`, `[PO]`, `[PLAN]` (seulement si `--with-plans`), `[ARCH]`,
`[DEV-BACKEND]`, `[DEV-FRONTEND]`, `[DONE/POC]` (variante `[DONE]`
spécifique POC — signale visuellement le mode). Granularité 5-7 updates
totaux. Bannières STEP 3 et STEP 8 obligatoires (non comptées dans la
limite). Bypass `SDD_CHAT_VERBOSE=1` (§10).
