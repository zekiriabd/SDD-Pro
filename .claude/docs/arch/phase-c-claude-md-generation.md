# arch — Phase C, STEP 12 : Génération `CLAUDE.md` PAR PROJET

> **Sous-doc extrait** de `agents/arch.md` STEP 12 (v7.0.0 trim phase 2,
> 2026-05-20) pour alléger le prompt root. Référencé via
> `Read @.claude/docs/arch/phase-c-claude-md-generation.md`.

Un `CLAUDE.md` par projet généré (auto-loading natif Claude Code,
contexte isolé par famille) :

| Fichier produit | Lu par | Contenu |
|---|---|---|
| `workspace/output/src/{BackendName}/CLAUDE.md` | dev-backend | architecture backend |
| `workspace/output/src/{AppName}/CLAUDE.md` | dev-frontend | architecture frontend + UI |
| `workspace/output/src/{LibName}/CLAUDE.md` (si défini) | dev-* (passif) | contrats partagés (DTOs / Models) |

Bénéfice : -30-40 % tokens (pas de cross-mapping) + isolation cognitive
dev-backend / dev-frontend.

## 12.1 Frontmatter commun

```yaml
---
generated-by: agent arch
generated-at: {ISO-8601 UTC}
stack-md-hash: {sha256-8 de stack.md + stacks actifs filtrés}
project-type: backend | frontend | shared-lib
project-name: {BackendName | AppName | LibName}
active-stacks:
  - .claude/stacks/backend/dotnet-minimalapi.md   # filtré par famille
  - .claude/stacks/auth/azure-ad.md
---
```

## 12.2 Gabarits + procédure

Templates dans `.claude/templates/` :

| Cible | Template | Quand |
|---|---|---|
| `{BackendName}/CLAUDE.md` | `claude-md-backend.template.md`   | toujours |
| `{AppName}/CLAUDE.md`     | `claude-md-frontend.template.md`  | toujours |
| `{LibName}/CLAUDE.md`     | `claude-md-shared-lib.template.md`| si `LibName` défini |
| `.github/workflows/quality.yml` | `ci-quality.github-actions.yml.template` | si `CiTemplatesGeneration: true` (v7.0.0 défaut) ET frontend stack actif. Câble axe-core + Lighthouse CI + CVE scan — compense la retraite v7.0.0 de `accessibility-auditor` + `performance-auditor`. Substituer `{{AppName}}`, `{{BackendName}}`, `{{NodeVersion}}` (22 LTS), `{{DotnetVersion}}` (10 LTS si .NET, sinon laisser vide). Idempotent : skip si fichier existe déjà (édité humain). |

Procédure par projet :
1. Read template
2. Substituer `{ISO-8601 UTC}`, `{sha256-8}` (§12.3),
   `{BackendName|AppName|LibName}`, `{AppNamespace}`, `{DatabaseType}`,
   `{backend|ui|auth-stack-id}`, `{build command}`, `{driver from §8.1}`
3. Sections "Architecture / Persistence / Auth / Forbidden" : condenser
   depuis §1.1, §1.2, §3-4, §5, §8 des stacks (pas de copy intégral)
4. Section auth supprimée si aucun stack auth actif
5. Write `create` (§12.4)

## 12.3 Calcul du hash

`stack-md-hash` = sha256-8 de `stack.md` + stacks actifs filtrés par famille :
- backend → `stack.md` + `backend/*` + `auth/*`
- frontend → `stack.md` + `frontend/*` + `ui/*` + `auth/*`
- shared-lib → `stack.md`

Permet aux dev-* de détecter un CLAUDE.md périmé (fallback stacks bruts).

## 12.4 Mode `create` / écrasement

Mode `create` : écrase l'existant. Idempotent. Édits humains entre runs
perdus — ces fichiers sont **dérivatifs**, pas source humaine.

## 12.5 Purge sections BREAKING CHANGES — RESOLVED

Avant écrasement d'un CLAUDE.md existant :
1. Read CLAUDE.md actuel
2. Glob `## BREAKING CHANGES — RESOLVED {date}` (marqué par dev-*
   STEP 8.5/11.5)
3. Section RESOLVED :
   - scaffolding Phase B reproduit l'ancien nom → **conserver** (non régression)
   - écart absorbé → **supprimer**
4. `## BREAKING CHANGES` non marquée RESOLVED → régénérer telle quelle

**Archivage optionnel** : section supprimée → écrire
`workspace/output/src/{Project}/.claude-archive/breaking-changes-{date}.md`
(répertoire ignoré par dev-* en lecture).

**Rationale** : sans purge, mode `create` réimprime sans marqueurs
RESOLVED → section ré-apparaît brute chaque `/arch-init`.
