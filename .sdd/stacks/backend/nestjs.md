# Tech FEAT: nestjs (backend)

> §2.4 (Librairies) regeneree depuis `nestjs.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id nestjs`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits et validés le 2026-09-02, chaque version résolue contre le registre npm. **Deux pièges de registre** identifiés à la construction et documentés en §2.3 : le plafond `typescript < 7` imposé par la chaîne de build, et le dist-tag `latest` de `prisma` qui pointe sur une préversion. **Jamais exécuté end-to-end via `/sdd-full`** : aucun `nest build` ni `jest` n'a tourné en CI. Non supporté commercialement en l'état.
Tech FEAT ID: tech-nestjs
Scope: **backend API REST** — application **NestJS 12** (TypeScript) dans UN projet `workspace/src/{BackendName}/`. Architecture par modules avec injection de dépendances, décorateurs, pipes et guards. Expose une API JSON consommée par un frontend séparé déclaré en `## Active Tech Specs`.

---

# 1. Architecture

## 1.1 Pattern applicatif

**API REST NestJS**, découpée en modules de domaine :

- **NestJS 12** — conteneur DI, modules, décorateurs, pipes, guards, interceptors
- **TypeORM 1.x** via `@nestjs/typeorm` — repositories injectables, migrations, transactions
- **class-validator + ValidationPipe** — validation déclarative des DTO
- **@nestjs/swagger** — OpenAPI 3 généré depuis les décorateurs de DTO
- **Passport + JWT** — authentification par stratégie
- **pino** — logs structurés corrélés par requête

Architecture cible :

```
{BackendName}/
├── src/
│   ├── main.ts                ── bootstrap (pipes globaux, Swagger, helmet)
│   ├── app.module.ts          ── module racine
│   ├── config/
│   │   ├── configuration.ts   ── @nestjs/config typee
│   │   └── validation.ts      ── validation de l'env au demarrage
│   ├── common/
│   │   ├── filters/           ── exception filters
│   │   ├── guards/            ── auth, roles
│   │   ├── interceptors/      ── logging, transformation
│   │   ├── pipes/
│   │   └── decorators/
│   ├── database/
│   │   ├── data-source.ts     ── DataSource TypeORM (CLI de migration)
│   │   └── migrations/
│   └── modules/
│       ├── auth/
│       └── {domaine}/
│           ├── {domaine}.module.ts
│           ├── {domaine}.controller.ts   ── HTTP uniquement
│           ├── {domaine}.service.ts      ── logique metier
│           ├── entities/                 ── entites TypeORM
│           ├── dto/                      ── DTO d'entree/sortie
│           └── {domaine}.service.spec.ts
├── test/                      ── tests e2e (supertest)
├── nest-cli.json
├── tsconfig.json
└── package.json
```

**Différence vs `backend/node-express`** :
- NestJS **impose** une architecture (modules + DI) ; Express laisse tout ouvert
- Décorateurs et métadonnées de réflexion — nécessitent `reflect-metadata` et `emitDecoratorMetadata`
- Le contrat OpenAPI est **déduit des DTO**, il n'est pas écrit à la main comme avec `swagger-jsdoc`
- Testabilité native : `Test.createTestingModule` substitue n'importe quel provider

---

## 1.2 Couches

- **Controller** (`{d}.controller.ts`) : HTTP seulement — routes, codes de statut, documentation Swagger. Aucune règle métier.
- **Service** (`{d}.service.ts`) : la logique métier. Injectable, testable sans HTTP.
- **Entity** (`entities/`) : schéma TypeORM.
- **DTO** (`dto/`) : contrat d'entrée/sortie, validé par `class-validator`. C'est la frontière de l'API.
- **Module** (`{d}.module.ts`) : câblage — déclare providers, imports, exports.
- **Common** (`common/`) : guards, filters, interceptors transverses.

---

## 1.3 Mapping couche → repertoire

