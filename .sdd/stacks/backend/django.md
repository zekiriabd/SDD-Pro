# Tech FEAT: django (backend)

> §2.4 (Librairies) regeneree depuis `django.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id django`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits et validés le 2026-09-02. Chaque version résolue contre PyPI, et la compatibilité de **chaque** paquet avec Django 5.2 vérifiée via ses classifiers `Framework :: Django ::` (pas seulement via `requires_dist`, qui est plus laxiste). **Jamais exécuté end-to-end via `/sdd-full`** : aucun `manage.py check` ni `pytest` n'a tourné en CI. Non supporté commercialement en l'état.
Tech FEAT ID: tech-django
Scope: **backend API REST** — application **Django 5.2 LTS + Django REST Framework** dans UN projet `workspace/src/{BackendName}/`. Expose une API JSON consommée par un frontend séparé (`frontend/*` ou `mobiles/*`) déclaré en `## Active Tech Specs`.

> **Django SSR ≠ ce stack.** Ici Django ne rend aucun HTML : il sert du JSON via DRF. Pour un monolithe Django rendant des templates, voir `fullstack/django-templates.md`.

---

# 1. Architecture

## 1.1 Pattern applicatif

**API REST Django + DRF**, découpée en applications Django :

- **Django 5.2 LTS** — ORM, migrations, admin, système d'authentification
- **DRF** — serializers, `ViewSet`, routers, permissions, pagination
- **SimpleJWT** — authentification par jeton (access + refresh)
- **drf-spectacular** — schéma OpenAPI 3 généré **depuis les serializers**
- **django-environ** — configuration typée lue dans l'environnement
- **structlog** — logs structurés, `request_id` corrélé sur toute la requête

Architecture cible :

```
{BackendName}/
├── manage.py
├── config/
│   ├── settings/
│   │   ├── base.py           ── socle commun
│   │   ├── local.py          ── dev (DEBUG, toolbar)
│   │   └── production.py     ── prod (durcissement)
│   ├── urls.py               ── routes racine + schema OpenAPI
│   ├── wsgi.py · asgi.py
├── apps/
│   └── {domaine}/
│       ├── models.py         ── modeles ORM
│       ├── serializers.py    ── (de)serialisation + validation DRF
│       ├── views.py          ── ViewSets
│       ├── urls.py           ── router de l'app
│       ├── services.py       ── logique metier (cf. 1.4)
│       ├── filters.py        ── django-filter
│       ├── permissions.py
│       ├── admin.py
│       ├── migrations/
│       └── tests/
├── common/                   ── pagination, exceptions, mixins transverses
├── pyproject.toml
└── .env.example
```

**Différence vs `backend/python-fastapi`** :
- Django apporte **ORM + migrations + admin + auth** en standard ; FastAPI les assemble (SQLAlchemy + Alembic + code maison)
- Validation par **serializers DRF** et non par modèles Pydantic
- Django est **synchrone par défaut** ; les vues async existent mais l'ORM n'est async que partiellement (cf. §5)
- L'**admin Django** est un livrable à part entière : un back-office CRUD sans code

---

## 1.2 Couches

- **Models** (`apps/{d}/models.py`) : schéma ORM, contraintes, `Meta`. Aucune règle métier complexe.
- **Serializers** (`apps/{d}/serializers.py`) : (dé)sérialisation + validation du payload. C'est la frontière du contrat d'API.
- **Views** (`apps/{d}/views.py`) : `ViewSet` — orchestration seulement, pas de règle métier.
- **Services** (`apps/{d}/services.py`) : la logique métier. Fonctions prenant des types simples, testables sans HTTP.
- **Filters / Permissions** : filtrage de querystring et autorisation.
- **Common** (`common/`) : pagination, gestionnaire d'exceptions, mixins.

---

## 1.3 Mapping couche → repertoire

