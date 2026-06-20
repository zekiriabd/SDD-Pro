# QA Stack — Angular Jasmine + Karma + istanbul

> §2.4 (Librairies) régénérée depuis `angular-jasmine.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id angular-jasmine`).

Status: Bench-validated
Validation: 🟢 bench (bench 2026-06-05 runtime PASS sur combos C8/C11/C13 — Angular 18 + Jasmine ; pipeline /sdd-full end-to-end pending v7.1)
Support: 🟢 Supporté best-effort (SLA Tier 2, cf. SLA.md §1.1) — pas de garantie idempotence /sdd-full. Promu de experimental le 2026-06-07 (audit Sprint 2 CRIT-11 closure).
QA FEAT ID: angular-jasmine
Scope: tests unitaires frontend Angular

---

## 1. Scope

Tests unitaires pour frontends Angular.
S'applique aux projets `workspace/output/src/{AppName}/` typés Angular.

Jasmine + Karma sont les outils par défaut générés par `ng new`.
Cette stack documente leur usage standard, sans migration vers Jest.

---

## 2. Tooling

### 2.1 Test runner
- **Karma** (test runner browser-based)
- **ChromeHeadless** (par défaut)

### 2.2 Test framework
- **Jasmine** (BDD-style, intégré par défaut Angular)

### 2.3 Coverage tool
- **istanbul** (intégré au CLI Angular via `karma-coverage`)
- Output : `lcov.info` + `coverage-summary.json`

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/qa/angular-jasmine.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id angular-jasmine`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| jasmine-core | 5.5.0 |  |
| @types/jasmine | 5.1.4 |  |
| karma | 6.4.4 |  |
| karma-jasmine | 5.1.0 |  |
| karma-chrome-launcher | 3.2.0 |  |
| karma-coverage | 2.2.1 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| test-reporter-html | karma-jasmine-html-reporter | 2.1.0 | html.*reporter, karma.*html |
| ng-mocks | ng-mocks | 14.13.2 | ng-mocks, MockBuilder, MockComponent |
<!-- LIBS_CATALOG_END -->

## 3. Init Commands (idempotent)

Pour un projet créé via `ng new`, tout est déjà configuré. Le block ci-dessous
est utile uniquement si vous installez Jasmine/Karma sur un projet existant.

<!-- CORE_PACKAGES_START -->
```bash
# Auto-genere depuis angular-jasmine.libs.json -- ne pas editer (utiliser sync_stack_md.py).
(cd workspace/output/src/{AppName} && npm install \
  jasmine-core@5.5.0 \
  @types/jasmine@5.1.4 \
  karma@6.4.4 \
  karma-jasmine@5.1.0 \
  karma-chrome-launcher@3.2.0 \
  karma-coverage@2.2.1)
```
<!-- CORE_PACKAGES_END -->

<!-- ONDEMAND_PACKAGES_START -->
```bash
# Auto-genere depuis angular-jasmine.libs.json (on-demand) -- installe par dev-* si l'US declenche un trigger.
# capability: test-reporter-html
(cd workspace/output/src/{AppName} && npm install karma-jasmine-html-reporter@2.1.0)

# capability: ng-mocks
(cd workspace/output/src/{AppName} && npm install ng-mocks@14.13.2)
```
<!-- ONDEMAND_PACKAGES_END -->

Si manquant, vérifier `karma.conf.js` :

```javascript
module.exports = function (config) {
  config.set({
    basePath: '',
    frameworks: ['jasmine', '@angular-devkit/build-angular'],
    plugins: [
      require('karma-jasmine'),
      require('karma-chrome-launcher'),
      require('karma-jasmine-html-reporter'),
      require('karma-coverage'),
      require('@angular-devkit/build-angular/plugins/karma'),
    ],
    coverageReporter: {
      dir: require('path').join(__dirname, './coverage'),
      subdir: '.',
      reporters: [
        { type: 'html' },
        { type: 'lcovonly' },
        { type: 'text-summary' },
        { type: 'json-summary' }
      ],
      check: {
        global: { lines: 80 }
      }
    },
    reporters: ['progress', 'kjhtml', 'coverage'],
    browsers: ['ChromeHeadless'],
    singleRun: true,
    restartOnFileChange: false
  })
}
```

---

## 4. Project structure

```
workspace/output/src/{AppName}/
├── src/
│   ├── app/
│   │   ├── auth/
│   │   │   ├── login.component.ts
│   │   │   ├── login.component.html
│   │   │   ├── login.component.FEAT.ts          # test (Jasmine)
│   │   │   ├── auth.service.ts
│   │   │   └── auth.service.FEAT.ts             # test (Jasmine)
│   │   └── ...
│   ├── test.ts                                   # bootstrap tests
│   └── ...
├── angular.json
└── karma.conf.js
```

Convention : tests sont **adjacents** au code (`*.FEAT.ts`).

---

## 5. Test patterns (Jasmine + Angular TestBed)

### 5.1 Service test (TestBed + spy)

```typescript
import { TestBed } from '@angular/core/testing'
import { HttpClient } from '@angular/common/http'
import { of } from 'rxjs'
import { AuthService } from './auth.service'

