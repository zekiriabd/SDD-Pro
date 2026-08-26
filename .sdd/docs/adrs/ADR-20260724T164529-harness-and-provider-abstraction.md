# ADR-20260724T164529-harness-and-provider-abstraction

- **Status**: Accepted
- **History**: Proposed 2026-07-24 (Phase 0.1) → Accepted 2026-07-24, bornes
  elicitor/constitutioner/reverse-inventory/reverse-us-writer arbitrées par le
  Tech Lead. Le verdict du prototype Codex P0.4 sera annexé ici avant clôture
  Phase 0.
- **Date**: 2026-07-24
- **Materialized**: 2026-07-24 — scaffolding `.sdd/` (README, capability-matrix,
  providers/*.yaml, agent-bounds.yaml, model_resolver.py + tests) ; câblage
  runtime NON réalisé (Phases 1-2)
- **Slug**: `harness-and-provider-abstraction`
- **Phase**: gouvernance (migration multi-harnais / multi-provider, Phases 0→5)
- **Relates-to**: `governance-reverse-complexity-ladder` (précédent maison de
  routage de modèle par complexité — généralisé ici en mode `dynamic`),
  `governance-major-config-ssot` (loader.yml SSoT — même philosophie appliquée
  au foyer `.sdd/`)

---

## Context

SDD-Pro v7.0.0 GA est soudé à Claude Code par sa couche de contrôle
(`.claude/` : 25 agents, 40 commandes, 11 rules, 13 skills, 328 refs
lazy-load `@.claude/…`) et par des IDs de modèles Anthropic hardcodés
(7 × `claude-opus-4-8`, 18 × `claude-sonnet-4-6`, + 41 fichiers citant ces
IDs). Le moteur réel est pourtant déjà portable : 331 scripts Python
harness-neutres (0 token), protections effectives = scripts + CI (les hooks
runtime ne sont pas câblés — `settings.json` ne contient que des
`permissions`), 100 scripts passent par le résolveur central
`sdd_lib/paths.py`.

La demande : exécuter SDD-Pro sous d'autres harnais (Codex, Gemini
CLI/Antigravity) ET d'autres providers de modèles (OpenAI, Google,
Moonshot/Kimi), sans dupliquer la substance ni dégrader silencieusement
les protections. Mesures détaillées : plan
`MIGRATION-PLAN-multi-harness-multi-provider.md` §3.

---

## Decision

### D1 — Deux axes orthogonaux

1. **Axe harnais** (où tourne l'orchestration LLM) : `claude-code` |
   `codex` | `antigravity` | `gemini-cli`. Sélection via
   `stack.md ## Active Harness`.
2. **Axe provider** (qui exécute les tokens) : `anthropic` | `openai` |
   `google` | `moonshot`. Sélection via `stack.md ## Active Model Provider`.

Les deux axes sont indépendants et composables (ex. Claude Code pointant
Kimi via `ANTHROPIC_BASE_URL` Anthropic-compat ; Codex pointant Kimi via
`base_url` OpenAI-compat). La matrice machine harnais × mécanismes vit dans
`.sdd/capability-matrix.yml` (SSoT du rapport d'impact).

### D2 — Foyer neutre unique `.sdd/`

- `.sdd/` = **le moteur** (agents, commandes, rules, templates, docs,
  python, skills, invariants, loader, adapters, providers). Seul répertoire
  édité à la main, versionné.
- `.claude/`, `.codex/`, `.gemini/` (+ `CLAUDE.md`/`AGENTS.md`/`GEMINI.md`)
  = **produits de build** émis par `harness_build.py`. En-tête
  `# GENERATED FROM .sdd/ — DO NOT EDIT`, garde CI rejetant tout commit
  les modifiant hors builder.
- Résolution racine par env var `SDD_HOME` (défaut `<repo_root>/.sdd`),
  jamais de symlink (Windows), `paths.py::_looks_like_repo_root()`
  bi-racine (`.sdd/` OU `.claude/`) pendant la transition Phases 1→2.

### D3 — Abstraction `model_tier`

Plus jamais d'ID modèle dans un agent. Chaque agent déclare un
`model_tier ∈ {deep, balanced, fast}` ; le provider actif traduit le tier
en modèle concret via `providers/{p}.yaml → tier_map`. Mapping mesuré au
2026-07-24 : 7 agents deep (dev-backend, dev-frontend, reverse-tech-analyst,
reverse-feat-composer, reverse-ui-extractor, reverse-sql-analyst,
reverse-sql-feat-composer), 18 balanced, 0 fast (tier réservé — levier
coût futur). `pricing.py`, `code_unit_complexity.py`,
`record_token_usage.py` migrent vers cette abstraction (Phase 1.5).

### D4 — Sélection par agent : mode `static | dynamic`

Section `stack.md ## Model Selection` avec `Mode: static` (défaut,
rétrocompatible : absence de section = static) ou `Mode: dynamic` :

- `static` : chaque agent reçoit son `tier_default` fixe (comportement
  actuel préservé).
- `dynamic` : à chaque spawn, un scoreur déterministe (0 token — réutilise
  `complexity_router.py` et `code_unit_complexity.py`) calcule la
  complexité du work-item → niveau `low|medium|high` → tier candidat,
  **borné** par les invariants par agent `tier_floor` / `tier_ceiling`
  (clamp `max(floor, min(candidat, ceiling))`). Bornes déclarées dans
  `.sdd/agent-bounds.yaml` (table §8.bis.7 du plan), non surchargeables
  par le Project Config — seul un commit framework les modifie.
  Chaque décision est persistée
  (`workspace/.sys/.routing/{n}[-{m}]-model-routing.json`).

Le mode `dynamic` reste opt-in et 🟡 UNTESTED jusqu'au premier conformance
run par provider (§10 du plan) ; `static` demeure le défaut GA.

### D5 — Invariant n°14 `harness-parity`

Ajout à `INVARIANTS.yml` : « toute façade committée (`.claude/`, `.codex/`,
`.gemini/`, fichiers mémoire racine) == sortie de `harness_build.py` sur
`.sdd/` HEAD ». Enforcer : golden test `test_harness_identity.py`
(diff octet-à-octet, créé Phase 2.3) — référencé en `planned:` jusqu'à P2.
Un combo harnais × provider non conformance-testé est marqué `UNTESTED`
et exige `SDD_ALLOW_UNTESTED_HARNESS=1` (audit-loggué, symétrique de
`preflight_stack_combo`).

---

## Consequences

**Positifs :**
- Une seule substance éditée (`.sdd/`), N façades générées — fin du risque
  de drift 3× (garde CI + golden test + invariant 14).
- Providers pluggables par YAML : Kimi/OpenAI/Google activables sans
  toucher aux agents ; mixage cross-provider par tier
  (`ModelTierMap: {deep: anthropic, balanced: moonshot, …}`) = levier coût.
- Mode `dynamic` borné = généralisation d'un mécanisme déjà audité et en
  production (module reverse, ADR `governance-reverse-complexity-ladder`),
  0 token, déterministe, auditable.
- Honnêteté contractuelle : rapport d'impact obligatoire par build
  (protections natives/émulées/reportées, niveau A/B/C) — jamais de
  dégradation silencieuse.

**Négatifs / dette acceptée :**
- Migration lourde (66–96 j-h) : move de 331 scripts, réécriture de 233
  littéraux `.claude`, 97 invocations dans les `.md`, extracteur pivot.
- Hors Claude Code : perte des hooks bloquants intra-session, du
  skills auto-trigger et du lazy-load `@` → répliqués en wrapper
  spawn/CI (émulation), coût contexte ↑ (risques R2, R9).
- Fidélité JSON schema-strict des modèles non-Claude à qualifier par
  conformance run avant tout SLA (risque R4) ; IDs/endpoints Moonshot
  « à confirmer » (risque R7).
- Sans les bornes floor/ceiling, le mode `dynamic` pourrait placer un
  reviewer sécurité sur `fast` = régression qualité silencieuse — d'où
  leur statut d'invariant (non surchargeable).

---

## Alternatives considérées

- **Forker `.claude/` par harnais** (copies `.codex/`, `.gemini/` éditées
  à la main) — écartée : drift certain de 3 surfaces × 65 fichiers de
  prompts, corruption SSoT (risque R3 maximal).
- **IDs modèles paramétrés sans tiers** (variable `MODEL_DEV_BACKEND=…`
  par agent) — écartée : 25 variables par provider, aucune sémantique
  (pas de floor/ceiling possible), pricing/télémétrie non factorisables.
- **Routage dynamique sans bornes par agent** — écartée : garde-fou
  non négociable (cf. D4), le cas `security-reviewer → fast` est
  exactement la dérive silencieuse que SDD-Pro proscrit.
- **Réécriture des prompts dans un format pivot riche** (steps structurés
  YAML) — écartée en faveur du choix assumé §4.2 du plan : le body
  markdown reste la substance ; le YAML n'ajoute que les métadonnées de
  transpilation (`model_tier`, `spawns`, `harness_hints`).
- **Symlinks `.claude → .sdd`** — écartée : Windows (repo principal),
  fragile en CI, ne résout pas la transpilation par harnais.

---

## Liens

- Plan source : `MIGRATION-PLAN-multi-harness-multi-provider.md`
  (§2 axes, §4 layout, §5 SDD_HOME, §7 matrice, §8 model_tier,
  §8.bis static/dynamic, §9 phases, §11 risques)
- Matrice machine : `.sdd/capability-matrix.yml`
- Providers : `.sdd/providers/{anthropic,openai,moonshot,google}.yaml`
- Bornes agents : `.sdd/agent-bounds.yaml`
- Résolveur : `.sdd/python/sdd_lib/model_resolver.py` +
  `.sdd/python/tests/test_model_resolver.py`
- Sections stack.md : **appliquées** dans `.sdd/templates/stack.md.template`
  (`## Active Harness`, `## Active Model Provider`, `## Model Selection`).
  L'ancien brouillon `.sdd/stack-sections.proposed.md` a été supprimé par
  l'audit 2026-08-26 : il affirmait encore « proposition, PAS appliquée »
  alors que le template les portait déjà.
- ADR précédent (routage reverse) :
  `.sdd/docs/adrs/ADR-20260629T120000-7c3a-governance-reverse-complexity-ladder.md`
- Prototype go/no-go P0.4 (Codex spawn) : **à réaliser** — verdict à
  annexer ici avant clôture Phase 0