| Layer | Path |
|---|---|
| Configuration | `config/settings/{base,local,production}.py` |
| Routes racine | `config/urls.py` |
| Modèle | `apps/{domaine}/models.py` → `class {Name}(models.Model)` |
| Serializer | `apps/{domaine}/serializers.py` → `{Name}Serializer` |
| ViewSet | `apps/{domaine}/views.py` → `{Name}ViewSet` |
| Routes de l'app | `apps/{domaine}/urls.py` |
| Service métier | `apps/{domaine}/services.py` |
| Filtre | `apps/{domaine}/filters.py` → `{Name}Filter` |
| Permission | `apps/{domaine}/permissions.py` |
| Admin | `apps/{domaine}/admin.py` |
| Migration | `apps/{domaine}/migrations/{n}_{desc}.py` (**générée**) |
| Test | `apps/{domaine}/tests/test_{sujet}.py` |
| Pagination / exceptions | `common/pagination.py`, `common/exceptions.py` |
| Manifeste projet | `pyproject.toml` |

---

## 1.4 Principes non negociables

**Architecture** :
- **Fat models / thin views**, et la logique qui dépasse le modèle va dans `services.py`. Une `View` de plus de 20 lignes signale une couche manquante.
- **Aucune règle métier dans un serializer** — il valide la *forme*, pas la décision métier.
- **`select_related` / `prefetch_related` systématiques** sur toute vue de liste. C'est le point de défaillance n°1 de Django : la requête N+1 est invisible en développement et létale en production.
- **`ViewSet` + router**, pas de vues fonctionnelles pour du CRUD.
- **Settings découpés** (`base` / `local` / `production`) — jamais un unique `settings.py` piloté par des `if DEBUG`.
- **`DEBUG=False` en production**, `ALLOWED_HOSTS` explicite.
- **Migrations committées** — elles font partie du code, jamais régénérées à la volée.
- **`get_user_model()`**, jamais `from django.contrib.auth.models import User` en dur.
- **Modèle `User` custom dès la première migration.** Le changer après coup impose une migration manuelle de toute la base : c'est irréversible en pratique.

**Sécurité** :
- **`SECRET_KEY` par l'environnement**, jamais en dur (cf. `stack.md`).
- **CORS explicite** via `django-cors-headers` — `CORS_ALLOW_ALL_ORIGINS = True` est interdit hors développement local.
- **`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`** activés en production.
- **Rotation + blacklist des refresh tokens** SimpleJWT.
- **Permissions explicites par ViewSet** ; `DEFAULT_PERMISSION_CLASSES = IsAuthenticated` en défaut global, un `AllowAny` s'écrit à la main et se justifie.
- **`manage.py check --deploy`** doit passer sans warning avant toute mise en production.

---

## 1.5 Base de donnees

| DatabaseType | Driver | Remarque |
|---|---|---|
| `postgres` / `postgresql` | `psycopg` (v3) | défaut recommandé — `psycopg2` est en maintenance |
| `sqlite` | intégré à Django | développement et tests uniquement |
| `mysql` / `mariadb` | `mysqlclient` | **non catalogué** — à instruire avant engagement |
| `oracle` / `sqlserver` | pilotes tiers | **non supportés** par ce stack |

Migrations : `manage.py makemigrations` puis `manage.py migrate`.

> ⚠️ **`migrate` est soumis à `rules/library-and-stack.md` Partie C.** Sur une base **existante**, un agent n'applique **jamais** de changement de structure : il écrit le DDL dans `workspace/db/migration-pending.sql` et émet `[DB_STRUCTURE_CHANGE_FORBIDDEN]`. La création du schéma initial d'une base **neuve** reste permise (§C.3).

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `backend-django`
- **Langage** : Python 3.12
- **Framework** : Django **5.2.17 LTS** + Django REST Framework 3.18
- **Serveur** : Gunicorn (WSGI) ; Uvicorn (ASGI) via la capability `asgi`
- **Package manager** : `uv` (aligné sur `backend/python-fastapi`)
- **Base par défaut** : PostgreSQL via `psycopg` 3

---

