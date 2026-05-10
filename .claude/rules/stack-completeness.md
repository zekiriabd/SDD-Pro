# Règle — Stack Completeness (anti-derive sur les librairies)

## Principe

Quand un agent dev-* (`dev-backend`, `dev-frontend`) a besoin d'une
**librairie** pour matérialiser une User Story, cette librairie DOIT
figurer **explicitement** dans la section §2.4 (Librairies pinnées) du
stack actif correspondant (`.claude/stacks/{cat}/{stack-id}.md`).

Si la librairie n'y figure pas → **STOP + ERROR**. Pas d'installation
"silencieuse", pas de "découverte autonome", pas de "dernière version
trouvée sur Stack Overflow". Le Tech Lead arbitre.

Cette règle est **load-bearing pour la sécurité, la traçabilité et la
reproductibilité** des projets générés. Elle prévient :
- L'introduction silencieuse de librairies obsolètes ou vulnérables
- La fragmentation du stack entre projets
- Les erreurs de scaffolding (lib installée mais pas dans le `.csproj` /
  `package.json` / `requirements.txt` / `build.gradle.kts`)
- Les faux-amis (lib similaire au nom mais usage différent)

---

## 1.0 Source de vérité : catalogue JSON `.libs.json` (depuis 2026-05-07)

Chaque stack a désormais **deux fichiers compagnons** :

| Fichier | Rôle | Audience |
|---|---|---|
| `.claude/stacks/{cat}/{stack-id}.md` | Documentation humaine : architecture, conventions, pièges, patterns | Tech Lead, agents (lecture passive du contexte applicatif) |
| `.claude/stacks/{cat}/{stack-id}.libs.json` | **Catalogue machine** : versions, libs core, libs on-demand, plugins, triggers regex | Agent `arch` (install), agent `dev-backend` (capability gating), scripts de validation |

**Le `.libs.json` est la source de vérité** pour tout ce qui touche à
l'installation et la résolution de dépendances. Le `.md` ne doit plus
contenir de table `§2.4` éditée manuellement — elle est régénérée à
partir du JSON via `sync-stack-md.ps1`.

### Schéma JSON

`.claude/templates/libs-catalog.schema.json` (JSON Schema draft 2020-12).

Structure résumée :
```json
{
  "stackId": "kotlin-spring-boot",
  "category": "backend",
  "schemaVersion": 1,
  "buildSystem": "gradle | dotnet | npm | pnpm | yarn | maven | pip | poetry | uv | cargo | go-mod",
  "manifest": { "files": [...], "versionCatalogPath": "..." },
  "versions": { "kotlin": "2.3.21", "spring-boot": "4.0.6" },
  "core":     [ { "id", "module", "versionRef", "rationale", "installCommand", "license" } ],
  "onDemand": [ { "id", "module", "versionRef", "rationale", "installCommand",
                  "capability", "triggers": [...], "alternative": false, "license" } ],
  "plugins":  [ { "id", "versionRef", "rationale" } ]
}
```

### Workflow agent

**arch (Phase A, bootstrap)** :
1. Pour chaque stack actif, charger `{stack-id}.libs.json`
2. Pour chaque `core[].installCommand`, substituer `{BackendName}`,
   `{AppName}`, `{LibName}`, `{AppNamespace}`, `{version}` puis exécuter
3. Pour chaque `plugins[]`, configurer le manifest (Gradle DSL,
   Maven `<plugin>`, etc.)
4. Si `Capabilities: [...]` dans `## Project Config`, forcer l'install
   des libs `onDemand[]` matchant ces capabilities au bootstrap

**dev-backend (STEP 5.bis, capability gating)** :
1. Charger `{stack-id}.libs.json`
2. Invoquer `detect-capabilities.ps1` qui matche les `triggers[]` regex
   contre le texte de l'US courante + ACs
3. Pour chaque capability détectée, installer la lib `onDemand[]`
   correspondante (default + override Project Config)

### Scripts

- **`.claude/scripts/validate-libs-catalog.ps1`** — valide tous les
  `.libs.json` contre le schéma + checks (versionRef pointe sur clé
  existante, capability/triggers pour onDemand, kebab-case versions,
  pre-release warning, etc.). Lancer après toute édition d'un catalogue.
