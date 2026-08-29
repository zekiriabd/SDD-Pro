# SDD_Pro — Harnais Gemini CLI / Antigravity

> Document d'honnêteté (Phase 4.4 du plan
> `MIGRATION-PLAN-multi-harness-multi-provider.md`). Décrit **ce qui est
> gagné, ce qui est perdu et ce qui est émulé** en passant de Claude Code
> à Gemini CLI (ou Antigravity, qui partage la même façade). SSoT machine
> = `.sdd/capability-matrix.yml`. Ce fichier en est la lecture Tech Lead.

> **Décision produit 2026-07-26 (audit R6)** — Antigravity est **alias
> non-natif** de Gemini CLI dans SDD_Pro : la même façade `.gemini/` est
> déployée, la même stratégie d'émulation `spawn_agent_cli.py` est
> utilisée. Le mode agents natif d'Antigravity (sessions persistantes,
> tool integration IDE) **n'est pas exploité** — investissement retenu
> par le Tech Lead comme non prioritaire tant que le combo Gemini CLI
> × Google n'est pas lui-même conformance-validé. Toute évolution vers
> un adapter Antigravity distinct doit ré-ouvrir l'ADR
> `harness-and-provider-abstraction` (D1).

## 1. Statut (2026-07-25)

| Dimension | Valeur |
|---|---|
| Niveau de protection | **B** (référence claude-code/anthropic = A) |
| Combo qualifié | ❌ **UNTESTED** — conformance run §10 non exécuté |
| Transpilation | ✅ Phase 4.1 — `.gemini/commands/*.toml`, `.gemini/GEMINI.md`, `.gemini/settings.json` régénérables par `.sdd/harness_build.py --harness gemini-cli` |
| Wrapper d'orchestration | ✅ Phase 4.2 — `.sdd/python/sdd_lib/spawn_agent.py` (mode `gemini -p` non-interactif, partage le même code que le mode Codex) |
| Validation E2E CalcABC | ❌ **Non exécutée** — nécessite clé Google + budget tokens |
| Fidélité sorties structurées provider | `to-measure` (au conformance run) |

**Bypass technique tant qu'UNTESTED** : `SDD_ALLOW_UNTESTED_HARNESS=1`
(audit-loggué), symétrique du hook `preflight_stack_combo`.

## 2. Matrice de mécanismes (7 pivots)

| Mécanisme | Claude Code | Gemini CLI | Stratégie de repli |
|---|:---:|:---:|---|
| Sous-agents isolés + `MaxParallel` | 🟢 native (tool Task/Agent) | 🟡 emulated | Wrapper `spawn_agent.py` mode `gemini -p` non-interactif : chaque agent = sous-processus, isolation contexte, parallélisme borné à `MaxParallel` (défaut 3). Antigravity a des agents natifs mais API d'orchestration différente — même wrapper appliqué. |
| Hooks bloquants runtime | 🟢 native (câblé — `.claude/settings.json` : PreToolUse cost-cap/TDD/ownership/env-bypass/glob-scope + SubagentStop acceptance-gate/file-ownership) | 🔴 ci_fallback | Idem Codex : gates pre/post-exec du wrapper + CI. **Perte réelle** : pas de blocage interactif intra-session — sous Gemini l'équivalent le plus proche tourne avant/après le process `gemini -p` complet, donc plus grossier que le blocage par tool-call de Claude Code. |
| Skills auto-trigger (13 skills) | 🟢 native | 🟡 emulated | Injection statique dans `.gemini/GEMINI.md` (skills SDD-owned critiques : `using-sddpro`, `test-driven-development`). Skills outillés → commandes explicites. **Perte réelle** : pas de déclenchement contextuel automatique. |
| Lazy-load `@file` | 🟢 native | 🟡 emulated | `@` **supporté par Gemini CLI dans les prompts** (pas en mémoire GEMINI.md — à confirmer selon version CLI). Wrapper émule l'inclusion à la volée si nécessaire. Coût contexte estimé ↑ marginal. |
| Slash-commands (41) | 🟢 native (`.claude/commands/*.md`) | 🟢 **native** (`.gemini/commands/*.toml`) | Transpilation directe : `.gemini/commands/*.toml` avec substitution `{{args}}`. **Format natif Gemini** — pas d'émulation, byte-diff golden test (Phase 2.3). C'est le point fort du harnais Gemini. |
| Python déterministe (331 scripts) | 🟢 native | 🟢 native | Aucun repli — cœur portable. |
| MCP | 🟢 native | 🟢 native | — |