## 2.2 Outils

- **Project file** : `workspace/src/{BackendName}/pyproject.toml`
- **Run dev** : `(cd workspace/src/{BackendName} && uv run manage.py runserver 0.0.0.0:8000)`
- **Migrations** : `uv run manage.py makemigrations` / `uv run manage.py migrate`
- **Superuser** : `uv run manage.py createsuperuser`
- **Shell** : `uv run manage.py shell`
- **Schéma OpenAPI** : `uv run manage.py spectacular --file schema.yml`
- **Gate de déploiement** : `uv run manage.py check --deploy` — **doit sortir sans warning**
- **Tests** : `uv run pytest`
- **Lint / format** : `uv run ruff check .` / `uv run ruff format .`
- **Typage** : `uv run mypy .`
- **Prod** : `uv run gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4`
- **Smoke Command** :

```bash
(cd workspace/src/{BackendName} && uv sync && uv run manage.py check)
test -f workspace/src/{BackendName}/manage.py
test -f workspace/src/{BackendName}/config/settings/base.py
```

- **Smoke Timeout** : 180s (`uv sync` + `check`)

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{BackendName}/manage.py" ]; then
  APP=workspace/src/{BackendName}
  mkdir -p "$APP" && cd "$APP"

  # STEP 1 — Projet uv + runtime pinne
  uv init --name {BackendName} --python 3.12 --no-workspace

  # STEP 2 — Dependances CORE (cf. 2.4.a)
  uv add \
    django==5.2.17 \
    djangorestframework==3.18.0 \
    django-environ==0.14.0 \
    psycopg==3.3.5 \
    django-cors-headers==4.9.0 \
    djangorestframework-simplejwt==5.5.1 \
    drf-spectacular==0.30.0 \
    django-filter==26.1 \
    gunicorn==26.2.0 \
    whitenoise==6.12.0 \
    structlog==26.1.0 \
    django-structlog==10.1.0

  # STEP 3 — Outillage de developpement
  uv add --dev \
    ruff==0.16.5 \
    mypy==2.3.1 \
    django-stubs==6.1.0 \
    djangorestframework-stubs==3.18.1 \
    pytest==9.1.1 \
    pytest-django==4.14.0

  # STEP 4 — Scaffolding Django (config/ comme paquet de configuration)
  uv run django-admin startproject config .

  # STEP 5 — Settings decoupes
  mkdir -p config/settings apps common
  git mv config/settings.py config/settings/base.py 2>/dev/null \
    || mv config/settings.py config/settings/base.py
  touch config/settings/__init__.py
  printf 'from .base import *  # noqa: F403\n' > config/settings/local.py
  printf 'from .base import *  # noqa: F403\n' > config/settings/production.py
  touch apps/__init__.py common/__init__.py

  # config/settings/base.py etant descendu d'un niveau, BASE_DIR doit remonter
  # un parent de plus, sinon tous les chemins (DB sqlite, static, templates)
  # pointent dans config/.
  python - <<'PY'
import pathlib, re
p = pathlib.Path("config/settings/base.py")
s = p.read_text(encoding="utf-8")
s = s.replace("BASE_DIR = Path(__file__).resolve().parent.parent",
              "BASE_DIR = Path(__file__).resolve().parent.parent.parent")
p.write_text(s, encoding="utf-8")
PY

  # STEP 6 — manage.py / wsgi / asgi pointent vers le module de settings dev
  sed -i 's/config.settings/config.settings.local/' manage.py config/wsgi.py config/asgi.py

  # STEP 7 — pytest.ini + .env.example
  cat > pytest.ini <<'INI'
[pytest]
DJANGO_SETTINGS_MODULE = config.settings.local
python_files = test_*.py
addopts = --strict-markers
INI

  cat > .env.example <<'ENV'
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://user:pass@localhost:5432/{BackendName}
CORS_ALLOWED_ORIGINS=http://localhost:5173
ENV

  # STEP 8 — Gate
  uv run manage.py check
