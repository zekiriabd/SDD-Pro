# QA Stack — pytest + coverage.py

> §2.4 (Librairies) régénérée depuis `python-pytest.libs.json` — ne pas éditer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id python-pytest`).

Status: Bench-validated
Validation: 🟢 bench (bench 2026-06-05 runtime PASS sur combos C4/C12 — FastAPI + pytest ; pipeline /sdd-full end-to-end pending v7.1)
Support: 🟢 Supporté best-effort (SLA Tier 2, cf. SLA.md §1.1) — pas de garantie idempotence /sdd-full. Promu de experimental le 2026-06-07 (audit Sprint 2 CRIT-11 closure).
QA FEAT ID: python-pytest
Scope: tests unitaires backend Python (FastAPI, Flask, Django)

---

## 1. Scope

Tests unitaires pour backends Python (FastAPI, Flask, Django).
S'applique aux projets `workspace/src/{BackendName}/` typés Python.

---

## 2. Tooling

### 2.1 Test runner
- **pytest** (>= 7.4)
- **pytest-asyncio** pour code async

### 2.2 Coverage tool
- **pytest-cov** (wrapper coverage.py)
- Output : `coverage.xml` (cobertura) + `htmlcov/`

### 2.3 Mock library
- **unittest.mock** (built-in)
- **pytest-mock** (`mocker` fixture)
- Pour HTTP : **httpx** + **respx**

## 1.bis Rattachement aux stacks applicatifs (MAJ 2026-09-02)

| Stack applicatif | Capability à activer |
|---|---|
| `backend/python-fastapi` | — (le CORE suffit) |
| `backend/django` | **`django-testing`** |
| `fullstack/django-templates` | **`django-testing`** |

> `pytest-django` n'est pas une commodité : sans lui, `pytest` ne sait pas
> amorcer Django, et **tout import de modèle lève `ImproperlyConfigured`**.
> Le message ne mentionne ni pytest ni le paquet manquant — d'où cette note.
>
> Il faut aussi déclarer `DJANGO_SETTINGS_MODULE` dans `pytest.ini` :
> ```ini
> [pytest]
> DJANGO_SETTINGS_MODULE = config.settings.local
> ```

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/qa/python-pytest.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id python-pytest`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| pytest | 9.1.1 |  |
| pytest-asyncio | 1.3.0 |  |
| pytest-cov | 7.1.0 |  |
| pytest-mock | 3.15.1 |  |
| httpx | 0.28.1 |  |
| coverage | 7.11.1 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| http-mock | respx | 0.22.0 | respx, mock.*http, intercept.*requests |
| django-testing | pytest-django | 4.14.0 | django, pytest-django, test.*modele.*django |
| django-testing | model-bakery | 1.24.0 | django, fixture.*modele, baker, donnees.*test |
<!-- LIBS_CATALOG_END -->

## 3. Init Commands (idempotent)

Si `workspace/src/{BackendName}/tests/` n'existe pas :

<!-- CORE_PACKAGES_START -->
```bash
# Auto-genere depuis python-pytest.libs.json -- ne pas editer (utiliser sync_stack_md.py).
uv add --project workspace/src/{BackendName} \
  pytest==9.1.1 \
  pytest-asyncio==1.3.0 \
  pytest-cov==7.1.0 \
  pytest-mock==3.15.1 \
  httpx==0.28.1 \
  coverage==7.11.1
```
<!-- CORE_PACKAGES_END -->

<!-- ONDEMAND_PACKAGES_START -->
```bash
# Auto-genere depuis python-pytest.libs.json (on-demand) -- installe par dev-* si l'US declenche un trigger.
# capability: http-mock
uv add --project workspace/src/{BackendName} respx==0.22.0

# capability: django-testing
uv add --project workspace/src/{BackendName} pytest-django==4.14.0 model-bakery==1.24.0
```
<!-- ONDEMAND_PACKAGES_END -->

```bash
mkdir -p workspace/src/{BackendName}/tests
touch workspace/src/{BackendName}/tests/__init__.py
```

Configuration `pyproject.toml` (ou `pytest.ini`) — append :

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
asyncio_mode = "auto"

[tool.coverage.run]
source = ["app"]
omit = ["*/tests/*", "*/migrations/*"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

---

## 4. Project structure

```
workspace/src/{BackendName}/
├── app/                              # code production
│   ├── services/
│   │   └── auth_service.py
│   └── routes/
│       └── auth.py
└── tests/
    ├── __init__.py
    ├── conftest.py                   # fixtures globales
    ├── services/
    │   └── test_auth_service.py
    └── routes/
        └── test_auth_routes.py
```

---

## 5. Test patterns

### 5.1 Service test (mock dependencies)

```python
import pytest
from unittest.mock import Mock, AsyncMock
from app.services.auth_service import AuthService

class TestAuthService:
    @pytest.fixture
    def user_repo(self):
        return Mock()

    @pytest.fixture
    def sut(self, user_repo):
        return AuthService(user_repo)

    @pytest.mark.asyncio
    async def test_login_with_valid_credentials_returns_token(self, sut, user_repo):
        # Arrange
        user_repo.find_by_email = AsyncMock(return_value={"id": 1, "email": "u@t.com"})

        # Act
        result = await sut.login("u@t.com", "pass")

        # Assert
        assert result is not None
        assert "token" in result
```

### 5.2 FastAPI endpoint test (TestClient)

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_post_login_with_invalid_credentials_returns_401(client):
    response = client.post("/auth/login", json={"email": "x", "password": "y"})
    assert response.status_code == 401
```

---

## 6. Run commands

### 6.1 Test command

```bash
cd workspace/src/{BackendName}
pytest --cov=app --cov-report=xml --cov-report=term
```

### 6.2 Linter

```bash
cd workspace/src/{BackendName}
ruff check app/ tests/
# OU
flake8 app/ tests/
```

### 6.3 Type checker (optionnel)

```bash
mypy app/
```

---

## 7. Coverage output format

Format : **coverage.xml** (Cobertura)
Path : `workspace/src/{BackendName}/coverage.xml`

Le script `parse_coverage.py` parse ce format via
`Parse-CoberturaXml`.

---

## 8. Naming conventions

- Fichiers : `test_{module}.py` ou `{module}_test.py`
- Classes : `Test{ClassName}` (optionnel — pytest accepte les fonctions plates)
- Méthodes : `test_{method}_{scenario}_{expected}`
  - Ex. : `test_login_with_valid_credentials_returns_token`

---

## 9. Forbidden patterns

- `time.sleep(...)` — utiliser `freezegun` pour mocker le temps
- Connexion à une vraie DB — utiliser fixtures pytest + DB en mémoire
- État partagé entre tests via variables module-level mutables
- Imports relatifs au-delà du package
