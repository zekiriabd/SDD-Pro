# Tech FEAT: django-templates (fullstack)

> §2.4 (Librairies) regeneree depuis `django-templates.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id django-templates`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits et validés le 2026-09-02. Chaque version résolue contre PyPI, et la compatibilité de chaque paquet avec Django 5.2 vérifiée via ses classifiers `Framework :: Django ::`. **Jamais exécuté end-to-end via `/sdd-full`** : aucun `manage.py check` ni `pytest` n'a tourné en CI. Non supporté commercialement en l'état.
Tech FEAT ID: tech-django-templates
Scope: **fullstack monolithe SSR** — application **Django 5.2 LTS** rendant des **templates Django** dans UN seul projet `{AppName}/`. `django-htmx` apporte l'interactivité sans SPA. Pas de séparation `{BackendName}` / `{AppName}` / `{LibName}`.

> **Django API ≠ ce stack.** Ici Django rend du HTML : ni DRF, ni serializers, ni JWT. Pour une API JSON consommée par un frontend séparé, déclarer `backend/django.md`. Les deux ne se déclarent **jamais ensemble**.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Monolithe SSR Django** :

- **Django 5.2 LTS** — ORM, migrations, **admin**, authentification, formulaires, templates
- **Templates Django** — héritage (`{% extends %}` / `{% block %}`) et inclusions
- **crispy-forms + crispy-tailwind** — rendu HTML structuré des formulaires
- **django-htmx** — interactivité par fragments HTML, sans écrire de JavaScript
- **django-template-partials** — fragments nommés **dans** un template, ce qui rend htmx exploitable sans éclater les fichiers
- **whitenoise** — service des fichiers statiques par l'application

Architecture cible :

```
{AppName}/
├── manage.py
├── config/
│   ├── settings/{base,local,production}.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   └── {domaine}/
│       ├── models.py
│       ├── views.py           ── vues rendant un template
│       ├── forms.py           ── formulaires Django
│       ├── urls.py
│       ├── services.py        ── logique metier
│       ├── admin.py
│       ├── migrations/
│       └── tests/
├── templates/
│   ├── base.html              ── layout racine
│   ├── partials/              ── fragments htmx
│   └── {domaine}/
├── static/
│   ├── css/                   ── Tailwind compile (ou CDN en dev)
│   └── js/                    ── htmx, Alpine (fichiers servis)
├── pyproject.toml
└── .env.example
```

**Différence vs `backend/django`** :
- **Pas de DRF** : ni serializers, ni ViewSets, ni schéma OpenAPI, ni JWT
- Les vues retournent `render(request, ...)`, pas `Response(...)`
- La validation passe par les **formulaires Django**, pas par des serializers
- L'**admin Django** prend encore plus de valeur : c'est un back-office complet, cohérent avec le reste de l'interface

**Différence vs `fullstack/laravel-blade`** :
- htmx est **agnostique du serveur** : le serveur renvoie des fragments HTML, htmx les insère. Aucun état de composant n'est maintenu côté serveur, contrairement à Livewire.
- Conséquence : plus simple à raisonner, mais chaque fragment doit être une vue à part entière.

---

## 1.2 Couches

- **Views** (`apps/{d}/views.py`) : orchestration + `render()`. Aucune règle métier.
- **Forms** (`apps/{d}/forms.py`) : validation et rendu des saisies. C'est la frontière d'entrée.
- **Services** (`apps/{d}/services.py`) : logique métier, testable sans HTTP.
- **Models** (`apps/{d}/models.py`) : schéma, contraintes, `Meta`.
- **Templates** (`templates/`) : présentation, avec `partials/` pour les fragments htmx.
- **Admin** (`apps/{d}/admin.py`) : back-office.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas.** Arch lève WARNING `[STACK_MALFORMED]` si `LibStrategy` déclare un mode `monorepo`.

