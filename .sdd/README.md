# `.sdd/` — Foyer neutre du moteur SDD-Pro (multi-harnais, multi-provider)

> **Statut : scaffolding Phase 0 / amorce Phase 1 — NON ENCORE CÂBLÉ.**
> Rien dans ce répertoire n'est consommé par le pipeline actuel (`.claude/`
> reste la surface servie à Claude Code, inchangée). Tout ce répertoire est
> réversible par simple suppression. Plan de référence :
> `MIGRATION-PLAN-multi-harness-multi-provider.md` (racine repo).

## 1. Rôle

`.sdd/` est le **foyer neutre unique** cible du framework (SSoT versionné,
édité à la main). À terme (Phase 2+), les répertoires de harnais
(`.claude/`, `.codex/`, `.gemini/`) deviennent des **produits de build**
générés par `harness_build.py` — jetables, read-only, en-tête
`# GENERATED FROM .sdd/ — DO NOT EDIT`. Deux axes orthogonaux pilotés
depuis `stack.md` :

- **Axe 1 — Harnais** : où tourne l'orchestration LLM (claude-code,
  codex, antigravity, gemini-cli). Cf. `capability-matrix.yml`.
- **Axe 2 — Provider** : qui exécute les tokens (anthropic, openai,
  google, moonshot). Cf. `providers/*.yaml` + abstraction
  `model_tier: deep|balanced|fast`.

## 2. Contrat `SDD_HOME`

- Variable d'environnement `SDD_HOME` — défaut : `<repo_root>/.sdd`.
- **Windows : aucun symlink.** Résolution = chemins relatifs + env var.
- Tous les scripts résolveront via `sdd_lib/paths.py::sdd_home()`
  (modification prévue Phase 1 — `_looks_like_repo_root()` bi-racine
  `.sdd/` OU `.claude/` pendant la transition). Jamais `.claude/` en dur.
- `SDD_HOME` n'existe pas encore dans le code du repo (0 occurrence
  mesurée le 2026-07-24) : ce contrat est figé ici avant câblage.

## 3. Principe « fichiers de harnais générés = read-only »

Toute façade générée (`.claude/`, `.codex/`, `.gemini/`, `CLAUDE.md`,
`AGENTS.md`, `GEMINI.md`) :

1. porte l'en-tête `# GENERATED FROM .sdd/ — DO NOT EDIT` + hash de build ;
2. est protégée par une garde CI qui rejette tout commit la modifiant
   hors `harness_build.py` (Phase 2.4) ;
3. est verrouillée par l'invariant n°14 `harness-parity` (« toute façade
   committée == sortie de `harness_build.py` sur `.sdd/` HEAD »),
   enforcé par le golden test d'identité (Phase 2.3).

Jamais de dégradation silencieuse : chaque combo harnais × provider
affiche son niveau de protection réel (A/B/C) via le rapport d'impact
de `harness_build.py` — **implémenté en Phase 2.5** (`sdd_lib/impact_report.py`).
Imprimé sur stdout + persisté (`{out}/harness-impact.md` et, si présent,
`workspace/.sys/harness-impact.md`) sur chaque build. Le rapport est
**informationnel** (ne fait jamais échouer une transpilation) ; le gate
bloquant `SDD_ALLOW_UNTESTED_HARNESS` (fonction `untested_gate_ok`) est
réservé au consommateur pipeline, symétrique du hook `preflight_stack_combo`.
Seul le combo de référence `claude-code × anthropic` (golden test + baseline
CalcABC) n'est pas `UNTESTED` ; tout autre combo attend un conformance run (§10).

## 4. Contenu actuel (incrément Phase 0 + amorce Phase 1)

