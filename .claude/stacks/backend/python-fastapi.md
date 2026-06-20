# Tech FEAT: fastapi (backend)

> §2.4 (Librairies) régénérée depuis `python-fastapi.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id python-fastapi`).

Status: Stable
Validation: 🟢 bench-validated runtime (2026-06-05 — CalcABCBackPy :44329, FastAPI + Pydantic inline + Uvicorn ASGI + structlog + CORSMiddleware, **97 LOC le plus court des 4 backends REST**, **POST 5+5 latence 33ms — le plus rapide du bench**, `/docs` Swagger UI + OpenAPI 3.1 auto-généré, 422 validation Pydantic riche, 16/16 curl cross-origin 4 SPA OK, AC-1/2/3/4 🟢. Substitution backend transparente sur :44329 (4e tour de swap après Kotlin/.NET/Node). Bug fix : `pydantic-core 2.10.3` no-wheel Py3.14 → `pydantic>=2.11`. Pipeline `/sdd-full` complet pas encore validé end-to-end — scaffolding manuel mainteneur, cf. `docs/benchmarks/known-gaps.md`)
Tech FEAT ID: tech-fastapi
Scope: backend uniquement (API REST async, logique métier, persistance)

---

## 1. Architecture

> **Pattern d'architecture** : ce stack suit l'**architecture canonique** définie dans
> `.claude/stacks/archi/{ArchiPattern}.md` (défaut `MVC` si `## Active Architecture Pattern`
> absent du `stack.md`). Section §1 ci-dessous ne décrit QUE les overrides Python/FastAPI-specific.

### 1.1 Pattern applicatif (Python/FastAPI idioms)

Pour `ArchiPattern: MVC` (défaut), suit `archi/mvc.md` avec idioms FastAPI 0.115 + Pydantic v2 + SQLAlchemy 2.x async :
- **Endpoint** = `APIRouter` FastAPI avec route decorators (`@router.get`, `@router.post`)
- **Validation Pydantic** auto sur Input DTOs (FastAPI parse + valide automatiquement le body)
- **Service interface** = classe abstraite `abc.ABC` dans `services/interfaces/` — convention `IXxxService` (préfixe `I` non-Python idiomatique, mais consistant cross-stack SDD_Pro)
- **Service impl** = classe concrète injectée via FastAPI `Depends()`
- **DTO** = `pydantic.BaseModel` avec `model_config = ConfigDict(frozen=True)` (immuables)
- **Entity** = SQLAlchemy 2.x `DeclarativeBase` (Database-First scaffolding via `sqlacodegen` ou Alembic introspection)
- **DB Session** = `AsyncSession` SQLAlchemy via `async_sessionmaker()` + `Depends(get_db)` (FastAPI dependency)
- **ProblemDetails** RFC 7807 via middleware FastAPI custom

Pour `ArchiPattern: DDD` → voir `archi/ddd.md` (Aggregates + UseCases via pattern manuel).
Pour `ArchiPattern: microservice` → voir `archi/microservice.md` (httpx + tenacity + OpenTelemetry).

### 1.3 Mapping couche → répertoire (override Python)

| Couche canonique (archi/mvc.md §3) | Path Python-specific |
|---|---|
| App entry | `workspace/output/src/{BackendName}/main.py` (FastAPI app + routers mount) |
| Config | `workspace/output/src/{BackendName}/config.py` (Pydantic Settings, depuis 2026-05-14) |
| Endpoint (APIRouter) | `workspace/output/src/{BackendName}/endpoints/` |
| Service interface | `workspace/output/src/{BackendName}/services/interfaces/` (abc.ABC) |
| Service impl | `workspace/output/src/{BackendName}/services/` |
| Mapper | `workspace/output/src/{BackendName}/mappers/` (fonctions ou classes statiques) |
| Entity (SQLAlchemy) | `workspace/output/src/{BackendName}/entities/` |
| DB Session config | `workspace/output/src/{BackendName}/entities/db/` |
| Middleware | `workspace/output/src/{BackendName}/middleware/` |
| Resources i18n | `workspace/output/src/{BackendName}/resources/` (`.po`/`.mo`) |
| Migrations Alembic | `workspace/output/src/{BackendName}/alembic/` |
| Input DTO | `workspace/output/src/{LibName}/inputs/` (Pydantic) |
| Output DTO | `workspace/output/src/{LibName}/outputs/` |
| Model DTO | `workspace/output/src/{LibName}/models/` |
| Project file | `workspace/output/src/{BackendName}/pyproject.toml` |

