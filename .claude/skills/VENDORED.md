# Skills tiers vendorisés (mise à jour MANUELLE uniquement)

> Politique SDD-Pro (2026-07-22) : les skills tiers sont **vendorisés**
> dans ce repo (copie locale, aucune connexion live au marketplace). Mise à jour :
> re-télécharger le repo source en local, re-copier le dossier du skill, re-tester
> (`framework_smoke.py`), commit + push sur notre GitLab. Jamais de sous-module git
> ni de fetch automatique.

## Inventaire

| Skill | Source (upstream) | Commit vendorisé | Licence | Rôle vs SDD-PRO |
|---|---|---|---|---|
| `webapp-testing` | https://github.com/anthropics/skills (`skills/webapp-testing`) | 2026-07-22 (HEAD) | Apache 2.0 | Tests E2E navigateur réel (Playwright) — complète l'API Gate in-memory du QA |
| `semgrep` | https://github.com/trailofbits/skills (`plugins/static-analysis`) | 2026-07-22 (HEAD) | CC BY-SA 4.0 | SAST déterministe Semgrep — complète `security-reviewer` (LLM) |
| `codeql` | https://github.com/trailofbits/skills (`plugins/static-analysis`) | 2026-07-22 (HEAD) | CC BY-SA 4.0 | SAST interprocédural CodeQL (taint tracking) |
| `sarif-parsing` | https://github.com/trailofbits/skills (`plugins/static-analysis`) | 2026-07-22 (HEAD) | CC BY-SA 4.0 | Parsing des sorties SARIF (support semgrep/codeql) |
| `insecure-defaults` | https://github.com/trailofbits/skills (`plugins/insecure-defaults`) | 2026-07-22 (HEAD) | CC BY-SA 4.0 | Détection fail-open (secrets par défaut) — complète `[SEC_SECRET_HARDCODED]` |
| `frontend-design` | https://github.com/anthropics/skills (`skills/frontend-design`) | 2026-07-22 (HEAD) | Apache 2.0 | Design UI distinctif — **création/retouche des mockups `workspace/ui/*.html` et retouches manuelles hors pipeline UNIQUEMENT**. Ne JAMAIS l'utiliser dans `dev-frontend` pendant `/sdd-full` : le contrat pipeline est la fidélité au mockup (`[UI_FIDELITY_GAP]`, mockup = SSoT). Flux correct : frontend-design → mockup → pipeline propage. |
| `c4-model` | https://github.com/cheriftj/c4-model-skill (`skills/c4-model`) | 2026-07-22 (HEAD) | MIT | Diagrammes C4 (Context/Container/Component, Mermaid/Structurizr/PlantUML) — documentation d'architecture **forward** (le reverse a déjà `sdd-reverse-synth`). Read-only sur le code. **Sorties dans `docs/` ou `workspace/.sys/` uniquement** (jamais `workspace/{feats,us,plans}/` — réservés pipeline). Destinations MCP (Notion/Linear/Drive) ignorées (politique local-only). Les commandes `/c4m:*` du plugin upstream ne sont PAS vendorisées (namespace commandes SDD-PRO préservé). Ne remplace pas les ADRs (`constitutioner`). |

## Skills NON vendorisables (licence propriétaire Anthropic)

`docx`, `pdf`, `pptx`, `xlsx` (anthropics/skills) : **source-available, PAS open
source** — la licence interdit d'en conserver des copies hors des Services
Anthropic. NE PAS les copier dans ce repo. Installation légale par poste :

```
/plugin marketplace add anthropics/skills
```

## Contenus minés (pas de skill installé — règles intégrées aux stacks)

| Source | Licence | Destination SDD-PRO | Décision |
|---|---|---|---|
| `vercel-labs/agent-skills` (`react-best-practices`, 70 règles perf) | MIT | `stacks/frontend/react.md §13` (client-side, profil SPA Vite) + `stacks/fullstack/next.md §13` (server/RSC/hydration) | Option A retenue (2026-07-22) : le skill s'auto-déclenche « when writing React components » → conflit `[OPTIMIZATION_PROACTIVE]`/`[UNDECLARED_DECISION]` s'il tournait pendant le pipeline. Les règles sont donc **minées comme conventions déclarées des stacks** (traçables par ID upstream `[async-parallel]`, etc.) au lieu d'installer le skill. Màj manuelle : re-lire le repo upstream, mettre à jour §13. |

## Attribution CC BY-SA 4.0 (Trail of Bits)

Les 4 skills Trail of Bits sont © Trail of Bits, sous CC BY-SA 4.0
(copie de licence : `LICENSE-CC-BY-SA-4.0.txt` dans chaque dossier).
Toute modification locale de ces skills doit rester sous la même licence.

## Coexistence avec les skills natifs SDD-PRO

**Natifs pipeline (5)** — contrat framework, auto-triggered en session :
`using-sddpro`, `starting-a-new-feat`, `starting-a-reverse-eng`,
`debugging-failed-pipeline`, `test-driven-development`.

**Natifs outil mode A (1)** — écrits par le framework, invocation Tech Lead
explicite uniquement, jamais pendant `/sdd-full` / `/dev-run` :

| Skill | Rôle | Plomberie réutilisée |
|---|---|---|
| `a11y-local` (2026-07-22) | Audit accessibilité axe-core **en local** (pendant local du CI ingest). Front servi → `npx @axe-core/cli` → `ingest_axe.py` → `qa_a11y` → `query_console_db.py a11y`. N'invente aucun script ni table (réutilise le pont d'ingest CI existant). | `sdd_scripts/ingest_axe.py`, table `qa_a11y`, taxonomie `[A11Y_*]` (`error-classification-legacy.md §1`) |

> Pendant identifié (non implémenté) : `perf-local` (Lighthouse →
> `ingest_lighthouse.py` → `qa_performance`), même patron mode A.

Les skills vendorisés + natifs mode A sont **hors pipeline SDD** (pas référencés
par `loader.yml` ni par les agents) — invocation à la demande par le Tech Lead
uniquement.
