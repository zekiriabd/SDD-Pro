# Tech FEAT: laravel-blade (fullstack)

> §2.4 (Librairies) regeneree depuis `laravel-blade.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id laravel-blade`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits et validés le 2026-09-02, chaque paquet résolu contre Packagist et npm avec sa contrainte `require.php`. **Jamais exécuté end-to-end via `/sdd-full`** : aucun `composer install`, `npm run build` ni `artisan test` n'a tourné en CI. Non supporté commercialement en l'état.
Tech FEAT ID: tech-laravel-blade
Scope: **fullstack monolithe SSR** — application **Laravel 13 + Blade + Livewire 4** dans UN seul projet `{AppName}/`. Blade rend le HTML côté serveur ; Livewire apporte l'interactivité **sans écrire de JavaScript** — l'état du composant vit en PHP. Pas de séparation `{BackendName}` / `{AppName}` / `{LibName}`.

> **Laravel API ≠ ce stack.** Ici Laravel rend du HTML. Pour une API JSON consommée par un frontend séparé, déclarer `backend/laravel.md`. Les deux ne se déclarent **jamais ensemble**.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Monolithe SSR** : le serveur renvoie du HTML complet, Livewire remplace des fragments à la demande.

- **Laravel 13** — Eloquent, migrations, routing web, sessions, validation
- **Blade** — templates serveur avec composants (`<x-…>`) et layouts
- **Livewire 4** — composants dont l'état vit **en PHP** : une interaction déclenche un aller-retour serveur qui renvoie du HTML partiel. Pas de client à écrire.
- **Alpine.js** — micro-interactions purement locales (menu, modale), sans aller-retour
- **Vite + Tailwind** — pipeline d'assets (CSS et le peu de JS nécessaire)

Architecture cible :

```
{AppName}/
├── app/
│   ├── Models/
│   ├── Livewire/                  ── composants Livewire (etat en PHP)
│   │   └── {Domaine}/{Name}.php
│   ├── Http/
│   │   ├── Controllers/           ── controllers rendant une vue
│   │   ├── Requests/              ── FormRequest
│   │   └── Middleware/
│   ├── Services/                  ── logique metier
│   ├── Policies/
│   └── View/Components/           ── composants Blade a classe
├── resources/
│   ├── views/
│   │   ├── layouts/app.blade.php  ── layout racine
│   │   ├── components/            ── composants Blade anonymes
│   │   ├── livewire/              ── vues des composants Livewire
│   │   └── {domaine}/
│   ├── css/app.css                ── Tailwind
│   └── js/app.js                  ── Alpine + bootstrap
├── routes/web.php                 ── routes SSR (PAS api.php)
├── database/{migrations,factories,seeders}/
├── tests/{Feature,Unit}/
├── vite.config.js
├── composer.json                  ── PHP
└── package.json                   ── assets
```

**Différence vs les autres stacks `fullstack/`** :
- vs `next` / `nuxt` : **aucune hydratation d'un arbre de composants client**. Livewire renvoie du HTML, pas du JSON à réconcilier. Le coût est un aller-retour réseau par interaction ; le gain est qu'il n'y a pas deux modèles de données à tenir synchronisés.
- vs `aspnet-mvc-razor` / `kotlin-mustache` : même famille (SSR classique), mais Livewire va plus loin que Razor/Mustache — il gère l'état entre deux requêtes.
- vs `blazor-server` : concept proche (état serveur, diff envoyé au client), mais Livewire fonctionne en **requêtes HTTP**, pas en WebSocket persistant. Pas de connexion à maintenir, donc pas de reprise sur coupure à gérer.

---

## 1.2 Couches

- **Routes** (`routes/web.php`) : SSR uniquement, avec middleware de session et CSRF.
- **Controllers** (`Http/Controllers/`) : reçoivent un `FormRequest`, appellent un Service, retournent une **vue**.
- **Composants Livewire** (`Livewire/`) : état + actions d'un fragment interactif. Ce sont eux qui portent l'interactivité.
- **Composants Blade** (`View/Components/` + `resources/views/components/`) : présentation réutilisable, **sans état**.
- **Services** (`Services/`) : logique métier — appelée aussi bien par un controller que par un composant Livewire.
- **Policies** : autorisation par modèle.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas.** Arch lève WARNING `[STACK_MALFORMED]` si `LibStrategy` déclare un mode `monorepo`.

