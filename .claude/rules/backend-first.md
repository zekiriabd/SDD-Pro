# Règle — Backend-First Gated Workflow (depuis 2026-05-07)

## Principe

`/dev-run {n}` (et donc `/sdd-full {n}`) exécute `dev-backend` puis
`dev-frontend` **en séquence stricte**, séparés par une **API Gate** :

```
arch + DB → dev-backend ALL US → QA API Gate (in-memory) → dev-frontend ALL US
                                       │
                                       └─ 🔴 RED → STOP, l'humain corrige et relance
```

Frontend consomme les routes backend par contrat. Tant que les endpoints ne
sont pas vérifiés runtime, générer le frontend est prématuré (chaque
mismatch = 4xx/5xx silencieux). Mode **non opt-in** depuis 2026-05-07.

---

## 1. Phase « QA API Gate »

### 1.1 Cas testés (par endpoint)

| Type | Cas |
|---|---|
| Happy | GET liste paginée → 200 ; GET by id → 200 ; POST → 201 + Location ; PUT → 200 ; DELETE → 204 puis GET → 404 |
| Négatif | GET id inexistant → 404 ; body invalide → 400 ProblemDetails ; sans Bearer → 401 ; scope manquant → 403 |

### 1.2 Fixtures (in-memory only, jamais la DB réelle)

| Stack QA | Stratégie |
|---|---|
| `qa/dotnet-xunit` | `WebApplicationFactory` + EF Core InMemory (DbContext remplacé via `services.RemoveAll`) |
| `qa/node-vitest` | `supertest` + Prisma SQLite `:memory:` ou mocks `PrismaClient` |
| `qa/python-pytest` | `httpx.AsyncClient(app=app)` + SQLAlchemy SQLite `:memory:` (override `get_db`) |
| `qa/kotlin-junit` | `MockMvc` + `@DataJpaTest` H2 in-memory |

**Seed** : 3-5 lignes par entité, IDs déterministes (1, 2, 3). **Auth** : JWT
mocké via `TestAuthHandler` (ClaimsPrincipal pré-rempli). **Jamais** d'appel
Azure AD réel.

### 1.3 Critère de passage

```
gate_passed = (failed == 0) AND (total >= MIN_PER_ENDPOINT × N_endpoints)
```

`MIN_PER_ENDPOINT = 2` (1 happy + 1 négatif min).

| Verdict | Action |
|---|---|
| 🟢 GREEN | continue vers `dev-frontend` |
| 🔴 RED | STOP + `workspace/output/qa/feat-{n}/api-tests.{md,json}` |
| 🟡 YELLOW | continue avec WARNING (couverture endpoints partielle, pas d'échec) |

### 1.4 Rapport

`workspace/output/qa/feat-{n}/api-tests.json` — schéma similaire à
`coverage.json` : `endpoints[].{verb, route, tests:{total,passed,failed}, cases[]}`
+ `summary.{endpoints_total, tests_total, gate_passed}`.

---

## 2. Boucle correction RED → GREEN

1. Consulter `api-tests.md` (par endpoint en échec)
2. Corriger : (a) `/dev-backend {n}-{m}` (idempotent), (b) édit manuel
   backend, ou (c) édit test (QA ownership, dans `*.Tests/Api/`)
3. Re-tester : `/qa-generate {n} --mode api-tests [--filter {endpoint}]`
4. GREEN → relancer `/dev-run {n}` (idempotent : skip backend si stable)

---

## 3. Configuration

```yaml
GatedWorkflow: true       # default — cette règle
ApiGateRequired: true     # default — false = WARN au lieu de RED
ApiGateMinPerEndpoint: 2  # default
```

`GatedWorkflow: false` = legacy parallèle (audit log
`workspace/output/.sys/.audit/legacy-parallel.log`). Déconseillé.

**Indépendance de `QAMode`** : la gate API (Phase 4) tourne toujours quand
`GatedWorkflow: true`, indépendamment de `QAMode` (qui pilote uniquement la
Phase 5 tests unitaires + coverage). `QAMode: off` ne désactive **pas** la
gate API ; pour la désactiver, utiliser `GatedWorkflow: false`.

---

## 4. Localisation des tests

```
workspace/output/src/{BackendName}.Tests/
├── Unit/                  # tests unitaires (qa-coverage.md)
└── Api/                   # tests intégration HTTP (cette règle)
    ├── Fixtures/          # TestWebApplicationFactory, TestAuthHandler, SeedData
    └── *EndpointsTests.cs
```

Dossier `Api/` généré uniquement si endpoints HTTP existent.

---

## 5. Anti-patterns

- ❌ dev-frontend avant que la gate passe
- ❌ Tester contre la DB réelle (toujours in-memory/mock)
- ❌ Bypass gate (`--no-validate` couvre `/feat-validate`, pas la gate API)
- ❌ Fixtures hors entités scaffoldées par arch
- ❌ Auth Azure AD réelle dans les tests
