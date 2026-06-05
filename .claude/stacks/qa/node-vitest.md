# QA Stack — Vitest + Testing Library + c8

> §2.4 (Librairies) régénérée depuis `node-vitest.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id node-vitest`).

Status: Stable
Validation: 🟢 reference (validated combo CMS — kotlin-spring-boot + react + shadcn + azure-ad, 2026-05-13)
QA FEAT ID: node-vitest
Scope: tests unitaires backend Node.js + frontend React/Vue

---

## 1. Scope

Tests unitaires pour :
- **Backend Node.js** (Express, Fastify, NestJS)
- **Frontend React** (avec React Testing Library)
- **Frontend Vue 3** (avec Vue Test Utils)

Pour Angular, utiliser `qa/angular-jasmine.md` (Jasmine est l'outil
natif via `ng test`).

---

## 2. Tooling

### 2.1 Test runner
- **Vitest** (compatible Jest API, plus rapide via Vite)

### 2.2 Coverage tool
- **c8** ou **@vitest/coverage-v8** (intégré à Vitest)
- Output : `lcov.info` + `coverage-summary.json`

### 2.3 Mock library
- **vitest** built-in (`vi.fn()`, `vi.spyOn()`, `vi.mock()`)
- Pour tests React : `@testing-library/react`
- Pour tests Vue : `@vue/test-utils`

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/qa/node-vitest.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id node-vitest`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| vitest | 2.1.8 |  |
| @vitest/coverage-v8 | 2.1.8 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| dom-env | happy-dom | 16.0.1 | happy-dom, test.*composant, test.*ui |
| dom-env | jsdom (alt) | 25.0.1 | jsdom, test.*composant, test.*ui |
| test-react | @testing-library/react | 16.1.0 | test.*react, testing-library, frontend.*react |
| test-react | @testing-library/jest-dom | 6.6.3 | test.*react, testing-library, frontend.*react |
| test-react | @testing-library/user-event | 14.5.2 | test.*react, testing-library, frontend.*react |
| test-vue | @vue/test-utils | 2.4.6 | test.*vue, vue-test-utils, frontend.*vue |
| api-tests | supertest | 7.0.0 | api.*test, supertest, integration.*http, qa.*api-tests |
| api-tests | @types/supertest | 6.0.2 | api.*test, supertest, integration.*http, qa.*api-tests |
| http-mock | msw | 2.7.0 | msw, mock.*service.*worker, intercept.*http |
<!-- LIBS_CATALOG_END -->

## 3. Init Commands (idempotent)

Si Vitest n'est pas dans `package.json` :

<!-- CORE_PACKAGES_START -->
```bash
# Auto-genere depuis node-vitest.libs.json -- ne pas editer (utiliser sync_stack_md.py).
(cd workspace/output/src/{BackendName} && pnpm add \
  vitest@2.1.8 \
  @vitest/coverage-v8@2.1.8)
```
<!-- CORE_PACKAGES_END -->

<!-- ONDEMAND_PACKAGES_START -->
```bash
# Auto-genere depuis node-vitest.libs.json (on-demand) -- installe par dev-* si l'US declenche un trigger.
# capability: dom-env
(cd workspace/output/src/{BackendName} && pnpm add happy-dom@16.0.1)
# OU (alt) : (cd workspace/output/src/{BackendName} && pnpm add jsdom@25.0.1)

# capability: test-react
(cd workspace/output/src/{BackendName} && pnpm add @testing-library/react@16.1.0 @testing-library/jest-dom@6.6.3 @testing-library/user-event@14.5.2)

# capability: test-vue
(cd workspace/output/src/{BackendName} && pnpm add @vue/test-utils@2.4.6)

# capability: api-tests
(cd workspace/output/src/{BackendName} && pnpm add supertest@7.0.0 @types/supertest@6.0.2)

