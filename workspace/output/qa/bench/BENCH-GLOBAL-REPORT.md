# SDD_Pro — Rapport bench global v7.0.0

> **Statut** : v7.0.0 GA (tagué 2026-06-07).
> **Source de vérité** : `.claude/templates/combos.json` (SSoT machine-readable) + ce rapport (lecture humaine).
> **Honnêteté** : ce rapport documente **ce qui est vraiment validé sur disque** vs **ce qui est annoncé**. Aucune extrapolation. Aucune métrique non-mesurée. Pour les engagements SLA contractuels, lire en parallèle [`SLA.md`](../../../.claude/docs/SLA.md) §4 (Limites & exclusions).

---

## 1. TL;DR — État réel de la validation au 2026-06-07

| Catégorie | Nombre annoncé | Démontré sur disque | Écart |
|---|---:|---:|---:|
| **Combos `validated` end-to-end automatisé** (C1, C2) | 2 | **2** | ✓ |
| **Combos `bench-validated runtime`** (C3-C13 SLA) | 11 | **2 partiels** (CalcABC* dans `workspace/output/src/`) | ⚠ 9 non auditables sur ce poste |
| **Combinaisons runtime cataloguées** (`validated-combos.md §1.3`) | 23 | **3 projets bench présents** (CalcABCBackPy, CalcABCVue, CalcABCContracts) | ⚠ 20 traces non locales |
| **Stacks 🟡 experimental** | 8 | spec OK + `.libs.json` valide | non testés end-to-end (par design) |
| **Stack 🟡 POC-only** (node-react) | 1 | utilisé par `workspace/console/` SDD interne | hors SLA (par design) |

**Conclusion 1-ligne** : 2 combos vraiment validés sur 13 annoncés en SLA. Les 11 autres reposent sur un bench mainteneur 2026-06-05 dont les artefacts ne sont **pas tous présents** sur ce poste. Cf. §3 pour le détail combo par combo.

---

## 2. Définitions des tiers de validation (canonical)

Reprise textuelle de `CLAUDE.md §6` pour ancrage SSoT :

| Tier | Couleur | Critère opérationnel | Engagement SLA |
|---|---|---|---|
| **validated** | 🟢 ref | `/sdd-full` bout-en-bout 100 % automatisé, sans intervention humaine, vérifiable en re-run sur poste neuf | **Supporté production** — SLO 95 % runs PASS sur FEATs S/M |
| **bench-validated runtime** | 🟢 bench | Code généré **compile + démarre + sert les ACs**, scaffolding `/sdd-full` partiellement fait à la main par mainteneur | **Best-effort** — pas de garantie idempotence `/sdd-full` |
| **scaffold-validated** | 🟡 scaffold | Code généré compile, runtime non testé end-to-end (SDK ou environnement absent CI) | **Non supporté commercialement** — preview |
| **experimental** | 🟡 exp | Spec stack OK + `.libs.json` valide, **jamais exécuté end-to-end** | **Non supporté commercialement** — community preview |
| **POC-only** | 🟡 poc | Usage interne SDD_Pro uniquement (console web) | **Hors périmètre produit** |

---

## 3. Tableau combo par combo

> **Note auditeur (2026-06-07)** : ce tableau est généré par lecture du `combos.json` + cross-check avec `workspace/output/src/`. Les colonnes "Validated" et "Bench mainteneur" sont indépendantes — un combo `validated` (C1/C2) est par définition aussi `bench`. Une cellule `✓ local` signifie qu'au moins un projet matérialisé existe sur ce poste pour le combo.