| Layer | Path |
|---|---|
| Routes SSR | `routes/web.php` |
| Controller | `app/Http/Controllers/{Name}Controller.php` |
| FormRequest | `app/Http/Requests/{Action}{Name}Request.php` |
| Composant Livewire | `app/Livewire/{Domaine}/{Name}.php` |
| Vue du composant Livewire | `resources/views/livewire/{domaine}/{name}.blade.php` |
| Composant Blade à classe | `app/View/Components/{Name}.php` + `resources/views/components/{name}.blade.php` |
| Composant Blade anonyme | `resources/views/components/{name}.blade.php` |
| Layout | `resources/views/layouts/app.blade.php` |
| Vue de page | `resources/views/{domaine}/{action}.blade.php` |
| Service | `app/Services/{Name}Service.php` |
| Modèle | `app/Models/{Name}.php` |
| Policy | `app/Policies/{Name}Policy.php` |
| Migration | `database/migrations/{ts}_{desc}.php` (**générée**) |
| Factory | `database/factories/{Name}Factory.php` |
| CSS / JS | `resources/css/app.css`, `resources/js/app.js` |
| Config Vite | `vite.config.js` |
| Test | `tests/Feature/{Name}Test.php` |

---

## 1.4 Principes non negociables

**Architecture** :
- **Aucune requête Eloquent dans un template Blade.** Un `{{ $user->orders->count() }}` dans une boucle produit un N+1 invisible : le template est le pire endroit pour le découvrir.
- **`with()` sur toute relation lue** par la vue — le profiler (capability `dev-profiling`) est le moyen de le vérifier.
- **La logique métier va dans `Services/`**, appelée par le controller **et** par le composant Livewire. Dupliquer la règle dans les deux est le piège de ce stack.
- **Un composant Livewire est un fragment, pas une page** : préférer plusieurs petits composants à un composant qui pilote tout l'écran. Chaque propriété publique est sérialisée à chaque aller-retour.
- **`wire:model.live` avec parcimonie** : il déclenche une requête à **chaque frappe**. Utiliser `wire:model.blur` ou `.live.debounce.300ms` par défaut.
- **Alpine pour le purement local** (ouvrir/fermer, onglet actif) ; Livewire dès que le serveur doit savoir.
- **`@csrf` sur tout formulaire** non-Livewire (Livewire le gère seul).
- **`$fillable` explicite** sur chaque modèle.
- **Pagination systématique** sur les listes — `paginate()`, jamais `all()` dans une vue.

**Sécurité** :
- **`{{ }}` et non `{!! !!}`** — `{{ }}` échappe le HTML. `{!! !!}` est une injection XSS sauf si le contenu est prouvé sûr (Markdown déjà assaini)
- **`APP_DEBUG=false` en production** — la page d'erreur Laravel expose la configuration
- **`APP_KEY` généré et secret** — clé de chiffrement des sessions
- **Propriétés Livewire : ce qui est public est modifiable par le client.** Une propriété publique arrive du navigateur à chaque requête : ne jamais y stocker un prix, un rôle ou un identifiant de propriétaire sans revalidation serveur. C'est la faille la plus spécifique à ce stack.
- **`#[Locked]`** sur une propriété publique qui ne doit pas changer côté client
- **Autorisation revérifiée dans l'action Livewire** — le rendu conditionnel d'un bouton n'est pas un contrôle d'accès
- **Rate limiting** sur les routes d'authentification
- **`config()` et non `env()`** hors des fichiers `config/` (renvoie `null` après `config:cache`)

---

## 1.5 Base de donnees

Identique à `backend/laravel.md §1.5` : les pilotes sont des **extensions PHP**
(`pdo_pgsql`, `pdo_mysql`…), pas des paquets Composer — d'où l'absence de bloc
`dbDrivers` dans ce catalog.

| DatabaseType | Support |
|---|---|
| `postgres` / `postgresql` | natif |
| `mysql` / `mariadb` | natif |
| `sqlite` | natif (dev / tests) |
| `sqlserver` | natif (pilote système requis) |

