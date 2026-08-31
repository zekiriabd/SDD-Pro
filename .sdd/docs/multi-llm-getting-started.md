# SDD_Pro — Getting started multi-LLM (harnais × provider)

> Guide Tech Lead pour activer un LLM alternatif à Claude Code. SDD_Pro v7.0.0+
> sépare **le harnais** (l'outil qui orchestre — Claude Code, Codex, Gemini CLI,
> Antigravity) du **provider** (le vendeur qui exécute les tokens — Anthropic,
> OpenAI, Google, Moonshot). Cette séparation est portée par le foyer neutre
> `.sdd/` et le transpileur `.sdd/harness_build.py` (voir
> `.sdd/docs/EXECUTION-PLAN-common-vs-harness-specific.md`).

> ⚠ **État opérationnel (2026-07-25)** : seul le combo de référence
> `claude-code × anthropic` est **pleinement fonctionnel end-to-end**. Les
> autres combos transpilent la couche statique (agents, commandes, mémoire,
> skills) — mais le wrapper d'orchestration `sdd_lib/spawn_agent.py` n'est pas
> encore branché au pipeline `/sdd-full`. Voir §7 pour valider et §5 pour les
> conséquences.

---

## 1. Prérequis

| Composant | Vérification |
|---|---|
| SDD_Pro v7.0.0+ | `python bootstrap.py --help` retourne l'aide (SSoT : `.sdd/docs/CHANGELOG.md`) |
| Un harnais CLI installé | `claude --version`, `codex --version`, `gemini --version`, ou `antigravity --version` |
| API key du provider | Env var conforme au provider (cf. §3) |
| Python 3.11+ | Requis par `harness_build.py`, `spawn_agent.py`, `conformance_run.py` |

Si un des CLI est absent, installez uniquement celui du harnais que vous voulez
utiliser — SDD_Pro n'exige pas tous les CLI en même temps.

---

## 2. Choix de la combinaison harness × provider

Les combos qualifiés SDD_Pro sont catalogués dans `.sdd/templates/combos.json`
(SSoT machine, consommée par `validate_stack_combo.py` et le hook
`preflight_stack_combo`). La table des 13 combos SLA v7.0.0 est décrite
dans `.sdd/docs/validated-combos.md`.

Sur l'axe **harnais × provider** proprement dit (indépendant du stack backend/
frontend/db), la matrice courante est :

| Harnais | Providers testables | Statut opérationnel | Doc dédiée |
|---|---|---|---|
| `claude-code` | anthropic (réf.), moonshot (via `ANTHROPIC_BASE_URL`) | ✅ référence conformance-validée | (ce guide) |
| `codex` | openai, moonshot (OpenAI-compat) | 🟡 transpile — spawn non câblé | `.sdd/docs/harness-codex.md` |
| `gemini-cli` | google | 🟡 transpile — spawn non câblé | `.sdd/docs/harness-gemini.md` |
| `antigravity` | google (idem gemini-cli) | 🟡 transpile — spawn non câblé | `.sdd/docs/harness-gemini.md` |

Les niveaux de qualification par mécanisme (7 pivots × 4 harnais) sont dans
`.sdd/capability-matrix.yml` — sortie humaine par
`sdd_lib/impact_report.build_impact_report()`.

**Recommandation** : démarrez avec `claude-code × anthropic` (référence). Ne
migrez sur un combo alternatif qu'après avoir exécuté un `/sdd-full` complet
sur un projet non critique (POC) — cf. §7.

---

## 3. Configuration `stack.md`

Le fichier `workspace/stack/stack.md` (SSoT projet, versionné — pas de secret réel)
pilote les 2 axes.
Exemple minimal pour un projet Gemini :

```markdown
## Active Harness
Harness: gemini-cli

## Active Model Provider
Provider: google
Endpoint: default
ModelTierMap:
  deep: google
  balanced: google
  fast: google

## Model Selection
Mode: static
```

Exemple pour Kimi (Moonshot) via Claude Code (Anthropic-compat) :

```markdown
## Active Harness
Harness: claude-code

## Active Model Provider
Provider: moonshot
Endpoint: default
ModelTierMap:
  deep: moonshot
  balanced: moonshot
  fast: moonshot
```

Le parseur est `.sdd/python/sdd_lib/stack_config.py` (défauts rétro-compatibles :
absence de section = `claude-code / anthropic / static`). Le template canonique
avec tous les commentaires est `.sdd/templates/stack.md.template`.

### 3.1 Env vars requises

Chaque provider déclare son env var d'auth dans son YAML :

| Provider | Env var (auth) | Env var (endpoint override) | YAML source |
|---|---|---|---|
| anthropic | `ANTHROPIC_API_KEY` | `ANTHROPIC_BASE_URL` | `.sdd/providers/anthropic.yaml` |
| openai | `OPENAI_API_KEY` | `OPENAI_BASE_URL` | `.sdd/providers/openai.yaml` |
| google | `GEMINI_API_KEY` | `GOOGLE_GEMINI_BASE_URL` | `.sdd/providers/google.yaml` |
| moonshot | `MOONSHOT_API_KEY` | `ANTHROPIC_BASE_URL` (sous claude-code) OU `base_url` de `.codex/config.toml` (sous codex) | `.sdd/providers/moonshot.yaml` |

