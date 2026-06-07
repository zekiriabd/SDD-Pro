# QA Stack — Playwright E2E (opt-in, v7.0.0)

Status: Experimental
Validation: 🟡 experimental (schema opt-in, non actif par défaut)
Support: ⚠ Non supporté commercialement (audit C3, 2026-06-06) — exclu du SLA produit. Voir CLAUDE.md §6 et docs/validated-combos.md.
QA FEAT ID: playwright
Scope: tests E2E navigateur multi-browser (combler trou API Gate v7)

> **But** : combler le trou E2E navigateur. L'API Gate v7 ne teste que
> le contrat HTTP back↔front, jamais le rendu SPA dans un vrai navigateur.
> Playwright fournit ≥ 1 happy path par US matérialisée.

---

## 1. Activation

Project Config (`workspace/input/stack/stack.md`) :

```yaml
E2EMode: off    # off (default) | smoke | happy-paths | full
E2EMinPerUs: 1
E2ETimeoutSec: 300
```

| Mode | Comportement | Coût wall-clock |
|---|---|---|
| `off` | skip (défaut) | 0 |
| `smoke` | 1 test : `app loads + login form visible` | +30-60s |
| `happy-paths` | 1 test par US (parcours nominal AC-1) | +2-5 min |
| `full` | tous AC observables UI + edge cases élicitor | +10-30 min |

## 2. Tooling

| Stack frontend | Adaptateur Playwright |
|---|---|
| `frontend/react` | `@playwright/test` (TypeScript) |
| `frontend/vue` | `@playwright/test` (TypeScript) |
| `frontend/angular` | `@playwright/test` (TypeScript) |
| `frontend/blazor-webassembly` | `Microsoft.Playwright` (.NET, BunitContext + browser) |

Install (Tech Lead manuel, pas `arch`) :
```bash
# Node-based stacks
npm install -D @playwright/test
npx playwright install --with-deps

# Blazor WASM
dotnet add package Microsoft.Playwright
dotnet build && pwsh bin/Debug/net10.0/playwright.ps1 install
```

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/qa/playwright.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id playwright`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| @playwright/test | 1.48.2 | Test runner E2E Node-based stacks (react, vue, angular). |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| blazor-e2e | Microsoft.Playwright | 1.48.0 | frontend/blazor-webassembly, blazor.*e2e, \.cshtml |
<!-- LIBS_CATALOG_END -->

## 3. Layout généré

```
workspace/output/src/{AppName}/
├── e2e/
│   ├── playwright.config.ts
│   ├── fixtures/
│   │   ├── auth.fixture.ts            # JWT mocké ou test user real
│   │   └── seed-data.fixture.ts
│   ├── feat-{n}/
│   │   ├── us-{n}-1-{Name}.spec.ts
│   │   ├── us-{n}-2-{Name}.spec.ts
│   │   └── ...
```

## 4. Critère de passage

```
status = "INFRA_BLOCKED"  if browsers not installed OR backend unreachable
status = "SKIPPED"        elif E2EMode: off OR no US has UI ACs
status = "FAIL"           elif tests_failed >= 1
status = "PASS"           elif tests_total >= E2EMinPerUs × N_us_with_ui
status = "WARN"           else
```

Aligné avec les statuts API Gate v7.0.0 (cf. `rules/build-and-loop.md §1.3`).

## 5. Intégration pipeline

Phase 5 (QA) — STEP 8.bis (nouveau, conditionnel) :
1. Skip si `E2EMode: off`
2. Démarrer backend in-memory (réutilise WebApplicationFactory de la
   gate API) + serve build SPA (`vite preview` / `ng serve` / `dotnet run`)
3. Exécuter `npx playwright test e2e/feat-{n}/` (filter par FEAT)
4. Parser le résultat JSON Playwright → `workspace/output/qa/feat-{n}/e2e.json`
5. Persist `console.db` table `qa_e2e` (migration v3 à créer)

## 6. Exemples concrets par mode

### 6.1 Mode `smoke` — 1 spec global

`e2e/smoke.spec.ts` (React) :
```typescript
import { test, expect } from '@playwright/test';

test('app loads and login form is visible', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/MyApp/);
  await expect(page.getByLabel('Email')).toBeVisible();
  await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible();
});
```

### 6.2 Mode `happy-paths` — 1 spec par US (AC-1 nominal)

`e2e/feat-1/us-1-2-Login.spec.ts` (couvre AC-1 de l'US 1-2) :
```typescript
import { test, expect } from '@playwright/test';
import { mockAuth } from '../fixtures/auth.fixture';

test('AC-1: login with valid credentials redirects to /dashboard', async ({ page }) => {
  await mockAuth(page, { user: 'alice@test.com', role: 'admin' });
  await page.goto('/login');
  await page.getByLabel('Email').fill('alice@test.com');
  await page.getByLabel('Password').fill('correct-horse-battery');
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByText(/welcome alice/i)).toBeVisible();
});
```

### 6.3 Mode `full` — happy + edge cases élicitor

`e2e/feat-1/us-1-2-Login.spec.ts` ajouts (FAIL-N + EDGE-N de la FEAT) :
```typescript
test('FAIL-1: invalid password shows error without leaking user existence', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Email').fill('alice@test.com');
  await page.getByLabel('Password').fill('wrong');
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page.getByRole('alert')).toHaveText(/invalid credentials/i);
  await expect(page).toHaveURL(/\/login/);  // pas de redirect
});