fi
```

**Contrat post-init** :
- `manage.py check` sort 0
- `config/settings/{base,local,production}.py` existent, `BASE_DIR` remonte 3 parents
- `pytest.ini` déclare `DJANGO_SETTINGS_MODULE`
- Un modèle `User` custom est déclaré **avant** la première `migrate` (§1.4)

---

## 2.3 Choix de version — pourquoi Django 5.2 et non 6.1

Django **6.1.1** est la dernière version publiée. Ce stack pin **5.2.17**.

Django publie des **LTS explicites** (4.2, 5.2, puis 6.2). La 6.0 et la 6.1
sont des versions intermédiaires, supportées ~16 mois. `rules/library-and-stack.md §0`
impose « runtime LTS only » — la 5.2, supportée jusqu'en **avril 2028**, est
donc le seul choix conforme.

Ce n'est pas qu'une question de règle : la vérification des classifiers PyPI
montre que l'écosystème n'a pas fini de suivre la 6.1.

| Paquet | `Framework :: Django ::` déclarés | Compatible 6.1 ? |
|---|---|---|
| `djangorestframework` 3.18.0 | 5.2, 6.0, 6.1 | oui |
| `django-filter` 26.1 | 5.2, 6.0, 6.1 | oui |
| `django-stubs` 6.1.0 | 5.2, 6.0, 6.1 | oui |
| `drf-spectacular` 0.30.0 | 5.0 → 6.0 | **non déclaré** |
| `django-redis` 7.0.0 | 5.2, 6.0 | **non déclaré** |
| `pytest-django` 4.14.0 | 5.2, 6.0 | **non déclaré** |
| `djangorestframework-simplejwt` 5.5.1 | 4.2 → 5.2 | **non déclaré** |

Ces quatre paquets *s'installeraient* sur 6.1 (leurs `requires_dist` sont plus
larges que leurs classifiers), mais aucun ne l'annonce comme supporté. Sur la
**5.2, les sept sont déclarés compatibles** — le catalog est cohérent de bout
en bout.

**Montée en 6.2 LTS** (attendue ~avril 2027) : tâche dédiée, à traiter comme
un bump de runtime, avec re-vérification de la même table.

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/backend/django.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id django`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| django | 5.2.17 | Framework — ligne LTS 5.2 (cf. metadata.notes) |
| djangorestframework | 3.18.0 | Couche API REST : serializers, ViewSets, routers, permissions |
| django-environ | 0.14.0 | Lecture typee de la configuration depuis l'environnement — evite os.environ dissemine dans settings |
| psycopg | 3.3.5 | Driver PostgreSQL v3 (psycopg2 est en maintenance). Le seul driver requis quand DatabaseType=postgres ; SQLite est integre a Django |
| django-cors-headers | 4.9.0 | CORS — OBLIGATOIRE des que le front est sur une origine distincte (cf. rules/library-and-stack.md Partie B) |
| djangorestframework-simplejwt | 5.5.1 | Authentification JWT (access + refresh, rotation, blacklist) |
| drf-spectacular | 0.30.0 | Schema OpenAPI 3 genere depuis les serializers + Swagger UI |
| django-filter | 26.1 | Filtres de querystring declaratifs sur les ViewSets |
| gunicorn | 26.2.0 | Serveur WSGI de production |
| whitenoise | 6.12.0 | Service des fichiers statiques par l'app (pas de reverse proxy requis en conteneur) |
| structlog | 26.1.0 | Logs structures — meme choix que backend/python-fastapi |
| django-structlog | 10.1.0 | Integration Django (request_id correle sur toute la requete) |
| ruff | 0.16.5 | Lint + format (dev) |
| mypy | 2.3.1 | Typage statique (dev) |
| django-stubs | 6.1.0 | Stubs Django pour mypy (dev) — sans eux, mypy ne comprend ni les managers ni les QuerySets |
| djangorestframework-stubs | 3.18.1 | Stubs DRF pour mypy (dev) |
| pytest | 9.1.1 | Runner de tests (dev) — cf. qa/python-pytest.md |
| pytest-django | 4.14.0 | Fixtures Django pour pytest (dev) : db, client, settings. Sans lui, pytest ne sait pas amorcer Django |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| background-jobs | celery | 5.6.3 | tache.*asynchrone, background job, worker, celery, file.*attente |
| background-jobs | redis | 8.1.0 | celery, broker, redis |
| redis-cache | django-redis | 7.0.0 | cache, redis, mise.*en.*cache |
| image-processing | pillow | 12.3.0 | image, upload.*photo, miniature, thumbnail |
| object-storage | django-storages | 1.14.6 | \bs3\b, stockage.*objet, azure.*blob, upload.*cloud |
| sentry | sentry-sdk | 2.68.1 | sentry, error.*tracking, monitoring.*erreurs |
| social-auth | django-allauth | 65.19.2 | oauth, connexion.*google, sso, allauth, auth.*sociale |
| transactional-email | django-anymail | 15.1 | email.*transactionnel, sendgrid, mailgun, envoi.*mail |
| healthcheck | django-health-check | 4.5.1 | health, readiness, liveness, sonde |
| dev-profiling | django-debug-toolbar | 8.0.0 | debug.*toolbar, profiler.*requetes, n\+1 |
| dev-profiling | django-silk (alt) | 5.5.2 | silk, profiling, n\+1 |
| dev-profiling | django-extensions (alt) | 4.1 | shell_plus, graph_models, django-extensions |
| excel | openpyxl | 3.1.5 | excel, xlsx, export.*tableur |
| pdf | reportlab | 5.0.1 | \bpdf\b, generation.*document, export.*pdf |
| asgi | uvicorn | 0.52.4 | websocket, asgi, async.*view, temps.*reel |
| coverage | pytest-cov | 7.1.0 | coverage, couverture.*tests |
| test-fixtures | model-bakery | 1.24.0 | fixture, donnees.*test, factory, baker |
| test-fixtures | factory-boy (alt) | 3.3.3 | factory_boy, factory |

