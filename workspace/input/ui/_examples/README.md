# Mockup examples (Sprint P1, 2026-06-08)

Canonical HTML mockups to copy as starting points when designing UI for
SDD_Pro FEATs. See [docs/ux-designer-guide.md](../../../../.claude/docs/ux-designer-guide.md)
for the full guide.

| File | Use case |
|---|---|
| [login-simple.html](login-simple.html) | Auth form with email + password, error state |
| [dashboard-cards.html](dashboard-cards.html) | KPI grid (4 cards) + activity table |
| [wizard-multi-step.html](wizard-multi-step.html) | 3-step form with stepper + nav |

## How to use

1. Copy the example matching your closest use case to `workspace/input/ui/{n}-{m}-{Name}.html`
   (replacing `{n}-{m}-{Name}` with your real US ID).
2. Adjust labels, fields, structure to match your FEAT's AC.
3. Open in browser to validate visually (Chrome DevTools responsive mode
   for mobile preview).
4. Run `/feat-validate {n}` — the mockup will be matched to its US.
5. Run `/sdd-full {n}` — the agent `dev-frontend` will translate it to
   the active DS (shadcn / Vuetify / Radzen).

## Limits

- No JS — interactivity comes from the US AC, not the mockup
- No external image URLs — use SVG inline or `data-ui-asset="..."` placeholders
- Tailwind CDN only — no `<link rel="stylesheet">` to local CSS
- Keep file size < 50 KB to fit agent context window comfortably
