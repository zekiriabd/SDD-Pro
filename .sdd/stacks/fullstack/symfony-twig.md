# Tech FEAT: symfony-twig (fullstack)

> §2.4 (Librairies) regeneree depuis `symfony-twig.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id symfony-twig`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits et validés le 2026-09-02, chaque paquet résolu contre Packagist avec sa contrainte `require.php`. **Jamais exécuté end-to-end via `/sdd-full`** : aucun `composer install`, `bin/console` ni `pest` n'a tourné en CI. Non supporté commercialement en l'état.
Tech FEAT ID: tech-symfony-twig
Scope: **fullstack monolithe SSR** — application **Symfony 8.1 + Twig + Doctrine ORM 3** dans UN seul projet `{AppName}/`. Twig rend le HTML côté serveur ; Symfony UX (Stimulus + Turbo) apporte l'interactivité sans SPA. Pas de séparation `{BackendName}` / `{AppName}` / `{LibName}`.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Monolithe SSR Symfony** :

- **Symfony 8.1** — conteneur de services, routing par attributs, formulaires, sécurité
- **Twig** — moteur de templates avec héritage (`extends`/`block`) et composants
- **Doctrine ORM 3** — **Data Mapper** : l'entité est un objet PHP ordinaire, c'est l'`EntityManager` qui persiste
- **AssetMapper** — modules ES servis via `importmap`, **sans Node ni bundler**
- **Symfony UX** (Stimulus + Turbo) — interactivité progressive sur le HTML rendu

Architecture cible :

```
{AppName}/
├── src/
│   ├── Controller/                ── controllers (routing par attributs)
│   ├── Entity/                    ── entites Doctrine
│   ├── Repository/                ── requetes (fournis par Doctrine)
│   ├── Form/                      ── FormType
│   ├── Service/                   ── logique metier
│   ├── Security/                  ── authenticators, voters
│   ├── Twig/                      ── extensions et composants Twig
│   └── Kernel.php
├── templates/
│   ├── base.html.twig             ── layout racine
│   ├── components/
│   └── {domaine}/
├── config/
│   ├── packages/                  ── config par bundle (ecrite par Flex)
│   ├── routes.yaml
│   └── services.yaml
├── migrations/                    ── Doctrine Migrations
├── assets/
│   ├── app.js                     ── point d'entree AssetMapper
│   ├── controllers/               ── controllers Stimulus
│   └── styles/app.css
├── public/index.php
├── tests/
├── composer.json
└── symfony.lock                   ── etat des recipes Flex (A VERSIONNER)
```

**Différence vs `fullstack/laravel-blade`** :
- **Data Mapper vs Active Record** : `$em->persist($entity); $em->flush();` au lieu de `$model->save()`. L'entité n'a aucune dépendance au framework — elle est testable seule.
- **Configuration explicite** : Symfony privilégie la déclaration (YAML, attributs) là où Laravel privilégie la convention.
- **Pas de Node par défaut** : AssetMapper sert les modules ES directement, là où Laravel-Blade passe par Vite.
- **Turbo vs Livewire** : Turbo intercepte navigations et soumissions pour éviter le rechargement complet ; il ne maintient **pas** d'état serveur par composant comme Livewire.

---

## 1.2 Couches

