# Règle — Dev-shared preflight (STEP 0/0.5/1/1.bis cross-agent, v7.0.0)

> **v7.0.0 hoist** : les STEP 0 (preflight script-driven), STEP 0.5
> (context budget), STEP 1 (mode From Plan), STEP 1.bis (path safety)
> étaient inlinés à l'identique dans `agents/dev-backend.md` et
> `agents/dev-frontend.md` (~50 lignes × 2). Substance hoistée ici ;
> les agents référencent par `@.claude/rules/dev-shared-preflight.md`
> et ne spécifient que les paramètres asymétriques (family, codes
> family-specific). Source de vérité unique pour évolutions futures.

## TOC

- §1 — STEP 0 HARD-GATE pre-flight (script `preflight.py`)
- §2 — STEP 0.5 HARD-GATE context budget
- §3 — STEP 1 Détection mode From Plan
- §4 — STEP 1.bis Hard-gate path safety (Front/Back isolation)
- §5 — Matrice paramètres par famille
- §6 — Enforcement (référence depuis agents dev-backend/dev-frontend)

---

## 1. STEP 0 — HARD-GATE pre-flight (script-driven, v6.1)

Invoquer `preflight.py` qui retourne JSON sur stdout :

```bash
python .claude/python/sdd_scripts/preflight.py --family {family} --arg "{n}-{m}[:plan]"
```

**Comportement** :
- Exit 0 + `ok:true` → préconditions A* + B* vertes. Variables JSON
  disponibles en mémoire pour la suite : `planOnly`, `name`,
  `appOrBackendName`, `activeStacks.{backend,frontend,uiDs,auth}`
  (+ `htmlPath` côté frontend). **Procéder à STEP 1**.
- Exit 1 + `ok:false` → STOP + ERROR 3-lignes pour la **première**
  entrée de `errors[]` (code + hint). Format :
  ```
  ERROR: {agent} {n}-{m} — preflight {code}
  CAUSE: [{code}] {détail extrait du JSON}
  FIX: {hint}
  ```

**Codes communs** : `INVALID_ARG`, `US_NOT_FOUND`, `US_AMBIGUOUS`,
`STACK_MISSING`, `STACK_NOT_SELECTED`, `STACK_MALFORMED`,
`STACK_DIGEST_MISSING`, `PROJECT_NOT_INIT` (dégradé en
`PROJECT_NOT_INIT_WARN` non bloquant en mode `:plan`).

**Codes family-specific** : cf. §5.

Le script remplace les checks A1-A* + B1-B* inlinés ; aucun Glob ni
Read manuel à effectuer ici. Détail :
`.claude/python/sdd_scripts/preflight.py`.

---

## 2. STEP 0.5 — HARD-GATE context budget

Pattern partagé — appliquer `@.claude/rules/build-and-loop.md §1`
avec `--agent {agent-id}` (cf. §5 mapping).

Exit non-zero → STOP. Ledger persisté dans `console.db` table
`context_budget` (SSoT v6.10).

---

## 3. STEP 1 — Détection mode From Plan

Pattern partagé — appliquer `@.claude/rules/build-and-loop.md §1.ter`
ligne `{agent-id}` de la matrice. Glob spécifique par famille
(cf. §5).

Variables résultantes en mémoire : `FROM_PLAN_PATH` (string|null),
`PLAN_ONLY` (bool, déjà set par STEP 0).

Côté frontend uniquement : mode Normal inclut le **fidelity check**
post-build (STEP 11 de `dev-frontend.md`).

---

## 4. STEP 1.bis — Hard-gate path safety (Front/Back isolation)

Pattern partagé — appliquer `@.claude/rules/build-and-loop.md §1.bis`
ligne `{agent-id}` de la matrice. Bloquant avant tout Write/Edit sous
`workspace/output/src/`.

Violation → STOP + ERROR `[FILE_OWNERSHIP_NESTED]`.

---

## 5. Matrice paramètres par famille

| Paramètre | `dev-backend` | `dev-frontend` |
|---|---|---|
| `--family` (preflight.py) | `backend` | `frontend` |
| `--agent` (context_budget.py) | `dev-backend` | `dev-frontend` |
| Glob mode From Plan | `*.back.md` | `*.front.md` |
| Codes preflight extra | (aucun) | `HTML_AMBIGUOUS`, `UI_DS_NOT_SELECTED` (si `htmlPath != null` sans `ui-*` actif) |
| Variables JSON extra | (aucune) | `htmlPath` (peut être `null`) |
| Path safety (root autorisé) | `workspace/output/src/{BackendName}/` | `workspace/output/src/{AppName}/` |
| Mode Normal post-1 | génération code + build | génération code + build + **fidelity check** |

---

## 6. Enforcement

- **`dev-backend.md`** et **`dev-frontend.md`** référencent cette
  règle dans leurs STEP 0–1.bis (≤ 4 lignes par STEP). Aucune
  duplication.
- Toute évolution du flux preflight/context-budget/from-plan/path-
  safety se fait **ici d'abord**. Les agents n'ajoutent que les
  asymétries family-specific (cf. §5).
- Coût lecture : ~2 KB par invocation dev-* (chargé en bloc avec
  `build-and-loop.md` au STEP 3 contexte).
