# `.sdd/stacks/` — Catalogue des stacks techniques SDD_Pro

> **Note de comptage** (audit MN2 2026-06-07, recount 2026-09-02) : ce fichier `README.md` est un **index documentaire**, PAS un stack. Le comptage canonique "42 stacks actifs" (cf. `CLAUDE.md §6`) **exclut** ce README — le validateur `validate_stack_md_headers.py` l'écarte explicitement (`if p.parent == root: continue`). Si `find .sdd/stacks -name "*.md"` retourne 43 entrées, le delta est ce fichier d'index. Pour un comptage juste : `find .sdd/stacks -mindepth 2 -name "*.md"`.

> Tous les stacks listés ici sont **chargeables** par le framework. Leur
> niveau de maturité (🟢 reference / 🟡 experimental) est signalé par le
> frontmatter `Validation:` de chaque `{stack-id}.md`.

## Structure

| Catégorie | Rôle | Sélection dans `stack.md` |
|---|---|---|
| `backend/` | Frameworks serveur (7) | `## Active Tech Specs` → `backend/{id}` |
| `frontend/` | SPA web (4) | `## Active Tech Specs` → `frontend/{id}` |
| `ui/` | Design systems (3) | `## Active UI Specs` |
| `qa/` | Frameworks de tests (12) | `## Active QA Specs` |
| `auth/` | Protocoles auth (2) | `## Active Tech Specs` → `auth/{id}` |
| `archi/` | Patterns d'architecture (3) | `## Active Architecture Pattern` (uniquement pour AppType=back-front) |
| `fullstack/` | SSR monolithes (10) — tier per-stack | `## Active Tech Specs` → `fullstack/{id}` (avec AppType=fullstack) |
| `mobiles/` | Mobile cross-platform, multiplateforme et natif (8) — tier per-stack | `## Active Tech Specs` → `mobiles/{id}` (avec frontendKind=mobile) |
| `desktop/` | Clients desktop natifs et hybrides (7) — tier per-stack | `## Active Tech Specs` → `desktop/{id}` (avec frontendKind=desktop) |

## Statut validation

Voir `.claude/CLAUDE.md §6` (table résumée) et `docs/validated-combos.md`
(détail combos validés bout-en-bout).

4 tiers de validation depuis v7.0.0 (cf. `CLAUDE.md §6`) — **56 stacks** depuis les batches `mobiles/`, `backend/`, `fullstack/` et `desktop/` du 2026-09-02 :
- **🟢 reference** (14 stacks) : combo C1/C2 validé end-to-end (production).
- **🟢 bench-validated runtime** (11 stacks) : code généré compile +
  démarre + sert les ACs (best-effort, gaps documentés).
- **🟡 experimental** (26 stacks) : spec OK, jamais exécuté end-to-end.
  Non supporté commercialement.
- **🟡 POC-only** (1 stack — `node-react`) : usage interne SDD uniquement.

## Catalogue machine `.libs.json`

Chaque stack a un fichier compagnon `{stack-id}.libs.json` qui est la
**source de vérité** pour les versions et libs (cf. `rules/library-and-stack.md §1.0`).
Le `.md` est documentation humaine ; le `.libs.json` est consommé par
`arch` (install) et `dev-backend` (capability gating).

Régénération via `python .sdd/python/sdd_admin/sync_stack_md.py --stack-id {id}`.

## Historique

- **v6.x** : 24 stacks actifs + nombreux drafts épars.
- **v7.0.0** (2026-05-20) : quarantine `_drafts/` introduite — 9 stacks
  (fullstack + mobiles + microservice) déplacés en `.sdd/stacks/_drafts/`
  (ADR `governance-major-stacks-quarantine`).
- **v7.x** : rollback de la quarantine — `_drafts/` supprimé, 9 stacks
  réintégrés sous leur catégorie native avec `Validation: 🟡 experimental`
  (ADR `governance-stacks-quarantine-rollback`). Surface unique, statut
  explicite par stack.

- **v7.4.x** (2026-09-02) : batch `mobiles/` — le catalogue mobile passe de
  4 à 8 stacks (ajout `flutter`, `kotlin-multiplatform`, `swiftui`,
  `ionic-capacitor`) et les 4 existants sont audités (12 défauts bloquants
  corrigés, dont 4 références de paquet/version inexistantes au registre).
  Deux stacks QA d'accompagnement (`qa/flutter-test`, `qa/swift-testing`) —
  les autres stacks mobiles se rattachent à un stack QA existant, cf. §10 de
  leur `.md`. Total 36 → **42**. Trois `buildSystem` ajoutés au schéma :
  `pub` (Dart/Flutter), `swift` (SwiftPM) et `msbuild` (Delphi — il était
  déjà accepté par `validate_libs_catalog.py` mais absent de l'enum du
  schéma : drift fermé).

- **v7.4.x** (2026-09-02) : batch `backend/` — le catalogue serveur passe de
  4 à 7 stacks (ajout `django`, `nestjs`, `laravel`) + `qa/php-pest`. Les 4
  existants sont rebasés sur les registres amont et 3 défauts de cohérence
  corrigés (EF Core 9 vs ASP.NET 10, `@types/express` 5 vs `express` 4,
  `@types/supertest` 6 vs `supertest` 7). `composer` ajouté au schéma comme
  quatrième `buildSystem` de l'audit. Total 42 → **46**.

- **v7.4.x** (2026-09-02) : batch `fullstack/` — le catalogue SSR passe de 7 à
  10 stacks (ajout `laravel-blade`, `symfony-twig`, `django-templates`). Les 7
  existants sont rebasés. Défaut le plus grave de l'audit fermé ici :
  `blazor-server` et `aspnet-mvc-razor` portaient la combinaison EF Core 10.0.6
  + Npgsql.EF 9.0.4 du post-mortem DemoApp, jamais corrigée sur ces deux
  stacks. Les 2 derniers WARN `PRERELEASE` du catalogue sont fermés.
  Total 46 → **49**, et `validate_libs_catalog.py` ne remonte plus aucun
  warning.

- **v7.4.x** (2026-09-02) : **nouvelle catégorie `desktop/`** (7 stacks :
  `delphi-vcl`, `wpf`, `qt-cpp`, `electron`, `winforms`, `javafx`, `pyside`).
  Câblage framework requis : enum `category` du schéma, `preflight.py`
  (`frontendKind=desktop`, exclusivité avec `mobiles/*` et `frontend/*`, globs
  `CMakeLists.txt` / `*.sln`), et un quatrième `buildSystem` : `cmake`.
  Total 49 → **56**.

> Pour ajouter ou valider un nouveau stack : voir
> `docs/poc-roi-methodology.md` (PoC formel) et `docs/validated-combos.md §3`
> (critères d'acceptation combo).
