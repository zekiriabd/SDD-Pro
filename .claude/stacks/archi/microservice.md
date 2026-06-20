# ARCHI_MICROSERVICES

Status: Experimental
Validation: 🟡 experimental — **roadmap v7.2.0 (cible 2026-Q4 stable, 2027-Q1 bench-validated)**. Pré-requis : ADR `governance-major-microservice-validation` (à créer) couvrant (1) périmètre exact (1 service / N services), (2) contracts inter-service (REST/gRPC/event), (3) observability minimum (OpenTelemetry, health probes), (4) test runtime end-to-end. Tant que cet ADR n'est pas accepté, le pattern reste utilisable mais hors SLA.
Support: ⚠ Non supporté commercialement (audit C3, 2026-06-06 + MN5, 2026-06-07) — exclu du SLA produit jusqu'à ADR ci-dessus. Voir CLAUDE.md §6 et docs/validated-combos.md.
Pattern ID: archi-microservice
Scope: **pattern d'architecture backend** — Microservices (Sam Newman 2015 + Chris Richardson 2018). S'applique aux stacks `backend/*.md` lorsque `ArchiPattern: microservice`. Ne s'applique PAS aux `fullstack/*` (monolithe par définition) ni aux `mobiles/*`.

> **Scope SDD_Pro important** : un microservice = **UN seul backend** géré par SDD_Pro. Ce pattern décrit comment **structurer UN service** pour qu'il soit prêt à vivre dans un écosystème microservices (résilience, observability, contracts, isolation). **Multi-service orchestration** (saga distribuée, service mesh, K8s manifests) est **hors scope** SDD_Pro v6 — relève des Ops/DevOps. Un `/sdd-full` génère **UN service** ; l'écosystème complet est construit en répétant l'opération pour chaque service.

---

# 1. Définition

**Microservices architecture** au sens SDD_Pro : chaque backend est un **service autonome, indépendamment déployable, propriétaire de ses données**, avec des **frontières métier explicites** (Bounded Context au sens DDD), une **communication externalisée** (REST/gRPC sync OU message bus async), et une **résilience + observability** built-in.

**Différence fondamentale vs MVC et DDD** :
- **MVC/DDD** se préoccupent de la **structure interne** du code
- **microservice** se préoccupe de **comment ce service interagit avec le monde extérieur** (réseau, autres services, observability, deploy)
- En interne, un microservice peut **réutiliser MVC ou DDD** pour son organisation locale (souvent DDD-lite par bounded context)

Architecture cible (vue système — 1 service) :

```
                    ┌─────────────────────────────────────────────────────┐
                    │   API Gateway / BFF (externe — pas dans ce projet)  │
                    └────────────────┬────────────────────────────────────┘
                                     │ HTTP/gRPC
                ┌────────────────────▼────────────────────┐
                │   This Microservice ({BackendName})     │
                │   ┌────────────────────────────────┐   │
                │   │ Presentation                   │   │ ← REST/gRPC controllers
                │   │  + HealthCheck /actuator/health │   │
                │   │  + Metrics /actuator/prometheus │   │
                │   │  + Versioned API /api/v1/...   │   │
                │   └────────────┬───────────────────┘   │
                │                │                       │
                │   ┌────────────▼───────────────────┐   │
                │   │ Application (DDD-lite)         │   │ ← UseCases, ports
                │   │  + Resilience (Polly/r4j)      │   │
                │   │  + DistributedTracing          │   │
                │   └────────────┬───────────────────┘   │
                │                │                       │
                │   ┌────────────▼───────────────────┐   │
                │   │ Domain                         │   │ ← Aggregates Bounded Context
                │   │  (ce service uniquement)       │   │
                │   └────────────┬───────────────────┘   │
                │                │                       │
                │   ┌────────────▼───────────────────┐   │
                │   │ Infrastructure                 │   │
                │   │  + DB Adapter (DB PRIVÉE)      │ ─┐│ ← DB par service, JAMAIS partagée
                │   │  + Event Publisher (Outbox)    │ ─┼┼─▶ Event Bus (Kafka/RabbitMQ — externe)
                │   │  + HTTP Clients (Refit/Feign)  │ ─┼┼─▶ Other services (REST/gRPC)
                │   │  + Auth (JWT validation)       │ ─┘│
                │   └────────────────────────────────┘   │
                └─────────────────────────────────────────┘
                          ↑                ↑
                  External Identity   External Logging (Loki/ELK)
                  Provider (OIDC)     External Metrics (Prometheus)
                                      External Traces (Jaeger/Tempo)
```

