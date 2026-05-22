# SDD_Pro — Baseline ROI (résultats PoC)

> **Squelette à remplir** post-exécution du PoC ROI (cf.
> `@.claude/docs/poc-roi-methodology.md`). Toute valeur ci-dessous
> marquée `<TBD>` doit être remplacée par une **mesure réelle**
> issue de `console.db` + journal humain.
>
> **Statut au 2026-05-20** : décision audit prise — bench focalisé
> **FEAT M Kotlin uniquement** pour rc1 (1 cellule mesurée > 6 bâclées).
> Runbook : `@.claude/docs/benchmarks/runbook-bench-m.md`.
> Cellules S, L, C1 dotnet : reportées post-rc1.
>
> **Cibles critères de release v7.0.0-rc1** (sync §5.2) :
> - FEAT M wall-clock : framework ≤ humain / 5
> - FEAT M coût $ : framework ≤ humain / 50
> - FEAT M coverage : framework ≥ humain - 5 pts
> - FEAT M AC verified : framework ≥ 90 %
> - Variance 3 runs : σ ≤ 15 % wall-clock & coût

---

> ## ⚠️ Périmètre de mesure (anti-R2 — honnêteté méthodologique)
>
> Ajouté 2026-05-22 après critique CTO : *« la variance artificielle introduite
> par des UI mocks HTML statiques + backend généré depuis spec figée mesure
> surtout l'orchestration framework, pas la charge fonctionnelle réelle ».*
>
> ### Ce que ce bench mesure
> - **Orchestration framework** : timing pipeline, gates, parallélisme, déterminisme LLM
> - **Génération code depuis spec figée** : FEAT M template + 3 mockups HTML statiques + DDL postgres seed
> - **Coût LLM + wall-clock + verdict auditors + coverage** sur scope spec-fixe
> - **Variance stochastique LLM** sur input strictement identique
>
> ### Ce que ce bench NE mesure PAS (à ne JAMAIS prétendre)
> - **Adéquation UI/UX réelle** sous usage utilisateur — les mockups sont des
>   stubs HTML statiques, pas un prototype testé en accessibilité ou usabilité
> - **Bugs surfaçant post-déploiement** — la review humaine 1h ≠ une revue prod
>   ni un canary deploy
> - **Résilience runtime, perf charge, observabilité, sécurité post-pentest**
> - **Variance "produit"** — edge cases métier non spécifiés, clients réels,
>   imprévus opérationnels
> - **Coût total cycle de vie** — déploiement, monitoring, évolutions, debt
>   accumulée, support, migrations
>
> ### Implication pour la publication
> La phrase publiable est :
>
> > *« Sur la génération de code conforme à une spec figée (FEAT M + mockups
> > HTML), le framework livre en X minutes et $Y vs Z h baseline humaine
> > codant la même spec sans IA. »*
>
> **PAS** :
>
> > ~~« Le framework remplace un dev senior pour livrer un produit en prod. »~~
>
> Cette nuance évite que R2 (claim ROI surévalué) ne resurgisse dès la
> première démo client critique. Le scope mesuré est nécessaire mais
> **insuffisant** pour conclure au remplacement humain end-to-end ; il
> qualifie le **gain sur la phase code-generation isolée**, qui reste une
> phase load-bearing d'un cycle produit.
>
> ### Action requise au moment de remplir §3 FEAT M
> Toute cellule chiffrée doit être suffixée du label `[scope: code-gen from
> fixed spec]` ou regroupée sous un en-tête de tableau le rappelant.
> Les comparatifs `Ratio humain/framework` ne doivent **jamais** être
> extrapolés en "gain produit total".

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