Pour Kimi via Claude Code (Anthropic-compat), exportez :

```bash
export ANTHROPIC_API_KEY="$MOONSHOT_API_KEY"
export ANTHROPIC_BASE_URL="https://api.moonshot.ai/anthropic"
```

Le mapping tier → model_id est déclaré dans le YAML provider (section
`tier_map:` — voir §8.2 du plan de migration).

---

## 4. Génération de la façade

Le foyer neutre `.sdd/` ne suffit pas au runtime : chaque harnais consomme une
façade (répertoire spécialisé). Après changement de harnais dans `stack.md`, il
faut régénérer la façade correspondante.

```bash
# Codex — génère .codex/ (agents, prompts, AGENTS.md, config.toml)
python .sdd/harness_build.py --stack workspace/stack/stack.md \
    --out .sdd/.build/codex --deploy

# Gemini CLI / Antigravity — génère .gemini/
python .sdd/harness_build.py --stack workspace/stack/stack.md \
    --out .sdd/.build/gemini --deploy

# Claude Code — la façade .claude/ est SSoT-transitionnelle et se
# reconstruit via un helper dédié (identité round-trip)
python .sdd/python/sdd_admin/rebuild_claude_facade.py
```

Le transpileur `harness_build.py` dérive le harnais et le provider depuis
`stack.md` si `--stack` est passé ; sinon `--harness` / `--provider` explicites
priment (rétro-compat).

Chaque build imprime un **rapport d'impact** (`sdd_lib/impact_report.py`) qui
liste les mécanismes natif / émulé / reporté-CI / absent — voir §5.

---

## 5. Différences opérationnelles par harnais

Les 7 mécanismes pivot SDD_Pro (SSoT : `.sdd/capability-matrix.yml`) n'ont pas
la même couverture selon le harnais.

| Mécanisme | Claude Code (référence) | Codex | Gemini CLI | Antigravity |
|---|:---:|:---:|:---:|:---:|
| `subagent_spawn` (Task/Agent) | 🟢 native | 🟡 emulated (`spawn_agent.py`) | 🟡 emulated | 🟡 emulated |
| `runtime_hooks` (Pre/Post/SubagentStop) | 🟢 native | 🔴 ci_fallback | 🔴 ci_fallback | 🔴 ci_fallback |
| `skills_autotrigger` (13 skills) | 🟢 native | 🟡 emulated (injection statique) | 🟡 emulated | 🟡 emulated |
| `at_include` (`@`-lazy, 328 refs) | 🟢 native | 🔴 unsupported (réécrit en Read explicite) | 🟡 emulated | 🟡 emulated |
| `slash_commands` (40) | 🟢 native | 🟡 emulated (`.codex/prompts/*.md`) | 🟢 native (`.gemini/commands/*.toml`) | 🟢 native |
| `deterministic_python` (331 scripts) | 🟢 native | 🟢 native | 🟢 native | 🟢 native |
| `mcp` | 🟢 native | 🟢 native | 🟢 native | 🟢 native |

**Conséquences concrètes** :

- **Claude Code (référence)** : subagent_spawn natif via tool `Task`/`Agent`,
  hooks runtime bloquants, skills auto-trigger, lazy-load `@file`. Aucune
  dégradation.
- **Codex** : subagent_spawn émulé via `sdd_lib/spawn_agent.py` (`codex exec`
  sous-processus isolé, parallélisme borné à `MaxParallel`). Hooks reportés
  au CI (gates pre/post-exec du wrapper). Skills SDD-owned critiques injectés
  statiquement dans `.codex/AGENTS.md`. `@`-refs réécrites en chemins bruts.
- **Gemini CLI** : idem Codex côté spawn/hooks/skills, mais slash-commands
  natives (`.gemini/commands/*.toml`).
- **Antigravity** : idem Gemini CLI, `@`-support à confirmer côté prompts.

La ligne complète par harnais (transpilation, wrapper, verdict conformance)
est dans `.sdd/docs/harness-codex.md §2` et `.sdd/docs/harness-gemini.md §2`.

---

## 6. Impact tokens / prompt caching

Le prompt caching **n'est pas portable** entre providers :

| Provider | Mécanisme cache | Statut sous SDD_Pro |
|---|---|---|
| anthropic | `cache_control: ephemeral` (Anthropic-native) | ✅ appliqué par `sdd_lib/cache_control.py` |
| openai | cache implicite server-side (pas de contrôle client) | ⚠ perte silencieuse |
| google | `context-caching` (API différente) | ⚠ non appliqué en v7.0.0 (roadmap Phase 3) |
| moonshot | absent | ⚠ perte silencieuse |