| Layer | Path |
|---|---|
| Configuration | `config/settings/{base,local,production}.py` |
| Routes racine | `config/urls.py` |
| Vue | `apps/{domaine}/views.py` |
| Formulaire | `apps/{domaine}/forms.py` → `{Name}Form` |
| Service | `apps/{domaine}/services.py` |
| Modèle | `apps/{domaine}/models.py` → `class {Name}(models.Model)` |
| Admin | `apps/{domaine}/admin.py` |
| Migration | `apps/{domaine}/migrations/{n}_{desc}.py` (**générée**) |
| Layout | `templates/base.html` |
| Template de page | `templates/{domaine}/{action}.html` |
| Fragment htmx | `templates/{domaine}/partials/{name}.html` (ou `{% partialdef %}`) |
| Statiques | `static/{css,js}/` |
| Test | `apps/{domaine}/tests/test_{sujet}.py` |

---

## 1.4 Principes non negociables

**Architecture** :
- **`select_related` / `prefetch_related` sur toute vue de liste** — un template qui traverse une relation dans une boucle produit un N+1 invisible. C'est le défaut n°1 de ce stack, comme de `backend/django`.
- **Pagination systématique** (`Paginator`) — jamais `.all()` rendu tel quel.
- **Logique métier dans `services.py`** ; une vue de plus de 20 lignes signale une couche manquante.
- **Validation par formulaire Django**, jamais lue directement dans `request.POST`.
- **Une vue htmx renvoie un fragment, pas une page** — utiliser `request.htmx` (fourni par `django-htmx`) pour choisir entre le template complet et le partiel.
- **`{% partialdef %}` plutôt qu'un fichier par fragment** quand le fragment appartient à la page : cela évite l'éclatement en dizaines de petits templates.
- **Migrations committées**, jamais régénérées à la volée.
- **`get_user_model()`**, et **modèle `User` custom dès la première migration** — le changer après coup impose une migration manuelle de toute la base (irréversible en pratique).

**Sécurité** :
- **`{% csrf_token %}` dans tout formulaire**, et `hx-headers` avec le token CSRF pour les requêtes htmx non-GET
- **L'auto-échappement des templates Django est actif par défaut** : `|safe` et `{% autoescape off %}` sont des injections XSS sauf contenu prouvé assaini
- **`DEBUG=False` en production**, `ALLOWED_HOSTS` explicite
- **`SECRET_KEY` par l'environnement** (`stack.md`)
- **`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`** en production
- **`@login_required` / `PermissionRequiredMixin`** explicites — masquer un lien dans le template n'est pas un contrôle d'accès
- **Admin restreint** (IP, ou désactivé) en production
- **`manage.py check --deploy`** sans warning avant mise en production

---

## 1.5 Base de donnees

| DatabaseType | Driver | Remarque |
|---|---|---|
| `postgres` / `postgresql` | `psycopg` (v3) | défaut recommandé |
| `sqlite` | intégré | développement et tests |
| `mysql` / `mariadb` | `mysqlclient` | **non catalogué** — à instruire |
| `oracle` / `sqlserver` | pilotes tiers | **non supportés** |

