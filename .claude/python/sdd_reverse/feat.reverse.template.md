<!--
  feat.reverse.template.md — Template ISOLÉ pour FEATs reverse engineering.

  ADV-9 closure : ce template est DUPLIQUÉ localement (jamais lu depuis
  .claude/templates/feat.template.md du framework standard) pour découplage
  total. Si SDD_Pro change son template standard, ce template reverse reste
  inchangé jusqu'à mise à jour explicite.

  Conformité §A (Annexe A du design doc) :
  - Frontmatter étendu reverse (generated-by, legacy-sources, confidence,
    extraction-date, language-detected, source-unit)
  - Commentaire REVERSE-GATE machine-parseable ADV-15
  - Sections obligatoires ordre figé
  - IDs stables SFD-N/FD-N/BR-N/AC-N
  - AC Given/When/Then
  - Evidence + confidence par item
  - Bannière humaine si confidence: low

  Placeholders : {n}, {Name}, {SourceUnit}, {LegacySources}, {Language},
  {Confidence}, {ExtractionDate}, {Actors}, {SFDs}, {FDs}, {BRs}, {ACs},
  {GateConfidence}, {GateAllowSddFull}, {GateReason}, {LowConfidenceBanner}.

  L'agent reverse-feat-composer (barreau 3c de l'escalier reverse) remplit ces
  placeholders à partir des User Stories 3b + l'analyse technique 3a (il ne lit
  PAS le code legacy directement — ADR governance-major-reverse-spec-ladder).

  Validation : validate_reverse_feat.py vérifie structure + sync
  frontmatter.confidence ↔ comment.confidence (ADV-22).
-->
---
generated-by: sdd-reverse
legacy-sources: {LegacySources}
confidence: {Confidence}
extraction-date: {ExtractionDate}
language-detected: {Language}
source-unit: {SourceUnit}
---

# FEAT {n} — {Name}
<!-- REVERSE-GATE: confidence={GateConfidence} ; allow-sdd-full={GateAllowSddFull} ; reason={GateReason} -->

> ⚠️ **Angles morts runtime (audit 2026-06-11 B15)** : cette FEAT est issue
> d'une extraction STATIQUE du code legacy. Elle ne voit PAS : les triggers et
> vues DB (noms inventoriés, corps non analysés), le schéma live de la base,
> les jobs planifiés externes (cron/Task Scheduler), la config serveur
> (IIS/registre/GPO), le SQL dynamique, ni les règles métier encodées en
> données de paramétrage. Une FEAT `confidence: high` est une **borne
> inférieure fiable** du comportement legacy — jamais une preuve
> d'équivalence. Revue humaine obligatoire avant refonte.

{LowConfidenceBanner}

## Actors

{Actors}

## Functional Needs

{SFDs}

## Functional Deliverables

{FDs}

## Business Rules

{BRs}

## Acceptance Criteria

{ACs}

## Project Config

<!-- À compléter par le Tech Lead Phase 5 (revue humaine) avant /sdd-full.
     Champs standards SDD_Pro à renseigner : stack actifs, QAMode,
     CoverageMin, GatedWorkflow, etc. Voir .claude/CLAUDE.md §7 et
     .claude/rules/quality.md §A. -->