# capability: http-mock
(cd workspace/output/src/{BackendName} && pnpm add msw@2.7.0)
```
<!-- ONDEMAND_PACKAGES_END -->

Configuration `vitest.config.ts` (créer si absent) :

```typescript
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    globals: true,
    environment: 'happy-dom',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'json-summary'],
      reportsDirectory: './coverage',
    },
  },
})
```

Ajouter au `package.json` :
```json
"scripts": {
  "test": "vitest run",
  "test:coverage": "vitest run --coverage"
}
```

---

## 4. Project structure

```
workspace/output/src/{AppName}/
├── src/
│   ├── components/
│   │   └── Login.tsx
│   └── services/
│       └── auth.service.ts
└── __tests__/                        # ou *.test.ts adjacents
    ├── components/
    │   └── Login.test.tsx
    └── services/
        └── auth.service.test.ts
```

Convention adjacente acceptée aussi :
```
src/components/
├── Login.tsx
└── Login.test.tsx
```

---

## 5. Test patterns

### 5.1 Service test (mock dependencies)

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { AuthService } from '../auth.service'

describe('AuthService', () => {
  let mockHttp: { post: ReturnType<typeof vi.fn> }
  let sut: AuthService

  beforeEach(() => {
    mockHttp = { post: vi.fn() }
    sut = new AuthService(mockHttp as any)
  })

  it('login_withValidCredentials_returnsToken', async () => {
    // Arrange
    mockHttp.post.mockResolvedValue({ data: { token: 'abc' } })

    // Act
    const result = await sut.login('user@test.com', 'pass')

    // Assert
    expect(result).toBeDefined()
    expect(result.token).toBe('abc')
  })
})
```

### 5.2 React component test

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen, userEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import { Login } from './Login'

describe('Login', () => {
  it('renders_email_and_password_fields', () => {
    render(<Login onSubmit={vi.fn()} />)
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  it('calls_onSubmit_with_credentials', async () => {
    const handleSubmit = vi.fn()
    render(<Login onSubmit={handleSubmit} />)
    await userEvent.type(screen.getByLabelText(/email/i), 'user@test.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'pass')
    await userEvent.click(screen.getByRole('button', { name: /se connecter/i }))
    expect(handleSubmit).toHaveBeenCalledWith({ email: 'user@test.com', password: 'pass' })
  })
})
```

### 5.3 Vue component test

```typescript
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Login from './Login.vue'

describe('Login.vue', () => {
  it('renders_form_fields', () => {
    const wrapper = mount(Login)
    expect(wrapper.find('input[type="email"]').exists()).toBe(true)
    expect(wrapper.find('input[type="password"]').exists()).toBe(true)
  })
})
```

---

## 6. Run commands

### 6.1 Test command

```bash
cd workspace/output/src/{AppName}
npm test
```

### 6.2 Coverage command

```bash
cd workspace/output/src/{AppName}
npm run test:coverage
```

### 6.3 Linter

```bash
cd workspace/output/src/{AppName}
npx eslint . --max-warnings 0
```

---

## 7. Coverage output format

Format : **lcov.info** + **coverage-summary.json**
Path :
- `workspace/output/src/{AppName}/coverage/lcov.info`
- `workspace/output/src/{AppName}/coverage/coverage-summary.json`

Le script `parse_coverage.py` détecte les deux et utilise lcov par
défaut (plus stable cross-tool).

---

## 8. Naming conventions

- Fichiers : `{module}.test.ts` ou `__tests__/{module}.test.ts`
- `describe` blocks : nom du module/composant
- `it` blocks : `{action}_{scenario}_{expected}` (camelCase + underscore mix toléré)

---

## 9. Forbidden patterns

- `setTimeout`/`setInterval` non motivés — utiliser `vi.useFakeTimers()`
- Connexion à une vraie API — utiliser `msw` ou `vi.mock`
- Tests qui partagent un état mutable global
- `it.only` ou `describe.only` (oubli en prod)
