# Tech FEAT: angular (frontend)

> §2.4 (Librairies) régénérée depuis `angular.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id angular`).

Status: Experimental
Validation: 🟢 bench-validated runtime (2026-06-05 — CalcABCAngular :4200, Angular 18 standalone + signals, 14839 LOC (ng new template), 4/4 curl cross-origin sur Kotlin/.NET/Node/Python backends OK, AC-1/2/3 🟢. Bug fix critique : `<input type=number>` + `[(ngModel)]` envoie number → état `signal<string>` cassé → bouton bloqué. Convention `signal<number\|null>(null)` inscrite dans `library-and-stack.md §7.2`. Pipeline `/sdd-full` complet pas encore validé end-to-end — scaffolding manuel mainteneur, cf. `docs/benchmarks/known-gaps.md`)
Tech FEAT ID: tech-angular
Scope: frontend uniquement (Angular SPA)

---

## 1. Architecture

### 1.1 Pattern applicatif

Angular SPA consommant les APIs backend via HttpClient Angular
centralise avec interceptors HTTP, gestion reactive RxJS
et state management NgRx.

Architecture standard :

Module → Page → Component → Service → HTTP Client → API

Les modeles de donnees (DTO, `ApiResponse<T>`) sont partages avec le backend
via le projet `{LibName}` lorsque disponible.

---

### 1.2 Couches

- **Page** : composant Angular route.
- **Component** : composant reutilisable UI.
- **Layout** : composants layout globaux.
- **Service** : logique client API.
- **HTTP Client** : configuration HttpClient Angular.
- **Interceptor** : middleware HTTP.
- **State** : gestion etat via NgRx.
- **Guard** : securisation routes.
- **Auth config** : integration MSAL Angular.
- **Resources** : fichiers JSON multilingue.

---

### 1.3 Mapping couche → repertoire

- Page → `workspace/output/src/{AppName}/pages/`
- Component → `workspace/output/src/{AppName}/components/`
- Layout → `workspace/output/src/{AppName}/layouts/`
- Service → `workspace/output/src/{AppName}/services/`
- HTTP Client → `workspace/output/src/{AppName}/api/`
- Interceptor → `workspace/output/src/{AppName}/interceptors/`
- Guard → `workspace/output/src/{AppName}/guards/`
- State → `workspace/output/src/{AppName}/store/`
- Models → `workspace/output/src/{AppName}/models/`
- Pipes → `workspace/output/src/{AppName}/pipes/`
- Directives → `workspace/output/src/{AppName}/directives/`
- Auth → `workspace/output/src/{AppName}/auth/`
- Utils → `workspace/output/src/{AppName}/utils/`
- Ressources → `workspace/output/src/{AppName}/i18n/`
- Assets → `workspace/output/src/{AppName}/assets/`

- Root → `workspace/output/src/{AppName}/main.ts`
- App module → `workspace/output/src/{AppName}/app/app.module.ts`
- Routing → `workspace/output/src/{AppName}/app/app-routing.module.ts`
- Project → `workspace/output/src/{AppName}/package.json`

---

### 1.4 Principes non negociables

- Aucune logique metier dans composants UI.
- Aucun appel HTTP direct dans composants.
- Tous appels via services.
- Retry jamais manuel.
- Retry via RxJS operators.
- Aucun console.log brut.
- Logging structure obligatoire.
- Traductions jamais codees en dur.
- Toujours utiliser ngx-translate.
- Toujours utiliser services Angular.
- Aucun state global hors NgRx.
- Lazy loading obligatoire.
- DTO strictement typés.
- Interceptors obligatoires.

---

## 2. Stack

### 2.1 Identite

- **Stack ID** : `front-angular`
- **Langage** : TypeScript
- **Runtime** : Node.js 22+
- **Framework principal** : Angular 18+
- **Build tool** : Angular CLI
- **Namespace racine** : `{AppNamespace}`

---

### 2.2 Outils

- **Project file** : `workspace/output/src/{AppName}/package.json`
- **Build** :

```bash
ng build
```

- **Serve** :

```bash
ng serve
```

- **Smoke Command**

```bash
ng build
test -f dist/index.html
```

- **Package manager** : npm
- **Lint** : ESLint
- **Format** : Prettier
- **Type-check** : TypeScript