#### 2.4.d DB Drivers (selectionne par arch selon DatabaseType)

| DatabaseType | Module | Version | Scope |
|---|---|---|---|
| postgres | `psycopg` | 3.3.5 | runtime |
| postgresql | `psycopg` | 3.3.5 | runtime |
| sqlite | `django` | 5.2.17 | runtime |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Rôle | Pattern | Exemple |
|---|---|---|
| App Django | `apps/{domaine}/` (singulier, minuscules) | `apps/billing/` |
| Modèle | `class {Name}(models.Model)` (singulier) | `Invoice` |
| Serializer | `{Name}Serializer` | `InvoiceSerializer` |
| Serializer d'écriture | `{Name}WriteSerializer` | `InvoiceWriteSerializer` |
| ViewSet | `{Name}ViewSet` | `InvoiceViewSet` |
| Filtre | `{Name}Filter` | `InvoiceFilter` |
| Permission | `Is{Condition}` | `IsInvoiceOwner` |
| Service | `apps/{d}/services.py` → fonctions verbales | `def issue_invoice(...)` |
| Test | `test_{sujet}.py` | `test_invoice_service.py` |
| Migration | **générée** — ne jamais renommer | `0003_invoice_status.py` |

**Suffixes INTERDITS** :
- `Manager` sur autre chose qu'un `models.Manager` (le nom est réservé par Django)
- `Helper`, `Util`
- `Model` en suffixe de classe (`InvoiceModel`) — redondant
- Nom d'app au pluriel (`apps/invoices/`) — Django conventionne le singulier

---

## 3. Endpoints standard

