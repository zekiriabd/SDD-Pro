# ADR-20260605T150000 — Bench Stack Versions Deviation (post-bench 2026-06-05)

- **Statut** : Accepted
- **Date** : 2026-06-05
- **Auteur** : Tech Lead (audit CTO bench)
- **Phase** : Framework governance

---

## Context

Session bench massif 2026-06-05 (~6h, 16 FEATs, 23 combinaisons runtime) a généré 14 projets sur 13 stacks distincts. **12 stacks** ont nécessité un **bump de versions** par rapport au pin `{stack}.libs.json` car le pin original :
- Pointe sur une version trop récente non encore stable (Spring Boot 4.0.6, Tailwind v4, Pydantic 2.10 sur Py3.14)
- Pointe sur une version refusée par les templates SDK actuels (.NET MAUI `-f net8.0` rejeté par SDK 10)
- Aurait introduit des bugs runtime (CVE AutoMapper 16, breaking changes Vue 4 alpha)

Sans backfill ADR, ces déviations restent silencieuses → contradiction avec règle "stack-completeness §0 → bump STS exception via ADR `runtime-sts-exception`".

---

## Decision

Documenter en **1 ADR consolidé** les 12 déviations stack-vs-runtime observées lors du bench. Cet ADR sert de **précédent** pour les futurs benchs : les pin `libs.json` sont des cibles théoriques, le bump runtime est légitime tant qu'il préserve les conventions §1.4 du stack et passe les tests unitaires.

---

## Déviations bench (12)

| # | Stack | Pin `.libs.json` | Bump runtime | Raison |
|---|---|---|---|---|
| 1 | `backend/kotlin-spring-boot` | Spring Boot 4.0.6 + Kotlin 2.3.21 + Java 21 | **3.3.5 + 2.0.21 + Java 21** | v4 trop récent 2026-06-05, écosystème pas prêt |
| 2 | `backend/dotnet-minimalapi` | net10.0 | **net10.0** maintenu (build SDK 10 OK) | conforme |
| 3 | `backend/dotnet-minimalapi` lib | AutoMapper 16.1.1 | **AutoMapper 13.0.1** | v16 breaking changes config, CVE NU1903 sur les deux versions |
| 4 | `backend/python-fastapi` | Python 3.12 + Pydantic 2.10.3 + FastAPI 0.115 + Uvicorn 0.32 | **Python 3.14.5 + Pydantic 2.13.4 + FastAPI 0.136 + Uvicorn 0.49** | `pydantic-core 2.10.3` no-wheel Py3.14 → `pydantic>=2.11` |
| 5 | `frontend/react` (composants bench) | React 19 + Vite 6 + Tailwind v4 + Turborepo + TanStack Router/Query | **React 18.3.1 + Vite 5.4.11 + Tailwind v3.4.14 + projet plat + composants vanilla** | écosystème React 19/Vite 6/Tailwind v4 instable 2026-06-05, bench trivial → overkill |
| 6 | `frontend/vue` | Vue 3.5.13 | **Vue 3.5.35** (auto-bump npm) | npm résout plus récent |
| 7 | `frontend/angular` | Angular 19 | **Angular 18** (template `ng new --strict --defaults`) | template par défaut SDK actuel |
| 8 | `frontend/blazor-webassembly` | (template legacy `blazorwasm`) | **`dotnet new blazor --interactivity WebAssemblyOnly --framework net8.0`** | template moderne SDK 10 |
| 9 | `fullstack/blazor-server` | (template legacy `blazorserver` rejeté) | **`dotnet new blazor --interactivity Server --framework net8.0`** | template legacy refuse net8.0 sur SDK 10 |
| 10 | `fullstack/next` | Next.js 15.1.0 + React 19 | **Next.js 15.5.19 + React 19** | npm résout plus récent automatiquement |
| 11 | `fullstack/nuxt` | Nuxt 3.15.0 | **Nuxt 4.4.7 + Nitro 2.13.4 + Vue 3.5.35** | template `nuxi init --template v4` choisi pour stabilité |
| 12 | `mobiles/maui` | net8.0 | **net9.0** (`dotnet new maui -f net8.0` rejeté SDK 10) | SDK 10 supporte net9.0/net10.0 uniquement |

---

## Consequences

**Positifs :**
- Bench démontre que SDD_Pro génère du code **fonctionnel runtime** avec versions adaptées au SDK/runtime du poste
- 23 combinaisons runtime validées avec bumps documentés → reproductibles
- Précédent ADR pour futurs benchs : déviation pin acceptable si conventions §1.4 respectées + tests passent

**Négatifs / dette acceptée :**
- 12 `libs.json` deviennent **obsolètes** vis-à-vis du runtime testé → à rebumper en passe systématique post-bench (chantier C2)
- Sans bump des `libs.json`, prochain `/arch-init` génèrera du code aux mêmes pin obsolètes → bugs runtime garantis
- L'agent `arch` ne consulte pas cet ADR → les bumps ne se propagent pas automatiquement
- Risque drift : les bumps locaux ne sont pas synchronisés cross-projet (chaque projet bench a ses propres bumps)

---

## Alternatives considérées

- **Bumper systématiquement les 12 `libs.json`** : effort 1-2j, garantit cohérence. Reporté en chantier C2 distinct.
- **1 ADR par déviation** : 12 fichiers ADR. Trop lourd, moins lisible que 1 consolidé.
- **Ignorer (statu quo)** : laisse les bumps non-tracés, viole la règle stack-completeness §0. Rejeté.
- **Bump le moins agressif possible** (rollback partiel sur chaque stack) : déjà ce qui est fait (Spring 4→3 préfère le LTS plus stable).

---

## Liens

- Bench rapport : `workspace/output/qa/bench/BENCH-GLOBAL-REPORT.md` (§31 matrice 14 FEATs × 22 combinaisons)
- Tests unitaires rapport : `workspace/output/qa/bench/BACKEND-UNIT-TESTS-REPORT.md` (37/37 passed)
- Rule : `.claude/rules/library-and-stack.md §0 (Runtime LTS)` + §7 (Pièges runtime documentés)
- Script : `.claude/python/sdd_scripts/validate_stack_combo.py` (déterministe, désormais câblé hook PreToolUse — cf. C5)
- Future ADR : `runtime-pydantic-py314-bump` (futur, si Python 3.14 devient LTS)

---

*Cette ADR officialise les déviations runtime du bench 2026-06-05. Les 12 `libs.json` doivent être bumpés en passe systématique (chantier C2) avant tag v7.0.0 GA pour synchroniser le catalogue machine avec la réalité runtime.*
