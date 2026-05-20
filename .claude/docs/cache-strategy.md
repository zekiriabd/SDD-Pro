# SDD_Pro — Prompt Caching Strategy (v7.0.0 P0-8)

## 1. Baseline mesurée (2026-05-20)

Source : `workspace/output/qa/roi-report-2026-05-20-FEAT2-postfix.json`.

| Métrique | Valeur |
|---|---:|
| Cache hit rate global (FEAT 2) | **40.8 %** |
| `input` tokens (full price) | 1 183 153 |
| `cache_read` tokens (90 % discount) | 816 432 |
| `cache_creation` tokens (1.25× premium) | 20 210 |

**Constat** : 40.8 % de cache hit = milieu de tableau. Le **gain restant
captable est ~50 %** du coût Opus (estimé ~$8-12 par FEAT M) si on
atteint 70-80 % de cache hit rate via `cache_control` markers explicites.

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
