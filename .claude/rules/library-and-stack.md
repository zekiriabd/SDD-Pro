# Règle — Library & Stack (consolidated v7.0.0)

> **v7.0.0 merge** : fusionne `stack-completeness.md` (libs anti-derive,
> §2.4 catalog, runtime LTS, CVE) + `cors.md` (CORS pattern stack-aware).
> Stubs originaux **supprimés au sweep v7.0.0-alpha 2026-05-20** — tous
> les Read `@.claude/rules/{stack-completeness,cors}.md` historiques
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
(`.claude/stacks/{cat}/{stack-id}.md`) ou son `.libs.json`.

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
| **Kotlin**  | 2.1 LTS (2025) | TBD | 🟡 pin `kotlin-spring-boot.libs.json` = 2.3.21 (STS exception tracée) |

**Interdictions** : pin sur version STS (.NET 9, Node 23, Java 22…),
prerelease (`-rc/-preview/-alpha/-beta/-snapshot`) sans ADR, version
`latest` non-pinnée.

**Bypass STS** (rare, tracé) : ADR `ADR-{ts}-runtime-sts-exception.md`
+ `RuntimeException: dotnet9 (fin: 2026-05-12, migration -> dotnet10)`
dans Project Config → `validate_libs_catalog.py` émet WARN
`[RUNTIME_STS_EXCEPTION]`.

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
FIX: migrer vers LTS courante ({lts-version}) dans .claude/stacks/{cat}/{stack-id}.libs.json#versions
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

