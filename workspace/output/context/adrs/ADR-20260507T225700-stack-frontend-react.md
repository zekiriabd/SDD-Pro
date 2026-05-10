# ADR-20260507T225700 -- Frontend stack -- React + Vite + shadcn/ui

- **Statut** : Accepted
- **Date** : 2026-05-07
- **Auteur** : arch
- **Phase** : 4-ARCH

---

## Context

Le projet simfront est une SPA consommant l'API simback. Le Tech Lead a selectionne React 19 + Vite + shadcn/ui dans workspace/input/stack/stack.md. shadcn/ui fournit des composants accessibles bases sur Radix UI avec Tailwind CSS v4.

---

## Decision

Le frontend est implemente avec React 19 + TypeScript + Vite 8 + Tailwind CSS v4 + shadcn/ui (style new-york, stacks `frontend/react.md` + `ui/shadcn.md`). shadcn@4.6.0 utilise pour l'init (shadcn@latest a un bug workspace config au 2026-05-07).

---

## Consequences

**Positifs :**
- TanStack Query pour le server state cache (retry, invalidation automatique).
- TanStack Router file-based avec routeTree autogenere.
- React Hook Form + Zod pour la validation type-safe.
- shadcn/ui composants copy-pastable (pas de dep tierce gere, code editable).

**Negatifs / dette acceptee :**
- shadcn@latest a un bug "workspace config" au 2026-05-07 -- utiliser shadcn@4.6.0 pour init.
- pnpm workspaces (Turborepo) du stack non mis en place (simfront standalone, pas de monorepo).

---

## Alternatives considerees

- NONE -- impose par workspace/input/stack/stack.md (## Active Tech Specs + ## Active UI Specs).

---

## Liens

- Stack : `.claude/stacks/frontend/react.md`
- Stack : `.claude/stacks/ui/shadcn.md`
