# Rapport d'impact — build harness

- **Harnais** : `gemini-cli`
- **Provider** : `anthropic`
- **Niveau de protection** : B (référence = A sous claude-code/anthropic)
- **Combo** : UNTESTED
- **Fidélité sorties structurées (provider)** : unknown
- **Pricing renseigné** : oui

## Mécanismes

native=3 · émulé=3 · reporté-CI=1 · absent=0

| Mécanisme | Statut |
|---|---|
| Sous-agents isolés + parallélisme borné | émulé (wrapper) |
| Hooks bloquants intra-session | reporté CI-time |
| Skills auto-trigger | émulé (wrapper) |
| Lazy-load @file | émulé (wrapper) |
| Slash-commands | natif |
| Python déterministe (gates, build_loop) | natif |
| MCP | natif |

## Avertissements

- ⚠ Sous-agents isolés + parallélisme borné : émulé (wrapper)
- ⚠ Hooks bloquants intra-session : reporté CI-time
- ⚠ Skills auto-trigger : émulé (wrapper)
- ⚠ Lazy-load @file : émulé (wrapper)
- ⚠ Provider anthropic : fidélité sorties structurées « unknown » — conformance run (§10) requis avant tout SLA

> ⚠ COMBO UNTESTED — le pipeline exige `SDD_ALLOW_UNTESTED_HARNESS=1` (audit-loggué) tant qu'aucun conformance run (§10 du plan) n'a qualifié ce combo. Le build (transpilation) reste, lui, non bloquant.