### 2.2.1 Init Commands (idempotent)

```bash
# Skip si package.json existe deja
if [ ! -f "workspace/output/src/{AppName}/package.json" ]; then
  ng new {AppName} --directory workspace/output/src/{AppName} \
    --routing --style=scss --skip-git --skip-tests --strict
fi
```

<!-- CORE_PACKAGES_START -->
```bash
# Auto-genere depuis angular.libs.json -- ne pas editer (utiliser sync_stack_md.py).
(cd workspace/output/src/{AppName} && npm install \
  @angular/core@19.0.5 \
  @angular/common@19.0.5 \
  @angular/router@19.0.5 \
  @angular/forms@19.0.5 \
  @angular/platform-browser@19.0.5 \
  @angular/platform-browser-dynamic@19.0.5 \
  @angular/compiler@19.0.5 \
  @angular/animations@19.0.5 \
  @angular/cdk@19.0.4 \
  @angular/material@19.0.4 \
  @ngrx/store@19.0.0 \
  @ngrx/effects@19.0.0 \
  @ngrx/entity@19.0.0 \
  @ngrx/router-store@19.0.0 \
  @tanstack/angular-query-experimental@5.62.7 \
  rxjs@7.8.1 \
  zone.js@0.15.0 \
  tslib@2.8.1 \
  typescript@5.6.3 \
  @ngx-translate/core@16.0.4 \
  @ngx-translate/http-loader@16.0.0 \
  ngx-logger@5.0.12 \
  @angular-eslint/builder@19.0.2 \
  eslint@9.17.0 \
  typescript-eslint@8.18.1 \
  prettier@3.4.2)
```
<!-- CORE_PACKAGES_END -->

<!-- ONDEMAND_PACKAGES_START -->
```bash
# Auto-genere depuis angular.libs.json (on-demand) -- installe par dev-* si l'US declenche un trigger.
# capability: auth-azure-ad
(cd workspace/output/src/{AppName} && npm install @azure/msal-angular@3.1.0 @azure/msal-browser@3.27.0)

# capability: date-utils
(cd workspace/output/src/{AppName} && npm install dayjs@1.11.13)

# capability: uuid-gen
(cd workspace/output/src/{AppName} && npm install uuid@11.0.5)

# capability: css-classes
(cd workspace/output/src/{AppName} && npm install clsx@2.1.1)
```
<!-- ONDEMAND_PACKAGES_END -->

---

### 2.3 Patterns erreurs compilation

Format standard TypeScript :

error TSxxxx: message

Codes prioritaires :

