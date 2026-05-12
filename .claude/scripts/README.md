# Scripts utilitaires SDD_Pro

Deux familles distinctes.

## A. Scripts invoques par les agents/commandes

| Script | Invoque par | Role |
|---|---|---|
| `validate-readiness.ps1` | `/spec-validate` | Gate deterministe SPEC vers US |
| `context-budget.ps1` | agents/commandes | Rend `loader.yml` executable : reads reels, globs bornes, budget, ledger |
| `parse-coverage.ps1` | agent `qa` | Parse coverage multi-stack vers JSON normalise |
| `quality-scan.ps1` | `/qa-generate` | Scan sonar-like, 0 token |
| `validate-fidelity.ps1` | agent `dev-frontend` STEP 11 | Fidelite HTML mockup vers markup genere |
| `detect-capabilities.ps1` | agent `dev-backend` STEP 5.bis | Trigger keywords US vers libs on-demand |
| `mark-breaking-resolved.ps1` | agents `dev-*` post-build | Marque les breaking changes resolus |
| `acquire-libname-lock.ps1` | agents `dev-*` | Lock atomique `{LibName}/.locks/{Entity}.lock` |

## B. Outils humains

Executes manuellement par le Tech Lead pour maintenance/diagnostic.

| Script | Usage |
|---|---|
| `framework-smoke.ps1` | Smoke test coherence interne |
| `measure-batch.ps1` | Agrege tokens consommes par session |
| `validate-libs-catalog.ps1` | Valide tous les `*.libs.json` contre le schema |
| `validate-inline-rules.ps1` | Detecte drift Inline Rules vs `.claude/rules/*.md` |
| `sync-stack-md.ps1 -StackId {id}` | Regenere la section libs du stack `.md` depuis `.libs.json` |
| `compact-front-plans.ps1` | Archive les plans frontend volumineux et les remplace par un contrat court |

Ces scripts ne sont pas charges en contexte LLM par defaut.
