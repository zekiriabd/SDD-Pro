---
schema: sdd.memory/v1
name: entrypoint
description: Pivot neutre du fichier-mémoire (entry point) SDD_Pro — régénéré par harness_build.py (emit_memory_file)
body_source: .sdd/entrypoint-body.md
at_includes_total: 30
at_includes_unique: 27
---
# .sdd/entrypoint.md — pivot neutre FICHIERS-MÉMOIRE (Phase 2, ADDITIF)

Généré 2026-07-24 depuis `.claude/CLAUDE.md` (source NON déplacée, lecture
seule — même patron que les pivots agents `.agent.yaml` / commandes
`.cmd.yaml`). Le corps du fichier-mémoire N'EST PAS recopié ici : il reste
dans `body_source` et est réattaché par `harness_build.py` :

- `ClaudeAdapter.emit_memory_file(out)` → `{out}/CLAUDE.md` (round-trip
  identité : corps verbatim, normalisation CRLF/BOM uniquement) ;
- `CodexAdapter.emit_memory_file(out)` → `{out}/AGENTS.md` (variante
  neutre : en-tête GENERATED + note protection_level, refs `@.claude/...`
  réécrites `.sdd/...` car `at_include: unsupported`) ;
- `GeminiAdapter.emit_memory_file(out)` → `{out}/GEMINI.md` (variante
  Gemini CLI : idem, `at_include: emulated` — pas de lazy-load mémoire).

Pivot réversible (suppression sans impact sur le vivant).

## Includes `@`-refs détectés dans le corps (30 occurrences, 27 uniques)

Détection : regex `@\.claude/[^\s\x60)\]]*` sur `body_source`
(occurrences × ref) :

| × | Ref |
|---|---|
| 1 | `@.claude/INVARIANTS.yml` |
| 1 | `@.claude/commands/*.md` |
| 1 | `@.sdd/docs/` |
| 1 | `@.sdd/docs/CHANGELOG.md` |
| 1 | `@.sdd/docs/VERSIONING.md` |
| 1 | `@.sdd/docs/architecture.md` |
| 1 | `@.sdd/docs/brainstorming-techniques.md` |
| 2 | `@.sdd/docs/conventions.md` |
| 1 | `@.sdd/docs/cookbook.md` |
| 1 | `@.sdd/docs/quickstart.md` |
| 1 | `@.sdd/docs/reverse-db-audit-2026-07.md` |
| 1 | `@.sdd/docs/reverse-engineering-workflow.md` |
| 1 | `@.sdd/docs/reverse-proc-engineering.audit.md` |
| 2 | `@.sdd/docs/validated-combos.md` |
| 1 | `@.sdd/docs/{VERSIONING,CHANGELOG,MIGRATION,WORKING-AGREEMENT}.md` |
| 1 | `@.sdd/docs/{WHY-SDD-PRO,COMPLIANCE,SLA,KNOWN-LIMITATIONS}.md` |
| 1 | `@.sdd/docs/{architecture,workflow,conventions,quickstart,gates-map}.md` |
| 1 | `@.sdd/docs/{glossary,hooks-and-protections,config-precedence,po-guide,ux-designer-guide}.md` |
| 1 | `@.sdd/docs/{poc-roi-methodology,roadmap-v7-v8,cache-strategy,validated-combos,orphan-cleanup-policy}.md` |
| 1 | `@.claude/loader.yml` |
| 1 | `@.sdd/python/README.md` |
| 2 | `@.sdd/rules/` |
| 1 | `@.sdd/rules/library-and-stack.md` |
| 1 | `@.sdd/rules/output-protocol.md` |
| 1 | `@.sdd/rules/reverse-engineering.md` |
| 1 | `@.sdd/skills/` |
| 1 | `@.sdd/templates/combos.json` |

## Politique de réécriture (variantes non-Claude)

Les harnais sans lazy-load `@file` en mémoire (cf.
`.sdd/capability-matrix.yml` — codex `at_include: unsupported`,
gemini-cli `at_include: emulated`) reçoivent le MÊME corps métier avec
`@.claude/` → `.sdd/` (repli documenté au §7.1 du plan : « inline ou
consigne Read X avant STEP n »). Les mentions littérales `.claude/...`
sans `@` (chemins descriptifs) sont conservées telles quelles.
