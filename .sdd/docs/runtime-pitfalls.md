# Runtime pitfalls — pièges multi-stack documentés (post-mortem bench)

> **Hoisted from `rules/library-and-stack.md §B.7`** lors de l'audit P1 tokens
> 2026-06-08 (économie ~2.5 KB par dispatch dev-backend/dev-frontend, lue à la
> demande uniquement quand un bug runtime correspondant est suspecté).
>
> **Source-first principle** : tout nouveau bug runtime spécifique à un stack
> détecté en CI/bench doit être patché ici **AVANT** le fix code applicatif
> (cf. `docs/principles/source-first.md §1`).

5 bugs détectés bench multi-stack qui n'apparaissent que **runtime** (compile vert, smoke OK, mais comportement cassé une fois le navigateur réel impliqué).

---

## 1. CORS `localhost` ≠ `127.0.0.1`

**Symptôme** : UI `Impossible de joindre l'API` malgré curl OK CLI.

**Cause** : navigateur sur `127.0.0.1:5186` envoie `Origin: http://127.0.0.1:5186`,
allowlist contient seulement `localhost:5186` → preflight 403 → `TypeError: Failed to fetch`.

**Convention** : allowlist **multi-host explicite** pour chaque port :
```
http://localhost:{port}
http://127.0.0.1:{port}
```

---

## 2. `<input type=number>` coerce → state framework cassé (Vue 3 / Angular 18)

**Symptôme** : bouton Calculate `disabled` côté Vue 3 / Angular 18.

**Cause** : `<input type=number>` + `v-model`/`[(ngModel)]` coerce DOM string
en `number`. State `ref<string>` reçoit `number` → `.trim()` throw silencieusement.

**Convention** :
- Vue : `ref<number | null>(null)` + `v-model.number`
- Angular : `signal<number | null>(null)`
- React/Blazor : non concernés (string ou `int?` natif)

---

## 3. JMustache rejette `null` keys strict

**Symptôme** : Spring Boot + Mustache → 500 sur `Model.addAttribute("x", null)`.

**Convention** : populer `Model` avec strings vides (`""`) + flags booléens
dérivés `hasX`/`hasError` pour sections conditionnelles
(`{{#hasX}}…{{/hasX}}`, jamais `{{#x}}…{{/x}}`).

---

## 4. `pydantic-core` no-wheel sur Python récent

**Symptôme** : `pip install pydantic==2.10.3` fail wheel-build sur Python 3.14.

**Convention** : pin `pydantic>=2.11` si Python ≥ 3.13. Pour Python 3.12 LTS,
pin 2.10.x OK. Vérifier wheels PyPI avant pin strict.

---

## 5. bUnit `.Change()` ≠ `@bind:event="oninput"` (post-mortem FEAT 3 tests)

**Symptôme** : bUnit teste Blazor WASM avec `cut.Find("input").Change("5")` →
`Bunit.MissingEventHandlerException : element does not have event handler 'onchange',
has 'oninput'`.

**Cause** : `.Change()` déclenche un événement `onchange`, mais le composant utilise
`@bind:event="oninput"` (binding immediate). Mismatch event handler → exception bUnit.

**Convention obligatoire** :
- Avec `@bind:event="oninput"` (binding immediate) → tests bUnit avec `.Input("value")`
- Avec `@bind` simple (binding onchange) → tests avec `.Change("value")`
- API bUnit v2 : `BunitContext` + `Render<T>()` (au lieu de `TestContext` + `RenderComponent<T>()` v1 obsolètes)

---

## Lien avec autres règles

- `rules/library-and-stack.md` Partie B (CORS pattern stack-aware) — résume la convention canonique CORS, ce fichier complète avec les pièges runtime spécifiques.
- `rules/build-and-loop.md` Partie A (QA API Gate) — doit inclure ≥ 1 test CORS preflight (OPTIONS avec Origin) par endpoint exposé à la SPA.
- `docs/principles/source-first.md §1` : tout bug CORS/coercion/null-strict en runtime → patch cette doc AVANT le fix code applicatif.