### 1.4 Override principes (Python-specific)

Hérités de `archi/mvc.md §4`. **Ajouts** Python :
- **Type hints partout** (Python 3.12+, `from __future__ import annotations` en tête de fichier)
- **Pydantic v2** pour DTOs (`BaseModel` + `model_config = ConfigDict(frozen=True)`)
- **SQLAlchemy 2.x style** uniquement (pas de legacy 1.x `query()` — utiliser `select()` + `await session.execute()`)
- **`async def`** partout pour I/O (DB, HTTP) — jamais bloquant
- **DI via `Depends`** FastAPI uniquement — pas de Service Locator
- **Migrations DB via Alembic** (pas de `Base.metadata.create_all()` en prod — Database-First)
- **`structlog`** pour logging structuré — pas de `print()`, pas de `logging.info()` brut
- **Fail-fast au démarrage** si env vars manquantes (Pydantic Settings raise validation error)
- **Pas de mutable default args** (anti-pattern Python classique)
- **`Optional[T]`** explicite (ou `T | None` Python 3.10+) — pas de `None` implicite

---

## 2. Stack

### 2.1 Identité

- **Stack ID** : `back-fastapi`
- **Langage** : Python 3.12+
- **Runtime** : ASGI (uvicorn 0.32+)
- **Framework principal** : FastAPI 0.115.x
- **Build tool** : pip + venv (Poetry / uv tolérés)
- **Namespace racine** : `{BackendNamespace}` (ex. `app`)

### 2.2 Outils

- **Project file** : `workspace/output/src/{BackendName}/pyproject.toml`
- **Build** : `cd workspace/output/src/{BackendName} && pip install -e .` (mode dev)
- **Smoke Command** :
  ```bash
  cd workspace/output/src/{BackendName}
  uvicorn main:app --host 0.0.0.0 --port 8000 &
  APP_PID=$!; sleep 5
  curl -sf http://localhost:8000/health -o /dev/null
  RC=$?; kill $APP_PID 2>/dev/null; wait $APP_PID 2>/dev/null; exit $RC
  ```
- **Smoke Timeout** : 30s
- **Lint** : `ruff check .`
- **Format** : `ruff format .` (alternative `black`)
- **Type-check** : `mypy app/` (optionnel mais recommandé)
- **Package manager** : pip (PyPI registry)
- **Test** : voir `qa/python-pytest.md`

### 2.2.1 Init Commands (idempotent)

```bash
# Skip si pyproject.toml existe déjà
if [ ! -f "workspace/output/src/{BackendName}/pyproject.toml" ]; then
  mkdir -p workspace/output/src/{BackendName}
  cd workspace/output/src/{BackendName}

  # Bootstrap pyproject.toml
  cat > pyproject.toml << 'EOF'
[project]
name = "{BackendName}"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true
EOF

  python -m venv .venv
fi

cd workspace/output/src/{BackendName}
source .venv/bin/activate 2>/dev/null || .venv\\Scripts\\activate

# uv recommande (plus rapide que pip). Si vous restez sur pip, remplacer
# `uv add --project ...` par `pip install ...` sous venv active.
```

<!-- CORE_PACKAGES_START -->
```bash
# Auto-genere depuis python-fastapi.libs.json -- ne pas editer (utiliser sync_stack_md.py).
uv add --project workspace/output/src/{BackendName} \
  fastapi==0.115.5 \
  uvicorn[standard]==0.32.1 \
  pydantic==2.10.3 \
  pydantic-settings==2.6.1 \
  sqlalchemy[asyncio]==2.0.36 \
  alembic==1.14.0 \
  structlog==24.4.0 \
  python-json-logger==2.0.7 \
  httpx==0.28.0 \
  tenacity==9.0.0 \
  fastapi-pagination==0.12.32 \
  slowapi==0.1.9 \
  python-multipart==0.0.20 \
  babel==2.16.0 \
  email-validator==2.2.0 \
  ruff==0.8.4 \
  mypy==1.13.0
```
<!-- CORE_PACKAGES_END -->