| Fichier | Rôle | Phase |
|---|---|---|
| `docs/adrs/ADR-20260724T164529-harness-and-provider-abstraction.md` | ADR fondateur (2 axes, model_tier, mode static\|dynamic, invariant 14) | 0.1 |
| `capability-matrix.yml` | Matrice machine harnais × mécanismes (§7.1 du plan) | 0.2 |
| `providers/{anthropic,openai,moonshot,google}.yaml` | Axe 2 — providers pluggables (schéma §8.2) | 1.8 |
| `agent-bounds.yaml` | Bornes tier par agent (25 agents, table §8.bis.7) | 1.9 |
| `python/sdd_lib/model_resolver.py` | Résolveur pur (clamp, level→tier, resolve) — testable en isolation | 1.5/1.9 |
| `python/tests/test_model_resolver.py` | Tests unitaires du résolveur | 1.5/1.9 |
| `rules-manifest.yaml` | Manifest neutre des 11 rules (body_source vers vivant, scope, mapping harnais) | 2.3 |
| `skills-manifest.yaml` | Classification des 13 skills (owned/vendored, support par harnais) — artefact de conception, pas d'émission | 2.3 |
| `python/sdd_lib/impact_report.py` | Rapport d'honnêteté des garanties par combo harnais × provider (§7.3) — consomme `capability-matrix.yml` + `providers/*.yaml`, imprimé + persisté (`harness-impact.md`) sur CHAQUE build, gate `untested_gate_ok` (SDD_ALLOW_UNTESTED_HARNESS) pour le futur consommateur pipeline | **2.5** |
| `python/tests/test_impact_report.py` | Tests du rapport d'impact (20) — comptes mécanismes, marquage UNTESTED, gate, intégration CLI non bloquante, render ASCII-safe | **2.5** |
| `python/sdd_lib/stack_config.py` | Parseur pur des 2 axes + Model Selection depuis `stack.md` (`## Active Harness`, `## Active Model Provider` + `ModelTierMap`, `## Model Selection`) — défauts rétro-compat (absence = claude-code/anthropic/static), `provider_for_tier` (mixage cross-provider §8.bis.6). GLU entre `stack.md` et `model_resolver` + `impact_report`. **Template live NON modifié** (édition réservée à la fenêtre Phase 1) | **1.7 (parseur)** |
| `python/tests/test_stack_config.py` | Tests du parseur (16) — défauts, mixage cross-provider, validation fail-explicit, composition avec model_resolver | **1.7** |
| `harness_build.py` (flag `--stack`) | Câblage CLI : `--stack <stack.md>` dérive harnais + provider (les flags `--harness`/`--provider` priment, chacun sur son axe) ; `--harness` devient optionnel si `--stack` le fournit. Rétro-compat totale (sans `--stack`, comportement inchangé). Tests `test_harness_build_stack.py` (7) | **1.7 (câblage)** |
| `python/sdd_lib/harness_preflight.py` | Brique de COMPOSITION : `preflight_combo(stack_path)` unifie stack_config → impact_report → gate UNTESTED. Point d'entrée unique du futur consommateur pipeline (« quel combo, autorisé ?, protection ? ») — symétrique de `preflight_stack_combo`. Verdict structuré non bloquant (`blocking_reason` prêt pour ERROR `[STACK_COMBO_UNTESTED]`). Tests `test_harness_preflight.py` (7) | **2.5 (composition)** |
| `python/sdd_lib/spawn_agent.py` | Wrapper d'orchestration de sous-agents multi-harnais (repli du `subagent_spawn` natif Claude). `codex exec` / `gemini -p` / `claude -p`, prompt auto-porteur + contrat JSON strict, extraction robuste (strict/fenced/balanced), `validate_schema`, **retry-on-schema-fail** (§10.2), parallélisme borné (`spawn_many`). **Token-free & testable** : runner subprocess INJECTABLE (seam). Industrialise le prototype P0.4. Tests `test_spawn_agent.py` (18) | **3.2** |
| `harness_build.py` (flag `--deploy`) | Installe la façade buildée en racine (`.codex/` ou `.gemini/` — jamais `.claude/`, refus `[FRAMEWORK_PROTECTED]`). Rend le multi-harnais visible/utilisable. | **3.1/4.1 (deploy)** |

