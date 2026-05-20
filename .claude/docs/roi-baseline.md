# SDD_Pro — Baseline ROI (résultats PoC)

> **Squelette à remplir** post-exécution du PoC ROI (cf.
> `@.claude/docs/poc-roi-methodology.md`). Toute valeur ci-dessous
> marquée `<TBD>` doit être remplacée par une **mesure réelle**
> issue de `console.db` + journal humain.
>
> **Statut au 2026-05-19** : aucune mesure. À exécuter avant tag `v7.0.0`
> (cf. `ADR-20260519T193000-governance-roi-poc §8` critères de release).

---

## 1. Méta

| Champ | Valeur |
|---|---|
| Date du PoC | `<TBD>` |
| Version framework | `<TBD>` (cible v7.0.0) |
| Tech Lead opérateur | `<TBD>` |
| Reviewer indépendant | `<TBD>` |
| Machine de bench | `<TBD>` (CPU, RAM, OS) |
| Modèles LLM utilisés | Sonnet 4.6, Opus 4.7, Haiku 4.5 |
| Pricing appliqué | `$3/M input, $15/M output, $0.30/M cache read` (Sonnet 4.6) |
| Stack figé | `dotnet-minimalapi × react × shadcn × postgresql × azure-ad` |

---

## 2. FEAT S — Trivial

### 2.1 Baseline humaine

| Métrique | Valeur |
|---|---:|
| Heures-homme | `<TBD>` h |
| Coût @ 150 $/h | `<TBD>` $ |
| Coverage lines | `<TBD>` % |
| AC verified (sur 5) | `<TBD>` |
| Quality issues (serious+) | `<TBD>` |
| Bugs review (1 h indep) | `<TBD>` (critical: `<TBD>`) |
| Lignes code | `<TBD>` |

### 2.2 Framework (3 runs)

| Run | Wall-clock | Tokens input | Tokens output | Tokens cache | Coût $ |
|---|---:|---:|---:|---:|---:|
| Run 1 | `<TBD>` min | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` |
| Run 2 | `<TBD>` min | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` |
| Run 3 | `<TBD>` min | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` |
| **Médiane** | `<TBD>` min | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` |
| **Variance** | `<TBD>` % | `<TBD>` % | `<TBD>` % | `<TBD>` % | `<TBD>` % |

### 2.3 Verdict comparatif

| Métrique | Humain | Framework (médiane) | Ratio | Verdict |
|---|---:|---:|---:|---|
| Wall-clock | `<TBD>` h | `<TBD>` h | `<TBD>` | 🟢/🟡/🔴 |
| Coût $ | `<TBD>` | `<TBD>` | `<TBD>` | 🟢/🟡/🔴 |
| Coverage lines | `<TBD>` % | `<TBD>` % | `<TBD>` pts | 🟢/🟡/🔴 |
| AC verified | `<TBD>` | `<TBD>` | `<TBD>` | 🟢/🟡/🔴 |
| Quality issues | `<TBD>` | `<TBD>` | `<TBD>` | 🟢/🟡/🔴 |
| Bugs review | `<TBD>` | `<TBD>` | `<TBD>` | 🟢/🟡/🔴 |

**Verdict global FEAT S** : `<TBD>`

---

## 3. FEAT M — Moyen

### 3.1 Baseline humaine
*(idem structure §2.1)*

### 3.2 Framework (3 runs)
*(idem structure §2.2)*

### 3.3 Verdict comparatif
*(idem structure §2.3)*

**Verdict global FEAT M** : `<TBD>`

---

## 4. FEAT L — Complexe

### 4.1 Baseline humaine
*(idem structure §2.1)*

### 4.2 Framework (3 runs)
*(idem structure §2.2)*

### 4.3 Cycles correctifs manuels

Le framework peut nécessiter des corrections Tech Lead post-`/sdd-full`.
Mesurer :

| Cycle | Cause | Action | Δ tokens additionnels | Δ wall-clock |
|---|---|---|---:|---:|
| C1 | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` |
| C2 | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` |
| ... | ... | ... | ... | ... |

### 4.4 Verdict comparatif

*(idem structure §2.3 + colonnes "avec cycles correctifs")*

**Verdict global FEAT L** : `<TBD>`

---

## 5. Synthèse globale

### 5.1 Ratio coût-temps cumulé (3 FEATs)

| | Humain | Framework | Économie |
|---|---:|---:|---:|
| Wall-clock total | `<TBD>` h | `<TBD>` h | `<TBD>` % |
| Coût total $ | `<TBD>` | `<TBD>` | `<TBD>` % |
| AC verified moyen | `<TBD>` % | `<TBD>` % | `<TBD>` pts |
| Coverage moyen | `<TBD>` % | `<TBD>` % | `<TBD>` pts |

### 5.2 Critères de release v7.0.0 (cf. methodology §8)

| Critère | Cible | Mesuré | Statut |
|---|---|---:|:---:|
| FEAT M wall-clock | framework ≤ humain / 5 | `<TBD>` | 🟢/🔴 |
| FEAT M coût $ | framework ≤ humain / 50 | `<TBD>` | 🟢/🔴 |
| FEAT M coverage | framework ≥ humain - 5 pts | `<TBD>` | 🟢/🔴 |
| FEAT M AC verified | framework ≥ 90 % | `<TBD>` | 🟢/🔴 |
| FEAT M quality serious+ | framework ≤ humain + 50 % | `<TBD>` | 🟢/🟡/🔴 |
| Variance 3 runs | ≤ 15 % écart-type | `<TBD>` | 🟢/🟡/🔴 |

**Release v7.0.0 autorisée ?** `<TBD>` (toutes les colonnes Statut doivent être 🟢 ou 🟡)

---

## 6. Cas où SDD_Pro N'EST PAS le bon outil

À documenter **explicitement** (anti-cherry-pick, cf. methodology §7.1) :

- `<TBD>` (e.g., tasks triviales 30 min — humain plus rapide)
- `<TBD>` (e.g., refactoring code legacy)
- `<TBD>` (e.g., debug runtime post-prod)
- ...

---

## 7. Historique inter-versions

À enrichir à chaque MAJOR (v8.0, v9.0, ...) — cf. methodology §6.3.

| Version | Date | FEAT S coût $ | FEAT M coût $ | FEAT L coût $ | Δ vs précédent |
|---|---|---:|---:|---:|---|
| v7.0.0 | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` | baseline |
| v7.1.0 | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` |
| v8.0.0 | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` |

---

## 8. Pointers

- `@.claude/docs/poc-roi-methodology.md` — méthodologie complète
- `workspace/output/.sys/.context/adrs/ADR-20260519T193000-governance-roi-poc.md` — décision + plan + critères release
- `@.claude/python/sdd_scripts/bench_run.py` *(à créer v7.0.0)* — agrégateur DB → table comparative auto
- `@.claude/python/sdd_scripts/report_token_usage.py` — agrégation tokens existante
- `@.claude/python/sdd_scripts/query_console_db.py` — read queries SQL