- **`.claude/scripts/sync-stack-md.ps1 -StackId {id}`** — régénère
  `§2.4` du `.md` à partir du `.libs.json` (tableau lisible humain
  + triggers + plugins). Idempotent. `-DryRun` pour preview.

### Maintenance — mettre à jour une version

```
1. Éditer .claude/stacks/{cat}/{stack-id}.libs.json
   → modifier versions.{key} (1 ligne)
2. .claude/scripts/validate-libs-catalog.ps1
   → vérifier cohérence
3. .claude/scripts/sync-stack-md.ps1 -StackId {stack-id}
   → régénérer le tableau du .md
4. Commit JSON + MD
```

### Maintenance — ajouter une lib core

```
1. Éditer .libs.json → append core[] avec id, module, versionRef,
   rationale, installCommand, license
2. Si nouvelle version : ajouter à versions{}
3. Validation + sync (idem ci-dessus)
```

### Maintenance — ajouter une capability on-demand

```
1. Éditer .libs.json → append onDemand[] avec capability +
   triggers[] (≥ 1 regex case-insensitive)
2. Validation + sync
```

### Migration progressive

Les stacks **non encore migrés** continuent à fonctionner avec leur
table `§2.4` markdown. arch lit le `.libs.json` en priorité, fallback
sur le `.md` parsing si absent.

Stacks migrés au 2026-05-07 (14 catalogues) :

**Backend** :
- `backend/dotnet-minimalapi.libs.json` (buildSystem=dotnet)
- `backend/kotlin-spring-boot.libs.json` (buildSystem=gradle)
- `backend/python-fastapi.libs.json` (buildSystem=uv)
- `backend/node-express.libs.json` (buildSystem=pnpm)

**Frontend** :
- `frontend/blazor-webassembly.libs.json` (buildSystem=dotnet)
- `frontend/react.libs.json` (buildSystem=pnpm — React 19 + Vite 6 + Tailwind v4 + shadcn + TanStack Query/Router + RHF/Zod + i18next + Turborepo + pnpm workspaces avec `catalog:` protocol)
- `frontend/vue.libs.json` (buildSystem=npm — Vue 3.5 + Pinia + TanStack Vue Query + VeeValidate/Zod + vue-i18n)
- `frontend/angular.libs.json` (buildSystem=npm — Angular 19 standalone + signals + control flow)

**QA** (depuis 2026-05-07 — séparation stricte propriété QA) :
- `qa/dotnet-xunit.libs.json` (xUnit + NSubstitute + coverlet + WebApplicationFactory pour API Gate)
- `qa/blazor-bunit.libs.json` (bUnit + xUnit + NSubstitute)
- `qa/node-vitest.libs.json` (Vitest + happy-dom/jsdom + testing-library + supertest pour API Gate)
- `qa/python-pytest.libs.json` (pytest + pytest-cov + pytest-mock + httpx pour API Gate)
- `qa/kotlin-junit.libs.json` (JUnit 5 + MockK + spring-boot-starter-test)
- `qa/angular-jasmine.libs.json` (Jasmine + Karma + istanbul)

### Dé-duplication QA (post-mortem 2026-05-07)

Initialement les libs de tests (vitest, supertest, pytest, etc.) avaient
été placées en `onDemand` des catalogues backend. **Erreur de
modélisation** : `qa-ownership.md` rappelle que l'agent QA est seul
propriétaire des fichiers de test ; dev-* n'installe **jamais** de lib
test dans le projet de production.

**Correction appliquée** :
- Catalogues backend `onDemand` ne contiennent que des **capabilities
  runtime production** (excel, pdf, redis-cache, cqrs, fast-mapping,
  file-upload, http-client, uuid-gen, etc.)
- Catalogues QA portent **toutes** les libs de tests + frameworks
  intégration HTTP (WebApplicationFactory, supertest, httpx) + mocking
  (NSubstitute, MockK, pytest-mock, ng-mocks)
- Aucun chevauchement entre les deux familles