<!-- ONDEMAND_PACKAGES_START -->
```bash
# Auto-genere depuis python-fastapi.libs.json (on-demand) -- installe par dev-* si l'US declenche un trigger.
# capability: auth-local
uv add --project workspace/output/src/{BackendName} passlib[bcrypt]==1.7.4

# capability: jwt
uv add --project workspace/output/src/{BackendName} python-jose[cryptography]==3.3.0

# capability: excel
uv add --project workspace/output/src/{BackendName} openpyxl==3.1.5

# capability: pdf
uv add --project workspace/output/src/{BackendName} reportlab==4.2.5
```
<!-- ONDEMAND_PACKAGES_END -->

```bash
# Driver DB selon DatabaseType (voir §4.1)
# uv add --project workspace/output/src/{BackendName} asyncpg|aiomysql|aioodbc

# Créer arborescence
mkdir -p endpoints services/interfaces services mappers entities/db
mkdir -p middleware resources alembic/versions tests

# Créer ../{LibName}
mkdir -p ../{LibName}/inputs ../{LibName}/outputs ../{LibName}/models

# main.py minimal
if [ ! -f main.py ]; then
cat > main.py << 'EOF'
from fastapi import FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown

app = FastAPI(title="{BackendName}", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok"}
EOF
fi
```

### 2.3 Patterns d'erreurs compilation / runtime

Format Python :
- `ImportError: No module named '...'`
- `ModuleNotFoundError: No module named '...'`
- `SyntaxError: invalid syntax`
- `NameError: name '...' is not defined`
- `TypeError: ...`
- `AttributeError: '...' object has no attribute '...'`

Erreurs Pydantic v2 :
- `ValidationError`: `1 validation error for {Model} {field}: {message}`
- `pydantic.errors.PydanticUserError` : usage incorrect

Erreurs SQLAlchemy 2.x :
- `OperationalError`: connexion DB
- `IntegrityError`: contrainte violée
- `DetachedInstanceError`: session fermée

