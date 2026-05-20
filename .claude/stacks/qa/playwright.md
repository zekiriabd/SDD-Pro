# QA Stack — Playwright E2E (opt-in, v7.0.0)

> **Validation** : 🟡 experimental — schema opt-in, non actif par défaut.
> **But** : combler le trou E2E navigateur. L'API Gate v7 ne teste que
> le contrat HTTP back↔front, jamais le rendu SPA dans un vrai navigateur.
> Playwright fournit ≥ 1 happy path par US matérialisée.

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

## 6. Anti-derive

- ❌ E2E contre prod (jamais — toujours in-memory backend + preview SPA local)
- ❌ Tests dépendant de l'ordre d'exécution
- ❌ Sleeps fixes (`page.waitForTimeout(3000)`) — utiliser `expect().toBeVisible()` waits
- ❌ Capture réseau prod (HAR files anonymisés OK pour debug, jamais commit)

## 7. Statut implémentation

**v7.0.0** : stack documenté, **infrastructure pas encore câblée** dans
`qa.md` ni `qa-generate.md`. Création migration `qa_e2e` table + STEP 8.bis
reporté en v7.1.

**Recommandation** : activer `E2EMode: smoke` sur 1 FEAT pilote en local,
mesurer coût marginal. Si < $0.50/FEAT et catches ≥ 1 bug réel → green-light
pour câblage pipeline.

## 8. Pourquoi pas `qa/cypress`

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
