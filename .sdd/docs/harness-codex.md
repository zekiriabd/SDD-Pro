# SDD_Pro — Harnais Codex (OpenAI CLI)

> Document d'honnêteté (Phase 3.6 du plan
> `MIGRATION-PLAN-multi-harness-multi-provider.md`). Décrit **ce qui est
> gagné, ce qui est perdu et ce qui est émulé** en passant de Claude Code
> à Codex. Aucun contenu marketing — la matrice `.sdd/capability-matrix.yml`
> est la SSoT machine ; ce fichier en est la lecture Tech Lead.

## 1. Statut (2026-07-25)

| Dimension | Valeur |
|---|---|
| Niveau de protection | **B** (référence claude-code/anthropic = A) |
| Combo qualifié | ❌ **UNTESTED** — conformance run §10 non exécuté |
| Transpilation | ✅ Phase 3.1 — `.codex/prompts/*.md`, `.codex/AGENTS.md`, `.codex/config.toml` régénérables par `.sdd/harness_build.py --harness codex` |
| Wrapper d'orchestration | ✅ Phase 3.2 — `.sdd/python/sdd_lib/spawn_agent.py` (`codex exec` isolé, parallélisme borné, retry-on-schema-fail) |
| Validation E2E CalcABC | ❌ **Non exécutée** — nécessite clé OpenAI + budget tokens |
| Fidélité sorties structurées provider | `to-measure` (au conformance run) |

**Bypass technique tant qu'UNTESTED** : le pipeline consommateur exige
`SDD_ALLOW_UNTESTED_HARNESS=1` (audit-loggué), symétrique du hook
`preflight_stack_combo`. Le *build* (transpilation) reste, lui, non bloquant.

## 2. Matrice de mécanismes (7 pivots)

| Mécanisme | Claude Code | Codex | Stratégie de repli |
|---|:---:|:---:|---|
| Sous-agents isolés + `MaxParallel` | 🟢 native (tool Task/Agent) | 🟡 emulated | Wrapper `spawn_agent.py` : `codex exec` sous-processus par agent, isolation contexte **par construction** (chaque process = mémoire vierge), parallélisme via `concurrent.futures` borné à `MaxParallel` (défaut 3). 26 commandes SDD-Pro spawnantes couvertes. |
| Hooks bloquants runtime | 🟢 native (câblé — `.claude/settings.json` : PreToolUse cost-cap/TDD/ownership/env-bypass/glob-scope + SubagentStop acceptance-gate/file-ownership) | 🔴 ci_fallback | Les 19 scripts `sdd_hooks/` deviennent des gates pre/post-exec appliqués **par le wrapper** (avant/après chaque spawn) + gates CI. **Perte réelle** : pas de blocage interactif intra-session utilisateur — sous Claude Code le hook bloque la tool-call elle-même ; sous Codex l'équivalent le plus proche est un check qui tourne avant/après le process `codex exec` complet, donc plus grossier (pas de granularité par tool-call individuelle). |
| Skills auto-trigger (13 skills) | 🟢 native | 🟡 emulated | Injection statique : `.codex/AGENTS.md` inline le contenu des skills SDD-owned critiques (proposé Phase 3 : `using-sddpro` + `test-driven-development`). Les skills outillés (semgrep, codeql, sarif-parsing…) deviennent des commandes explicites invoquées quand pertinentes. **Perte réelle** : pas de déclenchement contextuel automatique. |
| Lazy-load `@file` (328 refs) | 🟢 native | 🔴 unsupported | Repli = **Read explicite** au STEP contexte (déjà en place dans tous les agents SDD-Pro par discipline). La frontmatter `paths:` des rules Claude Code ne fait qu'éviter la redondance — les agents Read leurs rules eux-mêmes. Coût contexte estimé ↑ marginal (mesurable au conformance run). |
| Slash-commands (41) | 🟢 native (`.claude/commands/*.md`) | 🟡 emulated | Transpilation directe : `.codex/prompts/*.md` avec substitution `$ARGUMENTS`. Corps métier préservé byte-identique, `@`-includes réécrits `.sdd/…`. Golden test byte-diff (Phase 2.3). |
| Python déterministe (331 scripts) | 🟢 native | 🟢 native | Aucun repli nécessaire — c'est le cœur portable. Gates, `build_loop`, `validate_*` inchangés. |
| MCP | 🟢 native | 🟢 native | — |

