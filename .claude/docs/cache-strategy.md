# SDD_Pro — Prompt Caching Strategy (v7.0.0 P0-8)

> **STATUS v7.0.0-alpha (révision 2026-06-07)** : la baseline 40.8% datée
> 2026-05-20 sous-mesurait — le caching automatique Claude Code (auto-cache
> + 5min TTL) atteint en réalité **~99% de hit rate** sur les runs récents.
> L'ajout de markers `cache_control` reste utile pour les sessions étalées
> >5min entre 2 agents (rare en pratique). Priorité v7.1 reclassée P2.

## 1. Baseline mesurée

### 1.1 Mesure historique 2026-05-20 (roi-report FEAT 2)

Source : `workspace/output/qa/roi-report-2026-05-20-FEAT2-postfix.json`.

| Métrique | Valeur |
|---|---:|
| Cache hit rate global (FEAT 2) | 40.8 % |
| `input` tokens (full price) | 1 183 153 |
| `cache_read` tokens (90 % discount) | 816 432 |
| `cache_creation` tokens (1.25× premium) | 20 210 |

> Cette mesure considérait `cache_read / (input + cache_read)` mais avec une
> base `input` qui incluait des tokens transient (préfix non-cachable). Voir §1.2.

### 1.2 Mesure CTO 2026-06-06 (FEAT 4, run de1a78f4a4f1 → 20260606T182956-87ba)

Source : `console.db` table `token_usage`, agrégé sur la session.

| Agent | input | output | cache_read | cache_write |
|---|---:|---:|---:|---:|
| `code-reviewer` (Sonnet) | 1 | 2 514 | 170 349 | 499 |
| security-reviewer (Sonnet) | 1 | 2 403 | 176 892 | 592 |
| `dev-frontend` | 1 | 971 | 122 013 | 908 |
| spec-compliance (Sonnet) | 1 | 727 | 115 728 | 1 439 |
| `dev-backend` | 1 | 852 | 112 983 | 417 |
| `constitutioner` | 1 | 587 | 82 159 | 2 236 |
| `po` | 1 | 207 | 82 627 | 626 |
| **Total** | **7** | **8 261** | **862 751** | **6 717** |

**Cache hit rate effectif** = `862 751 / (7 + 862 751 + 6 717)` = **99.2 %**.
**Coût Opus 4.7 1M context** estimé : ~**$0.56 / FEAT M**.

### 1.3 Pourquoi l'écart 40.8% → 99.2%

- **2026-05-20** : le run mesuré incluait probablement un agent legacy
  (a11y/perf/dashboard, supprimés v7.0.0) qui re-lisait du contexte non
  partagé avec les autres agents → cache miss artificiel.
- **2026-06-06** : pipeline v7.0.0-alpha avec 12 agents (au lieu de 15-16),
  réutilisation maximale du contexte stack/rules/CLAUDE.md cross-agent,
  caching auto Claude Code en plein régime.
- Le **format de mesure** a aussi changé : v6.x divisait par `(input + cr)`
  excluant `cache_write` du dénominateur, v7.x inclut tous les flux pour
  une vraie fraction.

## 2. Implémentation `cache_control` explicite (P2, optionnel)

Le gain marginal d'ajouter des markers `cache_control: ephemeral` sur les
prompts est désormais estimé à **~1-3% supplémentaires** (vs les 99.2%
auto). Effort 1 jour, ROI faible. Maintenu en backlog v7.2+ pour sessions
batch (CI nocturne, multi-FEAT séquentielles) où le TTL 5min auto peut
expirer entre étapes.

## 2. Stratégie cible

### 2.1 Couches stables (cachables longuement)

Ces fichiers sont **invariants entre invocations d'une même FEAT** et
souvent entre FEATs d'un même projet. Marquer `cache_control: ephemeral`
avec TTL 5 min :

| Layer | Taille typique | Fréquence ré-utilisation |
|---|---:|---:|
| `loader.yml` | ~43 KB | 100 % des invocations dev-*/qa |
| Stacks actifs (backend + frontend + ui + auth + qa) | ~50-80 KB | 100 % |
| Règles consolidées (5 fichiers) | ~50 KB | 100 % |
| `stack.md` (Project Config) | ~3-5 KB | 100 % |
| Constitution (§1-§8) | ~2-5 KB | 100 % |
| Templates pertinents | ~10-15 KB | 100 % |

**Total cachable invariant** : ~150-200 KB ≈ ~40-50 ktokens.

### 2.2 Couches semi-stables (cache courte durée)

- `CLAUDE.md` per-project (~5 KB) : invariant tant que `arch` n'a pas re-tourné.
- Schema.json DB (~5-15 KB) : invariant entre US d'une même FEAT.

### 2.3 Couches volatiles (jamais cachables)

- US courante (chaque dev-* lit 1 US différente)
- Plan inline / from-plan (varie par US)
- Mockup HTML (varie par US)

## 3. Placement des markers `cache_control`

Anthropic API : `cache_control: {type: "ephemeral"}` sur les blocs system
ou content. **Maximum 4 cache breakpoints** par requête.

Stratégie recommandée pour `dev-backend` (le plus coûteux) :

```
[1] System prompt (agent .md inline)              → CACHE 1 (longue durée)
[2] Stacks + règles concaténés                    → CACHE 2 (longue durée)
[3] CLAUDE.md projet + schema.json                → CACHE 3 (courte durée)
[4] US + HTML mockup + plan                       → NO CACHE (volatile)
```

## 4. Implémentation

**v7.0.0** : pas encore implémenté côté harness Claude Code (les calls
Anthropic API par les hooks/agents passent par la Tool Agent qui gère
le caching de manière implicite via prompt assembly order).

**Recommandation v7.1** : instrumenter `loader.yml` avec un nouveau champ
`cache_layer: stable|semi-stable|volatile` par entrée `reads:`. Le
preflight injecte les markers lors de la composition du prompt.

## 5. Mesure cible

Critère release v7.0.0 final :
- Cache hit rate ≥ 60 % sur 3 FEAT M consécutifs (vs 40.8 % actuel)
- Coût Opus / FEAT M ≤ $15 (vs ~$20 actuel sur FEAT 2 mesuré)

## 6. ADR à créer

`ADR-{ts}-governance-cache-strategy-v7` une fois implémenté.

---

*Sources :*
- *audit CTO 2026-05-20 §4.2*
- *report_roi.py output (workspace/output/qa/roi-report-2026-05-20-FEAT2-postfix.json)*
- *Anthropic prompt caching docs (TTL 5 min, max 4 breakpoints, 1.25× write / 0.1× read pricing)*
