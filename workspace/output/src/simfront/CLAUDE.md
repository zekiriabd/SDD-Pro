---
generated-by: agent arch
generated-at: 2026-05-07T22:56:55Z
stack-md-hash: 0094A995
project-type: frontend
project-name: simfront
active-stacks:
  - .claude/stacks/frontend/react.md
  - .claude/stacks/ui/shadcn.md
  - .claude/stacks/auth/azure-ad.md
---

# simfront -- Frontend Project Context

## Project Config (subset)
- AppName: simfront
- AppNamespace: simfront
- LibStrategy: openapi-codegen

## Architecture
React 19 SPA avec Vite 8, Tailwind CSS v4, shadcn/ui (style new-york).
TanStack Query (server state) + TanStack Router (file-based routing).
React Hook Form + Zod (validation). i18next (FR/EN).

Route -> Page -> Component -> Hook (useQuery/useMutation) -> API client -> Backend

## Layer -> Path Mapping
- Route (file-based)    -> src/routes/
- Page                  -> src/pages/
- Component metier      -> src/components/
- Component UI shadcn   -> src/components/ui/ (genere par npx shadcn@latest add, jamais main-edit)
- Layout                -> src/layouts/
- Hook (server state)   -> src/hooks/
- API client            -> src/api/
- Schema Zod            -> src/schemas/
- Auth MSAL             -> src/auth/
- Lib helpers shadcn    -> src/lib/ (contient utils.ts avec cn())
- Utils metier          -> src/utils/
- i18n                  -> src/i18n/ (lang/translation.json + index.ts)
- Assets                -> src/assets/
- Global CSS + tokens   -> src/index.css (@theme Tailwind v4)

## Build Command
cd workspace/output/src/simfront && npm run build

## Design System
- Active: shadcn/ui (style new-york, Tailwind v4)
- Composants disponibles: Button, Card, Input, Label, Textarea, Select, Checkbox, Switch,
  Form, Dialog, DropdownMenu, Badge, Avatar, Tabs, Tooltip, Skeleton, Alert, Progress, Separator
- Forbidden: HTML natif <button>, <select>, <input> quand shadcn expose une primitive
- Interdiction d'editer src/components/ui/* manuellement (genere par npx shadcn@latest add)

## Tokens (UI Fidelity)
- Convention: hex hardcode INTERDIT dans CSS isoles -- utiliser les variables CSS shadcn/Tailwind
- Theme global = src/index.css (tokens @theme + variables CSS shadcn)
- Source de verite pour couleurs extraites des mockups HTML

## Auth
- Provider: azure-ad (MSAL React)
- Pattern injection client: via env var VITE_AZURE_CLIENT_ID, VITE_AZURE_TENANT_ID

## Forbidden patterns
- Hex hardcode dans CSS isole
- HTML natif quand DS primitive disponible
- Appels HTTP directs depuis composants (toujours via hooks)
- console.log brut (logging structure)
- Traductions codees en dur (toujours i18next)
- State global hors store
- Routes backend inventees (verifier existence dans workspace/output/src/simback/src/main/kotlin/simfront/controller/)

## Env vars consommees au runtime
- VITE_AZURE_CLIENT_ID
- VITE_AZURE_TENANT_ID

## Notes
- Ce fichier est regenere a chaque /arch-init.
- Source de verite: .claude/stacks/frontend/react.md + .claude/stacks/ui/shadcn.md
- shadcn@4.6.0 utilise pour l'init (shadcn@latest a un bug workspace config en 2026-05).
