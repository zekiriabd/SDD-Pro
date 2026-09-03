# Tech FEAT: laravel (backend)

> §2.4 (Librairies) regeneree depuis `laravel.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id laravel`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits et validés le 2026-09-02, chaque version résolue contre Packagist **avec sa contrainte `require.php`** — c'est cette lecture croisée qui a révélé que le plancher PHP réel du stack n'est pas celui du framework (cf. §2.3). Premier stack `composer` du catalogue : le `buildSystem` correspondant a été ajouté au schéma, au validateur et au générateur `sync_stack_md.py` au même passage. **Jamais exécuté end-to-end via `/sdd-full`** : aucun `composer install` ni `artisan test` n'a tourné en CI. Non supporté commercialement en l'état.
Tech FEAT ID: tech-laravel
Scope: **backend API REST** — application **Laravel 13** dans UN projet `workspace/src/{BackendName}/`. Expose une API JSON consommée par un frontend séparé (`frontend/*` ou `mobiles/*`) déclaré en `## Active Tech Specs`.

> **Laravel SSR ≠ ce stack.** Ici Laravel ne rend aucune vue Blade : il sert du JSON. Pour un monolithe Laravel + Blade, voir `fullstack/laravel-blade.md`.

---

# 1. Architecture

## 1.1 Pattern applicatif

**API REST Laravel**, organisée par domaine :

- **Laravel 13** — Eloquent, migrations, queues, conteneur de services, validation
- **Sanctum** — authentification par jetons d'API (SPA et mobile)
- **FormRequest** — validation en amont du controller
- **API Resources** — transformation de la réponse (le contrat de sortie)
- **spatie/laravel-query-builder** — filtres et tris de querystring **avec allowlist**
- **Scramble** — OpenAPI 3 **inféré** des FormRequest et Resources, sans annotations à maintenir

Architecture cible :

```
{BackendName}/
├── app/
│   ├── Models/                    ── modeles Eloquent
│   ├── Http/
│   │   ├── Controllers/Api/       ── controllers (HTTP uniquement)
│   │   ├── Requests/              ── FormRequest (validation d'entree)
│   │   ├── Resources/             ── API Resources (contrat de sortie)
│   │   └── Middleware/
│   ├── Services/                  ── logique metier (cf. 1.4)
│   ├── Policies/                  ── autorisation par modele
│   ├── Jobs/                      ── travaux en file
│   ├── Events/ · Listeners/
│   └── Exceptions/
├── config/
├── database/
│   ├── migrations/
│   ├── factories/                 ── requises par les tests
│   └── seeders/
├── routes/
│   └── api.php
├── tests/
│   ├── Feature/                   ── tests HTTP de bout en bout
│   └── Unit/
├── composer.json
└── .env.example
```

**Différence vs les autres stacks `backend/`** :
- Laravel apporte **ORM + migrations + queues + planificateur + mail + cache** en standard
- Convention forte : la structure de dossiers **est** l'architecture
- Eloquent est un **Active Record** (le modèle sait se sauvegarder), là où Django utilise un Manager/QuerySet et TypeORM/EF un Data Mapper. La logique métier a donc encore plus tendance à s'accumuler dans le modèle — d'où la règle `Services/` du §1.4.

---

## 1.2 Couches

- **Controller** (`Http/Controllers/Api/`) : HTTP seulement — reçoit un FormRequest, appelle un Service, retourne une Resource.
- **FormRequest** (`Http/Requests/`) : validation et autorisation d'accès à la route. Frontière d'entrée.
- **Resource** (`Http/Resources/`) : forme de la réponse JSON. Frontière de sortie.
- **Service** (`Services/`) : la logique métier. Testable sans HTTP.
- **Model** (`Models/`) : schéma, relations, scopes, casts. Pas d'orchestration métier.
- **Policy** (`Policies/`) : autorisation par modèle (`can`, `authorize`).
- **Job** (`Jobs/`) : travail différé (capability `queues`).

---

## 1.3 Mapping couche → repertoire