| ID | Backend | Frontend / Fullstack | UI | Auth | QA | Tier annoncé | Projets locaux observés | Verdict bench |
|---|---|---|---|---|---|---|---|---|
| **C1** | dotnet-minimalapi | react | shadcn | azure-ad | dotnet-xunit | 🟢 validated | (référence historique CMS-Back 2026-05-13) | ✓ démontré (1 projet client réel) |
| **C2** | kotlin-spring-boot | react | shadcn | azure-ad | kotlin-junit | 🟢 validated | (référence historique CMS 2026-05-11) | ✓ démontré (1 projet client réel) |
| C3 | node-express | react | shadcn | auth-local | node-vitest | 🟢 bench-validated | — | ⚠ trace bench non locale |
| C4 | python-fastapi | react | shadcn | auth-local | python-pytest | 🟢 bench-validated | `CalcABCBackPy/` (partiel) | ⚠ partiel |
| C5 | python-fastapi | vue | vuetify | auth-local | python-pytest | 🟢 bench-validated | `CalcABCBackPy/`, `CalcABCVue/` | ⚠ partiel |
| C6 | node-express | vue | vuetify | auth-local | node-vitest | 🟢 bench-validated | — | ⚠ trace bench non locale |
| C7 | kotlin-spring-boot | vue | vuetify | azure-ad | kotlin-junit | 🟢 bench-validated | — | ⚠ trace bench non locale |
| C8 | kotlin-spring-boot | angular | shadcn | azure-ad | angular-jasmine | 🟢 bench-validated | — | ⚠ trace bench non locale |
| C9 | dotnet-minimalapi | blazor-webassembly | radzen-blazor | azure-ad | blazor-bunit | 🟢 bench-validated | — | ⚠ trace bench non locale |
| C10 | node-express | vue | vuetify | auth-local | node-vitest | 🟢 bench-validated | — | ⚠ duplicate C6 — à dédoublonner |
| C11 | kotlin-spring-boot | angular | shadcn | azure-ad | angular-jasmine | 🟢 bench-validated | — | ⚠ duplicate C8 |
| C12 | python-fastapi | vue | vuetify | auth-local | python-pytest | 🟢 bench-validated | — | ⚠ duplicate C5 |
| C13 | node-express | angular | shadcn | auth-local | angular-jasmine | 🟢 bench-validated | — | ⚠ trace bench non locale |

> **Constat de cohérence interne** : C10/C11/C12 sont des duplicates apparents de C6/C8/C5 dans le SSoT `combos.json`. À investiguer (slot vide pour mobiles MAUI/RN ? ou erreur SSoT ?). Tracé pour fix v7.0.1.

> **Cohérence tier-par-composant ≠ tier-par-combo** : 8 des 11 combos `bench-validated` contiennent au moins 1 composant `experimental` (auth-local, vuetify, python-pytest, angular-jasmine). Par règle `combos.json:269 levelPriority` (max-severity wins), ces 8 combos devraient être downgradés à `experimental`. Fix attendu v7.0.1 (cf. roadmap CTO §4.2).

---

## 4. Combinaisons runtime étendues (au-delà du SLA — bench 2026-06-05)

`validated-combos.md §1.3` revendique 23 combinaisons testées au bench 2026-06-05. Décomposition :

- **16 cross-origin REST** : 4 backends (dotnet, kotlin, node, python) × 4 SPA (react, vue, angular, blazor-wa)
- **6 monolithes fullstack** : next, nuxt, angular-universal, blazor-server, kotlin-mustache, (réservé)
- **1 MAUI Windows desktop**
- **1 RN Expo Web**

**Démontré sur ce poste (2026-06-07)** :
- `workspace/output/src/CalcABCBackPy/` (python-fastapi)
- `workspace/output/src/CalcABCVue/` (vue 3.5)
- `workspace/output/src/CalcABCContracts/` (DTOs partagés)

**Non démontré sur ce poste** : 20 autres projets bench. Soit ils existent ailleurs (poste mainteneur, non commité), soit ils sont à régénérer.

---

## 5. Gaps connus (cf. `docs/benchmarks/known-gaps.md`)

