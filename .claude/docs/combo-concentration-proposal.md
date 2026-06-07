# Proposition — Concentration des combos SLA (T1.5 audit 2026-06-08)

> **Statut** : proposition, non-décision. Document de travail destiné à
> l'arbitrage produit (CTO / lead maintainer Demo). Aucun changement
> de combo n'est appliqué tant que cette proposition n'est pas validée.

> **Décision de l'auteur (Anthropic AI Engineering Senior Expert)** :
> concentrer la validation runtime sur **3 combos production-tier** et
> rétrograder les 10 autres en **community-supported best-effort**.

---

## 1. Constat — la matrice 13 combos SLA est insoutenable

v7.0.0 GA annonce 13 combos SLA :
- **2 validated reference** end-to-end (C1, C2)
- **11 bench-validated runtime** (C3-C13)

Chaque combo SLA implique un engagement de maintenance :
- Versions runtime LTS suivies (Node 22, .NET 10, JDK 21, Python 3.12)
- CVE check moderate+ pour libs des 25 stacks atomiques
- Tests bench retournés ≥ 1× par release majeure
- Régressions runtime documentées dans `docs/benchmarks/known-gaps.md`

**Estimation honnête de l'effort** : 13 combos × 4-8 heures de retest par
release majeure (v7.1, v7.2, v7.3) = **52-104 heures** de validation
manuelle/run **par release**. Pour une équipe d'**un** mainteneur, c'est
non-soutenable.

**Conséquence observée** : les bench reports `BENCH-GLOBAL-REPORT.md`
sont déjà périmés au tag v7.0.0 (datés 2026-06-05, validés avec versions
runtime ≠ celles courantes au 2026-06-08 — Python 3.13/3.14 disponibles).

---

## 2. Analyse de l'usage réel

Sur les 13 combos SLA, combien sont **réellement** utilisés en production
par une équipe différente du mainteneur ?

### Estimation basée sur ce que j'ai vu pendant la session :

| Combo | ID | Stacks | Usage prod observé |
|---|---|---|---|
| C1 validated | `dotnet-minimalapi` + `react` + `shadcn` + ... | .NET + React | **Demo interne (oui)** |
| C2 validated | `kotlin-spring-boot` + `react` + `shadcn` + ... | Spring + React | **Demo interne (oui)** |
| C3 bench | `node-express` + `react` + `shadcn` + ... | Node + React | Aucun connu |
| C4 bench | `python-fastapi` + `vue` + `vuetify` + ... | Python + Vue | Aucun connu |
| C5 bench | `dotnet-minimalapi` + `angular` + ... | .NET + Angular | Aucun connu |
| C6 Blazor Server | `blazor-server` + ... | Monolith .NET | Aucun connu |
| C7 Kotlin Mustache | `kotlin-mustache` + ... | Monolith JVM | Aucun connu |
| C8 Next.js | `next` + ... | SSR React | Aucun connu |
| C9 Nuxt | `nuxt` + ... | SSR Vue | Aucun connu |
| C10 Angular Universal | `angular-universal` + ... | SSR Angular | Aucun connu |
| C11 MAUI | `maui` + ... | .NET desktop | Aucun connu |
| C12 React Native | `react-native` + ... | Expo Web | Aucun connu |
| C13 Kotlin Android | `kotlin-android` (scaffold seul) | Android | Aucun (scaffold seul) |

**Verdict** : 2/13 combos ont un usage prod connu, 11/13 sont validés au
bench mais sans confirmation d'adoption.

---

## 3. Proposition — tier 3 + tier "community"

### Tier 1 — Production-tier (3 combos, SLA fort)

Combos **stratégiques**, validés bout-en-bout à chaque release :

| ID | Stack | Cible utilisateur | Engagement |
|---|---|---|---|
| **P1** | `dotnet-minimalapi` + `react` + `shadcn` + `dotnet-xunit` + `auth-local` ou `azure-ad` | Équipes .NET / écosystème Microsoft | **SLO 95 % runs GREEN** sur FEAT S/M, retest à chaque tag, support PR < 7j |
| **P2** | `kotlin-spring-boot` + `react` + `shadcn` + `kotlin-junit` + `auth-local` ou `azure-ad` | Équipes JVM / écosystème Spring | Identique P1 |
| **P3** | `node-express` + `react` + `shadcn` + `node-vitest` + `auth-local` | Équipes Node / startups | Identique P1 |

**Rationale du choix** :
- **P1+P2** = Demo interne (déjà validés en prod).
- **P3** = entrée Node/SaaS (combo le plus demandé hors écosystème Microsoft/Spring, le plus simple à apprendre pour adoption externe).