| Endpoint | Rôle |
|---|---|
| `GET /api/health/` | healthcheck (capability `healthcheck`) |
| `POST /api/auth/token/` | obtention du couple access + refresh (SimpleJWT) |
| `POST /api/auth/token/refresh/` | rotation du refresh |
| `GET /api/me/` | utilisateur courant |
| `GET /api/schema/` | schéma OpenAPI 3 (drf-spectacular) |
| `GET /api/docs/` | Swagger UI |
| `/admin/` | admin Django (à restreindre par IP ou à désactiver en production) |

> Django impose la **barre oblique finale** par défaut (`APPEND_SLASH`). Le contrat d'API doit la refléter, sinon chaque appel front subit une redirection 301 — et un `POST` redirigé **perd son corps**.

---

## 4. Versioning des API exposees

Préfixe `/api/v1/{domaine}/`, porté par `config/urls.py`. `drf-spectacular` génère un schéma par version. Les changements de contrat (champ retiré, type modifié) imposent une nouvelle version — cf. `rules/library-and-stack.md §6.bis` pour la synchronisation front↔back.

---

## 5. Interdits projet (django)

**Architecture** :
- Vue de liste sans `select_related` / `prefetch_related` — requête N+1
- `.all()` sans pagination sur un `ViewSet`
- Règle métier dans un serializer ou une vue — `services.py`
- `settings.py` unique piloté par des `if DEBUG`
- `from django.contrib.auth.models import User` — `get_user_model()`
- Modèle `User` custom introduit **après** la première migration — migration manuelle irréversible en pratique
- Migration éditée à la main après application
- `signals` pour de la logique métier — impossible à suivre, appeler le service explicitement
- Requête SQL brute sans `params=` — injection SQL
- `objects.raw()` là où l'ORM suffit

**Code quality** :
- `import *` (hors `from .base import *` des settings, où il est conventionnel)
- Fonction de plus de 30 lignes
- `except:` nu ou `except Exception: pass`
- `print()` — utiliser `structlog`
- `TODO`, `FIXME`, code commenté

**Sécurité** :
- `DEBUG=True` en production
- `SECRET_KEY` en dur ou committée
- `ALLOWED_HOSTS = ["*"]`
- `CORS_ALLOW_ALL_ORIGINS = True` hors développement local
- `AllowAny` sur une vue exposant des données métier
- `manage.py check --deploy` laissé avec des warnings
- Admin Django exposé publiquement sans restriction
- Mot de passe stocké autrement que par le hasher Django

**Base de données** :
- `migrate` exécuté par un agent sur une base **existante** (cf. §1.5 et `rules/library-and-stack.md` Partie C)
- `makemigrations --merge` automatique sans relecture
- Suppression d'un champ sans migration de dépréciation en deux temps

---

## 6. Persistance — voir §1.5

ORM Django + migrations. Phase B (DB) d'`arch` : **applicable** — introspection en lecture seule, scaffolding des modèles pour une base neuve uniquement.

---

## 7. Temps reel

- **WebSockets** : Django Channels — **non catalogué**, à instruire avant engagement
- **SSE** : `StreamingHttpResponse` sous ASGI (capability `asgi` + Uvicorn)
- **Tâches asynchrones** : capability `background-jobs` (Celery + Redis)

> Sous Gunicorn (WSGI), une vue async est exécutée dans un pool de threads : aucun gain, et un risque de saturation. Le temps réel exige la capability `asgi`.

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **CRUD métier riche** — l'admin Django livre un back-office sans écrire de code
- **Applications à fort modèle de données** — ORM, migrations et contraintes en standard
- **Équipes Python** cherchant un cadre complet plutôt qu'un assemblage
- **Time-to-market court** sur du métier classique (facturation, RH, catalogue)