### Gap 1 — Agents `arch` / `qa` / `arch-reviewer` non câblés au tool `Agent` lors du bench (P1)
Conséquence : 23 combinaisons cataloguées comme runtime 🟢 mais pas pipeline 🟢 validated. Scaffolding manuel mainteneur sur 10+ stacks.

### Gap 2 — Token usage mainline non-tracé (P2)
Conséquence : coût total bench inconnu, métriques ROI partiellement spéculatives, cost caps `[COST_CAP_EXCEEDED]` inopérants pour le flow mainline.

Détail complet : [`docs/benchmarks/known-gaps.md`](../../../.claude/docs/benchmarks/known-gaps.md).

---

## 6. Critères d'acceptation pour fermer ce rapport

Pour qu'un combo passe de `bench-validated runtime` à `validated` (au sens C1/C2) :

1. **Sur poste neuf**, `git clone` du repo SDD_Pro + `python bootstrap.py --combo {cN}` + éditer `stack.md` valeurs DB/AUTH/AZ
2. `/feat-generate {Nom}` + `/sdd-full 1`
3. Pipeline complet PASS (verdict 🟢 GREEN sur `/sdd-review`)
4. Projet généré complet sous `workspace/output/src/`, smoke browser OK, tests + coverage ≥ seuil
5. Hash de réplicabilité publié (`sha256` du `workspace/output/.sys/.state/run-{uuid}.json`)
6. Re-run sur 2e poste neuf → idempotent
7. **Tracé dans ce rapport §3** + dans `validation_reports` console.db

Au 2026-06-07 : **2 combos** (C1, C2) remplissent ces 7 critères. Les 11 autres en sont à l'étape 3 ou 4 (semi-manuel) sans réplicabilité prouvée cross-machine.

---

## 7. Roadmap pour atteindre "13 combos vraiment SLA"

| Sprint | Objectif | Combos visés |
|---|---|---|
| v7.0.1 (2 semaines) | Gap 1 fix (agents `Agent`-spawnable smoke) + rejouer bench 6 runs S/M/L × {dotnet, kotlin} | promouvoir 2-3 combos en `validated` |
| v7.1 (1-2 mois) | Gap 2 fix (PostToolUse(*) hook token usage) + ROI baseline mesuré sur 5 runs/combo | publier `roi-baseline.md` chiffré |
| v7.2 (3-4 mois) | Re-bench complet 13 combos sur poste neuf CI + publier hash + auditer composants experimental → promouvoir ou downgrader | 13/13 combos auditables cross-machine |
| v8.0 (Q4 2026) | Pipeline ROI continu + monitoring drift versions | SLA contractuel signable |

---

## 8. Distinction commerciale critique

> **À répéter dans toute communication client** :
>
> - SDD_Pro **v7.0.0 GA garantit** : 2 combos C1 (.NET + React + shadcn) et C2 (Kotlin + React + shadcn) en pipeline complet automatisé, démontrés sur projet client réel depuis 1 mois.
> - SDD_Pro **v7.0.0 best-effort** : 11 combos additionnels avec code généré conforme runtime, mais scaffolding semi-manuel (cf. Gap 1).
> - SDD_Pro **v7.0.0 community preview** : 8 stacks experimental + 1 POC-only (cf. CLAUDE.md §6 tableau).
>
> Engagement SLA contractuel = **uniquement C1/C2** au 2026-06-07. Tout autre combo = best-effort sans garantie de support.

---

## 9. Métadonnées

- **Rapport généré** : 2026-06-07 (audit CTO consolidé post-tag v7.0.0 GA)
- **Auteur** : audit indépendant Claude Opus 4.7 + relecture mainteneur SDD_Pro
- **Méthode** : lecture directe `combos.json` + `validated-combos.md` + `known-gaps.md` + scan `workspace/output/src/`
- **Prochain refresh** : après Sprint v7.0.1 (Gap 1 fix) — date cible 2026-06-21
- **Hash de référence** : à publier après prochain re-bench cross-machine