À migrer (work in progress) : `java-spring-boot`, `blazor-server`,
stacks `ui/*` (radzen, shadcn, vuetify), `auth/*` (azure-ad, auth0,
keycloak, local), `qa/code-quality.md` (pas de libs — purement règles
règles, peut rester sans `.libs.json`).

---

## 1.bis Capabilities core vs on-demand (depuis v3.1.3)

Depuis SDD_Pro v3.1.3, le tableau §2.4 de chaque stack backend est
**scindé en deux sous-sections** pour éviter l'installation de libs
non utilisées (audit C4).

### §2.4.a — Librairies CORE (installées par arch, toujours)

Libs sans lesquelles le pattern applicatif ne tient pas : ORM, mapping,
logging, validation, OpenAPI, auth (selon le stack auth actif),
résilience HTTP. arch les installe au bootstrap (§2.2.1), dev-* peut
les utiliser librement sans déclencheur.

Exemples .NET : `Microsoft.EntityFrameworkCore.*`, `AutoMapper`,
`Serilog.*`, `FluentValidation.*`, `Polly`, `Swashbuckle.*`,
`Microsoft.Identity.Web` (si auth Azure AD), `Microsoft.Extensions.Caching.Memory`.

### §2.4.b — Librairies ON-DEMAND (installées par dev-backend si trigger US)

Libs liées à des **capabilities optionnelles** (export Excel/PDF,
CQRS, Redis, mapping rapide, etc.). Une lib §2.4.b n'est installée
que si l'US courante contient un **trigger keyword** documenté dans
le stack §2.4.b (colonne "Triggers"). Voir `agents/dev-backend.md
§STEP 5.bis` pour le workflow d'installation.

Exemples .NET : `EPPlus`/`ClosedXML` (capability `excel`),
`QuestPDF`/`iText7` (`pdf`), `MediatR` (`cqrs`), `StackExchange.Redis`
(`redis-cache`), `Mapster` (`fast-mapping`).

### Tableau de décision dev-*

| Cas | Lib §2.4.a (core) | Lib §2.4.b (on-demand) | Lib hors §2.4 |
|---|---|---|---|
| US déclenche la lib | ✅ usable | ✅ install + usable | ❌ STOP + ERROR |
| US ne déclenche pas | ✅ usable | ❌ pas d'install, pas d'usage | ❌ STOP + ERROR |
| Déjà en csproj (héritée) | ✅ usable | ⚠️ tolérer, ne pas utiliser sans trigger | ⚠️ STOP + ERROR |

### Overrides (Project Config)

L'humain peut piloter via `## Project Config` de `workspace/input/stack/stack.md` :

```yaml
Capabilities: excel, pdf            # force install au bootstrap arch
## Capabilities Override
  excel: closedxml                  # alternative à EPPlus default
  pdf: itext7                       # alternative à QuestPDF default
```

Une capability listée en `Capabilities:` se comporte comme TRIGGERED
même sans trigger keyword US — utile pour pré-installer des libs
futures attendues. L'override redirige vers une lib alternative au
sein de la même capability (ex. ClosedXML MIT au lieu d'EPPlus
Polyform).

### Anti-derive maintenu

La règle "lib hors §2.4 → STOP + ERROR" reste **stricte**. Les
catégories §2.4.a et §2.4.b sont **exhaustives** : aucune lib
externe ne peut être installée sans figurer dans l'une des deux
sous-sections.

---

## 1. Périmètre

### 1.1 Stacks concernés

| Catégorie | Fichier | §2.4 obligatoire |
|---|---|---|
| Backend | `.claude/stacks/backend/*.md` | ✅ |
| Frontend | `.claude/stacks/frontend/*.md` | ✅ |
| UI Design System | `.claude/stacks/ui/*.md` | ✅ (composants natifs) |
| Auth | `.claude/stacks/auth/*.md` | ✅ |
| QA | `.claude/stacks/qa/*.md` | ✅ |

### 1.2 Agents soumis à la règle

Tous les agents qui **écrivent du code** :
- `dev-backend` (services, endpoints, mappers, validators, ...)
- `dev-frontend` (pages, components, layouts, services HTTP, ...)
- `qa` (génération de tests — soumis aux libs §2.4 du stack QA actif)