test('EDGE-2: rate-limit after 5 failed attempts', async ({ page }) => {
  for (let i = 0; i < 5; i++) {
    await page.goto('/login');
    await page.getByLabel('Email').fill('alice@test.com');
    await page.getByLabel('Password').fill('wrong');
    await page.getByRole('button', { name: /sign in/i }).click();
  }
  await expect(page.getByRole('alert')).toHaveText(/too many attempts/i);
});
```

### 6.4 Fixtures partagées

`e2e/fixtures/auth.fixture.ts` :
```typescript
import { Page } from '@playwright/test';

export async function mockAuth(page: Page, opts: { user: string; role: string }) {
  // Intercepte /api/auth/me pour retourner user + role sans appel réseau
  await page.route('**/api/auth/me', route =>
    route.fulfill({ json: { email: opts.user, role: opts.role, exp: 9999999999 } }),
  );
  // Inject JWT mocké dans localStorage (lu par le client React)
  await page.addInitScript(token => {
    localStorage.setItem('auth_token', token);
  }, 'mocked.jwt.token');
}
```

### 6.5 Mapping AC → spec

| AC (US 1-2-Login) | Spec name | Mode requis |
|---|---|---|
| AC-1 (happy path) | `'AC-1: login with valid credentials...'` | `happy-paths`, `full` |
| AC-2 (admin role redirect) | `'AC-2: admin user sees /admin...'` | `happy-paths`, `full` |
| FAIL-1 (élicitor) | `'FAIL-1: invalid password...'` | `full` |
| EDGE-2 (élicitor) | `'EDGE-2: rate-limit...'` | `full` |

Convention : 1 `test()` par AC, nom préfixé `AC-N:` / `FAIL-N:` / `EDGE-N:`
pour traçabilité automatique vers `spec-compliance-reviewer`.

## 7. Edge cases & pièges connus

| Piège | Symptôme | Solution |
|---|---|---|
| **Race condition login + redirect** | Test flaky 5–20 % | `await page.waitForURL(/\/dashboard/)` au lieu d'`expect(page).toHaveURL` |
| **CI sans display** | Browsers crash en CI Linux | `npx playwright install --with-deps` (installe Xvfb + deps OS) |
| **Backend in-memory ≠ prod** | E2E pass localement mais 500 en prod | Maintenir 1 spec contre staging (mode `containers` futur) |
| **JWT mocké invalide après refresh** | Test échoue après ~1h | Set `exp: 9999999999` (futur lointain) dans mock |
| **Vite preview port collision** | `EADDRINUSE :4173` | `PORT=0` (port aléatoire) + lecture stdout pour URL |
| **Blazor WASM lent à boot** | `expect.toBeVisible` timeout 5s | Augmenter `timeout: 15000` global pour les specs Blazor |

## 8. Anti-derive

- ❌ E2E contre prod (jamais — toujours in-memory backend + preview SPA local)
- ❌ Tests dépendant de l'ordre d'exécution
- ❌ Sleeps fixes (`page.waitForTimeout(3000)`) — utiliser `expect().toBeVisible()` waits
- ❌ Capture réseau prod (HAR files anonymisés OK pour debug, jamais commit)
- ❌ Tests authentifiés sans fixture mockAuth (auth réelle = flaky + couplage Azure AD)
- ❌ Sélecteurs CSS fragiles (`.btn-primary > span > i`) — préférer `getByRole`, `getByLabel`, `getByText`

## 9. Statut implémentation

**v7.0.0** : ✅ stack câblé. `qa.md` STEP 8.bis invoque Playwright si
`E2EMode != off`, persiste dans `console.db` table `qa_e2e` (migration
`0003_add-qa-e2e-table.sql`). **Opt-in strict** (`off` par défaut) —
aucun coût ajouté tant que le Tech Lead n'active pas via Project Config.
Install Playwright reste **manuel** (Tech Lead), pas `arch` Phase A.

**Recommandation** : activer `E2EMode: smoke` sur 1 FEAT pilote en local,
mesurer coût marginal. Si < $0.50/FEAT et catches ≥ 1 bug réel → green-light
pour câblage pipeline.

## 10. Pourquoi pas `qa/cypress`

Choix Playwright > Cypress (audit 2026-05-20) :
- Multi-navigateur natif (Chromium + Firefox + WebKit + Edge)
- Plus rapide (parallélisation native)
- Auto-wait intégré (`expect().toBeVisible()`)
- Maintenance Microsoft (LTS stable)
- API `.NET` officielle (couvre Blazor stack)

Cypress reste un choix valide mais demanderait un 2e stack `qa/cypress.md`
duplicant 90 % du contenu — préférer Playwright comme unique stack E2E.

---

*Source : risk audit 2026-05-20 §6.5 "Gaps non couverts — E2E navigateur".*