Chaque build `harness_build.py` imprime un rapport d'impact via
`sdd_lib/impact_report.py` (fonction `build_impact_report`) qui liste les
mécanismes dégradés du combo cible. Ce rapport est **non bloquant** au build
(mais bloquant au pipeline via l'env var `SDD_ALLOW_UNTESTED_HARNESS`, cf. §8).

Pour visualiser le rapport d'un combo :

```bash
python -c "
from sdd_lib.impact_report import build_impact_report
r = build_impact_report(harness='codex', provider='openai')
print(r.render_markdown())
"
```

---

## 7. Validation via `conformance_run.py`

Avant de sortir un combo de l'état UNTESTED, exécutez un conformance run — c'est
la tâche §10 du plan de migration.

### 7.1 Lancer un run

```bash
# Smoke CI (sans réseau, sans token) — les 5 combos par défaut
python .sdd/python/sdd_scripts/conformance_run.py --dry-run

# Ciblage explicite d'un combo
python .sdd/python/sdd_scripts/conformance_run.py --dry-run \
    --combo codex:openai --combo gemini-cli:google

# Live run (nécessite API keys — voir §3.1) — ~30 min par combo
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
python .sdd/python/sdd_scripts/conformance_run.py --live \
    --combo claude-code:anthropic --timeout-min 30
```

### 7.2 Lire le rapport

Chaque run écrit sous `.sdd/.build/conformance/{timestamp}/` :

- `report.md` — vue Tech Lead (résumé + détail des checks par combo)
- `report.json` — payload machine (schéma `sdd.conformance/v1`) pour CI
- `{harness}-{provider}/` — logs par combo (stdout/stderr capturés, stack.md
  dispatché en temp)

Le script n'écrit **jamais** dans `workspace/stack/stack.md` — chaque combo
travaille sur une copie temp (garantie d'isolation).

### 7.3 Codes `[CONFORMANCE_*]`

| Code | Sens | Exit code |
|---|---|:---:|
| `[CONFORMANCE_PASS]` | Combo validé (config + adapter + dispatch OK) | 0 |
| `[CONFORMANCE_DRIFT]` | Divergence vs baseline en mode `--live` — voir `report.md` | 2 (WARN, ou 1 avec `--strict`) |
| `[INFRA_BLOCKED]` | CLI absent, API key manquante, provider YAML KO, spawn non câblé | 3 |

Exit code SDD_Pro (SSoT `sdd_lib/exit_codes.py`) :
`SUCCESS=0`, `FAIL_FAST=1`, `CORRECTIBLE=2` (utilisé ici pour WARN),
`INFRA_BLOCKED=3`.

### 7.4 Ce qui bloque un run `--live` complet aujourd'hui

- Combos non-référence (`codex × *`, `gemini-cli × *`) : `sdd_lib/spawn_agent.py`
  n'est pas encore branché au pipeline `/sdd-full`. Le script émet
  `[INFRA_BLOCKED]` explicite avec pointer vers
  `.sdd/docs/harness-codex.md` / `.sdd/docs/harness-gemini.md`. C'est la
  Phase 3+ du plan de migration.
- Combo référence : le run `/sdd-full` end-to-end reste un exercice interactif
  du client Claude Code — le script utilise `bootstrap.py --dry-run` comme
  proxy live minimal (§10.3 du plan).

---

## 8. Combos non testés — bypass

Le hook `.sdd/python/sdd_hooks/preflight_stack_combo.py` bloque tout combo qui
n'est pas dans `.sdd/templates/combos.json` (ou dont la signature stack ne matche
pas un combo qualifié).

Bypass audit-loggué :

```bash
export SDD_ALLOW_UNTESTED_COMBO=1
```

L'émission de la classe `[STACK_COMBO_UNTESTED]` reste tracée dans les logs
(cf. `.sdd/rules/error-classification.md §1.14`). Ne pas utiliser en prod SLA
tant que le conformance run §7 n'a pas confirmé le combo.

Le pipeline consommateur de `harness_build.py` a un gate symétrique :
`SDD_ALLOW_UNTESTED_HARNESS=1` (SSoT `sdd_lib/impact_report.ALLOW_UNTESTED_ENV`).

---

## 9. Liens

- Plan de migration : `.sdd/docs/MIGRATION.md`, plan racine
  `MIGRATION-PLAN-multi-harness-multi-provider.md`
- SSoT capability-matrix : `.sdd/capability-matrix.yml`
- SSoT combos SLA : `.sdd/templates/combos.json` + `.sdd/docs/validated-combos.md`
- Wrapper spawn multi-harness : `.sdd/python/sdd_lib/spawn_agent.py`
- Rapport d'impact : `.sdd/python/sdd_lib/impact_report.py`
- Parseur stack.md : `.sdd/python/sdd_lib/stack_config.py`
- Prototype sous-agent Codex : `.sdd/experiments/p04-codex-subagent/`
- Docs harness dédiées : `.sdd/docs/harness-codex.md`, `.sdd/docs/harness-gemini.md`
