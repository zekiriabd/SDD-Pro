# Session Digest — SDD_Pro v6.10.5

> Reified persistent session (Niveau 5) from console.db tables.
> Stable for the duration of a single `/sdd-full` run ; refreshed
> at each phase transition. Cache key : `cache_005`.

## Session header

- **run_id** : `57108e40cca6`
- **feat** : 4-Campagne
- **command** : `C:/Program Files/Git/sdd-full`
- **status** : `partial`
- **current_phase** : `qa-generate`
- **started_at** : 2026-05-18T15:58:27.509Z
- **updated_at** : 2026-05-18T18:46:22.111Z

## Summary

| Métrique | Valeur |
|---|---:|
| Phases totales | 6 |
| Phases done | 0 |
| Phases failed | 0 |
| Agents actifs (run) | 0 |
| Input tokens cumulés | 0 |
| Cache read tokens cumulés | 0 |
| **Cache hit ratio global** | **0.0%** |

## Timeline phases

| Phase | Status | Started | Ended |
|---|---|---|---|
| `us-generate` | pass | — | 2026-05-18T16:00:51.976Z |
| `FEAT-validate` | warn | — | 2026-05-18T16:01:17.336Z |
| `dev-plan` | pass | — | 2026-05-18T17:44:13.433Z |
| `arch` | pass | — | 2026-05-18T17:44:13.611Z |
| `dev-run` | pass | — | 2026-05-18T18:22:03.631Z |
| `qa-generate` | pass | — | 2026-05-18T18:40:48.300Z |

## 8 derniers events

- `2026-05-18T18:46:22.110Z` · `run.end` · — 
- `2026-05-18T18:40:48.300Z` · `phase.end` · — phase=`qa-generate`
- `2026-05-18T18:22:03.631Z` · `phase.end` · — phase=`dev-run`
- `2026-05-18T17:44:13.611Z` · `phase.end` · — phase=`arch`
- `2026-05-18T17:44:13.433Z` · `phase.end` · — phase=`dev-plan`
- `2026-05-18T16:01:17.336Z` · `phase.end` · — phase=`FEAT-validate`
- `2026-05-18T16:00:51.976Z` · `phase.end` · — phase=`us-generate`
- `2026-05-18T15:58:27.509Z` · `run.start` · — 

---

*Digest régénérable : `compile_session_digest.py` (idempotent). Le `run_id` est la clé session naturelle reifiée depuis `sdd_state.py`.*