> ⚠️ **Soumis à `rules/library-and-stack.md` Partie C.** Sur une base **existante**,
> un agent n'exécute **jamais** `artisan migrate`. `migrate:fresh` et
> `migrate:refresh` sont **destructifs** — interdits hors base neuve.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `fullstack-laravel-blade`
- **AppType** : `fullstack` (rendu SSR, projet unique)
- **Langage** : PHP **8.4** (plancher `8.4.1`, cf. §2.3) + un peu de JavaScript (Alpine)
- **Framework** : Laravel 13.30.1 + Blade + Livewire 4.4.3
- **Pipeline d'assets** : Vite 8 + Tailwind 4
- **Package managers** : `composer` (PHP) **et** `npm` (assets) — cf. §2.3
- **Serveur** : PHP-FPM + nginx

---

## 2.2 Outils

- **Project files** : `workspace/src/{AppName}/composer.json` **et** `package.json`
- **Run dev** : deux processus — `php artisan serve` **et** `npm run dev` (Vite en watch)
- **Build assets** : `npm run build`
- **Migrations** : `php artisan migrate`
- **Générateurs** : `php artisan make:{model,controller,request,policy}` / `php artisan make:livewire {Domaine}/{Name}`
- **Tests** : `php artisan test`
- **Format** : `./vendor/bin/pint`
- **Analyse statique** : `./vendor/bin/phpstan analyse`
- **Cache de production** : `php artisan config:cache route:cache view:cache`
- **Smoke Command** :

```bash
(cd workspace/src/{AppName} && composer install --no-interaction --quiet && npm install --silent && npm run build && php artisan about)
test -f workspace/src/{AppName}/resources/views/layouts/app.blade.php
test -d workspace/src/{AppName}/public/build
```

- **Smoke Timeout** : 300s (`composer install` + `npm install` + build Vite)

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/artisan" ]; then

# STEP 0 — Gate runtime (plancher impose par l'outillage de test, cf. 2.3)
php -r 'exit(version_compare(PHP_VERSION, "8.4.1", ">=") ? 0 : 1);' || {
  echo "ERROR: arch {AppName} — runtime PHP insuffisant"
  echo "CAUSE: [INFRA_BLOCKED] PHP $(php -r 'echo PHP_VERSION;') < 8.4.1 requis par pest 5 + phpunit 13"
  exit 3
}

# STEP 1 — Scaffold Laravel
composer create-project laravel/laravel workspace/src/{AppName} "13.*" \
  --no-interaction --prefer-dist
cd workspace/src/{AppName}

# STEP 2 — Livewire (le coeur interactif de ce stack)
composer require --no-interaction livewire/livewire:4.4.3

# STEP 3 — Outillage de developpement
composer require --dev --no-interaction \
  pestphp/pest:5.1.3 \
  pestphp/pest-plugin-laravel:5.0.1 \
  larastan/larastan:3.11.0 \
  laravel/pint:1.30.5

# STEP 4 — Assets : Vite + Tailwind 4 + Alpine (cf. metadata.npmAssets)
npm install --save-dev \
  vite@8.2.2 \
  laravel-vite-plugin@3.2.0 \
  tailwindcss@4.3.3 \
  @tailwindcss/vite@4.3.3
npm install alpinejs@3.17.1 axios@1.20.0

# Tailwind 4 se configure DANS le CSS (plus de tailwind.config.js par defaut)
cat > resources/css/app.css <<'CSS'
@import "tailwindcss";
CSS

cat > vite.config.js <<'JS'
import { defineConfig } from 'vite';
import laravel from 'laravel-vite-plugin';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [
    laravel({ input: ['resources/css/app.css', 'resources/js/app.js'], refresh: true }),
    tailwindcss(),
  ],
});
JS

# STEP 5 — Arborescence
mkdir -p \
  app/Livewire \
  app/Services \
  app/Policies \
  app/View/Components \
  resources/views/{layouts,components,livewire} \
  tests/Feature tests/Unit

# STEP 6 — Layout racine (@vite injecte les assets construits)
cat > resources/views/layouts/app.blade.php <<'BLADE'
<!DOCTYPE html>
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ $title ?? config('app.name') }}</title>
    @vite(['resources/css/app.css', 'resources/js/app.js'])
</head>
<body class="antialiased">
    {{ $slot }}
</body>
</html>
BLADE

# STEP 7 — phpstan.neon
cat > phpstan.neon <<'NEON'
includes:
    - vendor/larastan/larastan/extension.neon
parameters:
    paths:
        - app
    level: 6