L'agent `arch` n'est **pas** soumis à la règle pour les libs §2.4
(il les **installe** justement à partir des Init Commands §2.2.1) —
mais il vérifie que §2.4 et §2.2.1 sont **cohérents** entre eux.

### 1.3 Types de librairies couverts

- Packages NuGet (`.NET`)
- Packages npm (`Node.js`, frontends JS/TS)
- Packages PyPI (`pip`)
- Dépendances Maven / Gradle (`Java`, `Kotlin`)
- Dépendances Cargo (`Rust`, futur)
- Dépendances Go modules (`Go`, futur)

Couvre les dépendances **runtime** ET **dev** (linters, formatters
inclus).

---

## 2. Workflow obligatoire des agents dev-*

Avant d'écrire ou planifier un fichier qui **importe** ou **utilise**
une librairie :

### 2.1 Vérification

```
1. Identifier la librairie nécessaire (par signature d'usage)
   ex. "j'ai besoin de mapper Entity → DTO" → AutoMapper
   ex. "j'ai besoin de valider un input" → FluentValidation
   ex. "j'ai besoin d'un client HTTP avec retry" → Refit + Polly

2. Lire §2.4 du stack actif (.claude/stacks/{cat}/{stack-id}.md)

3. Si la librairie figure dans le tableau §2.4 → continuer

4. Si la librairie n'y figure PAS → STOP + ERROR (cf. §3 ci-dessous)
```

### 2.2 Variantes équivalentes

Une librairie peut figurer sous plusieurs noms canoniques :
- `AutoMapper` ↔ `automapper.extensions.microsoft.dependencyinjection`
- `Serilog` ↔ `Serilog.AspNetCore` ↔ `Serilog.Sinks.Console`
- `MapStruct` (Java) — référencé par son artifactId Maven

L'agent vérifie le **paquet exact** qu'il s'apprête à importer. Si le
paquet en §2.4 est plus restrictif (ex. `Serilog.AspNetCore` mais pas
`Serilog.Sinks.File`) et que l'agent a besoin du sink File → la lib
manque → STOP + ERROR.

### 2.3 Ne pas confondre stack §2.4 et conventions §3

§2.4 liste les **paquets installables** (NuGet, npm, etc.).
§3 (Conventions d'usage) montre **comment utiliser** ces paquets.

Si une convention §3 mentionne un usage qui requiert une lib non
listée en §2.4 → c'est un bug du stack (à signaler au Tech Lead via
la même ERROR).

---

## 3. Format ERROR obligatoire (3 lignes + HINT)

Format strict avec préfixe `[STACK_LIBRARY_MISSING]` (cf.
`error-classification.md` futur) :

```
ERROR: dev-{backend|frontend} {n}-{m}-{Name} — librairie manquante
CAUSE: [STACK_LIBRARY_MISSING] besoin de {lib-canonique} pour {usage} (AC-{N} ou §{stack-section})
       absent du stack {stack-id} §2.4 (Librairies pinnées)
FIX: 1. Ajouter {lib-canonique} version {recommandation} dans
        .claude/stacks/{cat}/{stack-id}.md §2.4
     2. Mettre à jour §2.2.1 (Init Commands) pour installer la lib
     3. Relancer /dev-{backend|frontend} {n}-{m} (idempotent)
HINT: librairie(s) suggérée(s) pour ce besoin :
   - {lib-A} (rôle: {description}, version stable: {X.Y.Z})
   - {lib-B} (alternative, rôle: {description})
```

L'agent peut proposer **1-3 librairies suggérées** (sans les
installer). Le Tech Lead choisit et met à jour le stack.

### 3.1 Exemples concrets

#### Exemple 1 — backend .NET, besoin Excel non listé