> ⚠️ **Soumis à `rules/library-and-stack.md` Partie C.** Sur une base **existante**,
> un agent n'exécute **jamais** `migrate` : il écrit le DDL dans
> `workspace/db/migration-pending.sql` et émet `[DB_STRUCTURE_CHANGE_FORBIDDEN]`.
> La création du schéma initial d'une base **neuve** reste permise (§C.3).

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `fullstack-django-templates`
- **AppType** : `fullstack` (rendu SSR, projet unique)
- **Langage** : Python 3.12
- **Framework** : Django **5.2.17 LTS** + moteur de templates Django
- **Interactivité** : htmx (+ Alpine pour le purement local)
- **Serveur** : Gunicorn (WSGI)
- **Package manager** : `uv`
- **Assets** : fichiers statiques servis par whitenoise — **aucun pipeline Node par défaut**

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/pyproject.toml`
- **Run dev** : `uv run manage.py runserver 0.0.0.0:8000`
- **Migrations** : `uv run manage.py makemigrations` / `migrate`
- **Superuser** : `uv run manage.py createsuperuser`
- **Statiques (prod)** : `uv run manage.py collectstatic --noinput`
- **Gate de déploiement** : `uv run manage.py check --deploy` — **sans warning**
- **Tests** : `uv run pytest`
- **Lint / format** : `uv run ruff check .` / `uv run ruff format .`
- **Typage** : `uv run mypy .`
- **Prod** : `uv run gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4`
- **Smoke Command** :

```bash
(cd workspace/src/{AppName} && uv sync && uv run manage.py check)
test -f workspace/src/{AppName}/templates/base.html
test -f workspace/src/{AppName}/manage.py
```

- **Smoke Timeout** : 180s

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/manage.py" ]; then
  APP=workspace/src/{AppName}
  mkdir -p "$APP" && cd "$APP"

  # STEP 1 — Projet uv + runtime pinne
  uv init --name {AppName} --python 3.12 --no-workspace

  # STEP 2 — Dependances CORE (cf. 2.4.a) — NI DRF, NI JWT : ce stack rend du HTML
  uv add \
    django==5.2.17 \
    django-environ==0.14.0 \
    psycopg==3.3.5 \
    django-crispy-forms==2.7 \
    crispy-tailwind==1.0.3 \
    django-htmx==1.29.0 \
    django-template-partials==25.3 \
    whitenoise==6.12.0 \
    gunicorn==26.2.0 \
    structlog==26.1.0 \
    django-structlog==10.1.0

  # STEP 3 — Outillage de developpement
  uv add --dev \
    ruff==0.16.5 \
    mypy==2.3.1 \
    django-stubs==6.1.0 \
    pytest==9.1.1 \
    pytest-django==4.14.0

  # STEP 4 — Scaffolding Django
  uv run django-admin startproject config .

  # STEP 5 — Settings decoupes (+ patch BASE_DIR : il descend d'un niveau)
  mkdir -p config/settings apps templates/partials static/{css,js}
  mv config/settings.py config/settings/base.py
  touch config/settings/__init__.py apps/__init__.py
  printf 'from .base import *  # noqa: F403\n' > config/settings/local.py
  printf 'from .base import *  # noqa: F403\n' > config/settings/production.py

  python - <<'PY'
import pathlib
p = pathlib.Path("config/settings/base.py")
s = p.read_text(encoding="utf-8")
s = s.replace("BASE_DIR = Path(__file__).resolve().parent.parent",
              "BASE_DIR = Path(__file__).resolve().parent.parent.parent")
p.write_text(s, encoding="utf-8")
PY

  sed -i 's/config.settings/config.settings.local/' manage.py config/wsgi.py config/asgi.py

  # STEP 6 — base.html (htmx + CSRF global)
  cat > templates/base.html <<'HTML'
{% load static %}
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}{{ site_name|default:"App" }}{% endblock %}</title>
    <link rel="stylesheet" href="{% static 'css/app.css' %}">
    <script src="{% static 'js/htmx.min.js' %}" defer></script>
</head>
{# hx-headers propage le token CSRF a TOUTES les requetes htmx non-GET #}
<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
    {% block content %}{% endblock %}
</body>
</html>
HTML

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
DATABASE_URL=postgres://user:pass@localhost:5432/{AppName}
ENV

  # STEP 8 — Gate
  uv run manage.py check
fi
```

**Contrat post-init** :
- `manage.py check` sort 0
- `templates/base.html` existe et porte `hx-headers` avec le token CSRF
- `BASE_DIR` remonte 3 parents dans `config/settings/base.py`
- `INSTALLED_APPS` contient `crispy_forms`, `crispy_tailwind`, `django_htmx`, `template_partials`
- `CRISPY_TEMPLATE_PACK = "tailwind"` est déclaré
- Un modèle `User` custom est posé **avant** la première `migrate`

---

## 2.3 Notes de construction

### Django 5.2 LTS et non 6.1 — même raison que `backend/django`

Django publie des **LTS explicites** (4.2, 5.2, puis 6.2). La 6.1 n'en est pas
une, et `rules/library-and-stack.md §0` impose « runtime LTS only ». La 5.2 est
supportée jusqu'en **avril 2028**.