NEON

# STEP 8 — Cle + build + gate
php artisan key:generate
npm run build
php artisan about

fi
```

**Contrat post-init** :
- `artisan about` sort 0
- `resources/views/layouts/app.blade.php` existe et contient `@vite(...)`
- `public/build/` existe après `npm run build`
- `APP_KEY` est généré
- Livewire est installé (`composer.json` contient `livewire/livewire`)

---

## 2.3 Deux gestionnaires de paquets, un seul `buildSystem`

Ce stack a **deux** manifestes de dépendances :

| Manifeste | Gestionnaire | Contenu |
|---|---|---|
| `composer.json` | `composer` | Laravel, Livewire, outillage PHP |
| `package.json` | `npm` | Vite, Tailwind, Alpine |

Le schéma `libs-catalog.schema.json` n'admet **qu'un** `buildSystem` par
catalog. Il est déclaré à `composer` (les dépendances load-bearing sont PHP),
et les paquets npm vivent dans **`metadata.npmAssets`** — hors `core[]` et
`onDemand[]`, donc **non vérifiés** par `validate_libs_catalog.py`. C'est une
limite connue du schéma, pas un oubli : leur mise à jour est manuelle, et le
STEP 4 de §2.2.1 les installe explicitement.

> **Tailwind 4 ne se configure plus dans `tailwind.config.js`** mais dans le
> CSS (`@import "tailwindcss"`). Un `tailwind.config.js` généré par un ancien
> réflexe est ignoré silencieusement — les classes utilitaires ne sont alors
> pas générées, sans erreur.

### Plancher PHP — même cause que `backend/laravel`

| Paquet | `require.php` |
|---|---|
| `laravel/framework` 13.30.1 | `^8.3` |
| `livewire/livewire` 4.4.3 | `^8.1` |
| **`pestphp/pest` 5.1.3** | **`^8.4`** |
| **`phpunit/phpunit` 13.3.2** | **`>=8.4.1`** |

Le plancher est **8.4.1**, imposé par l'outillage de test et non par le
framework — détail et modèle de support PHP dans `backend/laravel.md §2.3`.

### Livewire ou API+SPA, jamais les deux

Ce stack et `backend/laravel` sont **mutuellement exclusifs** en
`## Active Tech Specs`. Déclarer les deux produirait deux projets Laravel
concurrents. Le choix se fait sur le mode de rendu :

| Besoin | Stack |
|---|---|
| HTML rendu serveur, interactivité modérée | **ce stack** |
| API JSON + frontend React/Vue/Angular séparé | `backend/laravel` |
| API JSON + application mobile | `backend/laravel` |

### Ce qui n'a PAS été validé