**NE PAS choisir si** :
- ❌ **Charge asynchrone forte** (beaucoup d'I/O concurrentes, WebSockets au cœur) → `backend/python-fastapi`, async de bout en bout
- ❌ **API à très faible latence** — DRF ajoute une surcouche de sérialisation notable face à Pydantic
- ❌ **Microservice minimal** — Django apporte beaucoup pour quelques endpoints
- ❌ **Le schéma est déjà figé par une base legacy complexe** — l'ORM Django s'y plie mal, `inspectdb` ne produit qu'un point de départ
- ❌ **Équipe .NET / Java / Node** — préférer le stack de leur langage
- ❌ **GraphQL en contrat principal** — Strawberry / Graphene ne sont pas catalogués ici

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `backend-django` + `react` + `shadcn` + `auth-local` + `postgres` | 🟡 experimental | jamais validé end-to-end |
| `backend-django` + `vue` + `vuetify` + `auth-local` + `postgres` | 🟡 experimental | jamais validé end-to-end |
| `backend-django` + `mobiles/react-native` + `auth-local` | 🟡 experimental | jamais validé end-to-end |
| `backend-django` + `qa/python-pytest` | 🟡 experimental | capability `pytest-django` requise, cf. `qa/python-pytest.md` |

---

## 10. Notes pour l'agent `arch`

1. **Détecter** `backend/django.md` en `## Active Tech Specs` → backend API, un frontend séparé est attendu
2. **Créer** `workspace/src/{BackendName}/` via §2.2.1. Le scaffolding découpe les settings : le patch de `BASE_DIR` du STEP 5 est **obligatoire**, sinon tous les chemins dérivés pointent dans `config/`
3. **Modèle `User` custom AVANT la première `migrate`** — décision irréversible en pratique (§1.4). Le poser au bootstrap même si l'US ne le demande pas encore
4. **Propager** `SECRET_KEY`, `DATABASE_URL`, `CORS_ALLOWED_ORIGINS`, `ALLOWED_HOSTS` depuis `stack.md` vers `.env` (lu par `django-environ`) — jamais de valeur en dur dans `settings/`
5. **CORS** : injecter l'origine du frontend déclaré (5173 React/Vue, 4200 Angular) dans `CORS_ALLOWED_ORIGINS`, comme au STEP 4.5.6 des autres stacks
6. **Phase B (DB)** : applicable, mais **lecture seule** sur une base existante. Ne jamais lancer `migrate` contre une base peuplée (`rules/library-and-stack.md` Partie C)
7. **`manage.py check --deploy`** dans le gate de production
8. **Phase C (ADRs)** : créer `ADR-{ts}-stack-backend-django.md` documentant Django 5.2 LTS (et **pourquoi pas 6.1**, cf. §2.3), DRF, SimpleJWT et le choix `services.py`

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

- `dev-backend` matérialise `apps/`, `common/`, `config/urls.py` et les settings applicatifs
- `dev-frontend` **ne touche pas** au projet Django — il code le frontend déclaré séparément

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `workspace/src/{BackendName}/apps/**` | `dev-backend` |
| `workspace/src/{BackendName}/common/**` | `dev-backend` |
| `workspace/src/{BackendName}/config/urls.py` | `dev-backend` |
| `workspace/src/{BackendName}/config/settings/**` | `arch` (create) + `dev-backend` (ajout d'app dans `INSTALLED_APPS`) |
| `workspace/src/{BackendName}/apps/*/migrations/**` | **généré** — `dev-backend` lance `makemigrations`, ne les édite jamais |
| `workspace/src/{BackendName}/pyproject.toml` | `arch` (create) + `dev-backend` (deps on-demand) |
| `workspace/src/{BackendName}/manage.py`, `pytest.ini` | `arch` exclusif |
| `workspace/src/{BackendName}/apps/*/tests/**` | `qa` |

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{BackendName}
uv sync

test -f manage.py
test -f config/settings/base.py
test -f pytest.ini
grep -q "parent.parent.parent" config/settings/base.py   # BASE_DIR patche (STEP 5)
grep -q "DJANGO_SETTINGS_MODULE" pytest.ini

uv run manage.py check
uv run manage.py makemigrations --check --dry-run   # aucune migration en attente
uv run ruff check .
uv run pytest

echo "smoke OK"
```

Gate de production supplémentaire : `uv run manage.py check --deploy` doit sortir **sans warning**.
