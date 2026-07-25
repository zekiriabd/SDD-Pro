# P0.4 — Prototype go/no-go : émulation de sous-agents sous Codex

**Question dérisquée** (plan `MIGRATION-PLAN-multi-harness-multi-provider.md`
§9 tâches 0.4-0.5, §11 risque R1) : Codex sait-il émuler l'orchestration de
sous-agents isolés dont dépendent les **26 commandes spawnantes** SDD-Pro,
de façon assez fiable ?

**Critère chiffré** : **GO si ≥ 95 % de complétions parseables sur 20 runs**
(soit ≥ 19/20). NO-GO → périmètre Codex réduit à « commandes mono-agent »
(dégradation affichée) + re-priorisation Gemini. Sans ce verdict consigné,
**la Phase 1 ne doit pas démarrer** (P0.4 est en tête du chemin critique
P0.4 → P1 → P2 → P3).

## Contenu

| Fichier | Rôle |
|---|---|
| `spawn_agent_codex.py` | Émule 1 spawn de sous-agent via `codex exec` (subprocess isolé : cwd temp neuf, sandbox read-only, prompt auto-porteur). Parse le JSON, valide le schéma, classe les échecs. |
| `run_experiment.py` | Orchestre les 20 runs (4 fixtures × 5, pool parallèle borné à 2), calcule taux parseable / latence médiane / distribution des erreurs, imprime GO/NO-GO, écrit `results/p04-report-*.{json,md}`. |
| `fixtures/*.json` | 4 tâches synthétiques représentatives : découpe FEAT→US (po), verdict d'audit (code-reviewer), plan de fichiers backend (dev-backend :plan), classification `[CLASS]` (contrat build_loop). |
| `test_spawn_agent_codex.py` | Tests unitaires 100 % mockés (seam `_invoke_codex`) — aucun appel réel. |

## Pré-requis exacts (humain)

1. **Installer le CLI Codex** (≥ 0.20, la commande `codex exec` et le flag
   `--output-last-message` doivent exister) :
   ```
   npm install -g @openai/codex
   codex --version
   ```
2. **Authentification** — au choix :
   - `codex login` (compte ChatGPT), ou
   - clé API : `set OPENAI_API_KEY=sk-...` (PowerShell :
     `$env:OPENAI_API_KEY = "sk-..."`), ou
   - **endpoint OpenAI-compatible** (ex. Kimi/Moonshot) : déclarer un
     `model_provider` avec `base_url` dans `~/.codex/config.toml` puis
     passer le modèle via `--model` / `SDD_CODEX_MODEL` (cf. doc codex
     `model_providers`).
3. **Python ≥ 3.10** (stdlib uniquement, aucune dépendance pip ;
   `pytest` requis seulement pour les tests mockés).

## Lancer l'expérience (le vrai verdict)

Depuis la racine du repo :

```
python .sdd/experiments/p04-codex-subagent/run_experiment.py
```

Options utiles :

```
python .sdd/experiments/p04-codex-subagent/run_experiment.py ^
  --codex-bin C:\chemin\vers\codex --model gpt-5-codex ^
  --runs 20 --max-parallel 2 --timeout-s 180
```

(équivalents env : `SDD_CODEX_BIN`, `SDD_CODEX_MODEL`, `SDD_CODEX_TIMEOUT_S`)

Exit code : `0` = GO, `1` = NO-GO, `2` = erreur d'orchestration.
Rapports : `results/p04-report-{timestamp}.json` + `.md` (créés au runtime).

## Lancer les tests mockés (sans codex, sans réseau)

```
python -m pytest .sdd/experiments/p04-codex-subagent/test_spawn_agent_codex.py -q
```

## Interprétation du verdict

- **🟢 GO (≥ 95 %)** : `spawn_mode: emulated` est viable — la matrice
  `capability-matrix.yml` (`codex.subagent_spawn: emulated`,
  `protection_level: B`) est confirmée ; la Phase 3 (industrialisation en
  `sdd_scripts/spawn_agent.py`, tâche 3.2) reste au plan.
- **🔴 NO-GO (< 95 %)** : regarder la `error_distribution` du rapport —
  `[JSON_UNPARSEABLE]`/`[SCHEMA_MISMATCH]` dominants → tester le mode
  « retry-on-schema-fail » (§10.2, GO conditionnel si ≥ 85 %) ;
  `[TIMEOUT]`/`[NONZERO_EXIT]` dominants → problème d'infra/CLI, corriger
  et relancer avant de conclure. Si NO-GO confirmé : périmètre Codex
  « mono-agent », re-scoper P3-P4 AVANT extraction (garde de sortie P0).

## Où annexer le résultat

Consigner le verdict (GO/NO-GO + taux + latence médiane + lien vers le
rapport `results/p04-report-*.md`) dans l'ADR :
`.sdd/docs/adrs/ADR-20260724T164529-harness-and-provider-abstraction.md`
(section critère go/no-go P0.4 / décision `spawn_mode`), et refléter la
décision dans `.sdd/capability-matrix.yml` (`codex.protection_level`).

## Limites assumées du prototype (jetable)

- Isolation testée = cwd temporaire + prompt auto-porteur (pas de mémoire
  partagée) ; l'isolation « contexte projet réel » complète est mesurée en
  P3.5 (1 FEAT CalcABC bout-en-bout).
- Le gate post-exec réel (`validate_readiness.py`) est remplacé ici par la
  validation de schéma JSON — même nature de contrôle (sortie structurée
  contrainte), sans dépendre d'un workspace.
- Taxonomie `[CLASS]` locale au prototype, non fusionnée dans
  `rules/error-classification.md`.