| Vérifié | Non vérifié |
|---|---|
| Existence + dernière version stable de chaque paquet (Packagist + npm, 2026-09-02) | `composer install`, `npm run build` |
| Contrainte `require.php` de chaque paquet PHP | `artisan test` |
| Cohérence `.md` ↔ `.libs.json` | Rendu Livewire réel |
| — | Pipeline `/sdd-full` complet |

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/fullstack/laravel-blade.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id laravel-blade`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| laravel/framework | 13.30.1 | Framework — Eloquent, migrations, routing web, sessions, validation |
| livewire/livewire | 4.4.3 | Composants interactifs rendus SERVEUR. C'est ce qui distingue ce stack d'un Laravel API : pas de SPA, pas de build JS pour la logique — l'etat vit en PHP |
| laravel/tinker | 3.0.2 | REPL applicatif |
| laravel/prompts | 0.3.24 | Invites CLI des commandes artisan generees |
| laravel/pint | 1.30.5 | Formateur officiel (dev) |
| larastan/larastan | 3.11.0 | Analyse statique avec connaissance d'Eloquent (dev) |
| phpstan/phpstan | 2.2.12 | Moteur d'analyse statique (dev) |
| pestphp/pest | 5.1.3 | Runner de tests (dev) — cf. qa/php-pest.md. Impose le plancher PHP 8.4 |
| pestphp/pest-plugin-laravel | 5.0.1 | Helpers Laravel pour Pest (dev) |
| mockery/mockery | 1.6.15 | Mocking (dev) |
| fakerphp/faker | 1.24.1 | Donnees de test (dev) — requis par les factories |
| nunomaduro/collision | 8.9.5 | Rapport d'erreurs lisible en CLI (dev) |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| auth-scaffold | laravel/breeze | 2.4.2 | login, inscription, authentification, mot.*de.*passe.*oublie, breeze |
| api-tokens | laravel/sanctum | 4.3.3 | api.*token, endpoint.*json, sanctum |
| rbac | spatie/laravel-permission | 8.3.0 | role, permission, habilitation, rbac |
| media | spatie/laravel-medialibrary | 11.23.6 | upload.*fichier, media, piece.*jointe, galerie |
| markdown | league/commonmark | 2.10.0 | markdown, contenu.*riche, commonmark |
| search | laravel/scout | 11.6.1 | recherche.*plein.*texte, full.*text, scout |
| queues | laravel/horizon | 5.48.3 | queue, job.*asynchrone, worker, horizon |
| redis | predis/predis | 3.6.0 | redis, cache.*redis, queue.*redis |
| object-storage | league/flysystem-aws-s3-v3 | 3.35.3 | \bs3\b, stockage.*objet |
| sentry | sentry/sentry-laravel | 4.27.0 | sentry, error.*tracking, monitoring.*erreurs |
| dev-profiling | barryvdh/laravel-debugbar | 4.4.3 | debugbar, profiler.*requetes, n\+1 |
| dev-profiling | laravel/telescope (alt) | 5.23.0 | telescope |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Rôle | Pattern | Exemple |
|---|---|---|
| Composant Livewire | `app/Livewire/{Domaine}/{Name}.php` → `class {Name} extends Component` | `app/Livewire/Invoices/InvoiceTable.php` |
| Vue Livewire | `resources/views/livewire/{domaine}/{name}.blade.php` (kebab-case) | `livewire/invoices/invoice-table.blade.php` |
| Composant Blade | `resources/views/components/{name}.blade.php` → `<x-{name} />` | `components/badge.blade.php` → `<x-badge />` |
| Composant Blade à classe | `app/View/Components/{Name}.php` | `app/View/Components/Alert.php` |
| Layout | `resources/views/layouts/{name}.blade.php` | `layouts/app.blade.php` |
| Vue de page | `resources/views/{domaine}/{action}.blade.php` | `views/invoices/index.blade.php` |
| Controller | `{Name}Controller.php` | `InvoicesController.php` |
| Service | `{Name}Service.php` | `InvoiceService.php` |
| Modèle | `{Name}.php` (singulier) | `Invoice.php` |
| Test | `{Name}Test.php` | `InvoiceTableTest.php` |

**Conventions** : classes en `StudlyCase` (PSR-4), fichiers Blade en `kebab-case` (c'est ce que résout `<x-…>`), tables et colonnes en `snake_case`.

**Suffixes INTERDITS** :
- `Manager`, `Helper`, `Util`
- `Repository` par-dessus Eloquent (double abstraction)
- `Component` en suffixe de classe Livewire (`InvoiceTableComponent`) — redondant
- Vue Blade en `PascalCase` — `<x-…>` ne la résoudra pas

---

## 3. Routes standard

| Route | Rôle |
|---|---|
| `GET /` | page d'accueil |
| `GET /login` · `POST /login` | authentification (capability `auth-scaffold`) |
| `POST /logout` | déconnexion |
| `GET /dashboard` | espace authentifié (middleware `auth`) |
| `GET /health` | healthcheck |

Tout vit dans `routes/web.php` avec les middleware de **session** et **CSRF**.
Ce stack ne crée **pas** `routes/api.php` (`artisan install:api` n'est pas
exécuté) — c'est précisément ce qui le distingue de `backend/laravel`.

---

## 4. Versioning

Un monolithe SSR n'expose pas de contrat d'API versionné : le HTML est
regénéré à chaque déploiement, client et serveur avancent ensemble. C'est
l'avantage structurel de ce stack — **il n'y a pas de drift de contrat
front↔back possible** (`rules/library-and-stack.md §6.bis` est sans objet ici).

Si la capability `api-tokens` est activée pour quelques endpoints annexes,
ceux-là se versionnent (`/api/v1/…`) et retombent sous le §6.bis.

---

## 5. Interdits projet (laravel-blade)

**Architecture** :
- Requête Eloquent dans un template Blade — N+1 invisible
- Relation lue par la vue sans `with()`
- `all()` sur une liste affichée — utiliser `paginate()`
- Logique métier dans un composant Livewire **et** dans un controller (duplication) — la placer dans `Services/`
- Composant Livewire pilotant tout un écran — découper
- `wire:model.live` sur un champ texte sans debounce — une requête par frappe
- Alpine utilisé là où le serveur doit connaître l'état (et inversement)
- Couche `Repository` par-dessus Eloquent
- `env()` hors des fichiers `config/`
- `routes/api.php` créé dans ce stack — c'est le signe qu'il fallait `backend/laravel`

**Sécurité** :
- **`{!! !!}` sur du contenu non assaini** — injection XSS
- **Propriété Livewire publique portant une donnée sensible** (prix, rôle, `owner_id`) sans `#[Locked]` ni revalidation serveur — le client la modifie à chaque requête
- Autorisation reposant sur le rendu conditionnel d'un bouton — revérifier dans l'action
- `@csrf` absent d'un formulaire non-Livewire
- `APP_DEBUG=true` en production
- `APP_KEY` committé ou absent
- `$guarded = []` sur un modèle
- Routes d'authentification sans `throttle`
- `debugbar` ou `telescope` actif en production
- `storage/` ou `.env` accessibles depuis la racine web