**Schéma JSON** : `.claude/templates/libs-catalog.schema.json` (draft 2020-12).
Structure :
```json
{
  "stackId": "kotlin-spring-boot",
  "category": "backend",
  "schemaVersion": 1,
  "buildSystem": "gradle | dotnet | npm | pnpm | yarn | maven | pip | poetry | uv | cargo | go-mod",
  "manifest": { "files": [...], "versionCatalogPath": "..." },
  "versions": { "kotlin": "2.3.21", "spring-boot": "4.0.6" },
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

### Scripts admin (`.claude/python/sdd_admin/`)

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

### Stacks migrés (17 catalogues au 2026-05-13)

**Backend** : `dotnet-minimalapi`, `kotlin-spring-boot`, `python-fastapi`,
`node-express`.

**Frontend** : `blazor-webassembly`, `react` (React 19 + Vite 6 +
Tailwind v4 + shadcn + TanStack + RHF/Zod + Turborepo), `vue` (Vue 3.5 +
Pinia + TanStack + VeeValidate), `angular` (19 standalone + signals).

**QA** (séparation stricte propriété QA, dé-dupliqué) : `dotnet-xunit`,
`blazor-bunit`, `node-vitest`, `python-pytest`, `kotlin-junit`,
`angular-jasmine`.

**UI Design Systems** : `radzen-blazor`, `shadcn` (7 core + 15 onDemand
Radix par capability), `vuetify`.

**Hors périmètre `.libs.json`** (par design) :
- `auth/*` : protocoles cross-langage (env vars, flux JWT/OIDC). Les
  libs auth concrètes (`Microsoft.Identity.Web`, `@azure/msal-browser`,
  `spring-security-oauth2-resource-server`, etc.) vivent dans le
  `.libs.json` du backend/frontend consommateur.
- `qa/code-quality.md` : règles QA pures (seuils sonar-like).
- `frontend/blazor-server` : **déplacé en `_drafts/fullstack/blazor-server.md` (v7.0.0 quarantine)**
  — le pattern monolithique est incompatible avec l'isolation front/back du
  scope `back-front` (cf. `ownership.md §1.bis`), et le scope `fullstack`
  est en quarantine v7.0.0 (non chargé, cf. CLAUDE.md §6). Pour Blazor,
  utiliser `frontend/blazor-webassembly` + un backend `.NET` séparé. Le `.libs.json`
  compagnon a été régénéré dans `fullstack/`.

### Dé-duplication QA (post-mortem 2026-05-07)

Libs de tests initialement en `onDemand` des catalogues backend.
**Erreur** : QA seul propriétaire des tests (cf. `qa.md` §Ownership) ;
dev-* n'installe JAMAIS de lib test en prod. Corrigé : backends
`onDemand` = capabilities **runtime prod** uniquement (excel, pdf,
redis-cache, cqrs, fast-mapping, file-upload, http-client) ; QA porte
toutes les libs test + frameworks intégration HTTP + mocking.

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
| Backend | `.claude/stacks/backend/*.md` | ✅ |
| Frontend | `.claude/stacks/frontend/*.md` | ✅ |
| UI Design System | `.claude/stacks/ui/*.md` | ✅ (composants natifs) |
| Auth | `.claude/stacks/auth/*.md` | hors périmètre (cf. §1.0) |
| QA | `.claude/stacks/qa/*.md` | ✅ |

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
FIX: 1. Ajouter {lib} version {X} dans .claude/stacks/{cat}/{stack-id}.libs.json
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

## 6.bis Schema/regex sync front↔back (post-mortem 2026-05-21)

**Règle load-bearing** : tout champ de DTO/payload partagé entre
backend et frontend DOIT avoir le **même contrat** (type, regex,
contraintes min/max) des deux côtés. Toute désynchro = bug runtime
silencieux à la première soumission de form.

### 6.bis.1 Type des IDs (post-mortem #1)

| Backend Kotlin/Spring | Frontend TS | Convention SDD_Pro |
|---|---|---|
| `val id: Int` (PostgreSQL serial) | `id: string` (RHF + DOM) | Coercer en string AU BOUNDARY fetch via `.map(o => ({ id: String(o.id), ... }))` côté `apiXxx.ts` |
| `val id: UUID` | `id: string` (UUID hex) | Pas de coercion (déjà string) |

**Anti-pattern** : laisser un `number` traverser jusqu'au form RHF.
React state + DOM value sont toujours string ; `===` strict échoue
silencieusement (`5 !== "5"`).

### 6.bis.2 Regex de validation (post-mortem #2)

| Backend `@Pattern` | Frontend Zod | Risque si désynchro |
|---|---|---|
| `^[0-9]{13}$` (EAN-13) | `^[0-9]+$` | 400 ProblemDetail au save sur user qui a tapé 5 chiffres |
| `^[0-9a-f]{8}-[0-9a-f]{4}-...$` (GUID) | `^\d+$` | rejet UI sur GUIDs valides backend |
| `@Size(max=100)` | `z.string().max(100)` | back rejette texte de 101 char accepté front |

**Convention canonique** : copier le regex exact de `@Pattern` (Jackson/
Jakarta Validation) côté Zod dans `src/schemas/{Domain}Schema.ts`.
Ajouter un commentaire `// MIRROR backend EanItemRequest.@Pattern "^[0-9]{13}$"`
pour traçabilité.

**Alternative future** : générer le client TS depuis l'OpenAPI 3 du
backend (`springdoc-openapi` → `openapi-typescript`) — élimine le drift
par construction. Non encore systématisé v7.0.0.

### 6.bis.3 Field naming (camelCase serialization)

Jackson par défaut sérialise les `val nom` Kotlin en `nom`, `val fkAnnonceur`
en `fkAnnonceur` (préservation du camelCase). Frontend TS DOIT utiliser
les mêmes clés. Tout renommage de champ DTO en backend exige un grep
frontend (`grep -rn "field.nom\|field.fkXxx" workspace/output/src/{AppName}/`)
pour aligner les consommateurs.

**Anti-pattern** : un champ `libelle` côté backend mappé sur `nom`
côté frontend → Jackson rejette le POST (400 `@NotBlank` sur `nom`
absent), ET la lecture en mode édition retourne `undefined` (front lit
`detail.nom` mais payload a `detail.libelle`). Cf. post-mortem FEAT 4.

### 6.bis.4 Pattern de revue

`code-reviewer` détecte ce type de drift via la classe
`[FRONTEND_BACKEND_CONTRACT_GAP]` (hard-blocking, override
`CodeReviewFailOn`). Cf. `error-classification.md §1.10`.

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

- `file-ownership.md §1` : agent dev-* ne touche pas les fichiers projet (réservé arch)
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

Dès qu'une SPA (React/Vue/Angular/Blazor WebAssembly) est servie sur
une origin différente du backend (typiquement dev `:5173` ↔ `:8080`,
prod `app.example.com` ↔ `api.example.com`), une **configuration CORS
explicite côté backend est OBLIGATOIRE**.

Sans elle, **toute requête `fetch`/`XHR` échoue silencieusement** avec
`TypeError: Failed to fetch` côté navigateur, page blanche error
boundary, backend logs vides (le préflight `OPTIONS` est rejeté avant
d'atteindre les handlers applicatifs).

Cette règle est **load-bearing** pour tout projet `appType: back-front`
avec `frontendKind: web` ou `mobile`. Sans elle, le contrat front↔back
est cassé en runtime.

---

## 1. Quand cette règle s'applique

| Cas | CORS requis ? |
|---|:---:|
| SPA + API séparés (`backend/*` + `frontend/*`) | ✅ OBLIGATOIRE |
| Mobile + API (`backend/*` + `mobiles/*`) | ✅ OBLIGATOIRE (origins `capacitor://`, `ionic://`, etc.) |
| ~~Fullstack monolithique~~ (`fullstack/*` en quarantine v7.0.0) | ⊘ non supporté en v7.0.0 — utiliser `back-front` |
| Backend headless (sans SPA) | ❌ N/A |

L'agent `arch` détecte le cas à partir de `## Active Tech Specs` du
`stack.md` (cf. CLAUDE.md §7 matrice de détection AppType).

### 1.bis Auto-injection arch (depuis v6.10.4)

L'agent `arch` STEP 4.5.6 propage automatiquement l'origin du frontend dev dans
la config backend (allowlist explicite, jamais de wildcard). Mapping :

| Frontend stack | Port dev | Origin injectée |
|---|---:|---|
| `react`, `vue` | 5173 | `http://localhost:5173` |
| `angular` | 4200 | `http://localhost:4200` |
| `blazor-webassembly` | 5097 | `http://localhost:5097` |

**Override possible** dans `## Project Config` de `stack.md` :
```yaml
Cors:AllowedOrigins: "http://localhost:5173,http://localhost:4173"
```
Si la clé est posée explicitement → arch préserve la valeur (User-set wins).

Détail algorithme : `agents/arch.md §4.5.6`.

---

## 2. Pattern correct par stack backend

### 2.1 .NET (dotnet-minimalapi)

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

### 2.2 Spring Boot (kotlin-spring-boot)

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

### 2.3 FastAPI (python-fastapi)

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

### 2.4 Node Express (node-express)

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

## 3. Alternative dev — Vite proxy (sans CORS backend)

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

## 4. Anti-patterns rejetés

| Anti-pattern | Pourquoi rejeté |
|---|---|
| `@CrossOrigin` annotation Spring sur controllers individuels | Fragmente la policy, oubli systématique sur nouveaux endpoints |
| `Access-Control-Allow-Origin: *` avec `AllowCredentials: true` | Spec CORS interdit cette combinaison (cookies refusés) |
| Allowed origins hardcodés dans le code | Doit venir de config/env (différent dev/prod) |
| Pas de `OPTIONS` preflight en allowed methods | Requêtes credentialled échouent silencieusement |
| Wildcard `*` sur `allowedHeaders` en prod avec credentials | Refusé par les navigateurs récents |
| CORS uniquement via reverse proxy (nginx, IIS) sans backup applicatif | Casse en dev local + tests intégration |

---

## 5. Vérification dev-backend / arch

### Pattern à grep en STEP build

```bash
# Backend Spring (Kotlin)
grep -r "@CrossOrigin" workspace/output/src/{BackendName}/ && WARN

# Backend .NET
grep -r "AddCors\|UseCors" workspace/output/src/{BackendName}/ || ERROR (manquant)

# FastAPI
grep -r "CORSMiddleware" workspace/output/src/{BackendName}/ || ERROR

# Node Express
grep -r "cors()" workspace/output/src/{BackendName}/ || ERROR
```

### Format ERROR

Préfixe `[SECURITY_CORS_MISSING]` (cf. `error-classification.md §1.6`
ou §1.11 selon contexte) :

```
ERROR: dev-backend {n}-{m} — CORS non configuré
CAUSE: [SECURITY_CORS_MISSING] backend SPA-facing sans config CORS — toute requête front échouera
FIX: ajouter Program.cs/CorsConfig.kt/main.py selon stack §2.{1..4}
     configurer CORS_ALLOWED_ORIGINS env var (csv des origins SPA dev + prod)
HINT: cf. .claude/rules/cors.md §2 pour le pattern stack-aware
```

---

## 6. Test d'acceptation

Toute FEAT impliquant un appel SPA→backend doit avoir au moins 1 AC
implicite couvert par cette règle :

> Given une SPA servie sur origin `X` et un backend sur origin `Y`,
> when la SPA envoie une requête fetch credentialled vers Y,
> then le préflight OPTIONS retourne 204/200 avec les headers
> `Access-Control-Allow-Origin: X` et `Access-Control-Allow-Credentials: true`,
> et la requête principale aboutit.

À matérialiser dans la phase QA API Gate (cf. `backend-first.md §1.1`).

---

## 7. Lien avec autres règles

- `backend-first.md` : la QA API Gate doit inclure ≥ 1 test CORS
  preflight (OPTIONS avec Origin) par endpoint exposé à la SPA.
- `source-first.md §1` : tout bug CORS en runtime → patch ce
  `rules/cors.md` (si gap) AVANT le fix code.
- `stack-completeness.md` : la lib CORS (Microsoft.AspNetCore.Cors,
  spring-security-config, fastapi[all], cors npm) est CORE de tout
  backend SPA-facing.

---

## 8. Source historique

Convention extraite du post-mortem CMS-Back 2026-05-11 (cf.
`source-first.md §1`) où CORS oublié sur Spring Boot avait causé
3 jours de debug sur projet client. Pattern canonique inliné aussi dans
`stacks/auth/azure-ad.md §5.2.7.9`.
