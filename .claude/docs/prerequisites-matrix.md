# Prerequisites Matrix — Installations requises par combo SDD_Pro

> Audience : Tech Leads et DSI évaluant l'adoption SDD_Pro. Cible :
> identifier en < 5 min ce qu'il faut installer sur la machine du dev
> selon le combo de stacks visé.

> Référence canonique : `@docs/validated-combos.md` (13 combos SLA v7.0.0).
> Cette matrice synthétise les **prérequis runtime** par combo, mis à
> jour au 2026-06-08.

---

## 1. Pré-requis universels (toutes machines, tous combos)

| Outil | Version mini | Vérification | Où installer |
|---|---|---|---|
| **Git** | 2.40+ | `git --version` | https://git-scm.com |
| **Python** | 3.12 (LTS) | `python --version` | https://python.org (Windows) ou apt/brew |
| **Claude Code CLI** | 0.5+ | `claude --version` | https://claude.com/claude-code |
| **VSCode** (recommandé) | 1.85+ | `code --version` | https://code.visualstudio.com |
| **sqlite3 CLI** | 3.40+ | `sqlite3 --version` | inclus macOS/Linux ; Windows : https://sqlite.org/download.html |

> **Note Windows** : PowerShell 5.1+ requis (préinstallé). WSL2 fortement
> recommandé pour les combos backend Node/Python (compatibilité paths).

---

## 2. Matrice par combo (13 combos SLA v7.0.0)

### Combo C1 — .NET + Blazor WebAssembly (validated reference)
| Outil | Version | Notes |
|---|---|---|
| .NET SDK | **10.0** (LTS Nov 2025) | https://dot.net |
| EF Core tools | 9.x | `dotnet tool install --global dotnet-ef` |
| SQL Server LocalDB **ou** PostgreSQL | 2022 / 16+ | LocalDB inclus Visual Studio |
| Visual Studio 2022 17.8+ **ou** VS Code + C# Dev Kit | — | optionnel mais recommandé |

### Combo C2 — Kotlin Spring Boot + React (validated reference)
| Outil | Version | Notes |
|---|---|---|
| JDK | **21** (LTS Sep 2023) | https://adoptium.net |
| Gradle | 8.5+ | wrapper inclus dans le scaffold |
| Kotlin compiler | **2.0.21** (LTS-aligned) | bundled with Gradle plugin |
| Node.js | **22.x** (LTS "Jod") | https://nodejs.org |
| pnpm | 9+ | `corepack enable && corepack prepare pnpm@latest --activate` |
| PostgreSQL **ou** MySQL | 16+ / 8+ | local ou Docker |

### Combo C3 — Node Express + React + Prisma (bench-validated runtime)
| Outil | Version | Notes |
|---|---|---|
| Node.js | **22.x** (LTS) | https://nodejs.org |
| pnpm | 9+ | corepack |
| PostgreSQL | 16+ | Prisma support natif |
| OpenSSL | 3.x | requis par Prisma sur Linux |

### Combo C4 — Python FastAPI + Vue 3 (bench-validated runtime)
| Outil | Version | Notes |
|---|---|---|
| Python | **3.12** (LTS) — 3.13 acceptable | éviter 3.14 (pydantic-core sans wheel) |
| uv **ou** pip | uv 0.4+ / pip 24+ | uv recommandé (10× plus rapide) |
| Node.js | **22.x** (LTS) | pour le frontend Vue |
| PostgreSQL | 16+ | SQLAlchemy async support |

### Combo C5 — .NET + Angular 19 (bench-validated runtime)
| Outil | Version | Notes |
|---|---|---|
| .NET SDK | **10.0** | comme C1 |
| Node.js | **22.x** (LTS) | requis par Angular CLI |
| Angular CLI | 19+ | `npm install -g @angular/cli` |
| PostgreSQL **ou** SQL Server | 16+ / 2022 | au choix |

### Combos C6-C13 — Fullstack monolithiques
- **C6 Blazor Server** : .NET 10 + SQL Server / PostgreSQL
- **C7 Kotlin Mustache** : JDK 21 + Gradle + PostgreSQL
- **C8 Next.js** : Node 22 + PostgreSQL (App Router monolith)
- **C9 Nuxt.js** : Node 22 + PostgreSQL (SSR monolith)
- **C10 Angular Universal** : Node 22 + Angular CLI 19 + PostgreSQL
- **C11 MAUI Windows** : .NET 10 + Visual Studio 2022 + MAUI workload (`dotnet workload install maui`)
- **C12 React Native (Expo Web)** : Node 22 + Expo CLI (`npm i -g expo-cli`)
- **C13 Kotlin Android scaffold** : JDK 21 + Android Studio + Android SDK 34+ (scaffold uniquement, pas de build runtime garanti)

---

## 3. Outils de qualité (tous combos)

Ces outils sont installés automatiquement par `arch` Phase A à partir
des `.libs.json` du stack QA actif. **Pas d'install manuel requis**, mais
ils consomment du disque :

| Outil | Combo concerné | Taille install approximative |
|---|---|---|
| xUnit + coverlet | .NET | ~80 MB |
| Vitest + Istanbul | Node/React/Vue | ~60 MB |
| pytest + coverage.py | Python | ~30 MB |
| JUnit 5 + JaCoCo | Kotlin | ~70 MB (déjà bundled avec Spring) |
| bUnit | Blazor | ~50 MB |
| Playwright | toutes UI | ~250 MB (download browsers une fois) |
| axe-core CLI | toutes UI | ~40 MB |
| Lighthouse CI | toutes UI | ~80 MB |