**Code quality** :
- Template Blade de plus de 100 lignes — extraire des composants
- Logique conditionnelle profonde dans un template — la remonter dans le composant
- `dd()`, `dump()` committés
- Méthode de plus de 30 lignes
- `TODO`, `FIXME`, code commenté

**Build / packaging** :
- Committer `vendor/`, `node_modules/`, `public/build/`, `.env`
- `composer.lock` ou `package-lock.json` absents (une **application** verrouille ses versions)
- `tailwind.config.js` créé pour Tailwind 4 — la configuration est dans le CSS (§2.3)
- Assets non construits avant déploiement (`@vite` échoue sans `public/build/`)
- `artisan migrate:fresh` sur une base non neuve

---

## 6. Persistance — voir §1.5

Eloquent + migrations. Phase B (DB) d'`arch` : **applicable** — introspection en lecture seule ; scaffolding de modèles pour une base neuve uniquement.

---

## 7. Temps reel

- **Livewire `wire:poll`** — rafraîchissement périodique d'un fragment, sans dépendance. Le plus simple, et souvent suffisant.
- **Laravel Reverb** (WebSockets) — **non catalogué**, à instruire avant engagement
- **Files d'attente** : capability `queues` (Horizon + Redis)

> Contrairement à `blazor-server`, Livewire ne maintient **pas** de connexion persistante : chaque interaction est une requête HTTP. Pas de reprise sur coupure à gérer, mais pas de push serveur non plus.

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **Applications métier internes** (back-office, gestion, CRUD riche) où l'interactivité est modérée
- **Équipes PHP sans compétence front avancée** — Livewire évite d'écrire du JavaScript
- **Time-to-market court** — un seul projet, un seul déploiement, un seul modèle de données
- **SEO** — le HTML est rendu serveur par construction

**NE PAS choisir si** :
- ❌ **Interface très interactive** (glisser-déposer, édition temps réel, canvas) — chaque interaction Livewire est un aller-retour réseau. C'est la limite structurelle du stack.
- ❌ **Application mobile prévue** — il faudra une API de toute façon : partir sur `backend/laravel` + un stack `mobiles/*`
- ❌ **Latence réseau élevée** (utilisateurs distants, réseau mobile) — l'aller-retour par interaction devient perceptible
- ❌ **Équipe front React/Vue déjà en place** — préférer `backend/laravel` + `frontend/*`
- ❌ **Besoin de fonctionner hors ligne** — impossible, l'état vit au serveur
- ❌ **Très forte charge concurrente** — chaque interaction consomme un worker PHP, là où une SPA n'appellerait le serveur qu'aux mutations

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `fullstack-laravel-blade` + `qa/php-pest` + `postgres` | 🟡 experimental | jamais validé end-to-end |
| `fullstack-laravel-blade` + `qa/php-pest` + `mysql` | 🟡 experimental | combinaison la plus courante de l'écosystème PHP |
| `fullstack-laravel-blade` + capability `auth-scaffold` (Breeze) | 🟡 experimental | vues d'authentification générées en Blade |

