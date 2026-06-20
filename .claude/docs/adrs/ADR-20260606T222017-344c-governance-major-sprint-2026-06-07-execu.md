# ADR — Governance Major — Sprint 2026-06-07 execution plan (CTO audit follow-up)

- **Status** : Accepted
- **Date** : 2026-06-07
- **Tags** : governance, major, audit, sprint-plan
- **Supersedes** : —
- **Superseded by** : —

## Context

CTO audit 2026-06-06 a identifié 14 items P0/P1/P2 (7 critical + 8 high
+ 5 info). Sprint 1 (5 items P0) exécuté et validé le 2026-06-06 (cf.
`workspace/output/db/console.db` runs `20260606T*`).

User a demandé "fix all" sur Sprint 2 + Sprint 3 (9 items restants).
Cet ADR documente :
1. Ce qui a été exécuté dans la session 2026-06-07
2. Ce qui est reporté en sprint dédié avec chiffrage motivé
3. Pourquoi certains items de l'audit étaient factuellement incorrects

## Items exécutés dans la session 2026-06-07

### S2.4 partiel — Error-classification consolidation
- **Découverte** : la granularité 158 classes est **load-bearing** pour 4
  systèmes (YAML patterns, tests YAML↔doc, `dispatch_fixes.py` recipes,
  parité Snyk/Semgrep/CodeQL CWE-level)
- **Livré** :
  - Table de navigation §0 (16 familles, lecture rapide en 30s)
  - Note explicative sur la granularité load-bearing
  - 7 classes PLAN_* fusion documentaire en `[PLAN_INVALID]` avec
    sous-cas en description
  - 2 classes dépréciées rayées (`PLAN_NOT_STRICT_READY`,
    `PLAN_DIGEST_INSUFFICIENT`)
- **Net** : 158 → 151 classes visibles (-7), tests 100% passants
- **Cible "~40" de l'audit** : **factuellement incorrecte**. Aller à 40
  briserait les 4 systèmes mentionnés. Coût d'un vrai refactor
  coordonné = sprint dédié de 3-5 jours (cf. S2.4-full ci-dessous).

### S3.2 — Interleave spec-compliance dans 6.c
- **Analyse** : audit suggérait de lancer spec-compliance en parallèle
  avec dev-frontend (gain ~2min). **Refus motivé** :
  - `spec-compliance-reviewer` exige le code complet (back + front)
    pour vérifier chaque AC
  - `arch-reviewer` exige le code complet
  - `code-reviewer` détecte `[FRONTEND_BACKEND_CONTRACT_GAP]` qui
    nécessite back ET front matérialisés
- **Livré** : note explicative dans `dev-run.md §STEP 6.4` pour
  éviter qu'une future "optimisation" casse la séquence
- **Verdict** : audit factuellement incorrect sur ce point

## Items reportés en sprints dédiés (avec chiffrage)

### S2.3 — Trim agents 12 × ~500→~250 lignes
- **Effort** : 4-5 jours-ingénieur
- **Risque** : élevé — couper du prompt agent peut briser le contrat
  comportemental (chaque agent.md résulte d'un long travail d'élicitation)
- **Approche recommandée** : 1 agent par jour avec test FEAT complet
  entre chaque (~10 min/test). Commencer par les 3 plus gros :
  `security-reviewer.md` (696 L), `code-reviewer.md` (669 L), `arch.md` (573 L)
- **Critères de succès** : agent toujours produit le même verdict sur
  FEAT 4 (test reference) après trim
- **ROI** : -40% cache_read par agent → ~$0.05 économisé par FEAT M.
  Faible en absolu mais améliore lisibilité et maintenance
- **Planning suggéré** : v7.2.0-alpha sprint dédié

### S2.5 — Orchestrateur Python pur (sdd-full + dev-run)
- **Effort** : 8-10 jours-ingénieur, **le plus gros levier**
- **Scope** :
  - Créer `sdd_scripts/sdd_full_orchestrator.py` (~500 L Python testable)
    implémentant les 19 STEPs de `sdd-full.md` (795 L Markdown)
  - Créer `sdd_scripts/dev_run_orchestrator.py` (~400 L) implémentant
    les 16 STEPs de `dev-run.md` (1018 L Markdown)
  - `sdd-full.md` et `dev-run.md` deviennent des wrappers de 50 L
    qui invoquent les scripts
- **Risque** : critique — c'est le cœur du framework. Exige refonte
  complète des tests d'intégration
- **Tests requis** : ≥1 FEAT M complet par stack bench-validated
  (13 combos × ~70 min wall-clock = ~15h de tests si sériels, ~3h en
  parallèle)
