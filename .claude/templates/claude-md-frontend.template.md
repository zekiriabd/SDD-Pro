---
generated-by: agent arch
generated-at: {ISO-8601 UTC}
stack-md-hash: {sha256-8-chars}
project-type: frontend
project-name: {AppName}
active-stacks:
  - .claude/stacks/frontend/{frontend-stack-id}.md
  - .claude/stacks/ui/{ui-stack-id}.md
  - .claude/stacks/auth/{auth-stack-id}.md     # si auth actif
---

# {AppName} — Frontend Project Context

## Project Config (subset)
- AppName: {AppName}
- LibName: {LibName}             # si défini (DTOs partagés via réf projet)
- AppNamespace: {AppNamespace}

## Architecture
{résumé §1.1 + §1.2 du stack frontend actif}

## Layer → Path Mapping
- Page               → Pages/
- Component          → Components/
- Layout             → Layouts/
- Style isolé        → fichier `.razor.css` / `.module.css` adjacent
- Theme global       → wwwroot/css/theme.css         (Blazor)
                     | src/styles/theme.css         (React/Vue)
                     | src/styles/theme.scss        (Angular)
- Bootstrap UI lib   → wwwroot/index.html (augment) (Blazor)

## Build Command
{build command — ex. dotnet build {AppName}.csproj --nologo OU npm run build}

## Design System
- Active: {ds name from ## Active UI Specs}
- Mapping composants: voir `.claude/stacks/ui/{id}.md §2`
- Bootstrap (scripts/CSS injectés): {pattern documenté}
- Forbidden: HTML natif `<button>`, `<table>`, `<input>` quand le DS expose une primitive (ex. RadzenButton)

## Tokens (UI Fidelity)
- Convention: hex hardcode INTERDIT dans CSS isolés — utiliser `var(--color-*)`, `var(--font-family-*)`, etc.
- Theme global = source de vérité pour les overrides extraits du mockup HTML (couleurs inline / `<style>`)
- Asset placeholder convention: <img data-ui-asset="{role}" ...>

## Auth (si stack auth actif)
- Provider: {azure-ad | auth-local | ...}
- Pattern injection client: {Vite VITE_* | appsettings.json | environment.ts}

## Forbidden patterns (filtrés à la famille frontend)
- Pas de hex hardcode dans CSS isolé
- Pas de HTML natif quand DS primitive disponible
- {patterns §5 Interdits du stack frontend + ui, condensés}

## Env vars consommées au runtime (côté client)
- {liste des VITE_* / AZ_FE_* selon stack auth/frontend}

## Notes
- Ce fichier est régénéré à chaque /arch-init.
- Source de vérité : `.claude/stacks/frontend/{id}.md` + `.claude/stacks/ui/{id}.md` (à relire si CLAUDE.md ne suffit pas).