- TS2307
- TS2322
- TS7006
- TS2339
- TS2554

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/frontend/angular.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id angular`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| @angular/core | 19.0.5 |  |
| @angular/common | 19.0.5 |  |
| @angular/router | 19.0.5 |  |
| @angular/forms | 19.0.5 |  |
| @angular/platform-browser | 19.0.5 |  |
| @angular/platform-browser-dynamic | 19.0.5 |  |
| @angular/compiler | 19.0.5 |  |
| @angular/animations | 19.0.5 |  |
| @angular/cdk | 19.0.4 |  |
| @angular/material | 19.0.4 |  |
| @ngrx/store | 19.0.0 |  |
| @ngrx/effects | 19.0.0 |  |
| @ngrx/entity | 19.0.0 |  |
| @ngrx/router-store | 19.0.0 |  |
| @tanstack/angular-query-experimental | 5.62.7 |  |
| rxjs | 7.8.1 |  |
| zone.js | 0.15.0 |  |
| tslib | 2.8.1 |  |
| typescript | 5.6.3 |  |
| @ngx-translate/core | 16.0.4 |  |
| @ngx-translate/http-loader | 16.0.0 |  |
| ngx-logger | 5.0.12 |  |
| @angular-eslint/builder | 19.0.2 |  |
| eslint | 9.17.0 |  |
| typescript-eslint | 8.18.1 |  |
| prettier | 3.4.2 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| auth-azure-ad | @azure/msal-angular | 3.1.0 | azure.ad, msal, tech-auth-azure |
| auth-azure-ad | @azure/msal-browser | 3.27.0 | azure.ad, msal, tech-auth-azure |
| date-utils | dayjs | 1.11.13 | dates.*format, duree, intervalle.*temps |
| uuid-gen | uuid | 11.0.5 | uuid, guid.*genere, id.*aleatoire |
| css-classes | clsx | 2.1.1 | clsx, classes.*conditionnel |
<!-- LIBS_CATALOG_END -->

## 3. Conventions d'usage

### 3.1 HttpClient — configuration

Toujours utiliser HttpClient Angular.

Fichier :

api/http-client.service.ts

Interdits :

- fetch direct
- XMLHttpRequest manuel

---

### 3.2 RxJS — appels API

Tous appels API via :

Observable

Operators obligatoires :

- retry
- catchError
- map
- switchMap

Retry configure via :

retry()

Ne jamais coder retry manuel.

---

### 3.3 Services Angular

Services obligatoires.

Structure :

services/

Ne jamais appeler API depuis composants.

---

### 3.4 Routing Angular

Router obligatoire.

Routes centralisees dans :

app-routing.module.ts

Lazy loading obligatoire.

Modules charges dynamiquement.

---

### 3.5 Interceptors

Interceptors obligatoires :

- AuthInterceptor
- ErrorInterceptor
- LoggingInterceptor

Structure :

interceptors/

---

### 3.6 Guards

Guards obligatoires :

- AuthGuard

Structure :

guards/

---

### 3.7 State Management

NgRx obligatoire.

Structure :

store/

actions/
reducers/
effects/
selectors/

Aucun state global hors NgRx.

---

### 3.8 Caching navigateur

Gestion via :

NgRx Store + RxJS.

Aucune gestion manuelle.

---

## 4. Integration back → front

- Payload JSON.
- DTO partages.
- Versioning API :

/api/v1/...

- Errors :

RFC 7807 ProblemDetails.

- Client HTTP :

HttpClient + RxJS.

- Authentification :

MSAL Angular.

---

## 5. URLs de developpement

Frontend dev :

http://localhost:4200

Backend :

http://localhost:5099

Configuration API :

environment.ts

```ts
export const environment = {
  apiUrl: "http://localhost:5099"
};
```

---

## 6. State Management

Gestion obligatoire via :

NgRx.

Structure :

store/

auth/
app/

Aucun state global hors NgRx.

---

## 7. Multilingue

Gestion via :

ngx-translate.

Structure :

i18n/

fr.json
en.json

Langue :

?langue=fr

---

## 8. Authentification

Integration obligatoire :

MSAL Angular.

Gestion :

- Login
- Logout
- Token refresh

Token :

Authorization: Bearer JWT

---

## 9. Layout System

Layouts obligatoires.

Structure :

layouts/

main-layout/
auth-layout/

---

## 10. Forms

Gestion via :

Reactive Forms Angular.

Validation via :

Validators Angular.

Jamais validation manuelle.

---

## 11. Styling

CSS moderne obligatoire.

Support :

- SCSS
- Angular Material
- CSS Modules

Structure :

styles/

---

## 12. Logging

Logging structure obligatoire.

Logger :

ngx-logger.

Logs obligatoires :

- HTTP errors
- UI errors
- Auth events

Interdits :

console.log

---

## 13. Performance

Optimisations obligatoires :

- OnPush ChangeDetection
- Lazy loading modules
- trackBy functions

---

## 14. SEO / Meta

Gestion meta via :

Meta Angular service.

---

## 15. Structure finale projet

workspace/output/

src/

{AppName}/

pages/
components/
layouts/
services/
api/
interceptors/
guards/
store/
models/
pipes/
directives/
auth/
utils/
i18n/
assets/

app/

app.module.ts
app-routing.module.ts

main.ts

package.json
angular.json
tsconfig.json

---

## 16. Commandes runtime

Dev :

ng serve

Build :

ng build

Preview :

ng serve --configuration production

Smoke :

ng build

---

## 17. Interdits projet (frontend)

- fetch direct dans composants
- HttpClient brut dans composants
- retry manuel
- console.log
- logique metier dans UI
- state global hors NgRx
- traduction en dur
- TODO
- FIXME
- hardcoded API URL
- hardcoded token
- validation manuelle
- duplication logique HTTP

---

# FIN FEAT