Erreurs ruff/mypy :
- `ruff: F401 '...' imported but unused`
- `mypy: error: Argument 1 has incompatible type ...`

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/backend/python-fastapi.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id python-fastapi`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| fastapi | 0.115.5 |  |
| uvicorn[standard] | 0.32.1 |  |
| pydantic | 2.11.0 |  |
| pydantic-settings | 2.7.0 |  |
| sqlalchemy[asyncio] | 2.0.36 |  |
| alembic | 1.14.0 |  |
| structlog | 24.4.0 |  |
| python-json-logger | 2.0.7 |  |
| httpx | 0.28.0 |  |
| tenacity | 9.0.0 |  |
| fastapi-pagination | 0.12.32 |  |
| slowapi | 0.1.9 |  |
| python-multipart | 0.0.20 |  |
| babel | 2.16.0 |  |
| email-validator | 2.2.0 |  |
| ruff | 0.8.4 |  |
| mypy | 1.13.0 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| auth-local | passlib[bcrypt] | 1.7.4 | auth-local, hash.*password, bcrypt |
| jwt | python-jose[cryptography] | 3.3.0 | jwt, jose, auth-local, auth-azure-ad |
| excel | openpyxl | 3.1.5 | excel, \.xlsx, export.*excel, import.*excel, tableur |
| pdf | reportlab | 4.2.5 | pdf, \.pdf, export.*pdf, generer.*pdf, imprim |

#### 2.4.d DB Drivers (selectionne par arch selon DatabaseType)

| DatabaseType | Module | Version | Scope |
|---|---|---|---|
| postgres | `asyncpg` | 0.30.0 | runtime |
| mysql | `aiomysql` | 0.2.0 | runtime |
| sqlserver | `aioodbc` | 0.5.0 | runtime |
| sqlite | `aiosqlite` | 0.20.0 | runtime |
<!-- LIBS_CATALOG_END -->

### 2.5 Conventions de nommage

- **Modules / fichiers** : `snake_case.py`
- **Classes** : `PascalCase` (ex. `UserService`, `UserDto`)
- **Fonctions / méthodes** : `snake_case` (ex. `find_user_by_id`)
- **Variables** : `snake_case` (ex. `user_id`)
- **Constantes** : `SCREAMING_SNAKE_CASE` (ex. `MAX_RETRY_COUNT`)
- **Privé** : préfixe `_` (ex. `_internal_helper`)
- **Type variables** : `T`, `T_co`, `T_contra` (PEP 484)
- **DTOs** : suffixe `Dto` ou `Input` / `Output` (ex. `UserInputDto`,
  `UserOutputDto`)
- **Tables DB** : `snake_case_plural` (ex. `users`, `points_vente`)
- **Tests** : `test_{module}.py`, fonctions `test_{scenario}`

---

## 3. Conventions d'usage

### 3.1 Configuration via Pydantic Settings (peuplée par arch, depuis 2026-05-14)

**Source de vérité** : blocs `## Active Database` et `## Active Auth
Specs` de `workspace/input/stack/stack.md`. L'agent `arch` Phase A —
STEP 4.5 écrit `app/config.py` avec les valeurs en **defaults Python**
(plus de fichier `.env` requis ; pydantic permet quand même l'override
par env var native si besoin runtime).

Exemple `app/config.py` généré par arch (valeurs littérales depuis
stack.md `## Active Database` + `## Active Auth Specs`) :

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class DBSettings(BaseSettings):
    type: str = "postgres"          # depuis ## Active Database DatabaseType
    host: str = "127.0.0.1"         # depuis DB_HOST
    port: int = 5432                # depuis DB_PORT
    name: str = "CMSPrint"          # depuis DB_NAME
    user: str = "postgres"          # depuis DB_USER
    password: str = "cmsprint."     # depuis DB_PASSWORD
    model_config = SettingsConfigDict(env_prefix="DB_")

class AzureADSettings(BaseSettings):
    tenant_id: str = "51a6b814-..."         # depuis AZ_TENANTID
    client_id: str = "2331229c-..."         # depuis AZ_CLIENTID
    domain: str = "softwe3.com"             # depuis AZ_DOMAIN
    audiences: List[str] = ["2331229c-...", "c3571161-..."]  # split/strip de AZ_AUDIENCES
    backend_callback_path: str = "/signin-oidc"
    frontend_callback_path: str = "/login-callback"
    model_config = SettingsConfigDict(env_prefix="AZ_")

db_settings = DBSettings()
azure_settings = AzureADSettings()
```

Le code applicatif fait :
```python
from app.config import db_settings, azure_settings
```

**Plus de `.env` requis** : les defaults Python suffisent pour dev. En
prod, override possible via env var (`DB_PASSWORD=...`) grâce à
`env_prefix` — sans modifier le code. La classe `AzureADSettings` est
omise par arch si aucun stack auth actif.

### 3.2 DB Session (async SQLAlchemy 2.x)

`entities/db/session.py` :
```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.engine import URL
from app.config import db_settings

# drivername selon db_settings.type (mappé par arch en STEP 4.5) :
#   postgres → postgresql+asyncpg
#   mysql    → mysql+aiomysql
#   sqlserver→ mssql+aioodbc
#   sqlite   → sqlite+aiosqlite
DRIVERS = {
    "postgres": "postgresql+asyncpg",
    "postgresql": "postgresql+asyncpg",
    "mysql": "mysql+aiomysql",
    "sqlserver": "mssql+aioodbc",
    "sqlite": "sqlite+aiosqlite",
}

url = URL.create(
    drivername=DRIVERS[db_settings.type.lower()],
    username=db_settings.user,
    password=db_settings.password,
    host=db_settings.host,
    port=db_settings.port,
    database=db_settings.name,
)