```
ERROR: dev-backend 1-2-Export-Excel — librairie manquante
CAUSE: [STACK_LIBRARY_MISSING] besoin de génération de fichier .xlsx pour AC-3
       absent du stack dotnet-minimalapi §2.4 (Librairies pinnées)
FIX: 1. Ajouter EPPlus version 7.4.0 dans
        .claude/stacks/backend/dotnet-minimalapi.md §2.4
     2. Mettre à jour §2.2.1 :
        dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package EPPlus --version 7.4.0
     3. Relancer /dev-backend 1-2
HINT: librairies suggérées pour génération Excel .xlsx en .NET :
   - EPPlus (recommandé) — licence Polyform Noncommercial OU commerciale
   - ClosedXML (alternative open-source MIT)
   - DocumentFormat.OpenXml (Microsoft, plus bas niveau)
```

#### Exemple 2 — frontend Vue, besoin date-picker non listé

```
ERROR: dev-frontend 2-1-Calendar — librairie manquante
CAUSE: [STACK_LIBRARY_MISSING] besoin d'un composant DatePicker pour AC-2
       absent du stack vue §2.4 (Librairies pinnées)
FIX: 1. Ajouter @vuepic/vue-datepicker version 8.7.0 dans
        .claude/stacks/frontend/vue.md §2.4
     2. Mettre à jour §2.2.1 :
        npm install @vuepic/vue-datepicker@8.7.0
     3. Relancer /dev-frontend 2-1
HINT: librairies suggérées pour DatePicker Vue 3 :
   - @vuepic/vue-datepicker (recommandé) — riche, accessible, dark mode
   - vue-datepicker-next (alternative, plus minimaliste)
   - vuetify (si déjà actif comme UI DS, utiliser <v-date-picker>)
```

---

## 4. Cas autorisés sans entrée §2.4

L'agent peut utiliser **sans** entrée §2.4 :

### 4.1 Modules built-in du langage / runtime

- `.NET` BCL : `System.*` (System.IO, System.Text.Json, etc.)
- Node.js : modules natifs `fs`, `path`, `crypto`, `http`, `url`, `events`
- Python : stdlib (`datetime`, `json`, `pathlib`, `os`, `re`, `typing`)
- Java : `java.*` / `javax.*` standard
- Kotlin : `kotlin.*` stdlib

### 4.2 Dépendances transitivement requises par une lib §2.4

Si AutoMapper §2.4 → tire `Microsoft.Extensions.DependencyInjection`,
l'agent peut l'utiliser sans entrée explicite (transitive auto-installée
par NuGet).

### 4.3 Types fournis par le framework principal

ASP.NET Core fournit `IConfiguration`, `ILogger<T>`, `IServiceProvider` :
pas besoin de les lister en §2.4.

Spring Boot fournit `@RestController`, `@Service`, `ResponseEntity` :
pas besoin de les lister.

### 4.4 Conventions stack

Si §3 (Conventions d'usage) du stack documente un usage **sans nommer
une lib externe** (ex. `IDbContextFactory` qui est dans EF Core déjà
listé) → autorisé.

---

## 5. Cas interdits (toujours)

- **Lib découverte ad-hoc** : "j'ai trouvé sur Stack Overflow un package
  qui fait ça, je l'installe" → INTERDIT, STOP + ERROR
- **Fork / mirror tiers** : seul le registry canonique (NuGet, npm
  registry, PyPI, Maven Central, MavenCentral via Gradle, Cargo crates,
  go.dev) est autorisé
- **Pre-release** (`-alpha`, `-beta`, `-rc`, `-preview`, `-snapshot`)
  sauf si pinné en §2.4 avec justification
- **Version "latest"** non pinnée — toujours pinner explicitement
- **CVE ≥ moderate** — vérifié post-install par `arch` (cf. politique
  inline `agents/arch.md`)

---

## 6. Anti-patterns rejetés

L'agent NE DOIT JAMAIS :
- Ajouter un `using ...;` / `import ...;` / `package.json devDependency`
  sans vérifier §2.4 préalablement
- Modifier `.csproj` / `package.json` / `pyproject.toml` /
  `build.gradle.kts` / `pom.xml` pour ajouter une dépendance
  (réservé à `arch` Phase A pour les libs déclarées en §2.2.1)
- Utiliser une lib via réflexion / chargement dynamique pour contourner
  la règle
- Considérer que "le compilateur trouve la dépendance" suffit pour la
  considérer comme autorisée

---

## 7. Workflow Tech Lead pour ajouter une lib

Quand un STOP + ERROR `[STACK_LIBRARY_MISSING]` est émis :

1. **Tech Lead lit l'ERROR** (HINT contient les suggestions de l'agent)
2. **Choisit une lib** parmi les suggestions ou une autre validée
3. **Vérifie CVE et licence** :
   - NuGet : `dotnet list package --vulnerable`
   - npm : `npm audit --omit=dev`
   - PyPI : `pip-audit`
   - Maven : `mvn dependency:check` (OWASP)
   - Gradle : plugin `dependency-check`