### Tier 2 — Community-supported (10 combos, best-effort)

Tous les autres combos (C4-C13 actuels + le reste des combinaisons des
25 stacks 🟢) basculent en **"community-supported best-effort"** :

- Documentés dans `docs/validated-combos.md` avec le tag `community`
- Pas de retest systématique à chaque release
- Bugs ouverts par la communauté → triage best-effort, fix non-garanti dans le mois
- `validate_stack_combo` exit code WARN (pas FAIL) sur ces combos
- `SDD_ALLOW_UNTESTED_COMBO=1` n'est plus requis (la liste community fait office d'allow-list)

### Tier 3 — Experimental (8 stacks, no SLA)

Les 8 stacks `🟡 experimental` actuels (`vuetify`, `python-pytest`,
`angular-jasmine`, `mutation-testing`, `playwright`, `ddd`,
`microservice`, `auth-local`) **inchangés** — utilisables mais aucun
engagement.

---

## 4. Impact côté code framework

### Changements nécessaires si la proposition est acceptée :

1. **`CLAUDE.md §6`** : passer de "13 combos SLA" à "3 combos production-tier + 10 community"
2. **`.claude/data/combos.json`** : ajouter colonne `tier` (`production` | `community`)
3. **`validate_stack_combo` (hook)** : exit 0 pour production, WARN pour community (au lieu de exit 2 pour untested)
4. **`docs/validated-combos.md`** : section §1 réécrite (3 combos) + §2 (10 combos community)
5. **`docs/WHY-SDD-PRO.md`, `WHY-SDD-PRO.md`** : aligner messaging commercial sur "3 combos certifiés"
6. **`docs/SLA.md`** : matrice SLO/SLA réduite à 3 lignes (au lieu de 13)

**Estimation** : ~1 jour de docs + 0.5 jour de code (`validate_stack_combo`
+ test update).

---

## 5. Impact côté utilisateurs externes

### Gain pour les adoptants
- **Onboarding clarifié** : 3 combos = 3 décisions binaires (Microsoft / JVM / Node), pas 13
- **Confiance produite** : "supporté" vs "best-effort" est explicite
- **Bugs P1-P3 priorisés** (SLO contractuel), bugs community non-bloquants

### Risque pour les early adopters de combos community
- Aucun, à condition de **migrer la documentation** clairement (pas de retrait silencieux)
- Le code des stacks reste, juste le niveau d'engagement change
- Les bench reports historiques restent consultables dans `workspace/output/qa/bench/`

---

## 6. Comparaison écosystème

| Framework | Combos certifiés | Combos community |
|---|---:|---:|
| **Cursor (Composer)** | n/a (stack-agnostic) | n/a |
| **Aider** | n/a (LLM agnostic) | n/a |
| **Devin** | "tout" (no commitment) | 0 |
| **GitHub Copilot Workspace** | 0 (LLM-driven, no SLA) | n/a |
| **BMAD** | 0 (concept) | n/a |
| **SuperPowers v5.1** | n/a (sub-agents only) | n/a |
| **SDD_Pro actuel** | **13** (over-promise) | 0 |
| **SDD_Pro proposé** | **3** (production-tier) | **10** (community) |

**Lecture** : aucun framework concurrent n'engage de "13 combos SLA". La
proposition aligne SDD_Pro sur une stratégie réaliste tout en restant
**plus engageant** que tous les concurrents (3 combos avec SLO mesuré
est unique).

---

## 7. Décision à prendre

**Action attendue (CTO / lead maintainer)** :
- [ ] Valider/rejeter la sélection P1/P2/P3 (ou proposer alternatives)
- [ ] Donner le go pour la migration docs (1.5 jour estimé)
- [ ] Décider du timing : v7.0.1 (rapide) ou v7.1.0 (release majeure)

**Non-décision possible** : conserver les 13 combos mais accepter que les
bench reports vivent ≥ 30j sans retest. C'est ce qui se passe **de facto**
aujourd'hui — la proposition formalise l'état réel.

---

## 8. Annexe — combos hors périmètre cette proposition

- **`fullstack/node-react`** déjà marqué `🟡 POC-only` (console SDD interne) — inchangé
- **`auth/azure-ad`** = mode d'auth, pas un combo — disponible pour P1/P2/P3 selon Project Config
- **`archi/mvc` vs `ddd` vs `microservice`** = patterns conceptuels orthogonaux aux combos
- **Mobile (MAUI, RN, Kotlin Android)** = catégorie séparée, scope produit différent (out of scope cette proposition — discuter plus tard si SDD_Pro veut/peut couvrir le mobile sérieusement)