La vérification des classifiers PyPI confirme le choix : `pytest-django`,
`django-redis` et `crispy-*` déclarent tous `Framework :: Django :: 5.2`, mais
plusieurs ne déclarent pas encore la 6.1. Table détaillée dans
`backend/django.md §2.3`.

### `crispy-forms` sans template pack ne rend rien

`django-crispy-forms` **ne fournit aucun template pack**. Installé seul, il
échoue au rendu avec un message sur `CRISPY_TEMPLATE_PACK`. Le pack est un
paquet séparé — d'où `crispy-tailwind` en **CORE** et non en on-demand.

```python
CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"
```

`crispy-bootstrap5` (capability `bootstrap-forms`) est l'alternative — **un seul
pack à la fois**.

### htmx et CSRF

Django rejette toute requête non-GET sans token CSRF. htmx n'en envoie pas
spontanément. La solution retenue est un `hx-headers` **sur `<body>`**, qui
couvre toutes les requêtes htmx de la page (STEP 6). L'oublier produit des
**403 sur toutes les actions htmx**, avec un message qui ne mentionne pas htmx.

### Pas de pipeline Node par défaut

htmx et Alpine sont servis comme **fichiers statiques** ; whitenoise les
distribue. Aucun `npm install` n'est requis — c'est un écart assumé avec
`fullstack/laravel-blade`, qui exige Vite.

Si Tailwind doit être compilé (plutôt que servi via CDN), la capability
`tailwind-build` (`django-tailwind`) introduit **une dépendance à Node** : à
n'activer que si l'US le justifie.

### Ce qui n'a PAS été validé