### 4.bis Golden test d'identité — surfaces couvertes (Phase 2.3)

Le transpileur `harness_build.py` régénère la couche de contrôle Claude
depuis `.sdd/` sous `.sdd/.build/claude/`, byte-diffée contre le vivant :

| Surface | Round-trip | Niveau | Émission variantes (codex/gemini) |
|---|---|---|---|
| 25 agents | 25/25 | sémantique | **N/A** (sous-agents émulés au runtime par spawn_agent.py, Phase 3+) |
| 40 commandes | 40/40 | **byte-identique** | **transpilées** : codex `.codex/prompts/*.md` (`$ARGUMENTS`) + gemini `.gemini/commands/*.toml` (`{{args}}`) |
| fichier-mémoire | CLAUDE.md | **byte-identique** | AGENTS.md + GEMINI.md générés |
| config harnais | (n/a Claude) | — | codex `config.toml` + gemini `settings.json` (dérivés du provider actif, IDs « à valider ») |
| 11 rules | 11/11 | **byte-identique** | non câblé (pas de path-scoped — inline universelles + pointeurs) |

> **Façades Codex/Gemini (Phase 3.1/4.1 transpilation, 2026-07-24)** : la
> couche COMMANDES + config est désormais générée pour codex et gemini-cli
> (`--commands-only` supporté), corps métier préservé + `@`-includes réécrits
> `.sdd/`, TOML/JSON validés. **Token-free** (transpilation pure) — les *runs*
> live (P0.4 verdict, conformance) et le wrapper d'orchestration `spawn_agent.py`
> attendent CLI+clés (P0.4) et restent hors de ce build. Tests
> `test_harness_codex_gemini.py` (15).

**`settings.json` — EXCLU du foyer neutre (décision 2026-07-24).** Le
`permissions.allow[]` vivant est une accumulation LOCALE de grants (chemins
absolus machine, autres projets `consent-hub-admin`, chemins scratchpad de
session) : c'est de l'état local, PAS un artefact de framework SSoT. Les
protections réelles vivent dans les scripts Python + hooks (non câblés dans
`settings.json` — permissions seulement). `settings.json`/`settings.local.json`
restent donc hors `.sdd/` par conception.

**skills — surface la moins portable.** Arborescences de répertoires (pas de
markdown simple) ; classées dans `skills-manifest.yaml` mais pas régénérées
en Phase 2 (déplacement physique = Phase 1 invasive). Codex/Gemini n'ont pas
d'équivalent natif des skills auto-déclenchés (cf. manifest `harness_support`).

## 5. Ce qui N'EST PAS fait ici

- Aucune modification de `.claude/`, `workspace/`, ni des fichiers racine.
- Pas de déplacement de `paths.py` ni des 331 scripts Python.
- Pas de prototype Codex P0.4 (`spawn_agent_codex.py`) — exige le CLI
  `codex` + clés API externes → action humaine préalable.
- Le mode `dynamic` reste opt-in et 🟡 UNTESTED tant qu'aucun
  conformance run (§10 du plan) n'a mesuré son impact qualité/coût.

## 6. Exécuter les tests

```
python -m pytest .sdd/python/tests/ -q                    # 212 (résolveur, golden, rapport/préflight 2.5, stack 1.7, façades codex/gemini 3.1/4.1, spawn_agent 3.2)
python -m pytest .sdd/experiments/p04-codex-subagent/ -q  # 20 (prototype Codex mocké)
```

Golden test manuel (régénère toutes les surfaces Claude sous `.sdd/.build/`) :

```
python .sdd/harness_build.py --harness claude-code \
    --agents-only --commands-only --rules-only --memory-only \
    --out .sdd/.build/claude
```