Total disque CI : **~500 MB** par projet (dépend du combo).

---

## 4. Connectivité réseau requise

L'agent `arch` Phase A fetch les dépendances depuis les registries
canoniques :

| Combo | Registries | Bandwidth (1ère install) |
|---|---|---|
| .NET | `api.nuget.org`, `dot.net` | ~500 MB |
| Node | `registry.npmjs.org` | ~300 MB (peut être 1 GB+ avec React+TanStack) |
| Python | `pypi.org` | ~100 MB |
| Kotlin/JVM | `repo1.maven.org`, `plugins.gradle.org` | ~400 MB |

**Proxies d'entreprise** : configurer `npm config set registry`, `pip
config set global.index-url`, `gradle.properties` `proxy.host=...`. Pas de
support natif SDD_Pro — c'est à la charge de la DSI.

**Offline mode** : non supporté en v7.0.0. Roadmap v7.3 : cache local
warmé (`docs/cache-strategy.md`).

---

## 5. Verification automatique

Lancer **avant** le premier `/sdd-bootstrap` :

```bash
python bootstrap.py --check-prereqs --combo c1
```

Sortie attendue :
```
[OK] git 2.43.0
[OK] python 3.12.7
[OK] claude CLI 0.5.2
[OK] dotnet 10.0.0
[OK] sqlite3 3.45.1
[OK] postgresql connectivity localhost:5432
=== Prerequisites for combo c1 (dotnet-minimalapi + blazor-webassembly) ===
All prerequisites OK. You can run /sdd-bootstrap.
```

Si un outil manque, le script affiche le lien de download et exit `1`.

---

## 6. Vérification manuelle (si bootstrap.py --check-prereqs indisponible)

### Combo Node-based (C2/C3/C4 frontend, C8/C9 fullstack)
```bash
node --version          # v22.x.x
pnpm --version          # 9.x.x
git --version           # git version 2.40+
```

### Combo .NET (C1/C5/C6/C11)
```bash
dotnet --version        # 10.0.x
dotnet --list-sdks      # vérifier qu'il y a bien la 10.0
dotnet ef --version     # 9.x.x
```

### Combo JVM (C2 backend, C7)
```bash
java -version           # openjdk 21.x.x
gradle --version        # 8.5+
kotlinc -version        # 2.0.21
```

### Combo Python (C4 backend)
```bash
python --version        # Python 3.12.x
uv --version            # uv 0.4+
psql --version          # 16+
```

---

## 7. Espace disque recommandé

| Usage | Espace |
|---|---|
| SDD_Pro framework (Python helpers, .claude/) | ~30 MB |
| Un projet SDD_Pro généré (combo C1 .NET+Blazor) | ~500 MB (bin/obj inclus) |
| Idem combo C2 (Kotlin+Spring+React) | ~800 MB (Gradle cache + node_modules) |
| node_modules typique (React + TanStack + Radix UI) | ~400 MB |
| ~/.nuget/packages global cache | ~2 GB après quelques projets |
| ~/.gradle/caches | ~1.5 GB après quelques projets |

**Recommandation** : SSD 256 GB minimum, 512 GB confortable.

---

## 8. Tooling éditeur recommandé

| Éditeur | Combo | Extensions clés |
|---|---|---|
| **VSCode** | tous | "Claude Code" (officielle), C# Dev Kit, Vue Volar, Angular Language Service, Python, GitLens |
| **JetBrains Rider** | .NET | C# + Blazor support natif |
| **JetBrains IntelliJ IDEA** | Kotlin/Spring | Spring Boot plugin + Kotlin plugin |
| **JetBrains WebStorm** | Node frontends | Vue/React/Angular support natif |
| **JetBrains PyCharm** | Python FastAPI | bien |
| **Visual Studio 2022** | .NET + MAUI | requis pour MAUI workload |

---

## 9. CI/CD prerequisites

Le CI auto-généré par `arch` (template `templates/ci-quality.github-actions.yml.template`)
fait tourner les checks acceptance gate (test/lint/build/coverage) +
axe-core + Lighthouse + sqlite3 ingest. Prérequis runner :

- **GitHub Actions** : runner `ubuntu-22.04` ou `windows-2022` selon stack
- **GitLab CI** : image `mcr.microsoft.com/dotnet/sdk:10.0` ou `node:22-bullseye`
- **Jenkins** : agent JDK 21 (pour Kotlin) ou Node 22 (pour SPA)
- **Azure DevOps** : `windows-latest` (combos .NET) ou `ubuntu-latest`

Le template CI est lisible et ajustable — voir `arch.md §STEP 4.7` pour
le placement (`workspace/output/src/{Project}/.github/workflows/quality.yml`).

---

## 10. Support adoption DSI

Si votre DSI bloque certains downloads (proxies, listes blanches), pré-warmer :

1. **Mirror NuGet/npm/Maven** dans Artifactory / Sonatype Nexus
2. **Pinned versions** dans le `.libs.json` du stack — pas de fetch latest
3. **Cache CI** : utiliser `actions/cache@v4` ou équivalent pour les
   répertoires `~/.nuget/packages`, `~/.gradle/caches`, `node_modules`

Contact framework : Softwe3 SDD_Pro maintenance team (interne).
