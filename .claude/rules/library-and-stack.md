---
# TOK-C1 (audit 2026-06-12) : chargement paresseux (path-scoped rule). Lue on-demand par
# dev-*/arch/qa ; auto-injection au contact du code généré ou des stacks. Économie en
# session forward sans matérialisation et en maintenance framework.
paths:
  - "workspace/src/**"
  - ".sdd/stacks/**"
---

# Règle — Library & Stack (consolidated v7.0.0)

> **v7.0.0 merge** : fusionne `stack-completeness.md` (libs anti-derive,
> §2.4 catalog, runtime LTS, CVE) + `cors.md` (CORS pattern stack-aware).
> Stubs originaux **supprimés au sweep v7.0.0-alpha 2026-05-20** — tous
> les Read `@.sdd/rules/{stack-completeness,cors}.md` historiques
> dans agents/commands/python pointent désormais directement ici.

## TOC

- **Partie A — Stack Completeness** (libs catalogs, runtime LTS,
  capabilities core vs on-demand, CVE check, anti-derive lib découverte).
- **Partie B — CORS** (configuration backend obligatoire SPA-facing,
  pattern par stack, auto-injection arch, anti-patterns, vérification).

---

# Partie A — Stack Completeness

## Principe

Toute librairie utilisée par dev-* pour matérialiser une US DOIT figurer
**explicitement** dans §2.4 du stack actif
(`.sdd/stacks/{cat}/{stack-id}.md`) ou son `.libs.json`.

Absente → **STOP + ERROR**. Pas d'install silencieuse, pas de "découverte
autonome", pas de "lib trouvée sur Stack Overflow". Tech Lead arbitre.

**Load-bearing** pour sécurité, traçabilité, reproductibilité. Prévient
libs obsolètes/vulnérables, fragmentation cross-projets, erreurs de
scaffolding, faux-amis.

---

## 0. Runtime LTS only (fusionné depuis library-policy.md, v6.1)

Stacks SDD_Pro **n'utilisent que des runtimes LTS**. STS ou prerelease
interdits en `## Active Tech Specs` pour prod.

### Matrice runtime LTS (2026-05)

| Plateforme | LTS courant | Fin support | Statut |
|---|---|---|---|
| **.NET**    | 10 (Nov 2025) | Nov 2028 | ✅ `dotnet-minimalapi`, `blazor-*` |
| **Node.js** | 22 "Jod" (Oct 2024) | Apr 2027 | ✅ `react`, `vue`, `angular`, `node-express` |
| **Java**    | 21 (Sep 2023) | Sep 2028 | ✅ `kotlin-spring-boot` |
| **Python**  | 3.12 (Oct 2023) | Oct 2028 | ✅ `python-fastapi` (3.13 OK) |
| **PHP**     | *aucune LTS* — 8.4 en `active support` | 8.4 : sécurité jusqu'à ~fin 2028 | ✅ `laravel` — PHP n'a PAS de LTS : ~2 ans d'`active support` puis ~1 an de `security support`. Plancher effectif du stack = **8.4.1**, imposé par `pestphp/pest` 5 (`^8.4`) et `phpunit` 13 (`>=8.4.1`), et NON par `laravel/framework` 13 (`^8.3`) — cf. `stacks/backend/laravel.md §2.3` |
| **Kotlin**  | 2.0.21 (Oct 2024) | TBD | ✅ pin `kotlin-spring-boot.libs.json` = 2.0.21 (stable, LTS-aligned via Java 21). ⚠️ Les stacks `mobiles/kotlin-android` et `mobiles/kotlin-multiplatform` sont pinnés sur **2.4.10** depuis le 2026-09-02 (Compose exige le plugin compilateur versionné avec Kotlin) — divergence assumée et documentée dans leur §2.3, pas un drift |

**Interdictions** : pin sur version STS (.NET 9, Node 23, Java 22…),
prerelease (`-rc/-preview/-alpha/-beta/-snapshot`) sans ADR, version
`latest` non-pinnée.

**Bypass STS** (rare, tracé) : ADR `ADR-{ts}-runtime-sts-exception.md`
+ `RuntimeException: dotnet9 (fin: 2026-05-12, migration -> dotnet10)`
dans Project Config → `validate_libs_catalog.py` émet WARN
`[RUNTIME_STS_EXCEPTION]`. **Référence canonique** :
`docs/adrs/ADR-20260605T163200-runtime-sts-prerelease-exceptions.md`
(matrice des bypass autorisés cas-par-cas, contrats expiration, plan
de migration vers LTS).

