# ARCHI_MVC

Status: Reference
Validation: 🟢 reference (utilisé en defaut implicite pour les 4 backends SDD_Pro depuis l'origine — extrait en archi/ canonique 2026-05-16)
Pattern ID: archi-mvc
Scope: **pattern d'architecture backend** — Model-View-Controller layered. S'applique aux stacks `backend/*.md` lorsque `ArchiPattern: MVC` (défaut implicite si `## Active Architecture Pattern` absent). Ne s'applique PAS aux `fullstack/*` ni aux `mobiles/*` qui ont leur propre architecture documentée par stack.

---

# 1. Définition

**MVC layered backend** au sens SDD_Pro : pattern à séparation stricte par couches, avec injection de dépendances systématique et orientation **API REST** (pas de View HTML server-side — c'est le rôle de `fullstack/*` pour ça). Le "View" du MVC classique est ici la couche **DTO + Mapper** qui sérialise vers JSON.

Architecture cible :

```
HTTP Request
    │
    ▼
Controller / Endpoint  ── routing, validation entrée, dispatch
    │
    ▼
Service               ── logique métier, transactionalité
    │
    ▼
Repository            ── accès DB (ORM), pas de SQL brut hors d'ici
    │
    ▼
Entity (ORM)          ── modèle persistant, aucune logique métier
    │
    ▼ (sens retour : sortie sérialisée)
Mapper                ── Entity → DTO, centralisé
    │
    ▼
DTO (Input/Output/Model) ── structures de transfert, immutables
    │
    ▼
ApiResponse<T>        ── wrapper standard (status, data, metrics, errors)
    │
    ▼
HTTP Response (JSON)
```

**Pattern primaire** : `Controller → Service → Repository → Entity → Mapper → DTO`.

---

# 2. Couches canoniques

8 couches obligatoires (peuvent être renommées selon idiom tech — cf. §7) :

| # | Couche | Responsabilité | Dépend de |
|---|---|---|---|
| 1 | **Route / Endpoint** | Mapping URL → handler. Pure routing, aucune logique. | Controller |
| 2 | **Controller** | Validation entrée (schema), dispatch vers service, sérialisation réponse. Aucune logique métier. | Service |
| 3 | **Service (interface)** | Contrat métier publique. Référence DI canonique. | (rien, pure abstraction) |
| 4 | **Service (impl)** | Logique métier, transactionalité, orchestration cross-repository. | Repository, Mapper |
| 5 | **Repository** | I/O persistance via ORM. Pas de SQL brut hors d'ici. Pas de logique métier. | Entity |
| 6 | **Entity** | Modèle ORM persistant. Mapping schema DB ↔ classe. Aucune logique métier (anémique côté SDD_Pro). | (ORM framework) |
| 7 | **Mapper** | Conversion `Entity ↔ DTO`. Centralisé, pas de mapping inline. | Entity, DTO |
| 8 | **DTO** | Input (validation entrée), Output (réponse paginée), Model (structure partagée). Immutables. | (rien — data classes pures) |

Couches **transverses** (pas dans le flux mais obligatoires) :
- **Middleware** : gestion globale des exceptions → ProblemDetails RFC 7807. Logging structuré. Auth gate.
- **DbContext / Session** : configuration ORM (registered via DI). Pas d'instance directe dans Service ou Controller.

---

# 3. Mapping couche → répertoire (template)

Placeholders : `{BackendName}` = projet API, `{LibName}` = librairie partagée DTOs (si `LibStrategy ≠ none`). Convention `workspace/output/src/{BackendName}/{layer}/`.

| Couche | Path canonique |
|---|---|
| Route / Endpoint | `workspace/output/src/{BackendName}/{endpoints\|controllers\|routes}/` (selon tech) |
| Service interface | `workspace/output/src/{BackendName}/services/interfaces/` |
| Service impl | `workspace/output/src/{BackendName}/services/` (ou `services/implementations/`) |
| Repository | `workspace/output/src/{BackendName}/repositories/` |
| Entity | `workspace/output/src/{BackendName}/entities/` (ou `data/entities/`) |
| Mapper | `workspace/output/src/{BackendName}/mappers/` |
| DbContext | `workspace/output/src/{BackendName}/{entities/dbcontext\|data/dbcontext\|database}/` |
| Middleware | `workspace/output/src/{BackendName}/middleware/` |
| Input DTO | `workspace/output/src/{LibName}/inputs/` (ou `{BackendName}/dto/inputs/` si pas de LibName) |
| Output DTO | `workspace/output/src/{LibName}/outputs/` |
| Model DTO | `workspace/output/src/{LibName}/models/` |
| Schemas validation | `workspace/output/src/{BackendName}/schemas/` (Node Zod / Python Pydantic, intégré directement à l'Input DTO) |
| App entry / bootstrap | `workspace/output/src/{BackendName}/{Program.cs\|main.py\|server.ts\|Application.kt}` |

> Chaque stack `backend/*.md` peut **overrider** ce mapping dans son §1.3 si la convention du framework l'exige (e.g. .NET `Endpoints/` vs Node `routes/`). L'override est documenté localement, mais reste compatible avec ce squelette canonique.

---

# 4. Principes non négociables

**Architecture / data flow** :
- Aucune logique métier dans Route / Controller / Endpoint → toujours dans Service
- Aucune logique métier dans Entity (modèles anémiques — pas de méthode `entity.recalculate()`)
- Aucun accès DB direct depuis Controller → toujours via Service → Repository
- Aucun SQL brut hors Repository (interdit `prisma.$queryRaw`, `db.executeRaw`, `EntityManager.createNativeQuery` ailleurs)
- Aucun mapping manuel inline dans Controller / Service → toujours via Mapper centralisé
- DI systématique pour toutes les dépendances (Service, Repository, DbContext, HttpClient, Logger) — pas de `new XxxService()`, pas de Service Locator
- Service retourne des DTOs (Model/Output), **JAMAIS** des Entities (fuite ORM + over-fetch)

**Validation** :
- Validation entrée via schemas typés (FluentValidation .NET / Zod TS / Pydantic Python / Bean Validation Kotlin)
- Pas de `if (!input.field) throw...` — toujours déclaratif via schema

**Transactions** :
- `@Transactional` (Kotlin/Java) ou `using (var tx = ...)` (.NET) sur les méthodes Service qui ÉCRIVENT
- Pas de transactions dans Controllers

**Async / I/O** :
- Async/await partout sur les opérations I/O (DB, HTTP) — pas de `.Wait()`, `.Result`, blocage sync
- Pas de N+1 query : utiliser `Include` / `eager loading` / `JOIN FETCH` selon ORM

**Erreurs** :
- Gestion centralisée des exceptions HTTP via middleware global → ProblemDetails RFC 7807
- Aucun `try/catch` de formatage HTTP dans Controllers / Services — sauf re-throw métier vers exception métier custom (e.g., `EntityNotFoundException`)

**Logging** :
- Logger structuré injecté via DI (Serilog .NET / Pino Node / structlog Python / SLF4J Kotlin)
- Aucun `console.log`, `Console.WriteLine`, `print()`, `System.out.println` dans le code livré

**Sécurité** :
- Aucun secret hardcodé (DB password, JWT secret, API key) — toujours via config + env vars
- Body request loggé avec masquage des champs sensibles (password, token, secret, authorization)
- CSRF protection si endpoints prennent formulaire HTML (rare en MVC API)

---

# 5. Anti-patterns rejetés

À détecter par dev-backend STEP 6 (forbidden content scan) — toute occurrence rejette le fichier :

**Couche-violation** :
- Logique métier dans Route/Controller → `[LAYER_VIOLATION]`
- Accès DB depuis Controller → `[LAYER_VIOLATION]`
- Mapping inline (création manuelle de DTO depuis Entity sans Mapper) → `[LAYER_VIOLATION]`
- DbContext / Session instancié dans Service ou Controller (toujours injecté DI) → `[LAYER_VIOLATION]`
- Service qui retourne une Entity (au lieu d'un DTO) → `[LAYER_VIOLATION]`

**ORM misuse** :
- `findAll()` / `select * from` sans pagination sur table métier → over-fetch
- N+1 query (loop de `findById` au lieu d'un `findMany` + `where in`) → `[REVIEW_ANTI_PATTERN_N_PLUS_ONE]`
- Mutation sans transaction quand plusieurs tables impactées
- `cascade = ALL` par défaut sur relations — toujours explicite par opération
- Auto DDL `ddl-auto: update` en prod (Database-First → toujours `validate` ou `none`)

**Code quality** :
- `console.log` / `println` / `print` / `Console.WriteLine` brut → `[REVIEW_CONFUSING_NAMING]` (couvert par quality_scan)
- `any` / `dynamic` / `Any?` injustifié
- `TODO`, `FIXME`, `HACK` dans le code livré
- Imports relatifs profonds (`../../../`) au-delà de 2 niveaux → utiliser path alias / namespace
- `eval()`, `new Function()` (sécurité)
- Méthode > 30 lignes sans décomposition

**Sécurité** :
- Hardcoded secrets / connection strings → `[REVIEW_SECRETS_HARDCODED]` (hard-blocking)
- Token JWT / API key / password loggé en clair
- Endpoint sensible sans auth annotation explicite
- CORS `*` en production

**API contract** :
- Réponse 2xx non-wrappée — toute réponse doit être un `ApiResponse<T>` ou `ApiResponse<T[]>` (cf. §2 couche DTO)
- Status code HTTP non standard (utiliser 200, 201, 204, 400, 401, 403, 404, 409, 422, 500)
- Body POST/PUT non validé par schema

---

# 6. Naming conventions canoniques

Suffixes **obligatoires** (cross-tech) :

| Rôle | Suffix | Exemple |
|---|---|---|
| Controller / Endpoint | `Controller` ou `Endpoints` | `UsersController`, `UsersEndpoints` |
| Service interface | `I{Name}Service` (.NET/Java) ou `{Name}Service` (Python class) | `IUsersService`, `class UsersService(ABC)` |
| Service impl | `{Name}Service` (sans `Impl` postfix sur le nom de fichier) | `UsersService.cs`, `users_service.py` |
| Repository | `{Name}Repository` (ou `{Name}Repo` rare) | `UsersRepository` |
| Mapper | `{Name}Mapper` (classe statique ou profil AutoMapper) | `UsersMapper`, `UsersMappingProfile` (AutoMapper) |
| Entity | `{Name}` (singulier, PascalCase) ou `{Name}Entity` | `User`, `UserEntity` |
| Input DTO | `{Name}{Action}Input` | `UserCreateInput`, `UserFilterInput` |
| Output DTO | `{Name}{Action}Output` | `UserListItemOutput`, `UserDetailOutput` |
| Model DTO | `{Name}Model` (réponse client générale) | `UserModel` |
| Validator / Schema | `{Name}{Action}Schema` | `UserCreateSchema` |

**Suffixes INTERDITS** (universels) :
- `Dto`, `InputDto`, `OutputDto`, `Request`, `Response`, `Result` — utiliser `Input/Output/Model` SDD_Pro
- `Manager`, `Helper`, `Util` (sauf `utils/` strict réservé aux pure functions sans state)
- `Impl` postfix sur le nom de classe (l'implémentation porte le nom canonique, l'interface a `I*` ou hérite `ABC`)

**Conventions de fichier** :
- 1 fichier = 1 export principal (1 classe, 1 fonction, 1 interface)
- Barrels (`index.ts`, `__init__.py`) autorisés UNIQUEMENT dans `services/`, `repositories/`, `mappers/`, `entities/` pour re-export

---

# 7. Tech-specific overrides

Chaque backend stack adapte le pattern à ses idioms. Tableau de correspondance canonique :

| Concept canonique | `dotnet-minimalapi` | `kotlin-spring-boot` | `node-express` | `python-fastapi` |
|---|---|---|---|---|
| **Couche Controller** | `Endpoints/{Domain}Endpoints.cs` (static methods + `MapGroup`) | `controllers/{Domain}Controller.kt` (`@RestController`) | `routes/{domain}.routes.js` (`registerXxxRoutes(fastify)`) | `endpoints/{domain}.py` (`APIRouter`) |
| **DI Injection** | Constructor (primary constructor C# 12) | `inject()` ou constructor | `module.exports` + import | `Depends()` FastAPI |
| **Service annotation** | `IService<T>` + concrete class registered via `AddScoped<>()` | `@Service` (Spring stereotype) | `export const xxxService = {...}` (objet ou class) | `class XxxService(IXxxService): ...` |
| **Repository pattern** | `IRepository<T>` + EF Core via `IDbContextFactory` | `extends JpaRepository<T, ID>` (Spring Data) | Prisma client wrapper class | `AsyncSession` via `Depends(get_db)` |
| **Validation entrée** | FluentValidation `[Validator<TInput>]` | Bean Validation `@Valid @NotBlank` | Zod schema `XxxSchema.parse(body)` | Pydantic `BaseModel` auto |
| **Mapping** | AutoMapper profile (`Profile` class) | Extension fn Kotlin (`Entity.toModel()`) ou MapStruct | Plain function (mapEntityToDto) | Plain function ou TypeAdapter Pydantic |
| **Error handling** | Middleware ASP.NET → ProblemDetails | `@ControllerAdvice` global | Fastify `setErrorHandler()` | Middleware FastAPI |
| **Logging** | Serilog `ILogger<T>` injecté | SLF4J `LoggerFactory.getLogger(javaClass)` | Pino `fastify.log.info()` | structlog `structlog.get_logger()` |
| **Async** | `async Task<T>` partout | `suspend fun` ou `Mono<T>` (WebFlux) ou bloquant Spring MVC | `async/await` ESM | `async def` partout |
| **Persistance ORM** | EF Core (`DbSet<T>`) | Spring Data JPA + Hibernate | Prisma | SQLAlchemy 2.x async |
| **DbContext** | `AddDbContextFactory<>()` (Blazor SSR) ou `AddDbContext<>()` (Web API) | `EntityManagerFactory` (auto) | `new PrismaClient()` (singleton) | `async_sessionmaker()` + `Depends(get_db)` |

---

# 8. Capabilities applicables au pattern

Capabilities (cf. `stack-completeness.md §1.bis`) sont **orthogonales** au pattern — elles ajoutent des fonctionnalités sans changer le pattern de couches :

| Capability | Pattern impact |
|---|---|
| `excel`, `pdf`, `smtp`, `markdown` | Ajout d'un Service spécialisé (e.g., `ExcelExportService`) — pas de changement de pattern |
| `jwt`, `auth-azure-ad`, `auth-local` | Middleware auth + `[Authorize]` annotations — pas de changement |
| `redis-cache`, `caffeine-cache` | Ajout `ICacheService` injecté dans Service métier — pas de changement |
| `cqrs` (MediatR .NET, Mediator Kotlin) | **Variant** : remplace Controller direct → Service par Controller → `IMediator.Send(command)` → `CommandHandler`. Reste compatible MVC (juste 1 indirection). |
| `file-upload`, `websocket`, `http-client` | Ajout endpoint/middleware spécialisé — pas de changement |

Pour des **changements de pattern** (Aggregates DDD, Microservices) → utiliser `archi/ddd.md` ou `archi/microservice.md` à la place.

---

# 9. Combinaisons stack × pattern validées

| Combo | Status | Notes |
|---|---|---|
| `dotnet-minimalapi` × MVC | 🟢 reference | combo validé NounouJob 2026-05 |
| `kotlin-spring-boot` × MVC | 🟢 reference | combo validé CMS 2026-05-13 |
| `node-express` × MVC | 🟡 experimental | viable, non encore validé end-to-end |
| `python-fastapi` × MVC | 🟡 experimental | viable, non encore validé end-to-end |

Pour les `fullstack/*` et `mobiles/*` : architecture **propre à chaque stack**, ne suit pas ce pattern. Cf. §1 de chaque fichier de stack.

---

# 10. Pour les agents `dev-backend` / `arch`

**Lecture obligatoire** : `dev-backend` et `arch` doivent lire `archi/mvc.md` (ce fichier) en STEP de chargement du contexte LORSQUE :
- `## Active Architecture Pattern` du `stack.md` contient `ArchiPattern: MVC` (explicite)
- OU `## Active Architecture Pattern` est absent (défaut implicite v6.7.5+ : MVC)
- ET un stack `backend/*.md` est actif (cf. AppType=`back-front`)

**Précédence** : en cas de conflit entre ce fichier et un `backend/*.md` :
1. Les **idioms tech** du `backend/*.md` priment (§2.5 Naming, §7 ici)
2. Les **principes architecturaux** de `mvc.md` (ce fichier) priment sur tout
3. Les **suffixes interdits** sont l'union des deux fichiers (intersection des autorisés)

**Ne PAS lire ce fichier si** :
- `AppType: fullstack` (les stacks fullstack ont leur architecture propre, intégrée)
- `AppType: mobile-*` (idem pour les stacks mobiles)
- `ArchiPattern: DDD` → lire `archi/ddd.md` à la place
- `ArchiPattern: microservice` → lire `archi/microservice.md` à la place

---

# 11. Diff vs DDD et microservice

Vue comparative rapide (détails dans `archi/ddd.md` et `archi/microservice.md` Phase 2 SDD_Pro) :

| Aspect | MVC (ici) | DDD | microservice |
|---|---|---|---|
| Layer principal | Controller-Service-Repository-Entity | Domain-Application-Infrastructure-Presentation | Service-Domain-Infrastructure + Comm bus |
| Entity | Anémique (data class) | Riche (méthodes métier sur Aggregate) | Bounded Context restreint |
| Communication inter-couche | DI direct | Ports & Adapters (interfaces strictes) | Event-driven (Kafka/RabbitMQ) + REST/gRPC |
| Mapping | Mapper centralisé | DTO intermédiaire entre Application et Presentation | Schemas versionnés (Avro/Protobuf) |
| Use case primary | CRUD + business logic mixte dans Service | UseCase / CommandHandler explicite | Per-service domain logic |
| Best for | Apps métier classiques, équipes mid-size | Apps complexes avec règles métier riches | Apps distribuées, équipes multiples, scaling indépendant |

**SDD_Pro defaut** = MVC car couvre 80% des projets d'entreprise.