| Layer | Path |
|---|---|
| Bootstrap | `src/main.ts` |
| Module racine | `src/app.module.ts` |
| Configuration | `src/config/configuration.ts` |
| Module de domaine | `src/modules/{domaine}/{domaine}.module.ts` |
| Controller | `src/modules/{domaine}/{domaine}.controller.ts` |
| Service | `src/modules/{domaine}/{domaine}.service.ts` |
| Entité | `src/modules/{domaine}/entities/{name}.entity.ts` |
| DTO | `src/modules/{domaine}/dto/{action}-{name}.dto.ts` |
| Guard | `src/common/guards/{name}.guard.ts` |
| Interceptor | `src/common/interceptors/{name}.interceptor.ts` |
| Exception filter | `src/common/filters/{name}.filter.ts` |
| DataSource TypeORM | `src/database/data-source.ts` |
| Migration | `src/database/migrations/{ts}-{desc}.ts` (**générée**) |
| Test unitaire | `src/modules/{domaine}/{domaine}.service.spec.ts` |
| Test e2e | `test/{domaine}.e2e-spec.ts` |

---

## 1.4 Principes non negociables

**Architecture** :
- **Controller mince** : il traduit du HTTP, rien de plus. Un controller de plus de 15 lignes par route signale de la logique mal placée.
- **`ValidationPipe` global** avec `whitelist: true` et `forbidNonWhitelisted: true` — sinon tout champ non déclaré traverse silencieusement le DTO (surface d'attaque par assignation de masse).
- **Un DTO par sens** : `CreateXDto` / `UpdateXDto` / `XResponseDto`. Ne jamais exposer une entité TypeORM directement — le schéma de base devient le contrat d'API.
- **`@nestjs/config` avec validation au démarrage** : une variable d'environnement manquante doit faire échouer le boot, pas la première requête.
- **DI par constructeur** ; pas de `new` sur un service.
- **`relations` explicites** sur les requêtes TypeORM — le chargement paresseux est la cause n°1 des N+1 ici.
- **Migrations committées et générées** (`migration:generate`), jamais `synchronize: true` (cf. §5).
- **Guards pour l'autorisation**, pas de `if (user.role === ...)` dans un service.

**Sécurité** :
- **`helmet` activé** dans `main.ts`
- **CORS explicite** — `app.enableCors({ origin: [...] })`, jamais `origin: true` en production (cf. `rules/library-and-stack.md` Partie B)
- **Argon2id** pour les mots de passe, jamais de SHA/MD5
- **Secret JWT par l'environnement** (`stack.md`), rotation des refresh tokens
- **Rate limiting** sur les routes d'authentification (capability `rate-limit`)
- **Pas d'entité exposée** en réponse : passer par un DTO de sortie, sinon un `passwordHash` finit dans le JSON
- **`pino-pretty` interdit en production** — coûteux et casse le parsing JSON des logs

---

## 1.5 Base de donnees

| DatabaseType | Driver | Capability |
|---|---|---|
| `postgres` / `postgresql` | `pg` | `postgres-driver` (défaut) |
| `mysql` / `mariadb` | `mysql2` | **non catalogué** — à instruire |
| `sqlite` | `better-sqlite3` | **non catalogué** — à instruire |
| `sqlserver` | `mssql` | **non catalogué** — à instruire |

Migrations TypeORM : `migration:generate` puis `migration:run`, pilotées par
`src/database/data-source.ts`.

> ⚠️ **Soumis à `rules/library-and-stack.md` Partie C.** `synchronize: true` est
> **interdit** (§C.4) : c'est un auto-`ALTER` du schéma au démarrage, exactement
> ce que la règle proscrit. Sur une base existante, un agent n'applique jamais de
> migration — il écrit le DDL dans `workspace/db/migration-pending.sql` et émet
> `[DB_STRUCTURE_CHANGE_FORBIDDEN]`.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `backend-nestjs`
- **Langage** : TypeScript **6.0.3** (plafonné, cf. §2.3)
- **Runtime** : Node.js 22 LTS (`@nestjs/core` 12 déclare `engines.node >= 20`)
- **Framework** : NestJS 12.0.1
- **Adaptateur HTTP** : Express (Fastify via la capability `fastify-adapter`)
- **ORM** : TypeORM 1.1.1 (Prisma via la capability `prisma-orm`, exclusive)
- **Package manager** : `pnpm` (aligné sur `backend/node-express`)

---

## 2.2 Outils

- **Project file** : `workspace/src/{BackendName}/package.json`
- **Run dev** : `(cd workspace/src/{BackendName} && pnpm start:dev)`
- **Build** : `pnpm build` (`nest build`)
- **Run prod** : `node dist/main.js`
- **Générer une ressource** : `pnpm nest generate resource modules/{domaine}`
- **Migration (générer)** : `pnpm typeorm migration:generate src/database/migrations/{desc} -d src/database/data-source.ts`
- **Migration (appliquer)** : `pnpm typeorm migration:run -d src/database/data-source.ts`
- **Tests unitaires** : `pnpm test`
- **Tests e2e** : `pnpm test:e2e` (capability `e2e-http`)
- **Coverage** : `pnpm test:cov`
- **Type-check** : `pnpm tsc --noEmit`
- **Lint** : `pnpm eslint .`
- **Smoke Command** :

```bash
(cd workspace/src/{BackendName} && pnpm install --silent && pnpm tsc --noEmit && pnpm build)
test -f workspace/src/{BackendName}/src/main.ts
test -f workspace/src/{BackendName}/src/app.module.ts
```

- **Smoke Timeout** : 240s (install + type-check + build)

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{BackendName}/package.json" ]; then

# STEP 1 — Scaffold NestJS
pnpm dlx @nestjs/cli@12.0.0 new {BackendName} \
  --directory workspace/src/{BackendName} \
  --package-manager pnpm \
  --skip-git \
  --skip-install \
  --language TS

cd workspace/src/{BackendName}

# STEP 2 — Pinner TypeScript AVANT le premier install
# @nestjs/cli 12 depend de `typescript: ~6.0.2` et ts-jest declare
# `typescript: >=4.3 <7`. Une resolution en 7.x casse le build. Cf. 2.3.
pnpm add -D typescript@6.0.3

pnpm install --silent

# STEP 3 — Dependances CORE (cf. 2.4.a)
pnpm add \
  @nestjs/config@12.0.0 \
  @nestjs/swagger@12.0.1 \
  @nestjs/typeorm@12.0.1 \
  typeorm@1.1.1 \
  @nestjs/jwt@12.0.1 \
  @nestjs/passport@12.0.0 \
  passport@0.7.0 \
  passport-jwt@4.0.1 \
  argon2@0.45.1 \
  class-validator@0.15.1 \
  class-transformer@0.5.1 \
  helmet@8.3.0 \
  pino@10.3.1 \
  nestjs-pino@5.1.0

# STEP 4 — Driver de base selon DatabaseType (defaut postgres)
pnpm add pg@8.23.0

# STEP 5 — Arborescence
mkdir -p \
  src/config \
  src/common/{filters,guards,interceptors,pipes,decorators} \
  src/database/migrations \
  src/modules/auth \
  test

# STEP 6 — tsconfig : les decorateurs EXIGENT ces deux flags
node -e "
  const fs = require('fs');
  const cfg = JSON.parse(fs.readFileSync('tsconfig.json', 'utf8'));
  cfg.compilerOptions = cfg.compilerOptions || {};
  cfg.compilerOptions.experimentalDecorators = true;
  cfg.compilerOptions.emitDecoratorMetadata = true;   // sans lui, la DI echoue au runtime
  cfg.compilerOptions.strict = true;
  cfg.compilerOptions.strictNullChecks = true;
  fs.writeFileSync('tsconfig.json', JSON.stringify(cfg, null, 2));
"

# STEP 7 — .env.example
cat > .env.example <<'ENV'
NODE_ENV=development
PORT=3000
DATABASE_URL=postgres://user:pass@localhost:5432/{BackendName}
JWT_SECRET=change-me
JWT_EXPIRES_IN=15m
CORS_ALLOWED_ORIGINS=http://localhost:5173
ENV

# STEP 8 — Gate
pnpm tsc --noEmit
pnpm build

fi
```

**Contrat post-init** :
- `src/main.ts` et `src/app.module.ts` existent
- `tsconfig.json` porte `experimentalDecorators` **et** `emitDecoratorMetadata`
- `package.json` pin `typescript` sur la ligne `6.0`
- `reflect-metadata` est présent (le template Nest l'inclut) et importé en tête de `main.ts`
- `pnpm build` sort 0

---

## 2.3 Contraintes de version (verifiees a la construction)

### 1. TypeScript est plafonné sous la 7

TypeScript **7.0.2** est disponible sur npm. Deux éléments de la chaîne de
build le refusent :

| Paquet | Contrainte déclarée |
|---|---|
| `@nestjs/cli` 12.0.0 | `dependencies.typescript: ~6.0.2` |
| `ts-jest` 29.4.12 | `peerDependencies.typescript: >=4.3 <7` |

Le stack pin donc **6.0.3**, et le STEP 2 de §2.2.1 l'installe **avant** le
premier `pnpm install` — sinon la résolution remonte en 7.x et le build casse
sans que la cause soit lisible dans le message d'erreur.

C'est la même classe de piège que sur `mobiles/ionic-capacitor` (plafond
`<6.1` imposé par `@ionic/angular-toolkit`) : **la dernière version publiée
n'est pas la version correcte.**

### 2. `prisma` : le dist-tag `latest` est une préversion

```
prisma  dist-tags: { latest: "8.0.0-rc.12", prev: "7.10.0", ... }
@prisma/client  dist-tags: { latest: "7.10.0", ... }
```

Un `pnpm add prisma @prisma/client` sans version installe un **CLI 8 RC** avec
un **client 7 stable**. Le CLI génère alors un client dans un format que la
version installée ne sait pas lire.

Le catalog pin **7.10.0 pour les deux**. La règle générale s'applique :
`rules/library-and-stack.md §5` interdit les préversions sans ADR — et ici la
préversion est ce que `latest` renvoie, donc le piège est silencieux.

### 3. Deux flags `tsconfig` sont load-bearing

`emitDecoratorMetadata` et `experimentalDecorators` ne sont pas des options de
confort : sans eux, les décorateurs NestJS n'émettent aucune métadonnée de
type, et **l'injection de dépendances échoue au démarrage** avec un message
portant sur un paramètre `undefined` — sans rapport apparent avec la cause.
Le STEP 6 les pose explicitement plutôt que de faire confiance au template.

### Ce qui n'a PAS été validé

| Vérifié | Non vérifié |
|---|---|
| Existence + dernière version stable de chaque paquet (npm, 2026-09-02) | `nest build` |
| Peer-dependencies et plafonds croisés (tables ci-dessus) | `jest` / `test:e2e` |
| Cohérence `.md` ↔ `.libs.json` | Migration TypeORM contre une vraie base |
| — | Pipeline `/sdd-full` complet |

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/backend/nestjs.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id nestjs`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| @nestjs/core | 12.0.1 | Noyau — conteneur DI, cycle de vie des modules |
| @nestjs/common | 12.0.1 | Decorateurs, pipes, guards, interceptors |
| @nestjs/platform-express | 12.0.1 | Adaptateur HTTP Express (defaut). L'adaptateur Fastify est en capability `fastify-adapter` |
| @nestjs/config | 12.0.0 | Configuration typee + validation au demarrage — evite process.env disperse |
| @nestjs/swagger | 12.0.1 | OpenAPI 3 genere depuis les decorateurs de DTO |
| @nestjs/typeorm | 12.0.1 | Integration TypeORM officielle (repositories injectables, transactions) |
| typeorm | 1.1.1 | ORM. La ligne 1.x est desormais stable — la 0.3.31 est taguee `legacy` sur npm |
| @nestjs/jwt | 12.0.1 | Signature et verification des JWT |
| @nestjs/passport | 12.0.0 | Pont Passport (strategies d'authentification) |
| passport | 0.7.0 |  |
| passport-jwt | 4.0.1 | Strategie JWT (Bearer) |
| argon2 | 0.45.1 | Hachage de mot de passe — Argon2id, retenu plutot que bcrypt (pas de compilation natif fragile, parametrage memoire) |
| reflect-metadata | 0.2.2 | PEER OBLIGATOIRE — sans lui les decorateurs NestJS n'emettent aucune metadonnee et la DI echoue au demarrage |
| rxjs | 7.8.2 | Peer declare par @nestjs/core (^7.1.0) — interceptors et pipes reposent sur Observable |
| class-validator | 0.15.1 | Validation des DTO via ValidationPipe |
| class-transformer | 0.5.1 | Peer de class-validator — transformation payload -> instance de DTO |
| helmet | 8.3.0 | En-tetes HTTP de securite |
| pino | 10.3.1 | Logs structures — meme choix que backend/node-express |
| nestjs-pino | 5.1.0 | Integration Nest (contexte de requete correle) |
| typescript | 6.0.3 | PIN OBLIGATOIRE sur la ligne 6.0 — la 7.x est refusee par @nestjs/cli et ts-jest (cf. metadata.notes) |
| ts-node | 10.9.2 |  |
| tsconfig-paths | 4.2.0 |  |
| @nestjs/cli | 12.0.0 | devDependency — build, generateurs, mode watch |
| @nestjs/schematics | 12.0.0 | devDependency — `nest generate resource` |
| @nestjs/testing | 12.0.1 | devDependency — Test.createTestingModule, cf. qa/node-vitest.md 10 |
| jest | 30.5.1 | devDependency — runner par defaut de NestJS |
| ts-jest | 29.4.12 | devDependency. C'est ce paquet qui plafonne TypeScript sous la 7 |
| @types/node | 26.4.1 |  |
| @types/express | 5.0.6 | Ligne 5.x — coherente avec l'Express embarque par @nestjs/platform-express 12 |
| @types/jest | 30.0.0 |  |
| eslint | 10.9.1 |  |
| typescript-eslint | 8.69.0 |  |
| prettier | 3.9.6 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| postgres-driver | pg | 8.23.0 | postgres, postgresql |
| prisma-orm | prisma (alt) | 7.10.0 | prisma |
| prisma-orm | @prisma/client (alt) | 7.10.0 | prisma |
| fastify-adapter | @nestjs/platform-fastify (alt) | 12.0.1 | fastify, haut.*debit, performance.*http |
| rate-limit | @nestjs/throttler | 6.5.0 | rate.*limit, throttle, limitation.*debit, anti.*abus |
| healthcheck | @nestjs/terminus | 12.0.0 | health, readiness, liveness, sonde |
| cache | @nestjs/cache-manager | 12.0.0 | cache, mise.*en.*cache |
| cache | cache-manager | 7.2.9 | cache |
| background-jobs | @nestjs/bullmq | 12.0.0 | tache.*asynchrone, background job, worker, file.*attente, bullmq |
| background-jobs | bullmq | 6.3.4 | background job, bullmq, worker |
| background-jobs | ioredis | 6.0.0 | redis, bullmq |
| domain-events | @nestjs/event-emitter | 12.0.0 | evenement.*domaine, event.*emitter, publication.*evenement |
| microservices | @nestjs/microservices | 12.0.1 | microservice, message.*broker, rabbitmq, kafka |
| zod-validation | nestjs-zod (alt) | 5.5.0 | \bzod\b, schema.*zod |
| zod-validation | zod (alt) | 4.5.4 | \bzod\b |
| sentry | @sentry/nestjs | 10.73.0 | sentry, error.*tracking, monitoring.*erreurs |
| auth-local | passport-local | 1.0.0 | login.*mot.*de.*passe, auth-local, connexion.*locale |
| http-logging | pino-http | 11.0.0 | log.*requete, access.*log |
| http-logging | pino-pretty | 13.1.3 | log.*lisible, pretty.*log |
| e2e-http | supertest | 7.2.2 | test.*e2e, supertest, test.*endpoint |
| e2e-http | @types/supertest | 7.2.1 | supertest |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Rôle | Pattern | Exemple |
|---|---|---|
| Module | `{domaine}.module.ts` → `{Domaine}Module` | `billing.module.ts` |
| Controller | `{domaine}.controller.ts` → `{Domaine}Controller` | `billing.controller.ts` |
| Service | `{domaine}.service.ts` → `{Domaine}Service` | `billing.service.ts` |
| Entité | `{name}.entity.ts` → `{Name}` | `invoice.entity.ts` / `Invoice` |
| DTO d'entrée | `{action}-{name}.dto.ts` → `{Action}{Name}Dto` | `create-invoice.dto.ts` |
| DTO de sortie | `{name}-response.dto.ts` → `{Name}ResponseDto` | `invoice-response.dto.ts` |
| Guard | `{name}.guard.ts` → `{Name}Guard` | `jwt-auth.guard.ts` |
| Interceptor | `{name}.interceptor.ts` → `{Name}Interceptor` | `logging.interceptor.ts` |
| Exception filter | `{name}.filter.ts` → `{Name}Filter` | `http-exception.filter.ts` |
| Test unitaire | `{sujet}.spec.ts` à côté du sujet | `billing.service.spec.ts` |
| Test e2e | `test/{domaine}.e2e-spec.ts` | `test/billing.e2e-spec.ts` |
| Migration | `{timestamp}-{desc}.ts` (**générée**) | `1730000000000-AddInvoiceStatus.ts` |

**Conventions de fichier** : `kebab-case` + suffixe de rôle (convention NestJS) ; classes en `PascalCase`.

**Suffixes INTERDITS** :
- `Manager`, `Helper`, `Util`
- `Repository` sur une classe maison — c'est le rôle du `Repository<T>` de TypeORM
- DTO sans suffixe `Dto` (indistinguable d'une entité)
- Entité exposée comme type de retour d'un controller (cf. §1.4)

---

## 3. Endpoints standard

| Endpoint | Rôle |
|---|---|
| `GET /health` | healthcheck (capability `healthcheck`) |
| `POST /auth/login` | émission du JWT |
| `POST /auth/refresh` | rotation du refresh token |
| `GET /auth/me` | utilisateur courant |
| `GET /docs` | Swagger UI (`@nestjs/swagger`) |
| `GET /docs-json` | schéma OpenAPI 3 |

---

## 4. Versioning des API exposees

NestJS fournit un versioning natif : `app.enableVersioning({ type: VersioningType.URI })` → `/v1/{domaine}`. Préférer cette voie à un préfixe global écrit à la main : le décorateur `@Version()` permet alors de faire cohabiter deux versions d'une même route. Cf. `rules/library-and-stack.md §6.bis` pour la synchronisation du contrat front↔back.

---

## 5. Interdits projet (nestjs)

**Architecture** :
- `synchronize: true` sur le `DataSource` TypeORM — auto-`ALTER` au démarrage, interdit par `rules/library-and-stack.md` §C.4
- Entité TypeORM retournée par un controller — passer par un DTO de sortie
- `ValidationPipe` sans `whitelist: true` — assignation de masse
- Logique métier dans un controller
- `new SomeService()` — passer par la DI
- Requête TypeORM sans `relations` explicites là où des relations sont lues (N+1)
- `@Injectable()` oublié sur un provider — échec de DI au démarrage
- Import circulaire entre modules sans `forwardRef` — le conteneur ne peut pas résoudre
- `process.env` lu directement dans un service — utiliser `ConfigService`
- Migration éditée à la main après application

**Code quality** :
- `any` injustifié
- `!` (non-null assertion) sur une valeur non prouvée
- `strictNullChecks` désactivé
- Fonction de plus de 30 lignes
- `console.log` — utiliser le logger pino injecté
- `TODO`, `FIXME`, code commenté

**Sécurité** :
- `app.enableCors({ origin: true })` en production
- `helmet` absent de `main.ts`
- Secret JWT en dur ou committé
- Mot de passe haché autrement qu'avec Argon2id (ou bcrypt à défaut)
- `passwordHash` présent dans un DTO de réponse
- Routes d'authentification sans rate limiting
- `pino-pretty` actif en production
- Stack trace renvoyée au client (exception filter absent)

**Build / packaging** :
- Laisser `pnpm install` remonter TypeScript au-delà de `6.0.x` (§2.3)
- Installer `prisma@latest` (§2.3)
- Livrer TypeORM **et** Prisma dans le même projet
- Committer `dist/`, `node_modules/`, `.env`
- `emitDecoratorMetadata` retiré du `tsconfig.json`
- Mélanger `npm` et `pnpm` (lockfiles concurrents)

---

## 6. Persistance — voir §1.5

TypeORM + migrations versionnées. Phase B (DB) d'`arch` : **applicable** — introspection en lecture seule ; scaffolding d'entités pour une base neuve uniquement.

---

## 7. Temps reel

- **WebSockets** : `@nestjs/websockets` + `@nestjs/platform-socket.io` — **non catalogué**, à instruire avant engagement
- **SSE** : natif — un handler renvoyant un `Observable<MessageEvent>` avec le décorateur `@Sse()`
- **Tâches asynchrones** : capability `background-jobs` (BullMQ + ioredis)
- **Événements internes** : capability `domain-events` (`@nestjs/event-emitter`) — in-process uniquement, pas de garantie de livraison

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **API structurées et durables** — l'architecture imposée résiste à la croissance de l'équipe
- **Équipes TypeScript** venant du front (Angular en particulier : mêmes concepts de DI et de décorateurs)
- **Contrat d'API fort** — OpenAPI déduit des DTO, pas maintenu à la main
- **Testabilité** — substituer un provider est trivial

**NE PAS choisir si** :
- ❌ **Quelques endpoints seulement** — la structure NestJS coûte plus qu'elle rapporte. `backend/node-express` suffit.
- ❌ **L'équipe rejette les décorateurs et la DI** — c'est le cœur du framework, pas une option
- ❌ **Charge CPU intensive** — Node reste mono-thread par requête ; préférer `backend/kotlin-spring-boot` ou `backend/dotnet-minimalapi`
- ❌ **Équipe Python / .NET / Java** — préférer le stack de leur langage
- ❌ **Besoin d'un admin CRUD livré** → `backend/django` (admin Django)
- ❌ **Démarrage à froid critique** (serverless au ticket) — NestJS construit son graphe DI au boot

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `backend-nestjs` + `react` + `shadcn` + `auth-local` + `postgres` | 🟡 experimental | jamais validé end-to-end |
| `backend-nestjs` + `angular` + `auth-local` + `postgres` | 🟡 experimental | affinité forte (mêmes concepts DI/décorateurs) |
| `backend-nestjs` + `mobiles/react-native` + `auth-local` | 🟡 experimental | jamais validé end-to-end |
| `backend-nestjs` + `qa/node-vitest` | 🟡 experimental | ⚠️ NestJS livre **Jest**, pas Vitest — cf. `qa/node-vitest.md §10` |

---

## 10. Notes pour l'agent `arch`

1. **Détecter** `backend/nestjs.md` en `## Active Tech Specs` → backend API, un frontend séparé est attendu
2. **Créer** `workspace/src/{BackendName}/` via `@nestjs/cli new` (cf. §2.2.1)
3. **Pinner TypeScript sur `6.0.3` AVANT le premier `pnpm install`** — plafond `<7` de la chaîne de build (§2.3)
4. **Ne jamais installer `prisma@latest`** — le dist-tag pointe sur une RC 8 (§2.3). Si la capability `prisma-orm` est active, pin `7.10.0` sur le CLI **et** le client
5. **`emitDecoratorMetadata` + `experimentalDecorators`** dans `tsconfig.json` (STEP 6) — sans eux la DI échoue au runtime
6. **Propager** `DATABASE_URL`, `JWT_SECRET`, `CORS_ALLOWED_ORIGINS`, `PORT` depuis `stack.md` vers `.env` (lu par `@nestjs/config`)
7. **CORS** : injecter l'origine du frontend déclaré dans `CORS_ALLOWED_ORIGINS`, comme au STEP 4.5.6 des autres stacks
8. **`synchronize: false`** obligatoire dans `src/database/data-source.ts` (§5 et `rules/library-and-stack.md` §C.4)
9. **Phase B (DB)** : applicable, **lecture seule** sur une base existante
10. **Phase C (ADRs)** : créer `ADR-{ts}-stack-backend-nestjs.md` documentant NestJS 12, TypeORM plutôt que Prisma, le plafond TypeScript et le piège du dist-tag Prisma

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

- `dev-backend` matérialise `src/modules/`, `src/common/`, `src/config/`
- `dev-frontend` **ne touche pas** au projet NestJS

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `workspace/src/{BackendName}/src/modules/**` | `dev-backend` |
| `workspace/src/{BackendName}/src/common/**` | `dev-backend` |
| `workspace/src/{BackendName}/src/app.module.ts` | `dev-backend` |
| `workspace/src/{BackendName}/src/main.ts` | `arch` (create) + `dev-backend` (pipes / middlewares globaux) |
| `workspace/src/{BackendName}/src/config/**` | `arch` (create) + `dev-backend` (ajout de clés) |
| `workspace/src/{BackendName}/src/database/data-source.ts` | `arch` exclusif |
| `workspace/src/{BackendName}/src/database/migrations/**` | **généré** — `dev-backend` lance `migration:generate`, ne les édite jamais |
| `workspace/src/{BackendName}/package.json` | `arch` (create) + `dev-backend` (deps on-demand) |
| `workspace/src/{BackendName}/tsconfig.json`, `nest-cli.json` | `arch` exclusif |
| `workspace/src/{BackendName}/**/*.spec.ts`, `test/**` | `qa` |

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{BackendName}
pnpm install --silent

test -f src/main.ts
test -f src/app.module.ts

# Plafond TypeScript (cf. 2.3) — la ligne 6, jamais la 7
grep -qE '"typescript": *"[~^]?6\.0\.' package.json

# Flags load-bearing des decorateurs (cf. 2.3)
grep -q "emitDecoratorMetadata" tsconfig.json
grep -q "experimentalDecorators" tsconfig.json

# Auto-ALTER interdit (cf. 5)
! grep -q "synchronize: true" src/database/data-source.ts

pnpm tsc --noEmit
pnpm build
pnpm test

echo "smoke OK"
```