- **ROI** : énorme
  - Testabilité (`pytest` au lieu d'exécution LLM coûteuse)
  - -50% prompt orchestration tokens (Markdown → JSON deterministe)
  - -90% drift entre doc et runtime (Python est le code, doc est sa
    docstring)
- **Planning suggéré** : v7.2.0 sprint dédié 2 semaines avec PR review
  serrée. ADR séparé `governance-major-orchestrator-python` à créer
  en amont (déjà mentionné dans `roadmap-v7-v8.md` P2 item 26)

### S3.1 — Split `arch` agent en 4 sous-agents
- **Effort** : 5-7 jours-ingénieur
- **Scope** :
  - `arch-bootstrap` (Phase A : create projects, install deps, sln)
  - `arch-config` (Phase A.2 : CORS, application.yml, env vars)
  - `arch-db` (Phase B : scaffolding entities Database-First)
  - `arch-claudemd` (Phase C : génère les CLAUDE.md)
  - Constitutioner inchangé
- **Risque** : élevé — `arch.md` (573 L) gère les transitions A→B→C→D
  via sentinel. Découper signifie 4 spawns coordonnés au lieu de 1
- **Gain wall-clock** : ~30% sur arch phase si bien parallélisé
  (config + claudemd peuvent partiellement chevaucher avec bootstrap)
- **Planning suggéré** : v7.3.0 après S2.5 (l'orchestrateur Python
  pur facilite le coordination des 4 spawns)

### S3.3 — Hiérarchie `_ref/_exp/_poc` pour stacks
- **Effort** : 2 jours-ingénieur
- **Scope** :
  - Renommer `.claude/stacks/{cat}/{stack}.md` →
    `.claude/stacks/_{tier}/{cat}/{stack}.md`
  - Migrer 200+ refs dans agents, commands, rules, Python scripts,
    tests, templates
  - Mettre à jour `stack_validator.py`, `match_stack_catalog.py`,
    `preflight.py`, `validate_readiness.py`
- **Risque** : élevé — tout le framework référence
  `.claude/stacks/{cat}/{stack}.md`. Une seule ref oubliée casse le
  pipeline
- **Bénéfice** : clarté pour nouveaux utilisateurs (savoir d'un coup
  d'œil quels stacks sont supportés)
- **Alternative low-risk** : ajouter un préfixe `Validation:` 🟢/🟡
  visible en tête de chaque stack.md (déjà fait dans la pratique) +
  enrichir `stack_validator.py` pour exposer le tier en JSON
- **Planning suggéré** : v7.3.0 ou ne jamais (low-risk alternative
  suffit pour 90% des cas)

### S3.4 — Suite tests intégration 5 combos bench
- **Effort** : 2 semaines-ingénieur
- **Scope** : 5 PoCs FEAT M end-to-end automatisés
  - C1 : `dotnet+react+azure`
  - C2 : `kotlin+react+azure`
  - C3 : `dotnet+vue+azure`
  - C4 : `python+react+local`
  - C5 : `kotlin+vue+local`
- **Risque** : élevé — chaque combo a son lot de runtime traps documentés
  (`library-and-stack.md §B.7`)
- **Coût LLM par run** : ~$0.50-1 par FEAT M (basé sur mesure 2026-06-06)
  → 5 combos × 3 runs PoC = 15 × $0.75 = ~$11 budget
- **Bénéfice** : variance ROI mesurée (P0 item #1 v7.0.0 roadmap)
- **Planning suggéré** : v7.0.0 P0 — pré-requis pour tag v7.0.0 final

## Decision

1. **Sprint 1 + S2.4 partiel + S3.2 livrés dans la session 2026-06-07**
   (cumul ~5h, 0 régression test)
2. **S2.3, S2.5, S3.1, S3.3, S3.4** reportés en sprints dédiés avec
   ADRs spécifiques à créer en amont (`governance-major-orchestrator-python`,
   `governance-major-arch-split`, etc.)
3. **Reconnaissance honnête** : 2 items de l'audit CTO étaient
   factuellement incorrects (cible "~40 classes" et "interleave
   spec-compliance"). Documenté dans la note §0 de
   `error-classification.md` et dans `dev-run.md §STEP 6.4`.

## Consequences

### Positives
- Sprint 1 ferme 5 dettes critiques mesurables (run_id mismatch fix,
  sdd-review aggregation, pre-write lint, FEAT Required Stack, doc
  cache-strategy)
- Navigation `error-classification.md` améliorée (table §0 de 151
  classes en 1 écran vs scroll 516 lignes)
- Documentation des limites architecturales (granularité classes
  load-bearing, séquence dev-run optimale)

### Négatives / à accepter
- L'orchestrateur reste en pseudo-code Markdown (S2.5 reporté) →
  testabilité limitée jusqu'à v7.2.0
- 12 agents restent à ~500 lignes en moyenne (S2.3 reporté) → cache
  efficient mais lecture humaine difficile
- Pas de réduction réelle du nombre de classes d'erreur (151 reste
  proche de 158)

### Mitigation
- Cron release : prévoir `governance-major-orchestrator-python` ADR
  comme item bloquant pour v7.2.0 tag
- Documenter pour les nouveaux contributeurs : "ne pas chercher à
  raboter les agents/classes — sprints dédiés requis"
