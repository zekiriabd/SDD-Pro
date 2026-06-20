---
id: ADR-20260605T163200-runtime-sts-prerelease-exceptions
title: Pre-release pins on Next.js, Nuxt, and MAUI stacks — STS exception
status: Accepted
date: 2026-06-05
deciders: SDD_Pro core (auditor v7.0.0-alpha)
supersedes: —
superseded-by: —
---

# Pre-release pins on Next.js, Nuxt, and MAUI stacks — STS exception

## Context

`library-and-stack.md §0` interdit les versions pre-release (`-alpha/-beta/-rc/-preview/-snapshot`) en `versions:` des `.libs.json` actifs sans bypass tracé. Le validateur `validate_libs_catalog.py` flag trois warnings persistants :

- `.claude/stacks/fullstack/next.libs.json` → `versions.next-auth = "5.0.0-beta.25"`
- `.claude/stacks/fullstack/nuxt.libs.json` → `versions.nuxt-ui = "3.0.0-alpha.10"`
- `.claude/stacks/mobiles/maui.libs.json` → `versions.livecharts-maui = "2.0.0-rc4.1"`

Ces trois libs sont chacune **leader incontesté** sur leur niche au moment du pin :
- `next-auth@5.x (Auth.js)` : V4 LTS deprecated par l'équipe Vercel (annonce 2025-08). Migration V5 requise pour App Router + Edge runtime ; aucune alternative aussi mature côté React Server Components.
- `nuxt-ui@3.x` : refonte complète sur Tailwind v4 + Reka UI ; v2 incompatible avec Nuxt 4 (Vue 3.5 stable). Pas d'alternative complète design system pour Nuxt 4.
- `livecharts-maui@2.0.0-rc4.1` : v1 ne supporte plus .NET 9/10 MAUI. Alternative `Microcharts.Maui` insuffisante (pas de zoom/pan/animations).

Les 3 combos correspondants (`fullstack/next`, `fullstack/nuxt`, `mobiles/maui`) sont marqués 🟡 **expérimental** dans `validated-combos.md` — pas C1/C2 (cibles production-ready).

## Decision

**STS exception tracée** pour les 3 versions ci-dessus, valide jusqu'à GA des packages amont :

| Stack | Lib | Version pinnée | Critère de levée |
|---|---|---|---|
| `fullstack/next` | next-auth | 5.0.0-beta.25 | Auth.js v5 GA (estimé Q3 2026) |
| `fullstack/nuxt` | nuxt-ui | 3.0.0-alpha.10 | Nuxt UI v3 stable (estimé Q4 2026) |
| `mobiles/maui` | livecharts-maui | 2.0.0-rc4.1 | LiveCharts2 v2 GA (estimé Q1 2027) |

Chaque `.libs.json` concerné ajoute dans Project Config (champ libre `runtime-exception`) :

```json
"runtime-exception": {
  "lib": "next-auth",
  "reason": "v4 LTS deprecated upstream — no V5 GA yet, no mature alternative for App Router",
  "review-by": "2026-09-30",
  "adr": "ADR-20260605T163200-runtime-sts-prerelease-exceptions"
}
```

`validate_libs_catalog.py` est étendu pour downgrader le warning à `INFO` lorsque le tuple `(stack, lib)` est listé dans cet ADR (matcher YAML inline).

## Consequences

### Positives
- Les 3 stacks expérimentaux peuvent être chargés sans warning bloquant dans le smoke test (réduit le bruit pour les utilisateurs des combos validés C1/C2).
- La levée des pins est tracée par date cible — l'agent `arch` flag automatiquement un `[STACK_RUNTIME_REVIEW_DUE]` si `now > review-by`.
- Trace `git blame` claire pour comprendre la décision.

### Negatives
- Les 3 stacks restent expérimentaux (🟡) et ne peuvent pas être promus 🟢 tant que les libs ne sont pas GA.
- Risque cassure mineure si breaking change pre→GA des libs.

### Suivi
- Re-évaluation trimestrielle (review-by dates ci-dessus).
- Si l'une des libs reste pre-release au-delà de 6 mois post-`review-by`, fork ou alternative à arbitrer par Tech Lead.

## References
- `library-and-stack.md §0` (runtime LTS policy)
- `validated-combos.md` (statut 🟡 des 3 stacks)
- `error-classification.md` → classe `[RUNTIME_STS_EXCEPTION]` (déjà définie §1.5)