| Layer | Path |
|---|---|
| Routes API | `routes/api.php` |
| Controller | `app/Http/Controllers/Api/{Name}Controller.php` |
| FormRequest | `app/Http/Requests/{Action}{Name}Request.php` |
| Resource | `app/Http/Resources/{Name}Resource.php` |
| Collection | `app/Http/Resources/{Name}Collection.php` |
| Service | `app/Services/{Name}Service.php` |
| Modèle | `app/Models/{Name}.php` |
| Policy | `app/Policies/{Name}Policy.php` |
| Job | `app/Jobs/{Verb}{Name}Job.php` |
| Middleware | `app/Http/Middleware/{Name}.php` |
| Migration | `database/migrations/{ts}_{desc}.php` (**générée**) |
| Factory | `database/factories/{Name}Factory.php` |
| Seeder | `database/seeders/{Name}Seeder.php` |
| Test Feature | `tests/Feature/{Name}Test.php` |
| Test Unit | `tests/Unit/{Name}Test.php` |
| Config | `config/{domaine}.php` |

---

## 1.4 Principes non negociables

**Architecture** :
- **Controller mince** : `FormRequest` → `Service` → `Resource`. Un controller qui construit une requête Eloquent contient déjà trop.
- **La logique métier va dans `Services/`.** Eloquent étant un Active Record, la tentation d'empiler les méthodes métier dans le modèle est structurelle — c'est ce qui produit les modèles de 800 lignes.
- **Toute validation passe par un `FormRequest`**, jamais `$request->validate()` en ligne dans le controller.
- **Toute réponse passe par une `Resource`.** Retourner `$model` directement expose la table : ajouter une colonne devient un changement de contrat d'API non voulu.
- **`with()` systématique** sur les relations lues — Eloquent charge en paresseux par défaut, et le N+1 est le défaut n°1 de ce stack.
- **Filtres via `spatie/laravel-query-builder` avec allowlist** — jamais de tri ou de filtre construit depuis un paramètre brut (injection dans l'`ORDER BY`).
- **Autorisation par `Policy`**, pas de `if ($user->role === 'admin')` disséminé.
- **`config()` et non `env()` hors des fichiers `config/`** — après `config:cache`, `env()` renvoie `null` en production. C'est un piège classique, et silencieux.
- **Migrations committées**, jamais éditées après application.

**Sécurité** :
- **`APP_DEBUG=false` en production** — sinon la page d'erreur expose la configuration et des extraits de code
- **`APP_KEY` généré et gardé secret** (`stack.md`) — c'est la clé de chiffrement des sessions et cookies
- **CORS explicite** dans `config/cors.php` — pas de `'allowed_origins' => ['*']` avec `supports_credentials: true` (interdit par la spec CORS)
- **`$fillable` explicite** sur chaque modèle, jamais `$guarded = []` (assignation de masse)
- **Rate limiting** sur les routes d'authentification (`throttle`)
- **Politique de mot de passe** via le hasher Laravel (bcrypt/argon2), jamais de hash maison
- **`storage/` et `.env` hors du répertoire servi** par le serveur web

---

## 1.5 Base de donnees

| DatabaseType | Support Laravel | Remarque |
|---|---|---|
| `postgres` / `postgresql` | natif (`pdo_pgsql`) | défaut recommandé |
| `mysql` / `mariadb` | natif (`pdo_mysql`) | supporté nativement |
| `sqlite` | natif (`pdo_sqlite`) | tests et développement |
| `sqlserver` | natif (`pdo_sqlsrv`) | pilote système requis |

Aucun paquet Composer n'est nécessaire : les drivers sont des **extensions PHP**
(`pdo_pgsql`…), activées au niveau du runtime. C'est pourquoi ce catalog ne
déclare pas de bloc `dbDrivers` — contrairement à `backend/dotnet-minimalapi`
ou `backend/django`, l'unité d'installation n'est pas un paquet.

Migrations : `artisan make:migration` puis `artisan migrate`.

> ⚠️ **Soumis à `rules/library-and-stack.md` Partie C.** Sur une base **existante**,
> un agent n'exécute **jamais** `artisan migrate` : il écrit le DDL dans
> `workspace/db/migration-pending.sql` et émet `[DB_STRUCTURE_CHANGE_FORBIDDEN]`.
> `artisan migrate:fresh` et `migrate:refresh` sont **destructifs** — interdits
> hors base neuve (§5).

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `backend-laravel`
- **Langage** : PHP **8.4** (plancher `8.4.1`, cf. §2.3)
- **Framework** : Laravel 13.30.1
- **Authentification** : Sanctum 4.3 (Passport via la capability `oauth2`, exclusive)
- **Package manager** : `composer`
- **Serveur** : PHP-FPM + nginx (ou Octane via la capability `high-throughput`)
- **Base par défaut** : PostgreSQL (extension `pdo_pgsql`)

---

## 2.2 Outils

- **Project file** : `workspace/src/{BackendName}/composer.json`
- **Run dev** : `(cd workspace/src/{BackendName} && php artisan serve --port=8000)`
- **Migrations** : `php artisan migrate` / `php artisan make:migration {desc}`
- **Générateurs** : `php artisan make:{model,controller,request,resource,policy,job}`
- **Schéma OpenAPI** : `php artisan scramble:export`
- **Tests** : `php artisan test` (Pest) ou `./vendor/bin/pest`
- **Coverage** : `php artisan test --coverage --min=80`
- **Format** : `./vendor/bin/pint`
- **Analyse statique** : `./vendor/bin/phpstan analyse`
- **Cache de production** : `php artisan config:cache route:cache view:cache`
- **Smoke Command** :

```bash
(cd workspace/src/{BackendName} && composer install --no-interaction --quiet && php artisan about)
test -f workspace/src/{BackendName}/artisan
test -f workspace/src/{BackendName}/routes/api.php
```

- **Smoke Timeout** : 240s (`composer install` est lent au premier passage)

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{BackendName}/artisan" ]; then

# STEP 0 — Gate runtime : le plancher vient de l'outillage de TEST, pas du framework (cf. 2.3)
php -r 'exit(version_compare(PHP_VERSION, "8.4.1", ">=") ? 0 : 1);' || {
  echo "ERROR: arch {BackendName} — runtime PHP insuffisant"
  echo "CAUSE: [INFRA_BLOCKED] PHP $(php -r 'echo PHP_VERSION;') < 8.4.1 requis par pestphp/pest 5 + phpunit 13"
  exit 3
}
composer --version

# STEP 1 — Scaffold Laravel
composer create-project laravel/laravel workspace/src/{BackendName} "13.*" \
  --no-interaction --prefer-dist

cd workspace/src/{BackendName}

# STEP 2 — Dependances CORE runtime (cf. 2.4.a)
composer require --no-interaction \
  laravel/sanctum:4.3.3 \
  spatie/laravel-query-builder:7.3.4 \
  dedoc/scramble:0.13.42 \
  guzzlehttp/guzzle:8.1.0

# STEP 3 — Outillage de developpement
composer require --dev --no-interaction \
  pestphp/pest:5.1.3 \
  pestphp/pest-plugin-laravel:5.0.1 \
  larastan/larastan:3.11.0 \
  laravel/pint:1.30.5

# STEP 4 — Publier la config Sanctum + routes API
# (Laravel 11+ ne cree PAS routes/api.php par defaut : il faut l'installer)
php artisan install:api --no-interaction

# STEP 5 — Arborescence applicative
mkdir -p \
  app/Http/Controllers/Api \
  app/Http/Requests \
  app/Http/Resources \
  app/Services \
  app/Policies \
  app/Jobs \
  tests/Feature tests/Unit

# STEP 6 — Basculer la suite de tests sur Pest
php artisan pest:install --no-interaction 2>/dev/null || true

# STEP 7 — phpstan.neon (larastan)
cat > phpstan.neon <<'NEON'
includes:
    - vendor/larastan/larastan/extension.neon
parameters:
    paths:
        - app
    level: 6
NEON

# STEP 8 — Cle applicative + gate
php artisan key:generate
php artisan about

fi
```

**Contrat post-init** :
- `artisan about` sort 0
- `routes/api.php` existe (créé par `install:api`, pas par le template)
- `APP_KEY` est généré
- `phpstan.neon` existe et référence l'extension larastan
- `composer.json` déclare `require.php: ^8.4`

---

## 2.3 Plancher PHP — il vient de l'outillage de test

C'est la principale découverte de la construction de ce catalog, et elle est
contre-intuitive : **le framework n'est pas le composant le plus exigeant.**

| Paquet | `require.php` déclaré sur Packagist |
|---|---|
| `laravel/framework` 13.30.1 | `^8.3` |
| `laravel/sanctum` 4.3.3 | `^8.2` |
| `spatie/laravel-permission` 8.3.0 | `^8.3` |
| **`pestphp/pest` 5.1.3** | **`^8.4`** |
| **`phpunit/phpunit` 13.3.2** | **`>=8.4.1`** |

Un projet installé sur PHP 8.3 passerait `composer require laravel/framework`
sans broncher, puis **échouerait à l'installation des dépendances de dev** —
c'est-à-dire au moment de mettre en place les tests, donc tard. Le STEP 0 de
§2.2.1 vérifie donc `8.4.1` **avant** tout scaffolding.

### PHP n'a pas de LTS

`rules/library-and-stack.md §0` impose « runtime LTS only » et sa matrice ne
comportait aucune ligne PHP (ajoutée au même audit). Le modèle amont de PHP est
différent de celui de .NET ou Java :

| Ligne | Statut au 2026-09-02 |
|---|---|
| 8.5.10 | dernière publiée, active support |
| **8.4.25** | **active support — retenue par ce stack** |
| 8.3.33 | active support (fin proche) |
| 8.2.33 | security-only |

Chaque version reçoit ~2 ans d'`active support` puis ~1 an de `security
support`. Le stack cible **8.4** : elle satisfait toutes les contraintes
ci-dessus et laisse de la marge. Les contraintes `^8.3` / `^8.4` admettent
également **8.5**, qui est donc utilisable — mais n'est pas ce que le catalog
déclare, faute d'avoir pu le vérifier à l'exécution.

### Sanctum ou Passport, jamais les deux

`laravel/sanctum` (CORE) et `laravel/passport` (capability `oauth2`) résolvent
le même problème à deux échelles : jetons d'API simples contre serveur OAuth2
complet. Les livrer ensemble produit deux gardes d'authentification concurrents
sur les mêmes routes. La capability est marquée `alternative`.

### Ce qui n'a PAS été validé

| Vérifié | Non vérifié |
|---|---|
| Existence + dernière version stable de chaque paquet (Packagist, 2026-09-02) | `composer install` |
| Contrainte `require.php` de **chaque** paquet (table ci-dessus) | `artisan test` |
| Cohérence `.md` ↔ `.libs.json` | `artisan migrate` contre une vraie base |
| — | Pipeline `/sdd-full` complet |

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/backend/laravel.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id laravel`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| laravel/framework | 13.30.1 | Framework — Eloquent, migrations, queues, validation, conteneur de services |
| laravel/sanctum | 4.3.3 | Authentification par jetons d'API (SPA + mobile). Plus simple que Passport tant qu'OAuth2 complet n'est pas requis |
| laravel/tinker | 3.0.2 | REPL applicatif (`artisan tinker`) |
| guzzlehttp/guzzle | 8.1.0 | Client HTTP — socle de `Http::` (le facade Laravel ne fonctionne pas sans) |
| spatie/laravel-query-builder | 7.3.4 | Filtres, tris et includes pilotes par la querystring, avec allowlist explicite — evite d'exposer Eloquent au client |
| dedoc/scramble | 0.13.42 | Schema OpenAPI 3 genere PAR INFERENCE depuis les FormRequest et les Resources, sans annotations a maintenir |
| laravel/pint | 1.30.5 | Formateur officiel (dev) |
| larastan/larastan | 3.11.0 | Analyse statique PHPStan avec la connaissance des magies Eloquent (dev) |
| phpstan/phpstan | 2.2.12 | Moteur d'analyse statique (dev) |
| pestphp/pest | 5.1.3 | Runner de tests (dev) — cf. qa/php-pest.md. C'est lui qui impose le plancher PHP 8.4 |
| pestphp/pest-plugin-laravel | 5.0.1 | Helpers Laravel pour Pest (dev) : get/post, assertDatabaseHas, actingAs |
| mockery/mockery | 1.6.15 | Mocking (dev) — utilise par les helpers de test Laravel |
| fakerphp/faker | 1.24.1 | Donnees de test (dev) — requis par les factories de modele |
| nunomaduro/collision | 8.9.5 | Rapport d'erreurs lisible en CLI et en test (dev) |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| rbac | spatie/laravel-permission | 8.3.0 | role, permission, habilitation, rbac, droits.*utilisateur |
| typed-dto | spatie/laravel-data | 4.23.0 | dto, objet.*typé, data.*object |
| media | spatie/laravel-medialibrary | 11.23.6 | upload.*fichier, media, piece.*jointe, image.*attachee |
| object-storage | league/flysystem-aws-s3-v3 | 3.35.3 | \bs3\b, stockage.*objet, disque.*distant |
| redis | predis/predis | 3.6.0 | redis, cache.*redis, queue.*redis |
| queues | laravel/horizon | 5.48.3 | queue, job.*asynchrone, worker, file.*attente, horizon |
| search | laravel/scout | 11.6.1 | recherche.*plein.*texte, full.*text, meilisearch, algolia, scout |
| oauth2 | laravel/passport (alt) | 13.8.0 | oauth2, authorization.*code, client.*credentials, passport |
| high-throughput | laravel/octane | 2.19.1 | octane, haut.*debit, swoole, roadrunner |
| sentry | sentry/sentry-laravel | 4.27.0 | sentry, error.*tracking, monitoring.*erreurs |
| dev-profiling | barryvdh/laravel-debugbar | 4.4.3 | debugbar, profiler.*requetes, n\+1 |
| dev-profiling | laravel/telescope (alt) | 5.23.0 | telescope, inspection.*requetes |
| docker-dev | laravel/sail | 1.67.0 | docker, sail, environnement.*conteneurise |
| phpunit-direct | phpunit/phpunit (alt) | 13.3.2 | phpunit, testcase.*classique |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Rôle | Pattern | Exemple |
|---|---|---|
| Modèle | `{Name}.php` → `class {Name}` (singulier) | `Invoice.php` |
| Controller | `{Name}Controller.php` (pluriel du domaine) | `InvoicesController.php` |
| FormRequest | `{Action}{Name}Request.php` | `StoreInvoiceRequest.php` |
| Resource | `{Name}Resource.php` | `InvoiceResource.php` |
| Service | `{Name}Service.php` | `InvoiceService.php` |
| Policy | `{Name}Policy.php` | `InvoicePolicy.php` |
| Job | `{Verb}{Name}Job.php` | `SendInvoiceJob.php` |
| Migration | `{ts}_{verb}_{table}_table.php` (**générée**) | `2026_09_02_000000_create_invoices_table.php` |
| Factory | `{Name}Factory.php` | `InvoiceFactory.php` |
| Test | `{Name}Test.php` | `InvoiceApiTest.php` |
| Table | `snake_case` pluriel | `invoices` |
| Colonne | `snake_case` | `issued_at` |

**Conventions** : classes en `StudlyCase` (PSR-4), méthodes en `camelCase`, tables et colonnes en `snake_case` — c'est ce qui permet aux conventions Eloquent de fonctionner sans configuration.

**Suffixes INTERDITS** :
- `Manager`, `Helper`, `Util`
- `Repository` — Eloquent est un Active Record ; ajouter une couche Repository par-dessus est un anti-pattern courant sur ce stack (double abstraction, perte des scopes)
- Nom de modèle au pluriel (`Invoices`) — casse la résolution automatique de table
- `Model` en suffixe (`InvoiceModel`)

---

## 3. Endpoints standard

| Endpoint | Rôle |
|---|---|
| `GET /api/health` | healthcheck |
| `POST /api/auth/login` | émission du jeton Sanctum |
| `POST /api/auth/logout` | révocation |
| `GET /api/user` | utilisateur courant (middleware `auth:sanctum`) |
| `GET /docs/api` | UI OpenAPI (Scramble) |

> **Laravel 11+ ne crée plus `routes/api.php` par défaut.** Il faut exécuter `php artisan install:api` (STEP 4). Sans lui, aucune route `/api/*` n'existe et le middleware Sanctum n'est pas enregistré — symptôme : 404 sur toutes les routes d'API alors que le code semble correct.

---

## 4. Versioning des API exposees

Préfixe `/api/v1/{domaine}` via un groupe de routes dans `routes/api.php`. Scramble génère un document par groupe. Cf. `rules/library-and-stack.md §6.bis` pour la synchronisation du contrat front↔back.

---

## 5. Interdits projet (laravel)

**Architecture** :
- Modèle Eloquent retourné directement par un controller — passer par une `Resource`
- `$request->validate()` dans un controller — utiliser un `FormRequest`
- Requête Eloquent construite dans un controller — la placer dans un Service ou un scope
- Relation lue sans `with()` — N+1
- `$guarded = []` sur un modèle — assignation de masse
- Tri ou filtre construit depuis un paramètre brut de querystring — passer par l'allowlist de `spatie/laravel-query-builder`
- Couche `Repository` par-dessus Eloquent (double abstraction, perte des scopes)
- Logique métier dans un `Observer` ou un événement de modèle — invisible à la lecture
- `env()` hors des fichiers `config/` — renvoie `null` après `config:cache`

**Code quality** :
- `@` (suppression d'erreur)
- Méthode de plus de 30 lignes
- `catch (\Exception $e) {}` silencieux
- `dd()`, `dump()`, `var_dump()` committés
- `TODO`, `FIXME`, code commenté
- Niveau PHPStan abaissé sous 6 pour faire passer l'analyse

**Sécurité** :
- `APP_DEBUG=true` en production
- `APP_KEY` committé ou absent
- `'allowed_origins' => ['*']` avec `supports_credentials: true` dans `config/cors.php`
- Routes d'authentification sans `throttle`
- Requête SQL brute avec interpolation de variable — utiliser les bindings
- `storage/` ou `.env` accessibles depuis la racine web
- Hachage de mot de passe maison

**Base de données** :
- `artisan migrate` exécuté par un agent sur une base **existante** (§1.5)
- `artisan migrate:fresh` / `migrate:refresh` — **destructifs**, interdits hors base neuve
- Migration éditée après application

**Build / packaging** :
- Committer `vendor/`, `.env`, `storage/logs/`
- `composer.lock` absent du dépôt (une **application** verrouille ses versions)
- Livrer Sanctum **et** Passport (§2.3)
- `composer update` en production — utiliser `composer install --no-dev --optimize-autoloader`

---

## 6. Persistance — voir §1.5

Eloquent + migrations. Phase B (DB) d'`arch` : **applicable** — introspection en lecture seule ; scaffolding de modèles pour une base neuve uniquement.

---

## 7. Temps reel

- **WebSockets** : Laravel Reverb — **non catalogué**, à instruire avant engagement
- **SSE** : `response()->stream()` avec les en-têtes `text/event-stream`
- **Files d'attente** : capability `queues` (Horizon + Redis)
- **Planificateur** : `artisan schedule:run` — natif, aucune dépendance

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **CRUD métier et SaaS** — le framework couvre nativement queues, mail, cache, planification, stockage
- **Équipes PHP** — de loin le framework le plus outillé de l'écosystème
- **Time-to-market court** — les générateurs `artisan` réduisent fortement le code d'amorçage
- **Hébergement mutualisé ou VPS classique** — PHP-FPM se déploie partout, sans runtime à installer

**NE PAS choisir si** :
- ❌ **Charge concurrente forte avec état en mémoire** — PHP repart d'un processus vierge à chaque requête. La capability `high-throughput` (Octane) y répond, mais change le modèle d'exécution et impose une revue du code.
- ❌ **Calcul intensif ou traitement de flux** — préférer `backend/kotlin-spring-boot` ou `backend/dotnet-minimalapi`
- ❌ **Typage statique fort exigé** — le typage PHP progresse, mais Larastan reste une analyse externe, pas un compilateur
- ❌ **Équipe .NET / Java / Node / Python** — préférer le stack de leur langage
- ❌ **PHP < 8.4 imposé par l'hébergement** — le stack est alors inutilisable en l'état (§2.3)
- ❌ **Contrat GraphQL principal** — Lighthouse n'est pas catalogué ici

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `backend-laravel` + `react` + `shadcn` + `auth-local` + `postgres` | 🟡 experimental | jamais validé end-to-end |
| `backend-laravel` + `vue` + `vuetify` + `auth-local` + `mysql` | 🟡 experimental | combinaison la plus courante de l'écosystème PHP |
| `backend-laravel` + `mobiles/react-native` + `auth-local` | 🟡 experimental | Sanctum prend en charge les jetons mobiles |
| `backend-laravel` + `qa/php-pest` | 🟡 experimental | stack QA dédié créé au même audit |

---

## 10. Notes pour l'agent `arch`

1. **Détecter** `backend/laravel.md` en `## Active Tech Specs` → backend API, un frontend séparé est attendu
2. **STEP 0 — gate runtime bloquant** : `php -v` doit rapporter **≥ 8.4.1**. En dessous, STOP `[INFRA_BLOCKED]` — le plancher vient de Pest et PHPUnit, pas du framework (§2.3). Ne pas rétrograder Pest pour contourner : c'est le runner de `qa/php-pest`
3. **Créer** `workspace/src/{BackendName}/` via `composer create-project` (§2.2.1)
4. **`php artisan install:api` est OBLIGATOIRE** (STEP 4) — Laravel 11+ ne crée plus `routes/api.php`. Sans lui : 404 sur toutes les routes d'API, sans erreur explicite
5. **`php artisan key:generate`** au bootstrap — sans `APP_KEY`, toute session ou cookie chiffré échoue
6. **Propager** `APP_KEY`, `DB_*`, `SANCTUM_STATEFUL_DOMAINS`, `CORS_ALLOWED_ORIGINS` depuis `stack.md` vers `.env`
7. **CORS** : renseigner `config/cors.php` avec l'origine du frontend déclaré, comme au STEP 4.5.6 des autres stacks
8. **Phase B (DB)** : applicable, **lecture seule** sur une base existante. `migrate:fresh` est destructif — jamais exécuté par un agent
9. **Pas de bloc `dbDrivers`** dans ce catalog : les pilotes de base sont des **extensions PHP** (`pdo_pgsql`…), pas des paquets Composer (§1.5). Vérifier leur présence via `php -m` plutôt que de tenter une installation
10. **Phase C (ADRs)** : créer `ADR-{ts}-stack-backend-laravel.md` documentant Laravel 13, Sanctum plutôt que Passport, le plancher PHP 8.4.1 et sa cause

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

- `dev-backend` matérialise `app/`, `routes/api.php`, `database/migrations/`
- `dev-frontend` **ne touche pas** au projet Laravel

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `workspace/src/{BackendName}/app/**` | `dev-backend` |
| `workspace/src/{BackendName}/routes/**` | `dev-backend` |
| `workspace/src/{BackendName}/database/migrations/**` | `dev-backend` (via `make:migration`, jamais éditées après application) |
| `workspace/src/{BackendName}/database/factories/**` | `dev-backend` (utilisées par `qa`) |
| `workspace/src/{BackendName}/config/**` | `arch` (create) + `dev-backend` (ajout de clés) |
| `workspace/src/{BackendName}/composer.json` | `arch` (create) + `dev-backend` (deps on-demand) |
| `workspace/src/{BackendName}/phpstan.neon`, `pint.json` | `arch` exclusif |
| `workspace/src/{BackendName}/tests/**` | `qa` |

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{BackendName}

# Plancher runtime (cf. 2.3) — impose par Pest 5 / PHPUnit 13, pas par Laravel
php -r 'exit(version_compare(PHP_VERSION, "8.4.1", ">=") ? 0 : 1);'

composer install --no-interaction --quiet

test -f artisan
test -f routes/api.php          # cree par `artisan install:api`, PAS par le template
test -f phpstan.neon
grep -q "APP_KEY=base64:" .env  # cle generee

php artisan about
php artisan config:clear
./vendor/bin/pint --test
./vendor/bin/phpstan analyse --no-progress
php artisan test

echo "smoke OK"
```