4. **Édite le stack** :
   - §2.4 : ajouter ligne `| {lib} | {version} | {rôle} |`
   - §2.2.1 : ajouter la commande d'install (ex. `dotnet add package ...`)
   - §3 (Conventions) : optionnel, ajouter pattern d'usage
5. **Relance** `/dev-run {n}` (idempotent — pas de duplication)

---

## 8. Validation manuelle obligatoire

L'ajout d'une lib au stack est une **décision humaine** :
- Pas d'auto-update du stack par les agents
- Pas de "PR auto" depuis l'agent vers le fichier stack
- Le Tech Lead **édite manuellement** le stack avec son arbitrage

Cette barrière préserve la **traçabilité** (git blame sur le stack
dit qui a ajouté quoi quand) et la **sécurité** (un humain a vérifié
CVE / licence / pertinence).

---

## 9. Enforcement par les agents

### 9.1 Agent dev-backend

Au STEP 5 (génération de code), avant chaque fichier produit :
1. Lister les `using ...;` / `import ...;` du fichier planifié
2. Pour chaque import non-built-in (cf. §4) → vérifier §2.4
3. Si manque → STOP + ERROR §3 + ne PAS écrire le fichier

### 9.2 Agent dev-frontend

Au STEP 5 (génération de code), avant chaque fichier produit :
1. Lister les `import ...;` du fichier planifié + entries `package.json`
   ajoutées
2. Pour chaque import non-built-in → vérifier §2.4
3. Si manque → STOP + ERROR §3

### 9.3 Agent qa

Au STEP 6 (génération tests), avant chaque fichier de test :
1. Lister les `import` / `using` du fichier de test
2. Pour chaque import → vérifier §2.4 du stack QA actif
3. Si manque → STOP + ERROR §3

---

## 10. Évolution du stack au fil du projet

Cette règle ne fige PAS le stack. Elle impose juste que toute
évolution passe par une décision humaine tracée :

- **Ajouts** : Tech Lead édite §2.4 + §2.2.1 + §3 (conventions)
- **Retraits** : Tech Lead édite §2.4 + §2.2.1, vérifie qu'aucune US
  ne dépend de la lib retirée
- **Updates de version** : Tech Lead édite §2.4 (pinning), vérifie
  CVE et breaking changes

Au fil du projet, le stack devient une **trace décisionnelle** des
libs validées — comparable à un `package-lock.json` enrichi.

---

## 11. Lien avec autres règles

- **`anti-derive.md`** (futur, dans le sens SDD_Lite) : extension
  naturelle. Anti-derive interdit l'ajout de fonctionnalité non
  scopée ; cette règle interdit l'ajout de **lib** non scopée.
- **`responsibilities.md`** : Tech Lead = sélection / édition stack ;
  agent = exécution stricte de ce qui est déclaré.
- **`file-ownership.md`** (v3.0.1) : agent dev-* ne touche pas
  `.csproj` / `package.json` / `build.gradle.kts` (réservé à `arch`).
- **`constitution.md`** (v3) : un ajout de lib peut justifier un ADR
  (ex. choix EPPlus vs ClosedXML) — créé par le Tech Lead manuellement.

---

## 12. Règle mentale

**"Si la lib n'est pas dans §2.4, je n'écris pas le fichier. Je STOP
avec une ERROR claire et 1-3 suggestions. Le Tech Lead ajoute la lib
au stack si pertinent. Puis je continue."**

L'agent est exécutif, jamais autonome dans le choix des outils.