- **Controller** (`src/Controller/`) : reçoit la requête, appelle un Service ou un Repository, retourne `$this->render(...)`. Aucune règle métier.
- **Entity** (`src/Entity/`) : état et invariants. PHP pur, mappé par attributs Doctrine.
- **Repository** (`src/Repository/`) : les requêtes. Toute requête non triviale y vit, jamais dans le controller.
- **Form** (`src/Form/`) : `FormType` — structure, contraintes et transformation du formulaire.
- **Service** (`src/Service/`) : logique métier, injectée par autowiring.
- **Security** (`src/Security/`) : authenticators et **voters** (l'autorisation).
- **Twig** (`src/Twig/`) : extensions et composants de présentation.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas.** Arch lève WARNING `[STACK_MALFORMED]` si `LibStrategy` déclare un mode `monorepo`.

| Layer | Path |
|---|---|
| Controller | `src/Controller/{Name}Controller.php` |
| Entité | `src/Entity/{Name}.php` |
| Repository | `src/Repository/{Name}Repository.php` |
| FormType | `src/Form/{Name}Type.php` |
| Service | `src/Service/{Name}Service.php` |
| Voter | `src/Security/Voter/{Name}Voter.php` |
| Extension Twig | `src/Twig/{Name}Extension.php` |
| Layout | `templates/base.html.twig` |
| Template de page | `templates/{domaine}/{action}.html.twig` |
| Composant Twig | `templates/components/{name}.html.twig` |
| Migration | `migrations/Version{ts}.php` (**générée**) |
| Controller Stimulus | `assets/controllers/{name}_controller.js` |
| Styles | `assets/styles/app.css` |
| Config de bundle | `config/packages/{bundle}.yaml` (**écrite par Flex**) |
| Test fonctionnel | `tests/Controller/{Name}ControllerTest.php` |
| Test unitaire | `tests/Service/{Name}ServiceTest.php` |

---

## 1.4 Principes non negociables

**Architecture** :
- **Aucune requête Doctrine dans un controller** — elle vit dans le Repository. Un controller de plus de 20 lignes signale une couche manquante.
- **`JOIN` / `addSelect` explicites** dans les Repository — Doctrine charge en **lazy** par défaut, et un `{% for %}` Twig qui traverse une relation déclenche un N+1 invisible depuis le template.
- **`$em->flush()` une seule fois** par requête, en fin d'opération — un `flush()` dans une boucle produit une transaction par itération.
- **Autorisation par voters** (`#[IsGranted]`), pas de `if ($user->getRoles()...)` disséminé.
- **Formulaires via `FormType`**, jamais construits à la main dans le controller — c'est ce qui apporte la protection CSRF et la validation.
- **Entités sans dépendance au framework** — c'est l'intérêt du Data Mapper : l'entité se teste sans conteneur ni base.
- **`symfony.lock` versionné** : il enregistre les recipes Flex appliquées. Sans lui, une réinstallation ne reproduit pas la configuration.
- **Autowiring par défaut** — déclarer un service à la main dans `services.yaml` seulement quand l'autowiring ne suffit pas.

**Sécurité** :
- **`{{ }}` échappe, `|raw` n'échappe pas** — `|raw` sur du contenu non assaini est une injection XSS
- **CSRF activé sur tout formulaire** (fourni par `symfony/security-csrf`, dans le CORE)
- **`APP_ENV=prod` et `APP_DEBUG=0`** en production — le profiler expose l'intégralité de la requête, des services et de la configuration
- **`web-profiler-bundle` et `debug-bundle` en `require-dev` uniquement** — jamais installés en production
- **`APP_SECRET` par l'environnement** (`stack.md`)
- **Voter vérifié côté serveur** — masquer un lien dans Twig n'est pas un contrôle d'accès
- **Requêtes DQL paramétrées** (`setParameter`), jamais de concaténation

---

## 1.5 Base de donnees

Doctrine ORM 3 + Doctrine Migrations. Les pilotes sont des **extensions PHP**
(`pdo_pgsql`, `pdo_mysql`…), pas des paquets Composer — d'où l'absence de bloc
`dbDrivers` (même situation que les stacks Laravel).

| DatabaseType | Support Doctrine |
|---|---|
| `postgres` / `postgresql` | natif (`pdo_pgsql`) — défaut recommandé |
| `mysql` / `mariadb` | natif (`pdo_mysql`) |
| `sqlite` | natif (`pdo_sqlite`) — dev / tests |
| `sqlserver` | natif (`pdo_sqlsrv`) |

Migrations : `bin/console make:migration` puis `doctrine:migrations:migrate`.

> ⚠️ **Soumis à `rules/library-and-stack.md` Partie C.** Sur une base **existante**,
> un agent n'exécute **jamais** `doctrine:migrations:migrate` : il écrit le DDL
> dans `workspace/db/migration-pending.sql` et émet
> `[DB_STRUCTURE_CHANGE_FORBIDDEN]`. **`doctrine:schema:update --force` est
> interdit en toutes circonstances** — c'est un auto-`ALTER` déduit du mapping,
> exactement ce que proscrit le §C.4.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `fullstack-symfony-twig`
- **AppType** : `fullstack` (rendu SSR, projet unique)
- **Langage** : PHP **8.4** (plancher `8.4.1`, cf. §2.3)
- **Framework** : Symfony 8.1.6 + Twig + Doctrine ORM 3.6.8
- **Assets** : AssetMapper (sans Node) — Webpack Encore en capability
- **Package manager** : `composer`
- **Serveur** : PHP-FPM + nginx, ou le Symfony CLI en développement

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/composer.json`
- **Run dev** : `symfony serve` (ou `php -S localhost:8000 -t public/`)
- **Générateurs** : `bin/console make:{entity,controller,form,voter,migration}`
- **Migrations** : `bin/console doctrine:migrations:migrate`
- **Vider le cache** : `bin/console cache:clear`
- **Assets** : `bin/console importmap:install` / `asset-map:compile` (production)
- **Debug** : `bin/console debug:router`, `debug:container`, `debug:autowiring`
- **Tests** : `./vendor/bin/pest` (ou `bin/phpunit`)
- **Format** : `./vendor/bin/php-cs-fixer fix`
- **Analyse statique** : `./vendor/bin/phpstan analyse`
- **Gate de sécurité** : `composer audit`
- **Smoke Command** :

```bash
(cd workspace/src/{AppName} && composer install --no-interaction --quiet && php bin/console cache:clear && php bin/console about)
test -f workspace/src/{AppName}/templates/base.html.twig
test -f workspace/src/{AppName}/symfony.lock
```

- **Smoke Timeout** : 240s (`composer install` + warmup du conteneur)

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/bin/console" ]; then

# STEP 0 — Gate runtime : ici c'est le FRAMEWORK qui exige 8.4.1 (cf. 2.3)
php -r 'exit(version_compare(PHP_VERSION, "8.4.1", ">=") ? 0 : 1);' || {
  echo "ERROR: arch {AppName} — runtime PHP insuffisant"
  echo "CAUSE: [INFRA_BLOCKED] PHP $(php -r 'echo PHP_VERSION;') < 8.4.1 requis par symfony/* 8.1"
  exit 3
}

# STEP 1 — Scaffold Symfony (skeleton `webapp` = Twig + Doctrine + formulaires + securite)
composer create-project symfony/skeleton workspace/src/{AppName} "8.1.*" \
  --no-interaction
cd workspace/src/{AppName}

# `composer require webapp` declenche les recipes Flex qui ecrivent config/packages/*.
# C'est Flex qui produit la configuration : sans lui, les bundles sont installes
# mais NON configures.
composer require --no-interaction webapp

# STEP 2 — Doctrine ORM 3 + migrations
composer require --no-interaction \
  doctrine/orm:3.6.8 \
  doctrine/doctrine-bundle:3.3.1 \
  doctrine/doctrine-migrations-bundle:4.0.1

# STEP 3 — Symfony UX (interactivite sans SPA)
composer require --no-interaction \
  symfony/stimulus-bundle:3.4.0 \
  symfony/ux-turbo:3.4.0

# STEP 4 — Outillage de developpement
composer require --dev --no-interaction \
  symfony/maker-bundle:1.67.0 \
  symfony/web-profiler-bundle:8.1.5 \
  pestphp/pest:5.1.3 \
  phpstan/phpstan:2.2.12 \
  friendsofphp/php-cs-fixer:3.95.24

# STEP 5 — Tailwind via AssetMapper (binaire standalone, PAS de Node)
composer require --no-interaction symfonycasts/tailwind-bundle:1.0.0
php bin/console tailwind:init

# STEP 6 — Arborescence applicative
mkdir -p \
  src/{Controller,Entity,Repository,Form,Service,Twig} \
  src/Security/Voter \
  templates/components \
  assets/controllers assets/styles \
  tests/{Controller,Service}

# STEP 7 — phpstan.neon
cat > phpstan.neon <<'NEON'
parameters:
    paths:
        - src
    level: 6
NEON

# STEP 8 — Gate
php bin/console cache:clear
php bin/console about

fi
```

**Contrat post-init** :
- `bin/console about` sort 0
- `symfony.lock` existe et est **versionné** (état des recipes Flex)
- `config/packages/` contient la configuration écrite par Flex
- `templates/base.html.twig` existe
- `APP_SECRET` est présent dans `.env`

---

## 2.3 Notes de construction

### Plancher PHP — ici c'est le framework, pas les tests

Sur `backend/laravel` et `fullstack/laravel-blade`, le plancher **8.4.1** venait
de l'outillage de test (Pest 5, PHPUnit 13) alors que le framework se contentait
de `^8.3`. **Ici la contrainte vient du framework lui-même** :

| Paquet | `require.php` |
|---|---|
| `symfony/framework-bundle` 8.1.6 | **`>=8.4.1`** |
| `symfony/twig-bundle` 8.1.2 | **`>=8.4.1`** |
| `doctrine/doctrine-bundle` 3.3.1 | `^8.4` |
| `pestphp/pest` 5.1.3 | `^8.4` |

Le plancher est le même dans les deux familles, mais l'échec se produit plus
tôt ici : `composer create-project` refuse directement.

### Flex écrit la configuration — `symfony.lock` doit être versionné

`symfony/flex` applique des **recipes** : à chaque `composer require`, il écrit
les fichiers de `config/packages/` correspondants. C'est ce mécanisme qui rend
un `composer require webapp` fonctionnel sans configuration manuelle.

`symfony.lock` enregistre les recipes appliquées. **Ne pas le versionner** rend
une réinstallation non reproductible : les paquets reviennent, la configuration
non.

### AssetMapper plutôt que Webpack Encore

AssetMapper sert les modules ES via `importmap` — **pas de Node, pas de
bundler, pas d'étape de build en développement**. C'est le défaut retenu ici,
et il simplifie nettement la chaîne face à `fullstack/laravel-blade` (qui, lui,
requiert `npm install` + `npm run build`).

En production, `asset-map:compile` produit les fichiers versionnés.

La capability `webpack-encore` reste disponible pour un pipeline classique
(Sass, transpilation avancée) — elle est **exclusive** d'AssetMapper.

### Doctrine : deux lignes majeures à ne pas mélanger

`doctrine/orm` 3.x va avec `doctrine/doctrine-bundle` 3.x. Le bundle 3.3.1
déclare `php: ^8.4`, cohérent avec Symfony 8.1. Panacher avec la ligne 2.x de
l'ORM produit des erreurs de mapping difficiles à diagnostiquer.

### Ce qui n'a PAS été validé

| Vérifié | Non vérifié |
|---|---|
| Existence + dernière version stable de chaque paquet (Packagist, 2026-09-02) | `composer create-project`, `bin/console` |
| Contrainte `require.php` de chaque paquet | Application des recipes Flex |
| Cohérence `.md` ↔ `.libs.json` | Migrations Doctrine contre une vraie base |
| — | Pipeline `/sdd-full` complet |

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/fullstack/symfony-twig.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id symfony-twig`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| symfony/framework-bundle | 8.1.6 | Noyau HTTP, conteneur de services, routing, configuration |
| symfony/runtime | 8.1.0 | Point d'entree decouple (public/index.php) — requis par Flex |
| symfony/flex | 2.11.0 | Recipes : configure automatiquement chaque bundle installe. Sans lui, `composer require` n'ecrit aucune config |
| symfony/console | 8.1.6 | bin/console — generateurs, migrations, cache |
| symfony/dotenv | 8.1.6 | Chargement de .env |
| symfony/twig-bundle | 8.1.2 | Moteur de templates Twig — c'est la couche de rendu de ce stack |
| symfony/asset | 8.1.0 | Fonction Twig asset() — versionnement des URL d'assets |
| symfony/asset-mapper | 8.1.5 | Sert les modules ES via importmap, SANS Node ni bundler. Defaut de ce stack (cf. capability webpack-encore pour un pipeline classique) |
| symfony/form | 8.1.6 | Formulaires typees — le pendant serveur des formulaires HTML rendus par Twig |
| symfony/validator | 8.1.6 | Contraintes de validation sur les entites et les DTO de formulaire |
| symfony/security-bundle | 8.1.6 | Authentification, autorisation, voters |
| symfony/security-csrf | 8.1.0 | Jetons CSRF — OBLIGATOIRE des qu'un formulaire est rendu (cf. .md 1.4) |
| symfony/translation | 8.1.5 | Catalogues de traduction utilises par Twig |
| symfony/monolog-bundle | 4.0.2 | Logs |
| doctrine/orm | 3.6.8 | ORM Data Mapper — a la difference d'Eloquent (Active Record), l'entite ne sait pas se sauvegarder : c'est l'EntityManager qui persiste |
| doctrine/doctrine-bundle | 3.3.1 | Integration Symfony de Doctrine. La ligne 3.3 exige `php: ^8.4` — elle va avec l'ORM 3.x |
| doctrine/doctrine-migrations-bundle | 4.0.1 | Migrations versionnees |
| twig/extra-bundle | 3.24.0 | Extensions Twig usuelles (intl, string, html) |
| symfony/maker-bundle | 1.67.0 | Generateurs (dev) : make:entity, make:controller, make:form |
| symfony/web-profiler-bundle | 8.1.5 | Barre de debug et profiler (dev) — indispensable pour reperer les N+1 Doctrine |
| friendsofphp/php-cs-fixer | 3.95.24 | Formateur (dev) |
| phpstan/phpstan | 2.2.12 | Analyse statique (dev) |
| pestphp/pest | 5.1.3 | Runner de tests (dev) — cf. qa/php-pest.md |
| symfony/phpunit-bridge | 8.1.6 | Pont PHPUnit Symfony (dev) — gere les depreciations et le bootstrap de test |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| symfony-ux | symfony/stimulus-bundle | 3.4.0 | interactivite, stimulus, controller.*javascript, symfony.*ux |
| symfony-ux | symfony/ux-turbo | 3.4.0 | turbo, navigation.*sans.*rechargement, spa.*like |
| tailwind | symfonycasts/tailwind-bundle | 1.0.0 | tailwind, utility.*css |
| webpack-encore | symfony/webpack-encore-bundle (alt) | 2.4.1 | webpack, encore, bundler.*js, sass |
| email | symfony/mailer | 8.1.5 | email, mail, notification.*mail, envoi.*courriel |
| queues | symfony/messenger | 8.1.6 | message.*asynchrone, queue, worker, messenger, bus |
| uuid | symfony/uid | 8.1.5 | uuid, ulid, identifiant.*opaque |
| fixtures | doctrine/doctrine-fixtures-bundle | 4.3.1 | fixture, jeu.*donnees, seed |
| pagination | knplabs/knp-paginator-bundle | 6.10.0 | pagination, paginer, liste.*paginee |
| markdown | league/commonmark | 2.10.0 | markdown, commonmark, contenu.*riche |
| cors | nelmio/cors-bundle | 2.6.1 | cors, origine.*distincte |
| api-tokens | lexik/jwt-authentication-bundle | 3.2.0 | jwt, api.*token, authentification.*api |
| api-platform | api-platform/core (alt) | 4.3.17 | api-platform, api.*rest.*generee, hydra, jsonld |
| automated-refactoring | rector/rector | 2.6.6 | rector, refactoring.*automatise, migration.*version.*php |
| test-fixtures | zenstruck/foundry | 2.12.1 | factory.*entite, foundry, donnees.*test |
| test-fixtures | dama/doctrine-test-bundle | 8.6.0 | isolation.*base.*test, transaction.*test |
| functional-tests | symfony/browser-kit | 8.1.5 | test.*fonctionnel, webtestcase, crawler |
| functional-tests | symfony/css-selector | 8.1.6 | crawler, selecteur.*css, assertion.*html |
| dev-profiling | symfony/debug-bundle | 8.1.0 | dump, var-dumper, debug |
| dev-profiling | symfony/stopwatch | 8.1.0 | stopwatch, profiling |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Rôle | Pattern | Exemple |
|---|---|---|
| Controller | `{Name}Controller.php` → `class {Name}Controller` | `InvoiceController.php` |
| Entité | `{Name}.php` (singulier) | `Invoice.php` |
| Repository | `{Name}Repository.php` | `InvoiceRepository.php` |
| FormType | `{Name}Type.php` | `InvoiceType.php` |
| Service | `{Name}Service.php` | `InvoiceService.php` |
| Voter | `{Name}Voter.php` | `InvoiceVoter.php` |
| Extension Twig | `{Name}Extension.php` | `PriceExtension.php` |
| Template | `templates/{domaine}/{action}.html.twig` (snake_case) | `templates/invoice/index.html.twig` |
| Controller Stimulus | `assets/controllers/{name}_controller.js` (snake_case) | `assets/controllers/dropdown_controller.js` |
| Migration | `Version{timestamp}.php` (**générée**) | `Version20260902120000.php` |
| Test | `{Name}Test.php` | `InvoiceServiceTest.php` |
| Table | `snake_case` pluriel | `invoices` |

**Conventions** : classes en `StudlyCase` (PSR-4), templates et controllers Stimulus en `snake_case` (c'est ce que résolvent respectivement Twig et Stimulus).

**Suffixes INTERDITS** :
- `Manager`, `Helper`, `Util`
- `Bundle` pour du code applicatif — la structure en bundles applicatifs est abandonnée depuis Symfony 4
- Entité au pluriel
- Template en `PascalCase`

---

## 3. Routes standard

| Route | Rôle |
|---|---|
| `GET /` | page d'accueil |
| `GET /login` · `POST /login` | authentification (`security-bundle`) |
| `GET /logout` | déconnexion |
| `GET /health` | healthcheck |
| `GET /_profiler` | profiler — **dev uniquement** |

Routing par **attributs** (`#[Route('/invoices', name: 'invoice_index')]`) sur les controllers ; `config/routes.yaml` ne sert qu'aux routes transverses.

---

## 4. Versioning

Monolithe SSR : pas de contrat d'API versionné, client et serveur avancent
ensemble à chaque déploiement. `rules/library-and-stack.md §6.bis` (drift de
contrat front↔back) est **sans objet** — c'est l'avantage structurel du SSR.

Si la capability `api-platform` ou `api-tokens` est activée pour des endpoints
JSON annexes, ceux-là se versionnent et retombent sous le §6.bis.

---

## 5. Interdits projet (symfony-twig)

**Architecture** :
- Requête Doctrine (`createQueryBuilder`, DQL) dans un controller — la placer dans le Repository
- Relation traversée par un template sans `JOIN`/`addSelect` au Repository — N+1 invisible
- `$em->flush()` dans une boucle
- `doctrine:schema:update --force` — auto-`ALTER`, interdit par `rules/library-and-stack.md §C.4`
- Logique métier dans un controller ou dans un template Twig
- Formulaire construit à la main dans le controller — utiliser un `FormType`
- Autorisation par `if ($user->getRoles()...)` — utiliser un voter
- Entité dépendant du conteneur ou de la requête
- Bundle applicatif maison (abandonné depuis Symfony 4)
- `services.yaml` surchargé de déclarations que l'autowiring gérerait

**Code quality** :
- `@` (suppression d'erreur)
- Méthode de plus de 30 lignes
- `catch (\Exception $e) {}` silencieux
- `dump()`, `dd()` committés
- Template Twig de plus de 100 lignes — extraire des composants
- Niveau PHPStan abaissé sous 6
- `TODO`, `FIXME`, code commenté

**Sécurité** :
- **`|raw` sur du contenu non assaini** — injection XSS
- `APP_ENV=dev` ou `APP_DEBUG=1` en production
- `web-profiler-bundle` / `debug-bundle` en `require` (et non `require-dev`)
- `_profiler` accessible en production
- `APP_SECRET` committé
- DQL construit par concaténation — utiliser `setParameter`
- Formulaire sans protection CSRF
- Voter contourné par un simple masquage dans le template

**Build / packaging** :
- Committer `vendor/`, `var/`, `.env.local`, `public/assets/`
- **`symfony.lock` non versionné** — la configuration Flex n'est plus reproductible (§2.3)
- `composer.lock` absent (une **application** verrouille ses versions)
- Livrer AssetMapper **et** Webpack Encore
- `composer update` en production — utiliser `composer install --no-dev --optimize-autoloader`
- `asset-map:compile` oublié avant déploiement

---

## 6. Persistance — voir §1.5

Doctrine ORM 3 + Migrations. Phase B (DB) d'`arch` : **applicable** — introspection en lecture seule ; `make:entity` pour une base neuve uniquement.

---

## 7. Temps reel

- **Turbo Streams** (capability `symfony-ux`) — le serveur pousse des fragments HTML à appliquer au DOM. C'est la voie native de ce stack.
- **Mercure** (hub SSE) — **non catalogué**, à instruire avant engagement
- **Messenger** (capability `queues`) — traitement asynchrone, pas du temps réel client

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **Applications métier complexes et durables** — le Data Mapper et la configuration explicite tiennent mieux la croissance qu'un Active Record
- **Domaines riches** — les entités sont du PHP pur, testables sans base ni conteneur
- **Équipes PHP structurées**, habituées à l'injection de dépendances
- **Chaîne d'assets simple** — AssetMapper évite Node entièrement

**NE PAS choisir si** :
- ❌ **Prototypage rapide / CRUD simple** — Symfony demande plus de déclaration que Laravel pour le même résultat. Préférer `fullstack/laravel-blade`.
- ❌ **Interface très interactive** — Turbo reste du rendu serveur ; pour une vraie SPA, `backend/*` + `frontend/*`
- ❌ **Application mobile prévue** — une API sera nécessaire de toute façon
- ❌ **Équipe sans culture DI / architecture en couches** — la courbe est réelle
- ❌ **PHP < 8.4 imposé par l'hébergement** — Symfony 8.1 est alors inutilisable (§2.3)
- ❌ **Équipe .NET / Java / Node / Python** — préférer le stack de leur langage

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `fullstack-symfony-twig` + `qa/php-pest` (capabilities `symfony-fixtures` + `symfony-functional`) + `postgres` | 🟡 experimental | jamais validé end-to-end |
| `fullstack-symfony-twig` + `qa/php-pest` + `mysql` | 🟡 experimental | jamais validé end-to-end |
| `fullstack-symfony-twig` + capability `symfony-ux` (Stimulus + Turbo) | 🟡 experimental | interactivité sans SPA |

> **Incompatible** avec tout stack `frontend/*` et avec les autres stacks `fullstack/*`.

---

## 10. Notes pour l'agent `arch`

1. **Détecter** `fullstack/symfony-twig.md` en `## Active Tech Specs` → `AppType=fullstack`, projet unique, **aucun** frontend séparé attendu
2. **Refuser la cohabitation** avec un stack `frontend/*` ou un autre `fullstack/*` → WARNING bloquant `[STACK_INCOMPAT]`
3. **STEP 0 — gate runtime bloquant** : `php -v` ≥ **8.4.1** — imposé ici par **le framework** (`symfony/* 8.1`), pas par les tests (§2.3)
4. **`composer require webapp` est load-bearing** : ce sont les **recipes Flex** qui écrivent `config/packages/*`. Sans cette étape, les bundles sont installés mais non configurés, et l'application ne démarre pas
5. **`symfony.lock` doit être versionné** — ne pas l'ajouter au `.gitignore` (§2.3)
6. **Propager** `APP_SECRET`, `DATABASE_URL`, `APP_ENV` depuis `stack.md` vers `.env.local`
7. **CORS** : sans objet — le HTML est servi depuis la même origine. Ne configurer `nelmio/cors-bundle` que si la capability `cors` est explicitement activée
8. **Phase B (DB)** : applicable, **lecture seule** sur base existante. **`doctrine:schema:update --force` est interdit en toutes circonstances** (§1.5)
9. **`web-profiler-bundle` et `debug-bundle` en `require-dev`** — jamais en `require`
10. **Phase C (ADRs)** : créer `ADR-{ts}-stack-fullstack-symfony-twig.md` documentant Symfony 8.1 + Twig + Doctrine ORM 3, le choix AssetMapper plutôt que Webpack Encore, et le plancher PHP

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Stack monolithe** : pas de séparation back/front (cf. `ownership.md §1.bis`).

- **`dev-backend`** matérialise `src/`, `migrations/`, `config/`
- **`dev-frontend`** matérialise `templates/`, `assets/`

**File ownership** :

| Path | Owner |
|---|---|
| `src/Controller/**`, `src/Entity/**`, `src/Repository/**` | `dev-backend` |
| `src/Service/**`, `src/Security/**`, `src/Form/**` | `dev-backend` |
| `src/Twig/**` (extensions) | `dev-backend` |
| `templates/**` | `dev-frontend` |
| `assets/**` (Stimulus, styles) | `dev-frontend` |
| `migrations/**` | `dev-backend` (via `make:migration`, jamais éditées après application) |
| `config/packages/**` | `arch` (écrit par Flex) + `dev-backend` (ajustements) |
| `config/routes.yaml`, `config/services.yaml` | `dev-backend` |
| `composer.json`, `symfony.lock` | `arch` (create) + `dev-backend` (deps on-demand) |
| `phpstan.neon`, `.php-cs-fixer.dist.php` | `arch` exclusif |
| `tests/**` | `qa` |

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{AppName}

php -r 'exit(version_compare(PHP_VERSION, "8.4.1", ">=") ? 0 : 1);'

composer install --no-interaction --quiet

test -f bin/console
test -f templates/base.html.twig
test -f symfony.lock                        # etat des recipes Flex — A VERSIONNER (cf. 2.3)
test -d config/packages                     # ecrit par Flex, pas a la main
test -f phpstan.neon
grep -q "APP_SECRET" .env

php bin/console cache:clear
php bin/console about
php bin/console debug:router --no-interaction >/dev/null

# Le profiler ne doit pas etre en dependance de production
! grep -q '"symfony/web-profiler-bundle"' <(php -r 'echo json_encode(json_decode(file_get_contents("composer.json"),true)["require"] ?? []);')

./vendor/bin/php-cs-fixer fix --dry-run
./vendor/bin/phpstan analyse --no-progress
./vendor/bin/pest

echo "smoke OK"
```