Bilan quantitatif (`.gemini/harness-impact.md`) : **native=3 · émulé=3 · reporté-CI=1 · absent=0** sur les 7 mécanismes pivot. Meilleur bilan que Codex sur `slash_commands` (natif TOML) et `at_include` (émulation légère plutôt qu'unsupported).

## 3. Providers compatibles

| Provider | Mécanisme | Statut | Notes |
|---|---|:---:|---|
| Google (Gemini) | natif Gemini CLI (défaut) | ✅ testable | Provider natif, API Google standard |
| Anthropic | via proxy | 🟡 possible mais non prioritaire | Utiliser Claude Code pour Anthropic reste plus sûr |
| OpenAI | via proxy | 🟡 non prioritaire | Utiliser Codex pour OpenAI reste plus sûr |
| Moonshot (Kimi) | via proxy de traduction (LiteLLM ou équivalent) | 🔴 hors périmètre initial | Documenté 🟡 dans le plan §7.2 — pas de compat native, hors SLA initial |

## 4. Comment activer (Tech Lead)

Dans `workspace/stack/stack.md` :

```markdown
## Active Harness
Harness: gemini-cli      # ou antigravity — même façade

## Active Model Provider
Provider: google
Endpoint: default
ModelTierMap:
  deep: google
  balanced: google
  fast: google
```

Puis (une fois `SDD_ALLOW_UNTESTED_HARNESS=1` positionné) :

```bash
python .sdd/harness_build.py --stack workspace/stack/stack.md --deploy
# → régénère .gemini/ à partir de .sdd/, affiche le rapport d'impact
```

Le flag `--deploy` refuse d'écraser `.claude/` (`[FRAMEWORK_PROTECTED]`) — il ne
touche que `.gemini/`.

## 5. Ce qui reste avant SLA (Phase 4.3 + Phase 5)

Le combo `gemini-cli × google` **ne peut être vendu** tant que :

1. **P4.3 — Validation E2E CalcABC sous Gemini** (3-4 j-h + budget tokens) : run
   d'1 FEAT bout-en-bout. Mêmes seuils que Codex (§10) : ≥ 95 % sorties JSON
   schema-valides au 1er essai, 0 violation `[DERIVE_VIOLATION]`,
   tool-calling ≥ 98 %, convergence `build_loop` ≤ référence + 1 iter.
2. **P5.1-P5.3 — Conformance run cross-combo** : publication de `gemini-cli×google`
   dans la matrice de confiance `docs/validated-combos.md`.
3. **Confirmation Antigravity** : Antigravity partage la façade `.gemini/` par
   design (même config commands TOML), mais l'API d'orchestration native
   d'Antigravity diverge côté agents (Phase 4 les traite comme émulés via
   wrapper — à revalider si Antigravity expose des primitives d'orchestration
   utilisables).

Tant que ces 3 blockers ne sont pas levés, le harnais Gemini est utilisable en
**exploration** (`SDD_ALLOW_UNTESTED_HARNESS=1`) mais n'entre pas dans les
combos SLA §6 de CLAUDE.md.

## 6. Pointeurs

- **Plan de migration** : `MIGRATION-PLAN-multi-harness-multi-provider.md` §3, §7, §9 Phase 4, §10
- **Rapport d'impact machine** : `.gemini/harness-impact.md` (régénéré à chaque build)
- **Matrice mécanismes SSoT** : `.sdd/capability-matrix.yml`
- **Wrapper spawn** : `.sdd/python/sdd_lib/spawn_agent.py` (mode `gemini`, partage le code Codex)
- **Doc complémentaire** : `harness-codex.md` (structure et raisonnement identiques — les 2 harnais partagent la même infrastructure)
- **ADR fondateur** : `.sdd/docs/adrs/ADR-20260724T164529-harness-and-provider-abstraction.md`