**5 piliers non négociables** :
1. **Database per service** (DB privée, jamais partagée)
2. **Communication explicite** (REST/gRPC sync OU events async — pas de DB access cross-service)
3. **Résilience** (circuit breaker, retry, timeout, bulkhead)
4. **Observability** (logs JSON, metrics Prometheus, traces OpenTelemetry, healthchecks)
5. **Idempotence + Versioning** (API versioned, opérations idempotentes par défaut)

---

# 2. Couches canoniques

Reprend l'organisation interne **DDD-lite** (cf. `archi/ddd.md`) + ajoute les couches spécifiques microservice :

### 2.1 Layers internes (héritées DDD-lite)

- **Domain** : Aggregates du bounded context **propre à ce service** (jamais d'Aggregates partagés cross-service)
- **Application** : UseCases / CommandHandlers / QueryHandlers (Mediator CQRS optionnel)
- **Infrastructure** : DB, Event Publisher, HTTP clients, Auth — décrites §2.2 ci-dessous
- **Presentation** : REST/gRPC controllers, contract DTOs

### 2.2 Couches microservice-specific (Infrastructure)

| Couche | Responsabilité |
|---|---|
| **HealthChecks** | Endpoints `/health/live` (liveness) + `/health/ready` (readiness) + `/health/startup` (Kubernetes). Vérifie DB connection, dépendances critiques. |
| **Metrics** | Endpoint `/metrics` (Prometheus format) ou `/actuator/prometheus` (Spring). Counters, gauges, histograms métier. |
| **Distributed Tracing** | OpenTelemetry SDK + exporter (Jaeger / Tempo / Azure Application Insights). Propage `traceparent` header sur tous les outbound HTTP/gRPC/messages. |
| **Logging structuré** | JSON only. Champs obligatoires : `timestamp`, `level`, `message`, `service` (= `{BackendName}`), `traceId`, `spanId`, `correlationId`. Pas de PII en clair. |
| **Resilience policies** | Circuit breaker + Retry (exponential backoff + jitter) + Timeout + Bulkhead (limit concurrent calls) — sur **TOUT** outbound network call. |
| **HTTP Clients typés** | Refit (.NET) / Retrofit (Kotlin) / Got (TS) / httpx + tenacity (Python). Toujours via interface contract, jamais HttpClient direct. |
| **Event Publisher (Outbox)** | Publie events vers message bus externe via pattern Transactional Outbox (cf. §6). |
| **Message Consumer** | Consomme events depuis bus externe avec **idempotence** (déduplication via message ID). |
| **API Versioning** | `/api/v1/...` strict obligatoire. Breaking change = nouvelle version (`/api/v2/...`), ancienne maintenue avec `Deprecation` header. |
| **Authentication adapter** | Valide JWT (issuer remote — pas d'IDP local), extract claims, expose `ICurrentUser` à l'Application layer. |
| **Service Discovery client** | (Optionnel) Consul / Eureka / DNS Kubernetes. Souvent géré par sidecar (Istio/Linkerd) — ce projet peut s'en passer si déploiement K8s natif. |

### 2.3 Contrats inter-service (OpenAPI / AsyncAPI)

- **OpenAPI 3.x** pour REST sync (Swagger UI + JSON spec exposés)
- **AsyncAPI 2.x** pour events async (Kafka / RabbitMQ schemas)
- **Proto3** pour gRPC (`.proto` files)
- **Schemas versionnés** : un changement breaking = nouvelle version du schema, ancienne maintenue
- **Contract testing** : Pact (consumer-driven contracts) — capability optionnelle

---

# 3. Mapping couche → répertoire (template)

Placeholders : `{BackendName}` = ce service. `{Module}` = bounded context interne (souvent **UN seul module** si le service est focalisé).

```
workspace/output/src/{BackendName}/
├── Domain/{Module}/                        ← cf. archi/ddd.md §3 (Aggregates, VOs, Events, Repositories interfaces)
├── Application/{Module}/                   ← cf. archi/ddd.md §3 (UseCases, Validators, Application DTOs)
├── Infrastructure/
│   ├── Persistence/
│   │   ├── {Orm}DbContext.{ext}
│   │   ├── Repositories/                   ← impl IRepository
│   │   └── Outbox/                         ← outbox pattern (OBLIGATOIRE microservice)
│   ├── Messaging/
│   │   ├── Producers/                      ← KafkaProducer, RabbitMqProducer
│   │   ├── Consumers/                      ← KafkaConsumer, message handlers
│   │   └── Schemas/                        ← Avro/Protobuf schemas si Kafka
│   ├── HttpClients/
│   │   ├── Interfaces/                     ← IOtherServiceClient (contract)
│   │   └── Adapters/                       ← Refit/Retrofit/Got impl avec resilience
│   ├── Authentication/                     ← JWT validation
│   └── Resilience/                         ← Polly policies / Resilience4j configs
├── Presentation/
│   ├── Controllers/                        ← versionés /api/v1/
│   ├── HealthChecks/                       ← /health/live, /health/ready, /health/startup
│   ├── Metrics/                            ← /metrics endpoint Prometheus
│   ├── Filters/                            ← global exception filter → ProblemDetails RFC 7807
│   └── Contracts/                          ← Output DTOs versionnés (v1, v2…)
├── Configuration/
│   ├── appsettings.json                    ← config base (lue par config lib)
│   ├── appsettings.{Environment}.json      ← dev/staging/prod
│   └── secrets.example                     ← template (jamais commit secrets réels)
├── Telemetry/
│   ├── Logging/                            ← Serilog/Pino/structlog config JSON
│   ├── Tracing/                            ← OpenTelemetry SDK config
│   └── Metrics/                            ← Prometheus exporter
├── Migrations/                             ← DB migrations (Flyway / EF / Alembic / Prisma)
├── docs/
│   ├── openapi.yaml                        ← spec API REST (OpenAPI 3.x)
│   ├── asyncapi.yaml                       ← spec events (AsyncAPI 2.x — si event-bus)
│   └── runbook.md                          ← procédures ops (alerts, troubleshooting)
└── Dockerfile                              ← container image build
```

**Convention `{Module}`** : pour un microservice typique, **1 seul `{Module}`** correspondant au bounded context du service. Si le service grossit avec plusieurs modules → considérer le splitter en 2 services.

---

# 4. Principes non négociables

### 4.1 Database per service (cardinal)
- Ce service a sa **propre instance de DB** (ou son propre schema/database dans une instance mutualisée — acceptable temporairement)
- **JAMAIS de connexion directe à la DB d'un autre service** — même pour lecture
- Communication cross-service = REST/gRPC (sync) OU events (async) UNIQUEMENT
- Si besoin de données d'un autre service → **api call** OU **read model** local (alimenté par events async)

### 4.2 Statelessness
- Service stateless : **aucune session in-memory** propre à un utilisateur (utiliser Redis pour caches partagés si capability `redis-cache`)
- Permet scaling horizontal (multiple instances) sans configuration session sticky
- **Idempotence** des opérations critiques (replays Kafka, retries client)

### 4.3 Resilience (obligatoire sur outbound calls)
- **Tout** appel HTTP/gRPC sortant DOIT avoir :
  - **Timeout** explicite (jamais infini — typiquement 5-30s selon SLA dépendance)
  - **Retry** : exponential backoff + jitter, max 3 retries, idempotence requise
  - **Circuit breaker** : open après N échecs consécutifs (typiquement 5), half-open après cooldown (30-60s)
  - **Bulkhead** : limite concurrent calls à une dépendance (typiquement 10-50)
- Patterns implémentés via : Polly (.NET 8+ via `Microsoft.Extensions.Http.Resilience`), Resilience4j (Java/Kotlin), opossum (Node), tenacity (Python)
- **Fallback** : sur circuit open, retourner valeur dégradée (cache, valeur par défaut) plutôt que erreur 503 si possible

### 4.4 Observability (3 piliers)
- **Logs structurés JSON** : Serilog / Pino / structlog avec champs `service`, `traceId`, `spanId`, `correlationId`, `level`, `timestamp`, `message`. Pas de logs free-form.
- **Metrics Prometheus** :
  - `http_requests_total` (counter, labels: method, route, status)
  - `http_request_duration_seconds` (histogram, labels: method, route)
  - `db_query_duration_seconds` (histogram)
  - `external_call_duration_seconds` (histogram, label: dependency)
  - `business_metric_*` (counters / gauges spécifiques métier)
- **Distributed Tracing OpenTelemetry** :
  - Auto-instrumentation HTTP server/client, DB calls, message bus
  - Propagation `traceparent` W3C header
  - Sampling tail-based ou rate-limit (typiquement 1-10% en prod)

### 4.5 API contracts stricts
- Versioning URL `/api/v1/...` obligatoire (jamais header-based — débat clos en faveur URL pour clarté)
- **Breaking change interdit** sur une version existante (= add only, ne jamais retirer un champ ou changer un type)
- OpenAPI spec **maintenue à jour** (CI fail si drift entre code et spec)
- **Idempotent par défaut** sur POST si possible (header `Idempotency-Key` accepté pour déduplication)
- Status codes RFC 7231 : 200 OK, 201 Created + Location, 202 Accepted (async), 204 No Content, 400 Bad Request, 401, 403, 404, 409 Conflict, 410 Gone (version dépréciée), 422 Unprocessable, 429 Rate Limited, 5xx serveur. Toujours `ProblemDetails` RFC 7807 pour erreurs.

### 4.6 HealthChecks (3 endpoints)
- **`/health/live`** : le process tourne (return 200 unconditional sauf bug interne). Kubernetes `livenessProbe`.
- **`/health/ready`** : le service est prêt à recevoir du traffic — DB joignable, event bus joignable, dépendances critiques OK. Kubernetes `readinessProbe`.
- **`/health/startup`** : initialisation terminée (migrations DB appliquées, cache warmup fini). Kubernetes `startupProbe` (pour services lents au boot, évite kill premature).

### 4.7 Configuration externalisée
- **Aucun secret en code** ni en config versionnée
- Source de vérité : env vars (12-factor) OU vault externe (HashiCorp Vault, AWS SSM, Azure KeyVault, K8s Secrets)
- En SDD_Pro : `arch` Phase A injecte env vars depuis `## Active Database` + `## Active Auth Specs` + `## Active SMTP Server` dans `config/default.json` (cf. `node-express.md §8.2`) OU `appsettings.{env}.json`
- Hot-reload de config (capability `config-hot-reload`) optionnel

### 4.8 Internal architecture
- Hérité de `archi/ddd.md` (recommandé) OU `archi/mvc.md` si service simple — le choix dépend de la complexité métier intra-service
- **Bounded context unique** par service (corollaire de Database per service)
- DDD-lite acceptable (Aggregate + Repository sans tout le tooling Mediator/CQRS si service simple)

---

# 5. Anti-patterns rejetés

### 5.1 Découpage / boundaries (cardinal)

- **Distributed monolith** : services qui se parlent en chaîne pour chaque opération (ex. service A → B → C → D pour CreateOrder) → re-fusionner en monolithe
- **Database partagée** entre 2 services → `[LAYER_VIOLATION]` cardinal. Toute requête cross-service via API ou events.
- **Données dupliquées hors raison** : un service ne maintient pas une copie complète d'un autre service "pour la commodité" — utiliser read model alimenté par events si vraiment nécessaire
- **Service trop petit** (anémique, "nano-service") : si un service ne contient que 2-3 endpoints CRUD sur 1 table → fusionner avec un service voisin
- **Pas de bounded context clair** : service nommé `utility-service` ou `helper-service` → c'est un monolithe déguisé

### 5.2 Communication

- **Synchronous chains** : Service A appelle B qui appelle C qui appelle D synchronously → latence cumulative, fragilité (1 down = chaîne down). Découper via events async.
- **Shared business logic** entre services → soit duplication acceptée (préférable), soit extract en library partagée (acceptable si stable), soit re-design (mauvais boundary)
- **Event payload bloated** : event contient toute la donnée d'un Aggregate au lieu de juste le diff/référence. Préférer **thin events** (juste id + type) + lookup via API si consumer a besoin plus.
- **No correlationId** propagé dans les events / API calls → débuggage cross-service impossible

### 5.3 Resilience absente

- **Outbound HTTP/gRPC sans timeout** → service hang sur dépendance lente
- **Outbound sans circuit breaker** → cascading failures pendant outage dépendance
- **Retry sur opération non-idempotente** sans dedup key → données dupliquées
- **Retry sans backoff** → exacerbe la panne de la dépendance (DDoS du downstream)

### 5.4 Observability lacunaire

- **`console.log` / `println` / `print()` brut** au lieu de logger structuré
- **Logs sans `traceId`** → impossible de corréler les logs d'une même requête cross-service
- **Pas de healthcheck** ou healthcheck qui ne vérifie pas les dépendances critiques
- **Pas de métriques métier** (uniquement HTTP standard) — perd la visibilité business
- **Secrets / tokens / PII loggés** → fuite données

### 5.5 API contracts

- **API sans versioning** → couplage temporel client/service, deploy frozen
- **Breaking change sur version existante** (champ obligatoire retiré, type changé)
- **OpenAPI spec out-of-sync** avec le code → consumer surpris
- **POST non-idempotent** sans dedup → double-trigger sur retry réseau
- **CORS `*` en production** → security risk

### 5.6 Deploy

- **Dockerfile multi-stage manquant** → image bloated (300MB+ au lieu de 50-100MB)
- **`USER root` dans le Dockerfile final** → security risk
- **Healthcheck Docker absent** → orchestrator ne sait pas si le service est sain
- **Migrations DB embarquées dans startup app** → race condition multi-instance → utiliser job de migration séparé (Init Container K8s)

### 5.7 Autres
Hérités de `archi/ddd.md §5` (couches DDD-lite respectées) + `archi/mvc.md §5` (anti-patterns universels — secrets hardcodés, console.log, etc.).

---

# 6. Naming conventions canoniques

Hérité de `archi/ddd.md §6` (Aggregate, Command, Query, etc.) + ajouts microservice-specific :

| Rôle | Suffix / Pattern | Exemple |
|---|---|---|
| HTTP Client interface | `I{Other}Client` (.NET) / `{Other}Client` (interface autres langs) | `IBillingServiceClient`, `BillingServiceClient (Kotlin interface)` |
| HTTP Client impl | `{Other}Client` (impl) ou `Refit{Other}Client` | `RefitBillingServiceClient`, `RetrofitBillingServiceClient` |
| Resilience policy | `{Other}{Operation}Policy` | `BillingChargePolicy` (circuit breaker + retry + timeout) |
| Event publisher | `{Module}EventPublisher` ou `Outbox{Module}Publisher` | `OrderEventPublisher`, `OutboxOrderPublisher` |
| Event consumer / handler | `{Event}Consumer` ou `{Event}Handler` | `PaymentReceivedConsumer`, `OrderShippedHandler` |
| Integration event (cross-service) | `{Aggregate}{PastTense}IntegrationEvent` | `OrderShippedIntegrationEvent` (distinct du Domain Event interne `OrderShipped`) |
| Outbox entity (DB) | `OutboxMessage` ou `IntegrationEventLog` | `OutboxMessage` |
| Inbox entity (dedup) | `InboxMessage` ou `ProcessedEvent` | `InboxMessage` |
| Saga / Process Manager | `{Process}Saga` | `OrderFulfillmentSaga` |
| API Version | suffix par module / classe — préfixe URL `/api/v1/` | `OrdersControllerV1`, `OrdersControllerV2` |
| HealthCheck | `{Dependency}HealthCheck` | `DatabaseHealthCheck`, `KafkaHealthCheck` |
| Metric | snake_case Prometheus convention | `orders_created_total`, `payment_processing_duration_seconds` |
| Configuration class | `{Concern}Options` ou `{Concern}Config` | `KafkaOptions`, `ResilienceConfig` |

**Suffixes INTERDITS** (en plus de DDD §6) :
- `Service` au sens generic — utiliser `Client` (HTTP), `Publisher`/`Consumer` (events), `Adapter` (external)
- `Manager`, `Helper` (sauf utils/ pure)
- `Util`
- `Mgr` (abbréviation interdite)

---

# 7. Tech-specific overrides

| Concept canonique | `dotnet-minimalapi` | `kotlin-spring-boot` | `node-express` | `python-fastapi` |
|---|---|---|---|---|
| **Resilience lib** | `Microsoft.Extensions.Http.Resilience` 9.0 (succède Polly direct) | **Resilience4j** 2.x (`@CircuitBreaker @Retry @TimeLimiter`) | **opossum** (circuit breaker) + **p-retry** + **AbortController** (timeout) | **tenacity** (retry) + **circuitbreaker** + **httpx** timeout |
| **HTTP client typed** | **Refit** 8.0 (interfaces avec attributes `[Get("...")]`) + `IHttpClientFactory` | **Retrofit** 2.x ou **Spring Cloud OpenFeign** | **got** 14.x + zod schemas pour parse responses | **httpx** + Pydantic models pour parse |
| **OpenTelemetry** | `OpenTelemetry.Extensions.Hosting` + exporters (Otlp / Jaeger / Console) | **OpenTelemetry Spring Boot starter** + auto-instrumentation | **`@opentelemetry/sdk-node`** + auto-instrumentation packages | **`opentelemetry-distro`** + `opentelemetry-instrumentation-fastapi` |
| **Prometheus metrics** | **OpenTelemetry.Exporter.Prometheus.AspNetCore** ou `prometheus-net.AspNetCore` | **Micrometer** + `micrometer-registry-prometheus` (built-in Spring Actuator) | **prom-client** | **prometheus-client** + `prometheus-fastapi-instrumentator` |
| **Structured logging** | **Serilog.AspNetCore** + `Serilog.Sinks.Console` (JsonFormatter) + `Serilog.Enrichers.Span` (OTel context) | **Logback** avec encoder JSON (`logstash-logback-encoder`) + MDC enrichment | **Pino** (déjà CORE node-express.md) + `pino-pretty` dev | **structlog** + `structlog.contextvars` pour traceId binding |
| **HealthCheck framework** | **`Microsoft.Extensions.Diagnostics.HealthChecks`** + UI optionnel | **Spring Boot Actuator** `/actuator/health/{liveness,readiness}` natif | **terminus** (custom) ou **@godaddy/terminus** | **starlette.responses** custom OU **fastapi-health** lib |
| **Event bus client (capability event-bus)** | **MassTransit** 8.x OU **Confluent.Kafka** OU **RabbitMQ.Client** | **Spring Cloud Stream** (Kafka/RabbitMQ binders) | **kafkajs** OU **amqplib** | **aiokafka** OU **aio-pika** |
| **Outbox** | **EF Core OutboxMessage** entity + **Quartz.NET** worker OU **MassTransit Outbox** built-in | **JPA OutboxMessage** entity + Spring `@Scheduled` poller OU **Outboxer** lib | **Prisma OutboxMessage** + **bull/bullmq** worker | **SQLAlchemy OutboxMessage** + **Celery** worker |
| **API versioning** | `Microsoft.AspNetCore.Mvc.Versioning` ou Minimal API URL prefix natif | `@RequestMapping("/api/v1/...")` ou Spring REST Docs versioning | URL prefix dans `route.ts` (`'/api/v1/'`) | `APIRouter(prefix="/api/v1")` |
| **JWT validation** | **Microsoft.AspNetCore.Authentication.JwtBearer** | **spring-boot-starter-oauth2-resource-server** | **fast-jwt** OU **jose** | **python-jose** OU **PyJWT** + auth dependency |
| **Service discovery (optionnel)** | **Consul.NET** OU **Steeltoe.Discovery** OU K8s DNS natif | **Spring Cloud Consul** / **Eureka** | **node-consul** | **python-consul2** |
| **Dockerfile pattern** | multi-stage `FROM mcr.microsoft.com/dotnet/sdk → mcr.microsoft.com/dotnet/aspnet` | multi-stage `FROM gradle:jdk21 → eclipse-temurin:21-jre-alpine` | multi-stage `FROM node:22-alpine → distroless/nodejs22-debian12` | multi-stage `FROM python:3.12-slim → python:3.12-alpine` + `uv` |

---

# 8. Capabilities applicables au pattern microservice

| Capability | Pattern impact | Recommandation |
|---|---|---|
| `event-bus` (Kafka/RabbitMQ/NATS) | Active producteurs + consommateurs + Outbox automatique | **Strongly recommended** pour communication async cross-service |
| `outbox` | Active Outbox table + worker + dedup | **Obligatoire** dès qu'event-bus actif (sinon perte events au crash) |
| `inbox` | Active Inbox table pour dedup côté consumer | Recommandé en complément outbox |
| `resilience` | Polly / Resilience4j / opossum / tenacity en CORE | **Obligatoire** (intégré dans CORE du stack microservice par défaut) |
| `opentelemetry` | OTel SDK + auto-instrumentation + exporters | **Obligatoire** (CORE) |
| `prometheus` | Exporter Prometheus | **Obligatoire** (CORE) |
| `healthchecks` | Endpoints `/health/{live,ready,startup}` | **Obligatoire** (CORE) |
| `api-versioning` | Helpers de versioning par framework | **Obligatoire** (CORE) |
| `contract-testing` (Pact) | Consumer-driven contract tests | Recommandé si >2 consumers du service |
| `jwt` | JWT validation (resource server, pas IDP) | **Obligatoire** sur tout endpoint non-public |
| `redis-cache` | Distributed cache | Recommandé si service stateless avec lookup fréquent |
| `service-discovery` (Consul/Eureka) | Client discovery | Optionnel — souvent géré par sidecar K8s/Istio |
| `saga` | Saga orchestrator (MassTransit Saga, Spring Cloud Sleuth) | Activé si transactions distribuées nécessaires (rare, à éviter — préférer eventual consistency) |
| `feature-flags` | LaunchDarkly / Unleash / custom | Recommandé pour déploiement progressif |

---

# 9. Combinaisons stack × pattern validées

| Combo | Status | Notes |
|---|---|---|
| `dotnet-minimalapi` × microservice | 🟡 experimental | excellent fit : `Microsoft.Extensions.Http.Resilience` 9.0 + OpenTelemetry natif + MassTransit |
| `kotlin-spring-boot` × microservice | 🟡 experimental | excellent fit : Spring Cloud + Resilience4j + Actuator + Micrometer (écosystème Java mature) |
| `node-express` × microservice | 🟡 experimental | viable mais demande discipline (opossum + OpenTelemetry + Pino bien configurés) |
| `python-fastapi` × microservice | 🟡 experimental | viable, tenacity + opentelemetry-instrumentation-fastapi + structlog matures |

**Combo NON recommandé** : `microservice` + AppType=`fullstack` → WARNING `[STACK_INCOMPAT]` car contradictoire (fullstack = monolithe par définition).

---

# 10. Pour les agents `dev-backend` / `arch`

**Lecture obligatoire** : `dev-backend` et `arch` doivent lire `archi/microservice.md` (ce fichier) en STEP de chargement du contexte LORSQUE :
- `## Active Architecture Pattern` du `stack.md` contient `ArchiPattern: microservice`
- ET un stack `backend/*.md` est actif (cf. AppType=`back-front`)

**Précédence** :
1. Idioms tech du `backend/*.md` priment (§2.5 Naming, §1.4 overrides)
2. Principes microservice (ce fichier §4) priment sur tout (Database per service, resilience, observability)
3. Internal architecture : suit `archi/ddd.md` par défaut OU `archi/mvc.md` si l'US ne nécessite pas l'overhead DDD
4. Suffixes interdits = union des fichiers

**Mapping différent vs MVC et DDD pur** : arch Phase A scaffolde :
- L'arborescence DDD (cf. `archi/ddd.md §3`) **PLUS** les dossiers microservice-specific (cf. §3 ci-dessus : `HealthChecks/`, `Metrics/`, `Resilience/`, `Telemetry/`, `Messaging/`, `HttpClients/`)
- **Dockerfile multi-stage** obligatoire (template stack-specific)
- **`docs/openapi.yaml`** + `docs/runbook.md` (templates initial)
- **CORE libs étendu** : ajoute resilience + OpenTelemetry + Prometheus + healthcheck framework par défaut (cf. §7 tech-specific)

**Discipline supplémentaire** :
- Au STEP 5 (plan), dev-backend DOIT vérifier que tout outbound HTTP/gRPC call a une policy resilience (circuit breaker + retry + timeout)
- Au STEP 6 (build), check : tous les endpoints exposés sont versionnés `/api/v1/...`
- Au STEP 6 : check OpenAPI spec mise à jour si endpoint ajouté (CI fail si drift)
- Aucun Domain Event publié SANS passer par Outbox (pattern transactionnel obligatoire pour event-bus actif)

**Ne PAS lire ce fichier si** :
- `AppType: fullstack` (incompat — WARNING au preflight)
- `AppType: mobile-*` (sans objet)
- `ArchiPattern: MVC` → lire `archi/mvc.md`
- `ArchiPattern: DDD` → lire `archi/ddd.md`

---

# 11. Diff vs MVC et DDD

| Aspect | MVC | DDD | microservice (ici) |
|---|---|---|---|
| Layers | Controller-Service-Repository-Entity | Domain-Application-Infrastructure-Presentation | DDD + couches microservice (Resilience, Telemetry, Messaging) |
| Cœur de gravité | Service | Aggregate | Service boundary + comm contracts |
| Communication interne | DI direct | Mediator + DomainEvents | DDD + Resilience policies obligatoires sur outbound |
| Communication externe | API REST simple | API REST + Events optionnels | API REST + Events + Contracts versionnés + Service discovery |
| DB | Partageable monolithe | Partageable monolithe (cohérence Aggregate) | **DB par service obligatoire** (cardinal) |
| Observability | Logs basiques + Serilog/Pino | Idem MVC | **3 piliers obligatoires** (logs + metrics + traces OTel) |
| Deploy unit | Monolithe (1 process) | Monolithe (1 process) | Service indépendant (1 image Docker par service) |
| Best for | CRUD simple | Métier complexe interne | Apps distribuées, équipes multiples, scaling indépendant |
| Coût ops | Faible | Moyen | **Élevé** (K8s, observability stack, event broker, service mesh) |
| Latence | Faible (in-process) | Faible (in-process) | Moyenne (network hops cross-service) |
| Cohérence | Forte (transactions ACID) | Forte intra-Aggregate, eventual inter-Aggregate | Eventual partout (eventual consistency par design) |
| Failure mode | All-or-nothing (1 bug = downtime) | All-or-nothing | Partiel (1 service down ≠ tout down si bien découpé) |

**Quand choisir microservice** :
- ✅ Multiple équipes indépendantes (ownership clair par service)
- ✅ Scaling indépendant requis (1 partie chargée 100×, autres 1×)
- ✅ Polyglot tech justifié (Node pour I/O, Python pour ML, .NET pour business core)
- ✅ Disponibilité critique (1 partie down ne tue pas le système)
- ✅ Équipe ops mature (K8s, observability, IaC)
- ❌ Équipe <10 devs ou MVP (over-engineering — monolithe modulaire suffit)
- ❌ Domaine métier flou (boundaries vont bouger → coût de refactor cross-service énorme)
- ❌ Latence critique (chaque hop réseau ajoute 1-50ms — chains se cumulent)
- ❌ Pas d'expertise distributed systems (CAP theorem, eventual consistency, saga patterns)

---

# 12. Ressources canoniques

Références théoriques (non lues par les agents, mais le pattern documenté s'aligne) :
- **Sam Newman** — *Building Microservices* (2015, 2e éd. 2021) + *Monolith to Microservices* (2019)
- **Chris Richardson** — *Microservices Patterns* (2018) + microservices.io (pattern catalog canonique)
- **Eric Evans** — DDD foundation (cf. `archi/ddd.md §12`)
- **Martin Fowler** — *Patterns of Enterprise Application Architecture* + posts blog sur Microservices
- **Susan J. Fowler** — *Production-Ready Microservices* (2016, focus ops)
- **Mike Amundsen** — *RESTful Web Clients* (contracts + HATEOAS)

Implémentations de référence :
- .NET : **eShopOnContainers** (Microsoft, comprehensive microservices reference), **CleanArchitecture** (Jason Taylor)
- Java/Kotlin : **Spring PetClinic Microservices**, **Lakeside Mutual** (DDD + microservices examples)
- Node : **moleculer-microservices** framework + samples
- Python : **FastAPI microservices template** (community), **cookiecutter-fastapi-microservice**

Patterns de référence (microservices.io catalogue Chris Richardson) :
- **Decomposition** : Decompose by business capability, Decompose by subdomain (DDD)
- **Data management** : Database per service, Saga, CQRS, Event sourcing, Transactional outbox
- **Communication** : API Gateway, Backends for Frontends (BFF), gRPC, Messaging, Remote Procedure Invocation
- **Reliability** : Circuit breaker, Bulkhead, Retry, Timeout
- **Observability** : Health Check API, Distributed tracing, Log aggregation, Application metrics, Exception tracking
- **Deployment** : Multiple service instances per host, Service instance per host, Serverless deployment, Service mesh
- **Cross-cutting concerns** : Externalized configuration, Service registry, Service discovery
- **Security** : Access token (JWT)
- **Testing** : Consumer-driven contract test (Pact), Service component test

---

## Note Phase 2 SDD_Pro

Ce fichier sera testé end-to-end via 1 projet pilote sur **dotnet-minimalapi × microservice** (combo le plus mature avec `Microsoft.Extensions.Http.Resilience` 9.0 + OTel + MassTransit) avant de passer 🟢 reference. Les ajustements seront capturés dans un ADR `ADR-{ts}-microservice-pattern-refinements.md`.

**Limite explicite SDD_Pro** : ce fichier décrit la **construction d'UN service** prêt à l'écosystème microservices. La **mise en place de l'écosystème complet** (K8s manifests, service mesh Istio/Linkerd, observability stack Loki+Prometheus+Tempo+Grafana, message broker Kafka cluster) est **hors scope SDD_Pro v6** — relève des Ops. SDD_Pro peut générer des **templates IaC** (Helm charts, Terraform modules) via capabilities futures `k8s-helm`, `terraform-aws`, `terraform-azure`, mais c'est pour Phase 3 (post-v6.7.6).