Bilan quantitatif (`.codex/harness-impact.md`) : **native=2 · émulé=3 · reporté-CI=1 · absent=1** sur les 7 mécanismes pivot.

## 3. Providers compatibles

| Provider | Mécanisme | Statut | Notes |
|---|---|:---:|---|
| OpenAI | natif Codex (défaut) | ✅ testable | Endpoint standard `https://api.openai.com/v1` |
| Moonshot (Kimi) | OpenAI-compat via `base_url` dans `.codex/config.toml` | 🟡 IDs à confirmer | `providers/moonshot.yaml` marque `kimi-k3`/`kimi-k2.7-code`/`kimi-k2.5` + endpoints comme « à confirmer ». Pricing absent → `[TELEMETRY_UNAVAILABLE]` sur runs cost-cappés (fail-open loggué). |
| Anthropic | ❌ non compatible | — | Le format API Anthropic n'est pas OpenAI-compat côté request/response. Utiliser Claude Code pour Anthropic. |
| Google | ❌ non compatible | — | Utiliser Gemini CLI pour Google. |

## 4. Comment activer (Tech Lead)

Dans `workspace/stack/stack.md` (gitignored, SSoT projet) :

```markdown
## Active Harness
Harness: codex

## Active Model Provider
Provider: openai         # ou moonshot (OpenAI-compat)
Endpoint: default        # ou URL Moonshot si applicable
ModelTierMap:
  deep: openai
  balanced: openai
  fast: openai
```

Puis (une fois `SDD_ALLOW_UNTESTED_HARNESS=1` positionné dans l'env) :

```bash
python .sdd/harness_build.py --stack workspace/stack/stack.md --deploy
# → régénère .codex/ à partir de .sdd/, affiche le rapport d'impact
```

Le flag `--deploy` refuse d'écraser `.claude/` (`[FRAMEWORK_PROTECTED]`) — il ne
touche que `.codex/`.

## 5. Ce qui reste avant SLA (Phase 3.5 + Phase 5)

Le combo `codex × {openai,moonshot}` **ne peut être vendu** tant que :

1. **P3.5 — Validation E2E CalcABC sous Codex** (4-6 j-h + budget tokens) : run
   d'1 FEAT bout-en-bout, back-only d'abord puis full. Métriques attendues §10 :
   ≥ 95 % sorties JSON schema-valides au 1er essai, 0 violation
   `[DERIVE_VIOLATION]`, tool-calling ≥ 98 %, convergence `build_loop` ≤ +1 iter
   vs référence anthropic.
2. **P5.1-P5.3 — Conformance run cross-combo** : rejoue LA MÊME FEAT sur ≥ 3
   combos (`codex×openai`, `codex×moonshot` en priorité). Publication de la
   matrice de confiance dans `docs/validated-combos.md`.
3. **Confirmation des IDs modèles Moonshot** + endpoints Anthropic-compat vs
   OpenAI-compat (aujourd'hui marqués « à confirmer » dans
   `.sdd/providers/moonshot.yaml`).

Tant que ces 3 blockers ne sont pas levés, le harnais Codex est utilisable en
**exploration** (`SDD_ALLOW_UNTESTED_HARNESS=1`) mais n'entre pas dans les
combos SLA §6 de CLAUDE.md.

## 6. Pointeurs

- **Plan de migration** : `MIGRATION-PLAN-multi-harness-multi-provider.md` §3, §7, §9 Phase 3, §10
- **Rapport d'impact machine** : `.codex/harness-impact.md` (régénéré à chaque build)
- **Matrice mécanismes SSoT** : `.sdd/capability-matrix.yml`
- **Wrapper spawn** : `.sdd/python/sdd_lib/spawn_agent.py` (+ 18 tests `test_spawn_agent.py`)
- **Prototype go/no-go** : `.sdd/experiments/p04-codex-subagent/` (20 tests mocked, verdict Phase 0.4)
- **ADR fondateur** : `.sdd/docs/adrs/ADR-20260724T164529-harness-and-provider-abstraction.md`