engine = create_async_engine(url, pool_pre_ping=True, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with SessionLocal() as session:
        yield session
```

### 3.3 Service avec DI

`services/interfaces/user_service.py` :
```python
from abc import ABC, abstractmethod
from {LibName}.outputs import UserOutputDto

class IUserService(ABC):
    @abstractmethod
    async def find_by_id(self, user_id: int) -> UserOutputDto: ...
```

`services/user_service.py` :
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.entities.user import User
from app.mappers.user_mapper import to_output_dto
from app.services.interfaces.user_service import IUserService
from {LibName}.outputs import UserOutputDto
import structlog

log = structlog.get_logger(__name__)

class UserService(IUserService):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_by_id(self, user_id: int) -> UserOutputDto:
        log.debug("Looking up user", user_id=user_id)
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise ResourceNotFoundError(f"User {user_id}")
        return to_output_dto(user)
```

### 3.4 Endpoint (Router)

`endpoints/users.py` :
```python
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.entities.db.session import get_db
from app.services.user_service import UserService
from {LibName}.outputs import UserOutputDto
from {LibName}.inputs import UserInputDto

router = APIRouter(prefix="/api/v1/users", tags=["users"])

def get_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)

@router.get("/{user_id}", response_model=UserOutputDto)
async def find_user(user_id: int, svc: UserService = Depends(get_service)):
    return await svc.find_by_id(user_id)

@router.post("", response_model=UserOutputDto, status_code=status.HTTP_201_CREATED)
async def create_user(input: UserInputDto, svc: UserService = Depends(get_service)):
    return await svc.create(input)
```

### 3.5 DTO Pydantic

`{LibName}/inputs/user_input_dto.py` :
```python
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class UserInputDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(min_length=1, max_length=50)
```

`{LibName}/outputs/user_output_dto.py` :
```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr

class UserOutputDto(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: int
    email: EmailStr
    role: str
    active: bool
    created_at: datetime
```

### 3.6 Exception handler global

`middleware/exception_handler.py` :
```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import structlog

log = structlog.get_logger(__name__)

class ResourceNotFoundError(Exception):
    pass

def register_exception_handlers(app: FastAPI):
    @app.exception_handler(ResourceNotFoundError)
    async def not_found_handler(request: Request, exc: ResourceNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"type": "https://example.com/probs/not-found",
                     "title": "Resource not found", "detail": str(exc)}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        log.warning("Validation failed", errors=exc.errors())
        return JSONResponse(
            status_code=400,
            content={"type": "https://example.com/probs/validation",
                     "title": "Validation error", "errors": exc.errors()}
        )

    @app.exception_handler(Exception)
    async def fallback_handler(request: Request, exc: Exception):
        log.error("Unhandled exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"type": "https://example.com/probs/server-error",
                     "title": "Internal server error"}
        )
```

### 3.7 Retry HTTP (tenacity + httpx)

```python
from tenacity import retry, stop_after_attempt, wait_exponential
import httpx

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4))
async def fetch_external(url: str) -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text
```

---

## 4. Persistence (cross-DatabaseType)

### 4.1 DB Drivers — matrice DatabaseType → pip package

| DatabaseType | pip package | SQLAlchemy drivername |
|---|---|---|
| `PostgreSQL` | `asyncpg` | `postgresql+asyncpg` |
| `MySql` | `aiomysql` | `mysql+aiomysql` |
| `SqlServer` | `aioodbc` (+ `pyodbc`) | `mssql+aioodbc` |
| `Sqlite` | `aiosqlite` (stdlib `sqlite3`) | `sqlite+aiosqlite` |

### 4.2 Connection string pattern (async, lecture depuis db_settings)

Convention : **`sqlalchemy.engine.URL.create`** (jamais string concat —
gère l'échappement automatique). Lecture depuis `app.config.db_settings`
(peuplée par arch en STEP 4.5 depuis `## Active Database` de stack.md).

```python
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import db_settings

DRIVERS = {
    "postgres": "postgresql+asyncpg",
    "postgresql": "postgresql+asyncpg",
    "mysql": "mysql+aiomysql",
    "sqlserver": "mssql+aioodbc",
    "sqlite": "sqlite+aiosqlite",
}

url = URL.create(
    drivername=DRIVERS[db_settings.type.lower()],
    username=db_settings.user,
    password=db_settings.password,
    host=db_settings.host,
    port=db_settings.port,
    database=db_settings.name,
)

engine = create_async_engine(url, pool_pre_ping=True)
```

Pour SQLite (path-based, pas d'host) :
```python
url = URL.create(drivername="sqlite+aiosqlite", database=db_settings.name)
```

### 4.3 Migrations Alembic

Init :
```bash
cd workspace/output/src/{BackendName}
alembic init alembic
```

Configuration `alembic.ini` — utiliser `env.py` Python plutôt qu'une
interpolation env var (pour aligner sur la source `db_settings`) :
```ini
# alembic.ini : laisser sqlalchemy.url vide
sqlalchemy.url =
```

```python
# alembic/env.py — résout l'URL depuis db_settings (depuis 2026-05-14)
from app.config import db_settings
from sqlalchemy.engine import URL

DRIVERS = {"postgres":"postgresql+psycopg","mysql":"mysql+pymysql","sqlserver":"mssql+pyodbc","sqlite":"sqlite"}
url = URL.create(
    drivername=DRIVERS[db_settings.type.lower()],
    username=db_settings.user, password=db_settings.password,
    host=db_settings.host, port=db_settings.port, database=db_settings.name,
)
config.set_main_option("sqlalchemy.url", str(url))
```

Création d'une migration auto (depuis modèles SQLAlchemy) :
```bash
alembic revision --autogenerate -m "create_users"
alembic upgrade head
```

Migrations versionnées : `alembic/versions/{rev}_{slug}.py`.

### 4.4 Entity SQLAlchemy 2.x

`entities/user.py` :
```python
from datetime import datetime
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.entities.db.base import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

`entities/db/base.py` :
```python
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

### 4.5 Scaffolding tool (Database-First, lu par arch §11)

**Outil** : `sqlacodegen` (reverse-engineering SQLAlchemy depuis le
schéma DB existant).

**Pattern d'invocation** (idempotent, READ-ONLY sur la base) :

```bash
# arch compose l'URL en RAM depuis ## Active Database de stack.md (cf. STEP 8)
# et la passe en argument au sqlacodegen (jamais via env var persistante)
uv add --dev --project workspace/output/src/{BackendName} sqlacodegen
uv run --project workspace/output/src/{BackendName} sqlacodegen \
  "<URL composée par arch en RAM depuis db_config>" \
  --generator declarative \
  --outfile workspace/output/src/{BackendName}/entities/db/models.py
```

Pour `--generator` : `declarative` (recommandé, SQLAlchemy 2.x typed),
`tables` (Core), ou `dataclasses` (style dataclass).

**Output** : `workspace/output/src/{BackendName}/entities/db/models.py`
(une classe `Base` + une classe par table).

**Idempotence** : sqlacodegen écrase le fichier en entier. arch détecte
les tables nouvelles vs déjà scaffoldées via `schema.json` (cf.
`arch.md §9-§10`). Pour incrémentalité : générer dans un fichier
temporaire puis merger via diff (avancé, non requis pour MVP).

**Filtres** (cf. arch.md §11.1 `## DB Scaffolding`) : passer
`--tables {csv}` à sqlacodegen pour limiter aux tables désirées.

---

## 5. URLs de développement

- HTTP : `http://localhost:8000`
- Swagger UI : `http://localhost:8000/docs`
- Redoc : `http://localhost:8000/redoc`
- OpenAPI JSON : `http://localhost:8000/openapi.json`

---

## 6. CORS

Conforme à `.claude/rules/library-and-stack.md §2.3`. Origins **explicites** lus depuis env
(`CORS_ALLOWED_ORIGINS`, CSV) ; fallback `http://localhost:5173` (port Vite par
défaut pour React, ajuster si le stack frontend utilise un autre port — Vue 5173,
Angular 4200, Next 3000).

```python
import os
from fastapi.middleware.cors import CORSMiddleware

allowed_origins = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Override via env :
```bash
CORS_ALLOWED_ORIGINS=http://localhost:5173,https://staging.example.com
```

**Interdits formellement** (déclenche `[SEC_CORS_PERMISSIVE]` du security-reviewer) :
- `allow_origins=["*"]` (wildcard incompatible avec `allow_credentials=True` per W3C spec)
- `allow_origin_regex=".*"`
- Origins hardcodées dans `main.py` (doit venir d'env / config)

Production : remplacer le fallback localhost par les origins prod réelles, jamais
de wildcard. Cf. `rules/library-and-stack.md §4` (anti-patterns).

---

## 7. Multilingue (Babel)

Structure :
```
resources/
├── messages.pot                       # template
└── locales/
    ├── fr/LC_MESSAGES/messages.po
    └── en/LC_MESSAGES/messages.po
```

Extraction :
```bash
pybabel extract -F babel.cfg -o resources/messages.pot .
pybabel init -i resources/messages.pot -d resources/locales -l fr
pybabel compile -d resources/locales
```

Usage :
```python
from babel.support import Translations

translations = Translations.load("resources/locales", ["fr", "en"])
_ = translations.gettext
print(_("Hello"))   # "Bonjour" si locale=fr
```

Détection locale via header `Accept-Language` dans middleware.

---

## 8. Logging structuré (structlog + python-json-logger)

`config_logging.py` :
```python
import structlog
import logging
import sys
from pythonjsonlogger import jsonlogger

def configure_logging(level: str = "INFO"):
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(jsonlogger.JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
```

Usage :
```python
import structlog

log = structlog.get_logger(__name__)
log.info("User logged in", user_id=42, ip="1.2.3.4")
```

---

## 9. Interdits projet (backend Python)

- **Secrets / mots de passe en dur** dans le code ou un fichier
  commité (sauf `.env.example` sans valeurs réelles)
- **Chaînes de connexion littérales** (toujours via `URL.create`)
- **`print(...)`** en code prod (toujours `structlog`)
- **`requests` (sync)** dans endpoints async — utiliser `httpx`
- **`time.sleep(...)`** dans code async — utiliser `asyncio.sleep`
- **Logique métier dans Endpoints** ou Entities
- **Mapping inline** dans Endpoints / Services (toujours dans `mappers/`)
- **`try/except` de formatage HTTP** dans Endpoints (rôle du middleware)
- **SQLAlchemy 1.x style** (`session.query(...)`, `Model.query`) —
  utiliser 2.x (`select(...)`, `session.execute(...)`)
- **`Mapped` sans annotations de type** (Python 3.12 + SQLAlchemy 2.x)
- **Modification manuelle des entities scaffoldées** (extension via
  classes héritées si nécessaire)
- **`async def` qui n'utilise jamais `await`** — soit synchrone, soit
  utiliser réellement async
- **`any` / `dict[str, Any]`** non motivé (préférer types stricts)
- **Pas de type hints** sur signatures publiques
- **`pip install ...` sans pinning** (toujours version exacte en §2.4)
- **Pre-release** (`-rc`, `-beta`) sauf justification stack
- **CVE ≥ moderate** — vérifier via `pip-audit` post-install
- **`TODO`, `FIXME`, code commenté, placeholders** (`changeme`, `foo`)
- **`from .* import *`** (imports wildcard interdits)

---

## 10. Recommended Skills (auto-trigger pendant la génération)

| Trigger (détecté dans la task ou les ACs) | Skill | Phase |
|---|---|---|
| Endpoint async avec DB lookup complexe | `python-fastapi:async-db-patterns` (futur) | STEP 5 (avant Service) |
| Upload de fichier | `python-fastapi:file-upload` (futur) | STEP 5 (avant Endpoint) |
| Génération Excel | `python-data:openpyxl-export` (futur) | STEP 5 |

**Interdits** :
- Ne jamais ajouter une lib non listée en §2.4 — STOP + ERROR
  `[STACK_LIBRARY_MISSING]` (cf. `rules/library-and-stack.md`)
- Ne jamais utiliser `pip install` ad-hoc — toujours mettre à jour
  §2.4 + §2.2.1 d'abord

---

## 11. Hors scope technique

- Tests unitaires → `qa/python-pytest.md`
- E2E → futur
- DevOps / CI / CD → hors scope SDD_Pro
- Async tasks (Celery, RQ, ARQ) → hors scope (futur stack séparé)
- WebSockets / SSE → hors scope (futur stack)
- GraphQL (Strawberry, Ariadne) → hors scope