describe('AuthService', () => {
  let service: AuthService
  let httpSpy: jasmine.SpyObj<HttpClient>

  beforeEach(() => {
    httpSpy = jasmine.createSpyObj('HttpClient', ['post'])
    TestBed.configureTestingModule({
      providers: [
        AuthService,
        { provide: HttpClient, useValue: httpSpy }
      ]
    })
    service = TestBed.inject(AuthService)
  })

  it('login_with_valid_credentials_returns_token', (done) => {
    // Arrange
    httpSpy.post.and.returnValue(of({ token: 'abc' }))

    // Act
    service.login('user@test.com', 'pass').subscribe(result => {
      // Assert
      expect(result.token).toBe('abc')
      expect(httpSpy.post).toHaveBeenCalledOnceWith(
        jasmine.any(String),
        { email: 'user@test.com', password: 'pass' }
      )
      done()
    })
  })
})
```

### 5.2 Component test (TestBed + ComponentFixture)

```typescript
import { ComponentFixture, TestBed } from '@angular/core/testing'
import { ReactiveFormsModule } from '@angular/forms'
import { LoginComponent } from './login.component'
import { AuthService } from './auth.service'

describe('LoginComponent', () => {
  let component: LoginComponent
  let fixture: ComponentFixture<LoginComponent>
  let authSpy: jasmine.SpyObj<AuthService>

  beforeEach(async () => {
    authSpy = jasmine.createSpyObj('AuthService', ['login'])
    await TestBed.configureTestingModule({
      imports: [ReactiveFormsModule, LoginComponent],
      providers: [{ provide: AuthService, useValue: authSpy }]
    }).compileComponents()

    fixture = TestBed.createComponent(LoginComponent)
    component = fixture.componentInstance
    fixture.detectChanges()
  })

  it('renders_email_and_password_fields', () => {
    const compiled = fixture.nativeElement as HTMLElement
    expect(compiled.querySelector('input[type="email"]')).toBeTruthy()
    expect(compiled.querySelector('input[type="password"]')).toBeTruthy()
  })

  it('submits_form_calls_authService_login', () => {
    component.loginForm.setValue({ email: 'u@t.com', password: 'p' })
    component.onSubmit()
    expect(authSpy.login).toHaveBeenCalledOnceWith('u@t.com', 'p')
  })
})
```

---

## 6. Run commands

### 6.1 Test command + coverage

```bash
cd workspace/output/src/{AppName}
ng test --code-coverage --watch=false --browsers=ChromeHeadless
```

> **Note CI** : `--browsers=ChromeHeadless` est obligatoire en
> environnement sans display. Ajuster selon installation.

### 6.2 Linter

```bash
cd workspace/output/src/{AppName}
ng lint
# OU
npx eslint src/ --max-warnings 0
```

### 6.3 Type checker

```bash
cd workspace/output/src/{AppName}
npx tsc --noEmit
```

---

## 7. Coverage output format

Format : **lcov.info** + **coverage-summary.json** (istanbul)
Path :
- `workspace/output/src/{AppName}/coverage/lcov.info`
- `workspace/output/src/{AppName}/coverage/coverage-summary.json`

Le script `parse_coverage.py` parse les deux. Préférence pour
lcov (plus stable cross-version).

---

## 8. Naming conventions

- Fichiers : `{name}.FEAT.ts` (adjacent au code)
- `describe` blocks : nom de la classe/component (`AuthService`, `LoginComponent`)
- `it` blocks : `{action}_{scenario}_{expected}` (snake_case toléré)
  - Ex. : `login_with_valid_credentials_returns_token`
  - Ex. : `renders_email_and_password_fields`

---

## 9. Forbidden patterns

- `setTimeout`/`setInterval` non motivés — utiliser `fakeAsync` + `tick()`
- HTTP réel — utiliser `HttpClientTestingModule`
- État partagé global mutable
- `fdescribe` ou `fit` (focus oublié en prod)
- `xdescribe` ou `xit` sans raison documentée
