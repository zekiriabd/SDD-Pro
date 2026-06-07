# `.claude/stacks/` — Catalogue des stacks techniques SDD_Pro

> **Note de comptage** (audit MN2 2026-06-07) : ce fichier `README.md` est un **index documentaire**, PAS un stack. Le comptage canonique "34 stacks actifs" (cf. `CLAUDE.md §6`) **exclut** ce README. Si `find .claude/stacks -name "*.md"` retourne 35 entrées, le delta est ce fichier d'index.

> Tous les stacks listés ici sont **chargeables** par le framework. Leur
> niveau de maturité (🟢 reference / 🟡 experimental) est signalé par le
> frontmatter `Validation:` de chaque `{stack-id}.md`.

## Structure

| Catégorie | Rôle | Sélection dans `stack.md` |
|---|---|---|
| `backend/` | Frameworks serveur (4) | `## Active Tech Specs` → `backend/{id}` |
| `frontend/` | SPA web (4) | `## Active Tech Specs` → `frontend/{id}` |
| `ui/` | Design systems (3) | `## Active UI Specs` |
| `qa/` | Frameworks de tests (9) | `## Active QA Specs` |
| `auth/` | Protocoles auth (2) | `## Active Tech Specs` → `auth/{id}` |
| `archi/` | Patterns d'architecture (3) | `## Active Architecture Pattern` (uniquement pour AppType=back-front) |
| `fullstack/` | SSR monolithes (6) — tier per-stack | `## Active Tech Specs` → `fullstack/{id}` (avec AppType=fullstack) |
| `mobiles/` | Mobile cross-platform (3) — tier per-stack | `## Active Tech Specs` → `mobiles/{id}` (avec frontendKind=mobile) |

## Statut validation

Voir `.claude/CLAUDE.md §6` (table résumée) et `docs/validated-combos.md`
(détail combos validés bout-en-bout).

4 tiers de validation depuis v7.0.0 (cf. `CLAUDE.md §6`) :
- **🟢 reference** (14 stacks) : combo C1/C2 validé end-to-end (production).
- **🟢 bench-validated runtime** (11 stacks) : code généré compile +
  démarre + sert les ACs (best-effort, gaps documentés).
- **🟡 experimental** (8 stacks) : spec OK, jamais exécuté end-to-end.
  Non supporté commercialement.
- **🟡 POC-only** (1 stack — `node-react`) : usage interne SDD uniquement.

## Catalogue machine `.libs.json`

Chaque stack a un fichier compagnon `{stack-id}.libs.json` qui est la
**source de vérité** pour les versions et libs (cf. `rules/library-and-stack.md §1.0`).
Le `.md` est documentation humaine ; le `.libs.json` est consommé par
`arch` (install) et `dev-backend` (capability gating).

Régénération via `python .claude/python/sdd_admin/sync_stack_md.py --stack-id {id}`.

## Historique

- **v6.x** : 24 stacks actifs + nombreux drafts épars.
- **v7.0.0** (2026-05-20) : quarantine `_drafts/` introduite — 9 stacks
  (fullstack + mobiles + microservice) déplacés en `.claude/stacks/_drafts/`
  (ADR `governance-major-stacks-quarantine`).
- **v7.x** : rollback de la quarantine — `_drafts/` supprimé, 9 stacks
  réintégrés sous leur catégorie native avec `Validation: 🟡 experimental`
  (ADR `governance-stacks-quarantine-rollback`). Surface unique, statut
  explicite par stack.

> Pour ajouter ou valider un nouveau stack : voir
> `docs/poc-roi-methodology.md` (PoC formel) et `docs/validated-combos.md §3`
> (critères d'acceptation combo).
