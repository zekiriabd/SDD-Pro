# Scripts utilitaires SDD_Pro

Deux familles distinctes.

## A. Scripts invoqués par les agents/commandes (runtime LLM)

| Script | Invoqué par | Rôle |
|---|---|---|
| `validate-readiness.ps1` | `/spec-validate` | Gate déterministe SPEC → US |
| `parse-coverage.ps1` | agent `qa` | Parse coverage multi-stack → JSON normalisé |
| `quality-scan.ps1` | `/qa-generate` | Scan sonar-like (0 token) |
| `validate-fidelity.ps1` | agent `dev-frontend` STEP 11 | Fidélité HTML mockup → markup généré |
| `detect-capabilities.ps1` | agent `dev-backend` STEP 5.bis | Trigger keywords US → libs §2.4.b |
| `mark-breaking-resolved.ps1` | agents `dev-*` post-build | Marquer BREAKING CHANGES résolu |
| `acquire-libname-lock.ps1` | agents `dev-*` | Lock atomique `{LibName}/.locks/{Entity}.lock` |
| `sdd-clear.ps1` | `/sdd-clear` | Nettoyage destructif des artefacts |

## B. Outils humains (hors Claude Code, non invoqués par agents)

Exécutés manuellement par le Tech Lead pour maintenance/diagnostic.

| Script | Usage |
|---|---|
| `framework-smoke.ps1` | Smoke test cohérence interne (rules, templates, stacks parseables) |
| `measure-batch.ps1` | Agrège tokens consommés par session |
| `validate-libs-catalog.ps1` | Valide tous les `*.libs.json` contre le schéma |
| `validate-inline-rules.ps1` | Détecte drift Inline Rules vs `.claude/rules/*.md` |
| `sync-stack-md.ps1 -StackId {id}` | Régénère §2.4 du stack `.md` depuis `.libs.json` |

Ces 5 scripts ne sont **pas** chargés en contexte LLM — ils n'apparaissent
plus dans CLAUDE.md depuis l'optimisation tokens Phase 1.
