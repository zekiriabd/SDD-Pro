<!--
  us.reverse.template.md — Template ISOLÉ pour les User Stories reverse
  (barreau 3b de l'escalier reverse, ADR governance-major-reverse-spec-ladder).

  ADV-9 : DUPLIQUÉ localement (jamais lu depuis .sdd/templates/us.template.md).
  Si SDD_Pro change son template US standard, celui-ci reste inchangé.

  Altitude 3b : MOYENNE. Plus métier que les tasks techniques 3a (« la procédure
  X est appelée »), moins global que la FEAT 3c. Un PO/analyste doit comprendre
  l'US sans lire le code.

  Direction ASCENDANTE (≠ forward) : en reverse, l'US est construite À PARTIR de
  l'analyse 3a (tasks T-N), et la FEAT 3c sera construite à partir des US. Donc :
    - chaque AC pointe vers les tasks 3a qu'elle abstrait  → <!-- covers: T-N -->
    - la FEAT 3c pointera ensuite vers les AC de cette US   (fait en 3c)
  Le fil de traçabilité (D3) se construit bas → haut.

  `Parent FEAT: {n}-{FeatName}` est PRÉ-ALLOUÉ par 3a (la FEAT n'existe pas
  encore à 3b). {FeatName} = famille FEAT ≠ {Name} (ID) = slug distinctif
  par US — jamais interchangeables (clôture nommage M4).

  `Parent FEAT hash: sha256:COMPUTE_REQUIRED` (sentinel, REV-C1 audit 2026-06-12) :
  posé non-résolu par 3b (la FEAT n'existe pas encore). 3c le résout via le
  resolver canonique `resolve_us_hash_sentinel.py` APRÈS composition de la FEAT
  — c'est le pont reverse→/sdd-full (sinon dev-*/auditors émettent
  `[FEAT_HASH_MISMATCH]` sur l'US reverse). Idem `Covers:` (back-fill 3c).

  `Confidence:` (ligne header, audit 2026-06-11 M2) : enforce la monotonie Q3
  (US ≤ analyse 3a, FEAT 3c ≤ min(US)) via check_ladder_traceability.py —
  doit rester synchrone avec le commentaire de provenance ci-dessous.

  Placeholders : {n}, {m}, {Name}, {FeatName}, {Title}, {SourceUnit}, {Confidence},
  {ExtractionDate}, {Actor}, {Action}, {Value}, {ACs}, {SourceTasks},
  {Dependencies}.
-->
# US-{m}: {Title}

ID: {n}-{m}-{Name}
Parent FEAT: {n}-{FeatName}
Parent FEAT hash: sha256:COMPUTE_REQUIRED
Status: Draft
Confidence: {Confidence}

<!-- Covers: back-fillé par 3c (reverse-feat-composer) après composition FEAT — REV-C1. Format forward : SFD-N, FD-N, BR-N, AC-N que cette US implémente. -->

<!-- LADDER: rung=3b ; produces=user-story ; from=tech-analysis ; consumed-by=reverse-feat-composer -->
<!-- generated-by: sdd-reverse ; artifact: user-story ; source-unit: {SourceUnit} ; confidence: {Confidence} ; extraction-date: {ExtractionDate} -->

## User Story
En tant que {Actor}
Je veux {Action}
Afin de {Value}

## Acceptance Criteria
<!-- AC-N observables. Chaque AC porte sa traçabilité descendante vers les tasks
     3a + la confidence (≤ confidence de l'analyse — min-monotone Q3). -->
{ACs}

## Source (barreau 3a — analyse technique)
<!-- Tasks T-N de plans/{n}-{FeatName}.analysis.md que cette US abstrait.
     Fil de traçabilité descendant (D3) : US → tasks → evidence file:line. -->
{SourceTasks}

## Dependencies
<!-- US reverse de la même unité dont celle-ci dépend (format {n}-{m}), ou NONE. -->
{Dependencies}

## Metadata
```json
{}
```