> **Incompatible** avec tout stack `frontend/*` et avec `backend/laravel` — cf. §2.3 et §10.

---

## 10. Notes pour l'agent `arch`

1. **Détecter** `fullstack/laravel-blade.md` en `## Active Tech Specs` → `AppType=fullstack`, projet unique, **aucun** frontend séparé attendu
2. **Refuser la cohabitation** : si `backend/laravel.md` **ou** un stack `frontend/*` est aussi déclaré → WARNING bloquant `[STACK_INCOMPAT]` (§2.3)
3. **STEP 0 — gate runtime bloquant** : `php -v` ≥ **8.4.1** (plancher imposé par Pest/PHPUnit, pas par Laravel)
4. **Deux installations** : `composer install` **et** `npm install`. Le STEP 4 de §2.2.1 pose les paquets npm depuis `metadata.npmAssets` — ils ne sont pas dans `core[]` (§2.3)
5. **`npm run build` fait partie du bootstrap** — `@vite(...)` échoue si `public/build/` n'existe pas, avec une erreur qui ne mentionne pas le build
6. **Pas de `tailwind.config.js`** : Tailwind 4 se configure dans `resources/css/app.css` (§2.3)
7. **Ne PAS exécuter `artisan install:api`** — ce stack n'expose pas de `routes/api.php` (§3)
8. **`php artisan key:generate`** au bootstrap
9. **Propager** `APP_KEY`, `DB_*`, `APP_URL` depuis `stack.md` vers `.env`
10. **CORS** : sans objet — le HTML est servi depuis la même origine. Ne pas configurer `config/cors.php` (contrairement à `backend/laravel`)
11. **Phase B (DB)** : applicable, **lecture seule** sur base existante
12. **Phase C (ADRs)** : créer `ADR-{ts}-stack-fullstack-laravel-blade.md` documentant Laravel 13 + Blade + Livewire 4, le choix SSR plutôt qu'API+SPA, le plancher PHP et la double chaîne composer/npm

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Stack monolithe** : il n'y a **pas** de séparation back/front. Convention
(alignée sur les autres stacks `fullstack/`, cf. `ownership.md §1.bis`) :

- **`dev-backend`** matérialise `app/`, `routes/web.php`, `database/`
- **`dev-frontend`** matérialise `resources/views/`, `resources/css/`, `resources/js/`
- **Les composants Livewire sont co-owned** : la classe PHP (`app/Livewire/`) est du ressort de `dev-backend`, sa vue (`resources/views/livewire/`) de `dev-frontend`. C'est la frontière la plus délicate de ce stack — les deux fichiers évoluent ensemble.

**File ownership** :

| Path | Owner |
|---|---|
| `app/Models/**`, `app/Services/**`, `app/Policies/**` | `dev-backend` |
| `app/Http/**` | `dev-backend` |
| `app/Livewire/**` (classes) | `dev-backend` |
| `resources/views/livewire/**` (vues) | `dev-frontend` |
| `resources/views/**` (layouts, pages, composants) | `dev-frontend` |
| `resources/css/**`, `resources/js/**` | `dev-frontend` |
| `routes/web.php` | `dev-backend` |
| `database/migrations/**` | `dev-backend` (via `make:migration`) |
| `database/factories/**` | `dev-backend` (utilisées par `qa`) |
| `composer.json` | `arch` (create) + `dev-backend` (deps on-demand) |
| `package.json`, `vite.config.js` | `arch` exclusif |
| `phpstan.neon`, `pint.json` | `arch` exclusif |
| `tests/**` | `qa` |

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{AppName}

php -r 'exit(version_compare(PHP_VERSION, "8.4.1", ">=") ? 0 : 1);'

composer install --no-interaction --quiet
npm install --silent
npm run build

test -f artisan
test -f resources/views/layouts/app.blade.php
test -d public/build                       # sinon @vite echoue au rendu
test ! -f routes/api.php                   # ce stack est SSR, pas API (cf. 3)
test ! -f tailwind.config.js               # Tailwind 4 se configure dans le CSS (cf. 2.3)
grep -q "APP_KEY=base64:" .env
grep -q "livewire/livewire" composer.json
grep -q "@vite" resources/views/layouts/app.blade.php

php artisan about
./vendor/bin/pint --test
./vendor/bin/phpstan analyse --no-progress
php artisan test

echo "smoke OK"
```