**Secrets / config en clair (Pattern B)** : `stack.md` est la SSoT
unique pour les valeurs sensibles (DB_PASSWORD, AUTH_JWT_SECRET,
AZ_TENANTID, ports, etc.). ⚠️ Le fichier est **VERSIONNÉ** depuis
2026-08-30 (`.gitignore` : `!workspace/stack/stack.md`) — n'y écrire
que des placeholders `${VAR}` ou des valeurs non sensibles, tout secret
réel y devient public au premier push (cf. amendement 2026-08-31 de
l'ADR ci-dessous). `arch`
propage les valeurs en clair dans les configs natives
(`appsettings.json`, `application.yml`, etc.) lors du scaffolding.
Le code applicatif lit les configs natives via `IConfiguration` /
`@Value` / `Settings()` — **jamais** via `process.env` / `os.environ`
direct (sinon `[SEC_ENV_VAR_FORBIDDEN]` cf. `error-classification.md
§1.11`). **Référence canonique** :
`docs/adrs/ADR-20260606T120000-secrets-config-ssot-stack-md.md`.

**Registries canoniques** : NuGet (`api.nuget.org`), npm
(`registry.npmjs.org`), PyPI (`pypi.org`), Maven Central
(`repo1.maven.org/maven2`), Gradle plugins portal. Pas de fork, mirror
tiers, ou feed privé non documenté.

**CVE check post-install** :
- NuGet : `dotnet list package --vulnerable --include-transitive`
- npm : `npm audit --omit=dev --audit-level=moderate`
- pip : `pip-audit`
- Maven/Gradle : `mvn dependency:check` (OWASP) ou plugin Gradle

**Format ERROR runtime LTS** :
```
ERROR: arch — runtime non-LTS detecte
CAUSE: [STACK_RUNTIME_NOT_LTS] {stack-id} pin {plateforme} {version} (STS, fin {date})
FIX: migrer vers LTS courante ({lts-version}) dans .sdd/stacks/{cat}/{stack-id}.libs.json#versions
```

---

## 1.0 Source de vérité : catalogue JSON `.libs.json` (depuis 2026-05-07)

Chaque stack a **deux fichiers compagnons** :

| Fichier | Rôle | Audience |
|---|---|---|
| `{stack-id}.md` | Documentation humaine (architecture, conventions, pièges) | Tech Lead, agents (lecture passive) |
| `{stack-id}.libs.json` | **Catalogue machine** (versions, libs core/onDemand, plugins, triggers regex) | `arch` (install), `dev-backend` (capability gating), validation scripts |

Le `.libs.json` est la **source de vérité** install/résolution. Le `.md`
ne contient plus de §2.4 manuel — régénéré via `sync_stack_md.py`.

**Schéma JSON** : `.sdd/templates/libs-catalog.schema.json` (draft 2020-12).
Structure :
```json
{
  "stackId": "kotlin-spring-boot",
  "category": "backend",
  "schemaVersion": 1,
  "buildSystem": "gradle | dotnet | npm | pnpm | yarn | maven | pip | poetry | uv | cargo | go-mod | msbuild | pub | swift | composer | cmake",
  "manifest": { "files": [...], "versionCatalogPath": "..." },
  "versions": { "kotlin": "2.0.21", "spring-boot": "3.3.5" },
  "core":     [ { "id", "module", "versionRef", "rationale", "installCommand", "license" } ],
  "onDemand": [ { ..., "capability", "triggers": [...], "alternative": false } ],
  "plugins":  [ { "id", "versionRef", "rationale" } ]
}
```

### Workflow agent

**arch Phase A** : charger `.libs.json`, exécuter `core[].installCommand`
avec substitution `{BackendName|AppName|LibName|AppNamespace|version}`,
configurer `plugins[]`, forcer install `onDemand[]` matchant
`Capabilities:` Project Config si présent.

**dev-backend STEP 5.bis** : charger `.libs.json`, invoquer
`detect_capabilities.py` qui matche les `triggers[]` regex contre US +
ACs, installer la `onDemand[]` correspondante (default + override
Project Config).

### Scripts admin (`.sdd/python/sdd_admin/`)

- `validate_libs_catalog.py` — valide schéma + cohérence (versionRef
  pointe sur clé existante, capability/triggers pour onDemand, etc.)
- `sync_stack_md.py --stack-id {id}` — régénère §2.4 du `.md` depuis
  `.libs.json`. Idempotent. `--dry-run` pour preview.

### Maintenance

| Action | Étapes |
|---|---|
| MAJ version | éditer `versions.{key}` → `validate_libs_catalog.py` → `sync_stack_md.py` → commit |
| Ajout lib core | append `core[]` (id, module, versionRef, rationale, installCommand, license) → idem |
| Ajout capability on-demand | append `onDemand[]` avec `capability` + `triggers[]` regex case-insensitive → idem |

### Stacks migrés (catalogues `.libs.json`)

| Catégorie | Stacks |
|---|---|
| Backend | `dotnet-minimalapi`, `kotlin-spring-boot`, `python-fastapi`, `node-express`, `django`, `nestjs`, `laravel` |
| Frontend | `blazor-webassembly`, `react`, `vue`, `angular` |
| QA | `dotnet-xunit`, `blazor-bunit`, `node-vitest`, `python-pytest`, `kotlin-junit`, `angular-jasmine`, `mutation-testing`, `playwright`, `flutter-test`, `swift-testing`, `php-pest` |
| UI DS | `radzen-blazor`, `shadcn` (7 core + 15 onDemand Radix), `vuetify` |
| Fullstack | `next`, `nuxt`, `angular-universal`, `blazor-server`, `kotlin-mustache`, `node-react`, `aspnet-mvc-razor`, `laravel-blade`, `symfony-twig`, `django-templates` |
| Mobiles | `kotlin-android`, `maui`, `react-native`, `delphi-fmx`, `flutter`, `kotlin-multiplatform`, `swiftui`, `ionic-capacitor` |
| Desktop | `delphi-vcl`, `wpf`, `qt-cpp`, `electron`, `winforms`, `javafx`, `pyside` |

**Hors périmètre `.libs.json`** (par design) : `auth/*` (protocoles
cross-langage — libs concrètes dans `.libs.json` consommateur),
`qa/code-quality.md` (règles sonar-like), `archi/*` (patterns conceptuels).

**`fullstack/blazor-server`** : `.libs.json` complet MAIS pattern monolithique
incompatible avec l'isolation back-front (`ownership.md §1.bis`) — usage
réservé `AppType=fullstack` explicite.

### Dé-duplication QA

QA seul propriétaire des tests (`qa.md §Ownership`) ; dev-* n'installe
JAMAIS de lib test en prod. Backends `onDemand` = capabilities **runtime
prod** uniquement (excel, pdf, redis-cache, cqrs, fast-mapping, file-upload,
http-client). QA porte libs test + intégration HTTP + mocking.

---

## 1.bis Capabilities core vs on-demand (v3.1.3)

Tableau §2.4 de chaque stack backend **scindé en deux** :

### §2.4.a CORE (installé par arch, toujours)

Libs sans lesquelles le pattern applicatif ne tient pas : ORM, mapping,
logging, validation, OpenAPI, auth, résilience HTTP. arch installe au
bootstrap ; dev-* utilise sans déclencheur.

Exemples .NET : `Microsoft.EntityFrameworkCore.*`, `AutoMapper`,
`Serilog.*`, `FluentValidation.*`, `Polly`, `Swashbuckle.*`,
`Microsoft.Identity.Web`, `Microsoft.Extensions.Caching.Memory`.

### §2.4.b ON-DEMAND (installé par dev-backend si trigger US)

Libs liées à des capabilities optionnelles. Installée uniquement si l'US
contient un **trigger keyword** (cf. `detect_capabilities.py` STEP 5.bis).

Exemples .NET : `EPPlus`/`ClosedXML` (`excel`), `QuestPDF`/`iText7`
(`pdf`), `MediatR` (`cqrs`), `StackExchange.Redis` (`redis-cache`),
`Mapster` (`fast-mapping`).

### Tableau de décision dev-*

| Cas | §2.4.a core | §2.4.b on-demand | Hors §2.4 |
|---|---|---|---|
| US déclenche | ✅ usable | ✅ install + usable | ❌ STOP + ERROR |
| US ne déclenche pas | ✅ usable | ❌ pas d'install | ❌ STOP + ERROR |
| Déjà en csproj (héritée) | ✅ usable | ⚠️ tolérer, pas d'usage sans trigger | ⚠️ STOP + ERROR |

### Overrides Project Config

```yaml
Capabilities: excel, pdf            # force install au bootstrap arch
## Capabilities Override
  excel: closedxml                  # alternative à EPPlus default
  pdf: itext7                       # alternative à QuestPDF default
```

`Capabilities:` = comme TRIGGERED même sans keyword US (pré-install).
Override = lib alternative dans la même capability.

**Anti-derive maintenu** : "lib hors §2.4 → STOP + ERROR" reste strict.
§2.4.a/§2.4.b sont **exhaustives**.

---

## 1. Périmètre

### 1.1 Stacks concernés

| Catégorie | Fichier | §2.4 obligatoire |
|---|---|:---:|
| Backend | `.sdd/stacks/backend/*.md` | ✅ |
| Frontend | `.sdd/stacks/frontend/*.md` | ✅ |
| UI Design System | `.sdd/stacks/ui/*.md` | ✅ (composants natifs) |
| Auth | `.sdd/stacks/auth/*.md` | hors périmètre (cf. §1.0) |
| QA | `.sdd/stacks/qa/*.md` | ✅ |

### 1.2 Agents soumis

Tous les agents qui **écrivent du code** : `dev-backend`, `dev-frontend`,
`qa`. `arch` n'est pas soumis (il **installe** §2.2.1) mais vérifie la
cohérence §2.4 ↔ §2.2.1.

### 1.3 Types couverts

NuGet, npm, PyPI, Maven/Gradle, Cargo (futur), Go modules (futur).
Couvre dépendances **runtime ET dev** (linters, formatters inclus).

---

## 2. Workflow obligatoire dev-*

Avant d'écrire un fichier qui importe une lib :

1. Identifier la lib nécessaire (par signature d'usage)
2. Lire §2.4 du stack actif (ou son `.libs.json`)
3. Si présente → continuer ; sinon → STOP + ERROR §3

**Variantes équivalentes** : vérifier le **paquet exact**. Si le paquet
§2.4 est plus restrictif (ex. `Serilog.AspNetCore` mais pas
`Serilog.Sinks.File` requis) → lib manque → STOP.

**§2.4 ≠ §3 Conventions** : §2.4 = paquets installables, §3 = comment
les utiliser. Si une convention §3 requiert une lib non listée §2.4 →
bug du stack à signaler.

---

## 3. Format ERROR (3 lignes + HINT)

Préfixe `[STACK_LIBRARY_MISSING]` (cf. `error-classification.md`) :

```
ERROR: dev-{backend|frontend} {n}-{m}-{Name} — librairie manquante
CAUSE: [STACK_LIBRARY_MISSING] besoin de {lib} pour {usage} (AC-{N})
       absent du stack {stack-id} §2.4
FIX: 1. Ajouter {lib} version {X} dans .sdd/stacks/{cat}/{stack-id}.libs.json
     2. Régénérer §2.4 du .md via sync_stack_md.py
     3. Relancer /dev-{backend|frontend} {n}-{m} (idempotent)
HINT: 1-3 libs suggérées :
   - {lib-A} (rôle, version stable)
   - {lib-B} (alternative)
```

**Exemple** (backend .NET, besoin Excel) :
```
ERROR: dev-backend 1-2-Export-Excel — librairie manquante
CAUSE: [STACK_LIBRARY_MISSING] besoin de génération .xlsx pour AC-3
       absent du stack dotnet-minimalapi §2.4
FIX: ajouter EPPlus 7.4.0 dans .libs.json, sync_stack_md, relancer
HINT: EPPlus (Polyform Noncommercial OU commercial), ClosedXML (MIT,
      alternative), DocumentFormat.OpenXml (Microsoft, bas niveau)
```

---

## 4. Cas autorisés sans entrée §2.4

- **Built-in langage/runtime** : `.NET BCL` (`System.*`), Node natifs
  (`fs`, `path`, `crypto`, `http`, `url`, `events`), Python stdlib
  (`datetime`, `json`, `pathlib`, `os`, `re`, `typing`), `java.*`,
  `kotlin.*` stdlib
- **Dépendances transitives** auto-installées par le package manager
  (ex. `Microsoft.Extensions.DependencyInjection` tiré par AutoMapper)
- **Types fournis nativement** par le framework principal (ASP.NET :
  `IConfiguration`, `ILogger<T>` ; Spring : `@RestController`,
  `ResponseEntity`)
- **Conventions §3** sans lib externe nommée

---

## 5. Cas interdits

- Lib découverte ad-hoc ("trouvée sur Stack Overflow")
- Fork / mirror tiers (registries canoniques uniquement)
- Pre-release (`-alpha/-beta/-rc/-preview/-snapshot`) sans ADR
- Version `latest` non-pinnée
- CVE ≥ moderate (vérifié post-install par arch)

---

## 6. Anti-patterns rejetés

L'agent NE DOIT JAMAIS :
- Ajouter un `using`/`import`/`devDependency` sans vérifier §2.4
- Modifier `.csproj`/`package.json`/`pyproject.toml`/`build.gradle.kts`/
  `pom.xml` (réservé arch Phase A pour libs §2.2.1)
- Utiliser une lib via réflexion / chargement dynamique pour
  contourner la règle
- Considérer "le compilateur trouve la dépendance" comme suffisant

---

## 6.bis Schema/regex sync front↔back

**Règle load-bearing** : tout champ DTO/payload partagé back↔front DOIT
avoir **même contrat** (type, regex, min/max). Désynchro = bug runtime
silencieux à la 1ère soumission form.

### 6.bis.1 Type des IDs

| Backend | Frontend | Convention |
|---|---|---|
| `val id: Int` (PG serial) | `id: string` (RHF + DOM) | Coerce string AU BOUNDARY fetch (`.map(o => ({ id: String(o.id), ... }))` dans `apiXxx.ts`) |
| `val id: UUID` | `id: string` | Pas de coercion (déjà string) |

**Anti-pattern** : laisser `number` traverser jusqu'au form RHF — React
state + DOM = string ; `===` échoue (`5 !== "5"`).

### 6.bis.2 Regex de validation

| Backend `@Pattern` | Frontend Zod | Risque désynchro |
|---|---|---|
| `^[0-9]{13}$` EAN-13 | `^[0-9]+$` | 400 ProblemDetail au save sur 5 chiffres |
| `^[0-9a-f]{8}-...$` GUID | `^\d+$` | rejet UI sur GUIDs valides backend |
| `@Size(max=100)` | `z.string().max(100)` | back rejette texte 101 chars accepté front |

Copier le regex exact `@Pattern` côté Zod dans `src/schemas/{Domain}Schema.ts`
+ commentaire `// MIRROR backend X.@Pattern "..."` pour traçabilité.

**Alternative future** : générer le client TS depuis OpenAPI 3 backend
(`springdoc-openapi` → `openapi-typescript`) — élimine drift par
construction. Non systématisé v7.0.0.

### 6.bis.3 Field naming (camelCase serialization)

Jackson préserve camelCase (`val fkAnnonceur` → `fkAnnonceur`). Frontend
TS DOIT utiliser mêmes clés. Tout renommage DTO backend exige grep front
(`grep -rn "field.X" workspace/src/{AppName}/`).

**Anti-pattern** : champ `libelle` back mappé `nom` front → Jackson rejette
POST (400 `@NotBlank` sur `nom` absent), lecture retourne `undefined`.

### 6.bis.4 Pattern de revue

`code-reviewer` détecte ce drift via `[FRONTEND_BACKEND_CONTRACT_GAP]`
(hard-blocking, override `CodeReviewFailOn`). Cf. `error-classification.md §1.10`.

---

## 7. Workflow Tech Lead (ajout d'une lib)

Sur STOP + ERROR `[STACK_LIBRARY_MISSING]` :
1. Lire l'ERROR + HINT (suggestions de l'agent)
2. Choisir une lib + vérifier CVE et licence (cmds §0)
3. Éditer `.libs.json` du stack (append `core[]` ou `onDemand[]`)
4. `validate_libs_catalog.py` → `sync_stack_md.py` → commit
5. Relancer `/dev-run {n}` (idempotent)

**Validation manuelle obligatoire** : pas d'auto-update par les
agents. Le Tech Lead édite manuellement, ce qui préserve la
traçabilité (`git blame`) et la sécurité (humain vérifie CVE/licence).

---

## 8. Évolution du stack

Toute évolution passe par décision humaine tracée :
- **Ajouts** : édition `.libs.json` + sync
- **Retraits** : vérifier qu'aucune US ne dépend de la lib retirée
- **Updates version** : vérifier CVE + breaking changes

Le stack devient une **trace décisionnelle** des libs validées,
comparable à un `package-lock.json` enrichi.

---

## 9. Lien avec autres règles

- `ownership.md §1` (Partie A) : agent dev-* ne touche pas les fichiers projet (réservé arch)
- `constitution.md` : ajout de lib peut justifier un ADR (créé par Tech Lead)

Note : la matrice rôles (Tech Lead = sélection stack ; agent =
exécution stricte) est inlinée dans chaque agent (po, arch, dev-*, qa).

---

## 10. Règle mentale

**"Si la lib n'est pas dans §2.4, je n'écris pas le fichier. STOP +
ERROR avec 1-3 suggestions. Le Tech Lead arbitre."**

L'agent est exécutif, jamais autonome dans le choix des outils.

---

# Partie B — CORS Configuration (SPA ↔ backend)

## Principe

SPA (React/Vue/Angular/Blazor WASM) servie sur origin ≠ backend (dev
`:5173`↔`:8080`, prod `app.example.com`↔`api.example.com`) → **config CORS
backend OBLIGATOIRE**. Sans elle : `fetch`/`XHR` → `TypeError: Failed to
fetch` silent, page blanche, backend logs vides (preflight `OPTIONS` rejeté
avant les handlers). **Load-bearing** pour `appType: back-front`.

## B.1 Quand cette règle s'applique

| Cas | CORS requis ? |
|---|:---:|
| SPA + API séparés | ✅ OBLIGATOIRE |
| Mobile + API (origins `capacitor://`, `ionic://`) | ✅ OBLIGATOIRE |
| Fullstack monolithique | ⊘ N/A (SSR same-origin) |
| Backend headless | ❌ N/A |

`arch` détecte le cas via `## Active Tech Specs` du `stack.md` (cf. CLAUDE.md
§7 matrice AppType).

### 1.bis Auto-injection arch

`arch` STEP 4.5.6 propage l'origin frontend dev dans la config backend
(allowlist explicite, jamais wildcard) :

| Frontend stack | Port dev | Origin injectée |
|---|---:|---|
| `react`, `vue` | 5173 | `http://localhost:5173` |
| `angular` | 4200 | `http://localhost:4200` |
| `blazor-webassembly` | 5097 | `http://localhost:5097` |

**Override** dans `## Project Config` : `Cors:AllowedOrigins: "..."` (User-set
wins). Détail : `docs/arch/phase-a-config-propagation.md §4.5.6` (substance hoistée hors d'arch.md).

---

## B.2 Pattern correct par stack backend

### B.2.1 .NET (dotnet-minimalapi)

`Program.cs` :
```csharp
var allowedOrigins = builder.Configuration["Cors:AllowedOrigins"]?
    .Split(',', StringSplitOptions.RemoveEmptyEntries)
    ?? ["http://localhost:5173"];

builder.Services.AddCors(options => options.AddPolicy("Spa", policy =>
    policy.WithOrigins(allowedOrigins)
          .AllowAnyHeader()
          .AllowAnyMethod()
          .AllowCredentials()));

// après UseRouting, avant UseAuthorization
app.UseCors("Spa");
```

`appsettings.json` / env `Cors__AllowedOrigins=http://localhost:5173,http://localhost:4173`.

### B.2.2 Spring Boot (kotlin-spring-boot)

Bean dédié `CorsConfig.kt` :
```kotlin
@Configuration
class CorsConfig(
    @Value("\${APP_CORS_ALLOWED_ORIGINS:http://localhost:5173,http://localhost:4173}")
    private val allowedOriginsCsv: String,
) {
    @Bean
    fun corsConfigurationSource(): CorsConfigurationSource {
        val config = CorsConfiguration().apply {
            allowedOrigins = allowedOriginsCsv.split(",").map { it.trim() }
            allowedMethods = listOf("GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH")
            allowedHeaders = listOf("*")
            allowCredentials = true
            maxAge = 3600
        }
        return UrlBasedCorsConfigurationSource().apply { registerCorsConfiguration("/**", config) }
    }
}
```

Activer dans `SecurityConfig.kt` :
```kotlin
http.cors { } // utilise le bean ci-dessus
```

### B.2.3 FastAPI (python-fastapi)

`main.py` :
```python
from fastapi.middleware.cors import CORSMiddleware
import os

allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### B.2.4 Node Express (node-express)

`server.ts` :
```typescript
import cors from "cors";

const allowedOrigins = (process.env.CORS_ALLOWED_ORIGINS ?? "http://localhost:5173").split(",");

app.use(cors({
  origin: allowedOrigins,
  credentials: true,
  methods: ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
}));
```

---

## B.3 Alternative dev — Vite proxy (sans CORS backend)

Si le projet veut éviter la config CORS backend en dev (mais doit
quand même la faire en prod), Vite peut proxifier l'API :

`vite.config.ts` :
```typescript
export default defineConfig({
  server: {
    proxy: {
      "/api": { target: "http://localhost:8080", changeOrigin: true },
    },
  },
});
```

**Limite stricte** : cette alternative ne supprime PAS le besoin CORS en
prod (où le proxy Vite n'existe pas). Garder la config CORS backend
même si proxy actif en dev — sinon dérive prod garantie.

---

## B.4 Anti-patterns rejetés

| Anti-pattern | Pourquoi rejeté |
|---|---|
| `@CrossOrigin` annotation Spring sur controllers individuels | Fragmente la policy, oubli systématique sur nouveaux endpoints |
| `Access-Control-Allow-Origin: *` avec `AllowCredentials: true` | Spec CORS interdit cette combinaison (cookies refusés) |
| Allowed origins hardcodés dans le code | Doit venir de config/env (différent dev/prod) |
| Pas de `OPTIONS` preflight en allowed methods | Requêtes credentialled échouent silencieusement |
| Wildcard `*` sur `allowedHeaders` en prod avec credentials | Refusé par les navigateurs récents |
| CORS uniquement via reverse proxy (nginx, IIS) sans backup applicatif | Casse en dev local + tests intégration |

---

## B.5 Vérification dev-backend / arch

### Pattern à grep en STEP build

```bash
# Backend Spring (Kotlin)
grep -r "@CrossOrigin" workspace/src/{BackendName}/ && WARN

# Backend .NET
grep -r "AddCors\|UseCors" workspace/src/{BackendName}/ || ERROR (manquant)

# FastAPI
grep -r "CORSMiddleware" workspace/src/{BackendName}/ || ERROR

# Node Express
grep -r "cors()" workspace/src/{BackendName}/ || ERROR
```

### Format ERROR

Préfixe `[SEC_CORS_MISSING]` (cf. `error-classification.md §1.11`) :

```
ERROR: dev-backend {n}-{m} — CORS non configuré
CAUSE: [SEC_CORS_MISSING] backend SPA-facing sans config CORS — toute requête front échouera
FIX: ajouter Program.cs/CorsConfig.kt/main.py selon stack §2.{1..4}
     configurer CORS_ALLOWED_ORIGINS env var (csv des origins SPA dev + prod)
HINT: cf. .sdd/rules/library-and-stack.md (Partie B §2) pour le pattern stack-aware
```

---

## B.6 Test d'acceptation

Toute FEAT impliquant un appel SPA→backend doit avoir au moins 1 AC
implicite couvert par cette règle :

> Given une SPA servie sur origin `X` et un backend sur origin `Y`,
> when la SPA envoie une requête fetch credentialled vers Y,
> then le préflight OPTIONS retourne 204/200 avec les headers
> `Access-Control-Allow-Origin: X` et `Access-Control-Allow-Credentials: true`,
> et la requête principale aboutit.

À matérialiser dans la phase QA API Gate (cf. `build-and-loop.md` Partie A §1.1).

---

## B.7 Pièges runtime documentés (post-mortem bench) — hoisté v7.0.1

Substance complète déplacée vers `@.sdd/docs/runtime-pitfalls.md` (audit P1
tokens 2026-06-08, économie ~2.5 KB par dispatch dev-*). 5 bugs runtime multi-stack
documentés : (1) CORS `localhost`≠`127.0.0.1`, (2) `<input type=number>` coerce
Vue/Angular, (3) JMustache null-strict, (4) `pydantic-core` no-wheel Python récent,
(5) bUnit `.Change()` ≠ `@bind:event="oninput"`.

**Read on-demand uniquement** quand un bug runtime correspondant est suspecté en
build_loop ou bench — pas en stable layer dev-*.

---

## B.9 Lien avec autres règles

- `build-and-loop.md` (Partie A) : la QA API Gate doit inclure ≥ 1 test CORS
  preflight (OPTIONS avec Origin) par endpoint exposé à la SPA.
- `docs/principles/source-first.md §1` : tout bug CORS/coercion/null-strict en runtime
  → patch cette règle (Partie B, §B.7) AVANT le fix code.
- Partie A §2.4 ci-dessus : la lib CORS (Microsoft.AspNetCore.Cors,
  spring-security-config, fastapi[all], cors npm) est CORE de tout
  backend SPA-facing.

---

## B.10 Source historique

Convention extraite du post-mortem CMS-Back 2026-05-11 (cf.
`source-first.md §1`) où CORS oublié sur Spring Boot avait causé
3 jours de debug sur projet client. Pattern canonique inliné aussi dans
`stacks/auth/azure-ad.md §5.2.7.9`.

---

# Partie C — Database structural safety (base existante protégée)

> **Nouveau (décision Tech Lead 2026-06-13)** : règle dure inter-agent.
> Périmètre retenu : **« existant protégé, création greenfield OK »**.
> Émet `[DB_STRUCTURE_CHANGE_FORBIDDEN]` (`error-classification.md §1.3`).

## C.1 Principe

**Aucun agent SDD_Pro (arch, dev-backend, dev-frontend, qa) ne modifie
JAMAIS la structure d'une base de données *existante* ni n'exécute
d'action destructive.** La base de données d'un projet déjà provisionné
(brownfield, reverse, prod, base partagée) est traitée comme une
**ressource en lecture / DML uniquement** :

| Catégorie SQL | Autorisé pour un agent ? |
|---|:---:|
| `SELECT` (lecture) | ✅ oui |
| `INSERT` / `UPDATE` ciblés (DML, avec `WHERE` pour update) | ✅ oui |
| Introspection métadonnées (`information_schema`, `INFORMATION_SCHEMA`) READ-ONLY | ✅ oui (arch Phase B) |
| `CREATE TABLE` du **schéma initial d'un projet greenfield** (base neuve, vide) | ✅ oui (scaffolding ; cf. C.3) |
| `DROP` (table/colonne/index/contrainte/base) | ❌ **INTERDIT** |
| `ALTER` de structure sur une **base existante** (add/drop/rename column, change type, contrainte) | ❌ **INTERDIT** |
| `TRUNCATE` | ❌ **INTERDIT** |
| `DELETE` de masse (sans `WHERE` ciblé, ou ciblant la structure logique) | ❌ **INTERDIT** |
| Application de migration contre une base existante (`dotnet ef database update`, `db.Database.Migrate()`, `EnsureCreated()` au runtime, `prisma migrate deploy`, `alembic upgrade`, `flyway migrate`) | ❌ **INTERDIT** (sauf exception FEAT de migration Flyway — cf. §C.6) |
| Tout SQL destructif / DDL non listé ci-dessus | ❌ **INTERDIT** |

## C.2 Comportement obligatoire face à un besoin de changement structurel

Si une US/FEAT exige une modification de structure d'une base existante
(nouvelle colonne, nouvel index, table d'association, contrainte) :

1. L'agent **NE l'exécute PAS** et **NE l'applique PAS**.
2. Il **écrit le DDL souhaité** (jamais exécuté) dans
   `workspace/db/migration-pending.sql` (append-only, daté, avec
   le contexte US/FEAT en commentaire SQL).
3. Il **émet** `[DB_STRUCTURE_CHANGE_FORBIDDEN]` (ERROR 3L disque + chat 1L)
   et **s'arrête** sur le scope concerné (STOP, pas de build_loop).
4. Le **Tech Lead humain** applique la migration à la main après revue,
   puis relance le pipeline.

```
ERROR: dev-backend 5-4 — changement de structure DB requis
CAUSE: [DB_STRUCTURE_CHANGE_FORBIDDEN] US 5-4 nécessite ALTER TABLE Cadenciers_DataImport ADD COLUMN Signer_manuellement — base existante, interdit à l'agent
FIX: DDL écrit dans workspace/db/migration-pending.sql ; Tech Lead applique manuellement puis relance
```

## C.3 Exception unique — création greenfield

La **création du schéma initial d'un projet neuf** (base vide, première
matérialisation) reste permise :
- via le scaffolding **Database-First READ-ONLY** d'arch (introspection
  seule, jamais d'écriture sur la base — `arch.md` anti-derive « DB READ-ONLY ») ;
- ou via une migration **initiale** générée en fichier (`migrations/`,
  `*.sql`) que le Tech Lead applique sur la **base neuve**.

Ce qui distingue l'exception : la base est **vide / inexistante**, il n'y
a **aucune donnée ni structure à préserver**. Dès qu'une base contient
des tables ou des données (existant, reverse, prod), C.1 s'applique sans
exception. **En cas de doute « base neuve vs existante » → traiter comme
existante** (fail-safe, escalade C.2).

## C.4 Code de démarrage généré (anti-auto-migrate)

Le code applicatif généré par dev-backend **ne doit jamais** auto-appliquer
de migration / auto-créer le schéma au runtime contre une base existante :
- ❌ `context.Database.Migrate()` au startup
- ❌ `context.Database.EnsureCreated()` en environnement non-greenfield
- ❌ `synchronize: true` (TypeORM), `ddl-auto: update|create-drop` (Hibernate/JPA)
  sur base existante
- ✅ `ddl-auto: validate` (ou `none`) : valide le mapping sans modifier la structure

Si le stack impose un `ddl-auto`/équivalent, la valeur par défaut sûre est
`validate`/`none` ; tout autre choix sur base existante = `[DB_STRUCTURE_CHANGE_FORBIDDEN]`.

## C.5 Lien avec autres règles

- `error-classification.md §1.3` : classe `[DB_STRUCTURE_CHANGE_FORBIDDEN]` (STOP).
- `agents/arch.md` (anti-derive « DB READ-ONLY ») : arch n'écrit jamais sur la base.
- `agents/dev-backend.md` (anti-derive) : pas de migration appliquée, pas d'auto-migrate.
- `ownership.md §1` : `workspace/db/migration-pending.sql` (escalade) co-owné arch/dev-backend.

## C.6 Exception sanctionnée — FEAT de migration Flyway

> **Nouveau (décision Tech Lead 2026-06-30)** : seule dérogation explicite à
> C.1. Flyway devient le **mécanisme de migration sanctionné** (versionné,
> idempotent via `flyway_schema_history`). Toute autre voie d'altération de
> structure (DDL ad-hoc, `Migrate()`/`EnsureCreated()` runtime, `prisma migrate
> deploy`, `alembic upgrade`) **reste interdite** (C.1 inchangé).

### C.6.1 Déclencheur — nom de fichier FEAT contient « Flyway »

Une **FEAT de migration** est une FEAT dont le **basename** matche
`(?i)flyway` (substring case-insensitive), p.ex.
`workspace/feats/2-Flyway-Migration.md`, `5-Flyway-Add-Audit-Cols.md`.

La détection vit **dans l'orchestrateur** (`/sdd-full` STEP 2, `/sdd-poc`
STEP 2.1) — **jamais dans arch** (qui ne lit jamais les FEATs, anti-derive).
L'orchestrateur, sur match :
1. écrit le sentinel `workspace/.sys/.state/flyway-migrate-requested.flag`
   (contenu : `feat={n}-{FeatName}` + `requested_at={ISO-8601}`) ;
2. force le comportement `--rebuild-arch` pour la phase DB (défait le
   short-circuit arch — le scaffolding **doit** être refait à chaque run).

### C.6.2 Comportement — `flyway migrate` PUIS re-scaffolding

À chaque `/sdd-full {n}` ou `/sdd-poc {n}` sur une FEAT de migration, arch
(Phase B, STEP 8.5 — cf. `docs/arch/phase-b-db-scaffolding.md`) :

1. compose la connection string en RAM (STEP 8 existant, jamais persistée) ;
2. exécute **`flyway migrate`** contre la base, scripts versionnés
   `V{version}__{desc}.sql` lus depuis l'emplacement conventionnel du stack
   (Spring Boot : `src/main/resources/db/migration/` ; sinon
   `workspace/db/migration/`) ;
3. ré-introspecte le schéma (STEP 9, **forcé** même si `schema.json` existe) ;
4. re-scaffolde les entities (STEP 11, `--force` incrémental) pour refléter
   le schéma migré ;
5. **consomme** (supprime) le sentinel après migrate réussi (per-run).

**Idempotence** : `flyway migrate` ne ré-applique jamais une version déjà
inscrite dans `flyway_schema_history` → relancer le pipeline est sûr.

### C.6.3 Garde-fous (l'exception reste étroite)

- **Périmètre** : seules les commandes `/sdd-full` et `/sdd-poc` honorent le
  sentinel. `/dev-run`, `/arch-init` hors pipeline et les agents dev-* ne
  déclenchent **jamais** `flyway migrate`.
- **Runner absent** : si le stack backend actif ne fournit pas de runner
  Flyway exécutable → STOP `CAUSE: [INFRA_BLOCKED]` (« je n'ai pas pu
  exécuter »), pas de fallback DDL silencieux.
- **Migrate en échec** : exit ≠ 0 → STOP `CAUSE: [SCHEMA_MISMATCH]` (script
  invalide, conflit de version, base injoignable) ; aucune ré-écriture
  partielle masquée.
- **arch n'écrit pas les scripts** : les `V*__*.sql` sont des artefacts de la
  FEAT (Tech Lead / dev-backend), arch **exécute** seulement le runner — il
  ne génère ni ne modifie le DDL (toujours pas de code applicatif).
- **C.4 inchangé** : le code applicatif généré ne doit **toujours pas**
  auto-migrer au runtime (`Migrate()`/`EnsureCreated()`/`ddl-auto: update` au
  startup restent `[DB_STRUCTURE_CHANGE_FORBIDDEN]`). §C.6 est une **phase de
  pipeline explicite et opt-in**, pas du code de démarrage.
- **Hors FEAT Flyway** : un besoin structurel détecté sur une FEAT *non*
  nommée Flyway suit C.2 (DDL écrit dans `migration-pending.sql`, STOP,
  escalade Tech Lead) — aucune migration auto.

### C.6.4 Lien avec autres règles

- `error-classification.md §1.3` : note d'exception sur
  `[DB_STRUCTURE_CHANGE_FORBIDDEN]`.
- `docs/arch/phase-b-db-scaffolding.md §8.5` : substance opérationnelle
  (lecture sentinel, invocation runner, consommation flag).
- `commands/{sdd-full,sdd-poc}.md` : détection basename + écriture sentinel +
  forçage `--rebuild-arch`.
