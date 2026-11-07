# SDD_Pro — Coûts et cache de prompt (révision 2026-11-07)

> **STATUS (audit tokens 2026-11-06, transcripts réels du run FEAT 15)** — cette
> page remplace la version v7.0.0 GA, dont les chiffres étaient des **artefacts de
> télémétrie** : le hook de mesure n'enregistrait que le **dernier tour** de chaque
> sous-agent. D'où les « 7 lignes, `input` = 1, hit 99,2 %, ~$0.56 / FEAT M » de
> l'ex-§1.2 — un sous-comptage de ×7 à ×126 selon l'agent. Ces chiffres sont
> **retirés** ; ne pas les citer.
>
> - Le cache de prompt est **l'auto-cache de Claude Code**. SDD-Pro ne pose aucun
>   marqueur `cache_control` et **ne peut pas en poser** : le harnais compose
>   lui-même le prompt des sous-agents (outil `Agent`), sans point d'injection.
> - `sdd_lib/cache_control.py` (annotations `cache_layer:` → breakpoints) est
>   **déprécié / sans effet** : son « Phase 3 wiring v7.1 » ne peut pas être livré
>   dans Claude Code (constat déjà fait dans `sdd_scripts/context_pack.py`). Le
>   fichier est conservé (dépendances de tests et d'autres lots) mais ne produit
>   aucun gain. Les annotations `cache_layer:` de `loader.yml` restent un **ordre
>   de lecture conseillé** (stable → semi → volatile), rien de plus.

## 1. Mesures réelles — run FEAT 15 (2026-11-06)

Source : transcripts JSONL Claude Code du run (tous les tours de chaque
sous-agent, pas seulement le dernier), tarifs génération **4.x**.

| Poste | Mesure |
|---|---:|
| Sous-agents (tous tours, toutes invocations) | **≈ 87 $** |
| Orchestrateur (session principale) | **≈ 14 $** |
| Périmètre | 2 US, stack **desktop** (WPF), **sans backend** |
| Hit rate cache mesuré | **91,8 %** — auto-cache Claude Code, pas un levier SDD-Pro |
| Contexte d'un agent dev au 1er tour | ≈ 48 k tokens |
| Contexte d'un agent dev au dernier tour | 180-220 k tokens (sur 44-74 tours) |

Lecture : le coût est dominé par la **croissance du contexte au fil des tours**
(chaque tour relit tout le contexte accumulé, même en cache à 0,1×), pas par le
contexte initial. Les leviers réels sont donc : (1) un contexte initial plus
petit (Reads bornés, pas de relecture — lot 2026-11-07), (2) moins de tours
(build loop qui converge vite), (3) un `effort:` adapté au rôle (`medium` hors
dev-*/arch, lot 2026-11-07), (4) le tier de modèle.

## 2. Extrapolation `/sdd-full` (estimation, non mesurée)

| Scénario | Estimation |
|---|---:|
| `/sdd-full` FEAT de 3 US back-front, nominal (tarifs 4.x) | **≈ 170 $** |
| Fourchette (convergence du build loop, taille des stacks, nb de reviewers) | **100 à 250 $** |
| Même scénario sur la génération 5.5 | ≈ -30 % (tarifs), **non re-mesuré** |

Toute affirmation de coût doit citer un run mesuré sur **tous les tours**
(`python -m sdd_admin.measure_cache_hit_rate` lit les JSONL complets ; le ledger
`token_usage` de `console.db` n'est fiable que depuis la correction du hook
« dernier tour »). Aucune cible de coût n'est engagée tant que 3 runs comparables
n'ont pas été mesurés (cf. `poc-roi-methodology.md`).

## 3. Monitoring du hit rate

```bash
cd .sdd/python && python -m sdd_admin.measure_cache_hit_rate --days 7
python -m sdd_admin.measure_cache_hit_rate --days 30 --json   # CI / dashboards
```

Lit `~/.claude/projects/<encoded-cwd>/**/*.jsonl` et agrège
`cache_read_input_tokens` / `cache_creation_input_tokens` / `input_tokens` par
session et par modèle. Utile pour détecter une **régression** (ex. un Read
non déterministe en tête de contexte qui casse le préfixe), pas pour revendiquer
un gain : le hit rate élevé est une propriété du harnais.

## 4. Ce qui reste valable de l'ancienne stratégie

- **Ordre de lecture stable → semi → volatile** dans chaque STEP contexte :
  maximise le préfixe commun entre invocations, donc l'auto-cache. Gratuit.
- **Schema slices** (`workspace/db/schema-slice-{n}-{m}.json`, Levier 4) :
  réduisent réellement le contexte des dev-* et de qa.
- **Lecture par section** des stacks et des rules (lot 2026-11-07) : un stack
  de 30-60 Ko lu en entier, plusieurs fois par run, pesait davantage que tout
  le reste du contexte initial.

## 5. Historique (non normatif)

- 2026-05-20 : 40,8 % de hit sur FEAT 2 (`roi-report-2026-05-20-FEAT2-postfix.json`)
  — mesure de format différent, conservée pour mémoire.
- 2026-06-06 / 2026-06-08 : « 99,2 % » et « 93,8 % sur 30 j » — mesures
  dernier-tour, invalidées par l'audit du 2026-11-06.
- Critère release v7.0.0 « coût Opus / FEAT M ≤ $15 » : déclaré atteint sur la
  base de ces mesures invalides ; **retiré**.