| Vérifié | Non vérifié |
|---|---|
| Existence + dernière version stable de chaque paquet (PyPI, 2026-09-02) | `manage.py check` |
| Classifiers `Framework :: Django :: 5.2` de chaque paquet | `pytest` sur un projet généré |
| Cohérence `.md` ↔ `.libs.json` | Rendu htmx réel |
| — | Pipeline `/sdd-full` complet |

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/fullstack/django-templates.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id django-templates`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| django | 5.2.17 | Framework — ligne LTS 5.2. Le moteur de templates, le systeme de formulaires et l'admin sont integres |
| django-environ | 0.14.0 | Configuration typee lue dans l'environnement |
| psycopg | 3.3.5 | Driver PostgreSQL v3 |
| django-crispy-forms | 2.7 | Rendu des formulaires Django en HTML structure. Sans lui, `{{ form }}` produit un balisage brut inutilisable en production |
| crispy-tailwind | 1.0.3 | Template pack Tailwind pour crispy-forms. OBLIGATOIRE avec crispy-forms : le paquet de base ne fournit AUCUN pack, `CRISPY_TEMPLATE_PACK` doit pointer sur un pack installe |
| django-htmx | 1.29.0 | Middleware + helpers pour htmx : detecte `request.htmx`, gere les reponses partielles. C'est l'interactivite de ce stack, sans SPA |
| django-template-partials | 25.3 | Fragments nommes DANS un template — c'est ce qui rend htmx exploitable sans multiplier les fichiers de partiels |
| whitenoise | 6.12.0 | Service des fichiers statiques par l'app (htmx, Alpine, CSS) sans reverse proxy |
| gunicorn | 26.2.0 | Serveur WSGI de production |
| structlog | 26.1.0 | Logs structures |
| django-structlog | 10.1.0 | Integration Django (request_id correle) |
| ruff | 0.16.5 | Lint + format (dev) |
| mypy | 2.3.1 | Typage statique (dev) |
| django-stubs | 6.1.0 | Stubs Django pour mypy (dev) |
| pytest | 9.1.1 | Runner de tests (dev) — cf. qa/python-pytest.md |
| pytest-django | 4.14.0 | Fixtures Django pour pytest (dev) — sans lui tout import de modele leve ImproperlyConfigured |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| form-tweaks | django-widget-tweaks (alt) | 1.5.1 | classe.*css.*champ, widget, personnaliser.*formulaire |
| bootstrap-forms | crispy-bootstrap5 (alt) | 2026.3 | bootstrap |
| tailwind-build | django-tailwind | 4.5.0 | tailwind, build.*css |
| asset-pipeline | django-compressor | 4.6.0 | minifier.*css, concatener.*assets, compressor |
| image-processing | pillow | 12.3.0 | image, upload.*photo, miniature |
| object-storage | django-storages | 1.14.6 | \bs3\b, stockage.*objet, azure.*blob |
| background-jobs | celery | 5.6.3 | tache.*asynchrone, background job, worker, celery |
| background-jobs | redis | 8.1.0 | celery, broker, redis |
| redis-cache | django-redis | 7.0.0 | cache, redis |
| auth-scaffold | django-allauth | 65.19.2 | login, inscription, authentification, oauth, connexion.*google |
| transactional-email | django-anymail | 15.1 | email.*transactionnel, sendgrid, mailgun |
| healthcheck | django-health-check | 4.5.1 | health, readiness, liveness |
| sentry | sentry-sdk | 2.68.1 | sentry, error.*tracking, monitoring.*erreurs |
| dev-profiling | django-debug-toolbar | 8.0.0 | debug.*toolbar, profiler.*requetes, n\+1 |
| dev-profiling | django-extensions (alt) | 4.1 | shell_plus, graph_models |
| excel | openpyxl | 3.1.5 | excel, xlsx, export.*tableur |
| pdf | reportlab | 5.0.1 | \bpdf\b, export.*pdf, generation.*document |
| coverage | pytest-cov | 7.1.0 | coverage, couverture.*tests |
| test-fixtures | model-bakery | 1.24.0 | fixture, donnees.*test, baker |

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
| Vue | fonction `{verbe}_{objet}` ou `{Name}ListView` | `invoice_list`, `InvoiceDetailView` |
| Formulaire | `{Name}Form` | `InvoiceForm` |
| Service | `apps/{d}/services.py` → fonctions verbales | `def issue_invoice(...)` |
| Template de page | `templates/{domaine}/{action}.html` | `templates/billing/invoice_list.html` |
| Fragment htmx | `templates/{domaine}/partials/{name}.html` | `partials/invoice_row.html` |
| Nom d'URL | `{domaine}:{action}` | `billing:invoice_list` |
| Test | `test_{sujet}.py` | `test_invoice_service.py` |
| Migration | **générée** — ne jamais renommer | `0003_invoice_status.py` |

**Suffixes INTERDITS** :
- `Manager` sur autre chose qu'un `models.Manager` (nom réservé par Django)
- `Helper`, `Util`
- `Model` en suffixe de classe (`InvoiceModel`)
- Nom d'app au pluriel (`apps/invoices/`) — Django conventionne le singulier

---

## 3. Routes standard

| Route | Rôle |
|---|---|
| `GET /` | page d'accueil |
| `GET /accounts/login/` · `POST` | authentification (`django.contrib.auth`) |
| `POST /accounts/logout/` | déconnexion |
| `GET /health/` | healthcheck (capability `healthcheck`) |
| `/admin/` | admin Django — à restreindre ou désactiver en production |

> Django impose la **barre oblique finale** (`APPEND_SLASH`). Les attributs `hx-post` doivent la porter : sans elle, Django redirige en 301 et **le corps du POST est perdu**.

---

## 4. Versioning

Monolithe SSR : pas de contrat d'API versionné. Client et serveur avancent
ensemble à chaque déploiement — `rules/library-and-stack.md §6.bis` (drift de
contrat front↔back) est **sans objet**.

---

## 5. Interdits projet (django-templates)

**Architecture** :
- Vue de liste sans `select_related` / `prefetch_related` — N+1 traversé par le template
- `.all()` rendu sans pagination
- Règle métier dans une vue ou dans un template — `services.py`
- `request.POST` lu directement — passer par un formulaire Django
- Vue htmx renvoyant la page entière au lieu d'un fragment
- Un fichier de template par micro-fragment — utiliser `{% partialdef %}`
- `from django.contrib.auth.models import User` — `get_user_model()`
- Modèle `User` custom introduit après la première migration
- `signals` pour de la logique métier
- DRF, serializers ou JWT installés ici — c'est le signe qu'il fallait `backend/django`

**Code quality** :
- `import *` (hors `from .base import *` des settings)
- Fonction de plus de 30 lignes
- `except:` nu ou `except Exception: pass`
- `print()` — utiliser `structlog`
- Template de plus de 100 lignes — extraire des partials
- Logique conditionnelle profonde dans un template
- `TODO`, `FIXME`, code commenté

**Sécurité** :
- **`|safe` ou `{% autoescape off %}` sur du contenu non assaini** — injection XSS
- `{% csrf_token %}` absent d'un formulaire
- `hx-headers` CSRF absent de `base.html` — toutes les actions htmx tombent en 403 (§2.3)
- `DEBUG=True` en production
- `SECRET_KEY` en dur ou committée
- `ALLOWED_HOSTS = ["*"]`
- Vue métier sans `@login_required` / `PermissionRequiredMixin`
- Autorisation reposant sur le masquage d'un lien dans le template
- `manage.py check --deploy` laissé avec des warnings
- `django-debug-toolbar` actif en production
- Admin Django exposé sans restriction

**Base de données** :
- `migrate` exécuté par un agent sur une base **existante** (§1.5)
- Migration éditée à la main après application
- `makemigrations --merge` automatique sans relecture

**Build / packaging** :
- Committer `.venv/`, `__pycache__/`, `staticfiles/`, `.env`, `db.sqlite3`
- `uv.lock` absent du dépôt (une **application** verrouille ses versions)
- `collectstatic` oublié avant déploiement — whitenoise ne sert alors rien
- Node introduit sans justification (§2.3)

---

## 6. Persistance — voir §1.5

ORM Django + migrations. Phase B (DB) d'`arch` : **applicable** — introspection en lecture seule ; scaffolding de modèles pour une base neuve uniquement.

---

## 7. Temps reel

- **`hx-trigger="every 5s"`** — rafraîchissement périodique d'un fragment, sans dépendance. Le plus simple et souvent suffisant.
- **SSE** : `StreamingHttpResponse` + `hx-ext="sse"` — nécessite un serveur ASGI (Uvicorn), non installé par défaut ici
- **WebSockets** : Django Channels — **non catalogué**, à instruire
- **Tâches asynchrones** : capability `background-jobs` (Celery + Redis)

> Sous Gunicorn (WSGI), une réponse en streaming monopolise un worker. Le polling htmx est préférable tant que la charge le permet.

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **Applications métier internes** — l'admin Django livre un back-office complet sans code
- **Équipes Python sans compétence front** — htmx évite d'écrire du JavaScript
- **Chaîne de build minimale** — pas de Node, pas de bundler, un seul déploiement
- **SEO** — HTML rendu serveur par construction

**NE PAS choisir si** :
- ❌ **Interface très interactive** (glisser-déposer, édition temps réel, canvas) — htmx couvre le CRUD enrichi, pas une application riche
- ❌ **Application mobile prévue** — une API sera nécessaire : partir sur `backend/django` + un stack `mobiles/*`
- ❌ **Équipe front React/Vue déjà en place** — préférer `backend/django` + `frontend/*`
- ❌ **Charge asynchrone forte** (WebSockets au cœur) — Django reste synchrone sous WSGI
- ❌ **Besoin de fonctionner hors ligne**
- ❌ **Équipe .NET / Java / PHP / Node** — préférer le stack de leur langage

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `fullstack-django-templates` + `qa/python-pytest` (capability `django-testing`) + `postgres` | 🟡 experimental | jamais validé end-to-end |
| `fullstack-django-templates` + capability `auth-scaffold` (allauth) | 🟡 experimental | vues d'authentification prêtes à l'emploi |
| `fullstack-django-templates` + capability `background-jobs` (Celery) | 🟡 experimental | jamais validé end-to-end |

> **Incompatible** avec tout stack `frontend/*` et avec `backend/django`.

---

## 10. Notes pour l'agent `arch`

1. **Détecter** `fullstack/django-templates.md` en `## Active Tech Specs` → `AppType=fullstack`, projet unique, **aucun** frontend séparé attendu
2. **Refuser la cohabitation** avec `backend/django.md` ou un stack `frontend/*` → WARNING bloquant `[STACK_INCOMPAT]`
3. **Ne PAS installer DRF, drf-spectacular ni simplejwt** — leur présence signale une erreur de choix de stack (§5)
4. **Patch `BASE_DIR` obligatoire** au STEP 5 : les settings descendent d'un niveau, sans le patch tous les chemins dérivés pointent dans `config/`
5. **Modèle `User` custom AVANT la première `migrate`** — irréversible en pratique
6. **`hx-headers` CSRF sur `<body>`** dans `base.html` (STEP 6) — sans lui **toutes** les actions htmx tombent en 403, avec un message qui ne mentionne pas htmx (§2.3)
7. **`CRISPY_TEMPLATE_PACK = "tailwind"`** dans les settings — `crispy-forms` sans pack ne rend rien (§2.3)
8. **`INSTALLED_APPS`** doit contenir `crispy_forms`, `crispy_tailwind`, `django_htmx`, `template_partials` ; `MIDDLEWARE` doit contenir `django_htmx.middleware.HtmxMiddleware` et `whitenoise.middleware.WhiteNoiseMiddleware`
9. **Propager** `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS` depuis `stack.md` vers `.env`
10. **CORS** : sans objet — même origine. Ne pas installer `django-cors-headers` (contrairement à `backend/django`)
11. **Phase B (DB)** : applicable, **lecture seule** sur base existante
12. **Phase C (ADRs)** : créer `ADR-{ts}-stack-fullstack-django-templates.md` documentant Django 5.2 LTS (et **pourquoi pas 6.1**), htmx plutôt qu'une SPA, et l'absence de pipeline Node

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Stack monolithe** : pas de séparation back/front (cf. `ownership.md §1.bis`).

- **`dev-backend`** matérialise `apps/`, `config/`
- **`dev-frontend`** matérialise `templates/`, `static/`
- **Les vues htmx sont la frontière** : la vue Python (`views.py`) est du ressort de `dev-backend`, le fragment rendu (`templates/**/partials/`) de `dev-frontend`. Les deux évoluent ensemble.

**File ownership** :

| Path | Owner |
|---|---|
| `apps/*/models.py`, `services.py`, `forms.py`, `admin.py` | `dev-backend` |
| `apps/*/views.py`, `urls.py` | `dev-backend` |
| `config/urls.py` | `dev-backend` |
| `config/settings/**` | `arch` (create) + `dev-backend` (`INSTALLED_APPS`, `MIDDLEWARE`) |
| `templates/**` | `dev-frontend` |
| `static/**` | `dev-frontend` |
| `apps/*/migrations/**` | **généré** — `dev-backend` lance `makemigrations`, ne les édite jamais |
| `pyproject.toml` | `arch` (create) + `dev-backend` (deps on-demand) |
| `manage.py`, `pytest.ini` | `arch` exclusif |
| `apps/*/tests/**` | `qa` |

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{AppName}
uv sync

test -f manage.py
test -f templates/base.html
test -f pytest.ini
grep -q "parent.parent.parent" config/settings/base.py   # BASE_DIR patche (STEP 5)
grep -q "hx-headers" templates/base.html                 # CSRF htmx (cf. 2.3)
grep -q "CRISPY_TEMPLATE_PACK" config/settings/base.py   # sinon crispy ne rend rien
grep -q "HtmxMiddleware" config/settings/base.py

# Ce stack rend du HTML : DRF n'a rien a y faire (cf. 5)
! grep -q "rest_framework" config/settings/base.py

uv run manage.py check
uv run manage.py makemigrations --check --dry-run
uv run ruff check .
uv run pytest

echo "smoke OK"
```

Gate de production supplémentaire : `uv run manage.py check --deploy` sans warning.
