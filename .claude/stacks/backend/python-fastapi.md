# Tech Spec: fastapi (backend)

Status: Stable
Tech Spec ID: tech-fastapi
Scope: backend uniquement (API REST async, logique métier, persistance)

---

## 1. Architecture

### 1.1 Pattern applicatif

FastAPI 0.115 + Pydantic v2 + SQLAlchemy 2.x async, séparation stricte :

```
Endpoint → Service (via Depends) → Entity → Mapper → DTO → ApiResponse[T]
```

Le wrapper `ApiResponse[T]` porte les métriques (`query_time`,
`mapping_time`) et est défini dans la librairie partagée `{LibName}`.

### 1.2 Couches

- **Endpoint (Router)** : `APIRouter` FastAPI, validation auto via
  Pydantic, aucune logique métier
- **Service (interface)** : classe abstraite (`abc.ABC`) dans
  `services/interfaces/`
- **Service (impl)** : classe concrète injectée via `Depends()`
- **Mapper** : fonctions ou classes statiques dans `mappers/`
- **DTO** : `pydantic.BaseModel` immuable (`model_config = ConfigDict(frozen=True)`)
- **Entity** : modèles ORM SQLAlchemy 2.x Declarative (`DeclarativeBase`)
- **DB Session** : `AsyncSession` SQLAlchemy via `Depends(get_db)`
- **Exception handler** : middleware global qui transforme toute
  exception en `ProblemDetails` (RFC 7807 via `fastapi.responses`)

### 1.3 Mapping couche → répertoire

```
workspace/output/src/{BackendName}/
├── pyproject.toml
├── main.py                                       # FastAPI app + routers
├── config.py                                     # settings Pydantic
├── endpoints/                                    # APIRouters
├── services/
│   ├── interfaces/                               # abstract base classes
│   └── ...                                       # implementations
├── mappers/                                      # entity ↔ dto
├── entities/                                     # SQLAlchemy ORM models
│   └── db/                                       # DB session + base
├── middleware/                                   # custom middleware
├── resources/                                    # i18n .po/.mo files
├── alembic/                                      # migrations Alembic
└── tests/                                        # cf. qa/python-pytest.md

workspace/output/src/{LibName}/
├── inputs/                                       # Input DTOs Pydantic
├── outputs/                                      # Output DTOs Pydantic
└── models/                                       # Models partagés
```

### 1.4 Principes non négociables

- **Type hints** partout (Python 3.12 + `from __future__ import annotations`)
- Aucune logique métier dans Endpoints ni Entities
- Mapping centralisé dans `mappers/`
- DI systématique via `Depends`
- Async/await pour I/O (DB, HTTP) — jamais bloquant
- ORM SQLAlchemy 2.x style (pas de legacy 1.x `query()`)
- DTOs Pydantic immuables (`frozen=True`)
- Exception handling centralisé (middleware) — pas de `try/except`
  HTTP dans Endpoints/Services
- Migrations DB via **Alembic** uniquement
- Pas de `print()` — utiliser **structlog**
- Fail-fast au démarrage si env vars manquantes

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
# Auto-genere depuis python-fastapi.libs.json -- ne pas editer (utiliser sync-stack-md.ps1).
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

> Source de verite : `.claude/stacks/backend/python-fastapi.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/scripts/sync-stack-md.ps1 -StackId python-fastapi`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| fastapi | 0.115.5 |  |
| uvicorn[standard] | 0.32.1 |  |
| pydantic | 2.10.3 |  |
| pydantic-settings | 2.6.1 |  |
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

Triggers (regex case-insensitive) cherches par `detect-capabilities.ps1` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| auth-local | passlib[bcrypt] | 1.7.4 | auth-local, hash.*password, bcrypt |
| jwt | python-jose[cryptography] | 3.3.0 | \bjwt\b, jose, auth-local, auth-azure-ad |
| excel | openpyxl | 3.1.5 | \bexcel\b, \.xlsx\b, export.*excel, import.*excel, tableur |
| pdf | reportlab | 4.2.5 | \bpdf\b, \.pdf\b, export.*pdf, generer.*pdf, imprim |

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

### 3.1 Configuration via Pydantic Settings

`config.py` :
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    azure_tenant_id: str | None = None
    azure_client_id: str | None = None

settings = Settings()  # fail-fast au démarrage si env vars manquent
```

### 3.2 DB Session (async SQLAlchemy 2.x)

`entities/db/session.py` :
```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.engine import URL
from app.config import settings

url = URL.create(
    drivername="postgresql+asyncpg",
    username=settings.db_user,
    password=settings.db_password,
    host=settings.db_host,
    port=settings.db_port,
    database=settings.db_name,
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

### 4.2 Connection string pattern (async)

Convention : **`sqlalchemy.engine.URL.create`** (jamais string concat —
gère l'échappement automatique).

```python
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine

url = URL.create(
    drivername="postgresql+asyncpg",   # selon DatabaseType (§4.1)
    username=settings.db_user,
    password=settings.db_password,
    host=settings.db_host,
    port=settings.db_port,
    database=settings.db_name,
)

engine = create_async_engine(url, pool_pre_ping=True)
```

Pour SQLite (path-based, pas d'host) :
```python
url = URL.create(drivername="sqlite+aiosqlite", database="path/to/db.sqlite")
```

### 4.3 Migrations Alembic

Init :
```bash
cd workspace/output/src/{BackendName}
alembic init alembic
```

Configuration `alembic.ini` :
```ini
sqlalchemy.url = ${DATABASE_URL}    # injecté via env
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
uv add --dev --project workspace/output/src/{BackendName} sqlacodegen
uv run --project workspace/output/src/{BackendName} sqlacodegen \
  "$DB_URL" \
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

## 6. CORS développement

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,   # incompatible avec "*"
)
```

Conforme à `.claude/rules/cors.md`. Production : remplacer `*` par
allowlist explicite.

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
  `[STACK_LIBRARY_MISSING]` (cf. `rules/stack-completeness.md`)
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
