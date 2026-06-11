<!--
  us.reverse.template.md — Template ISOLÉ pour les User Stories reverse
  (barreau 3b de l'escalier reverse, ADR governance-major-reverse-spec-ladder).

  ADV-9 : DUPLIQUÉ localement (jamais lu depuis .claude/templates/us.template.md).
  Si SDD_Pro change son template US standard, celui-ci reste inchangé.

  Altitude 3b : MOYENNE. Plus métier que les tasks techniques 3a (« la procédure
  X est appelée »), moins global que la FEAT 3c. Un PO/analyste doit comprendre
  l'US sans lire le code.

  Direction ASCENDANTE (≠ forward) : en reverse, l'US est construite À PARTIR de
  l'analyse 3a (tasks T-N), et la FEAT 3c sera construite à partir des US. Donc :
    - chaque AC pointe vers les tasks 3a qu'elle abstrait  → <!-- covers: T-N -->
    - la FEAT 3c pointera ensuite vers les AC de cette US   (fait en 3c)
  Le fil de traçabilité (D3) se construit bas → haut.

  `Parent FEAT: {n}-{Name}` est PRÉ-ALLOUÉ par 3a (la FEAT n'existe pas encore à
  3b — elle sera composée en 3c). Pas de `Parent FEAT hash` (mécanique forward
  inversée ici : US précède FEAT).

  Placeholders : {n}, {m}, {Name}, {Title}, {SourceUnit}, {Confidence},
  {ExtractionDate}, {Actor}, {Action}, {Value}, {ACs}, {SourceTasks},
  {Dependencies}.
-->
# US-{m}: {Title}

ID: {n}-{m}-{Name}
Parent FEAT: {n}-{Name}
Status: Draft

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
<!-- Tasks T-N de output/plans/{n}-{Name}.analysis.md que cette US abstrait.
     Fil de traçabilité descendant (D3) : US → tasks → evidence file:line. -->
{SourceTasks}

## Dependencies
<!-- US reverse de la même unité dont celle-ci dépend (format {n}-{m}), ou NONE. -->
{Dependencies}

## Metadata
```json
{}
```
