<!--
  analysis.reverse.template.md — Template ISOLÉ pour l'analyse technique legacy
  (barreau 3a de l'escalier reverse, ADR governance-major-reverse-spec-ladder).

  D5 : format « analyse technique legacy » DISTINCT du schéma plan forward
  (plans/{n}-{m}.back.md, orienté pilotage-dev avec ## Files/operation/
  layer/covers_acs). Ce document décrit ce que le code legacy FAIT (observé),
  pas ce qu'il faut CRÉER. Il n'est JAMAIS réexécuté par /sdd-full.

  Extension distincte : `.analysis.md` (≠ `.back.md`/`.front.md`) → pas de
  collision avec les plans forward dans plans/.

  Rôle dans l'escalier :
    code source --[reverse-tech-analyst 3a]--> CE DOCUMENT
                --[reverse-us-writer 3b]------> us/{n}-{m}-{Name}.md
                --[reverse-feat-composer 3c]--> feats/{n}-{Name}.md

  Traçabilité (D3) : chaque task T-N porte une evidence file:line. C'est le
  BARREAU DU BAS du fil de traçabilité — les US (3b) pointeront vers les T-N,
  la FEAT (3c) pointera vers les AC d'US, jusqu'à la ligne de code.

  Placeholders : {n}, {Name}, {SourceUnit}, {LegacySources}, {Language},
  {Confidence}, {ExtractionDate}, {Kind}, {RolesTable}, {Tasks}, {SqlQueries},
  {StoredProcs}, {ConfigPlumbing}, {Calculations}, {ExternalSideEffects},
  {CliCommands}, {ExtractionNotes}, {LowConfidenceBanner}.
-->
---
generated-by: sdd-reverse
artifact: tech-analysis
source-unit: {SourceUnit}
legacy-sources: {LegacySources}
confidence: {Confidence}
extraction-date: {ExtractionDate}
language-detected: {Language}
unit-kind: {Kind}
n: {n}
name: {Name}
---

# Analyse technique legacy — {n}-{Name}
<!-- LADDER: rung=3a ; produces=tech-analysis ; consumed-by=reverse-us-writer -->

> Photo fidèle de l'implémentation legacy (barreau 3a). Document de référence
> dev / tech-lead — **jamais réexécuté** par `/sdd-full`. La plomberie (connexion,
> timeouts, mécaniques d'accès données) vit ICI, pas dans la FEAT métier (3c).

{LowConfidenceBanner}

## Rôles & classes

<!-- Table dérivée de inventory.json.units[U-N].classes (carte des rôles L0). -->

| Classe | Rôle | Fichier:lignes | SQL | HTTP |
|---|---|---|:---:|:---:|
{RolesTable}

## Comportements observés (tasks techniques)

<!-- T-N séquentiels. 1 par comportement mécanique observable. Chaque ligne
     porte une evidence file:line OBLIGATOIRE (barreau bas du fil de traçabilité D3).
     Décrire ce que le code FAIT, sans interprétation métier (ça, c'est 3b/3c). -->

{Tasks}

## Accès données

### Requêtes SQL
<!-- tables de dataAccess.queries[].tables + evidence -->
{SqlQueries}

### Procédures stockées
<!-- dataAccess.storedProcedureCalls[].name + contrat d'appel + evidence
     (contrat d'interface DB que la migration doit préserver) -->
{StoredProcs}

### Connexion & configuration (plomberie)
<!-- connection strings, timeouts, params applicatifs. DÉMOTÉ ICI volontairement
     (D6) : ces éléments ne sont PAS des règles métier, ils ne remonteront pas
     dans la FEAT 3c. -->
{ConfigPlumbing}

## Calculs & algorithmes

<!-- Formules, transformations, conditions observées + evidence. -->
{Calculations}

## Dépendances & effets de bord externes

<!-- FTP, email/Outlook, Excel, Azure, fichiers, etc. (static-helper roles). -->
{ExternalSideEffects}

## Commandes CLI

<!-- Uniquement si unit-kind == job : switch args du Main/App (mode batch). -->
{CliCommands}

## Notes d'extraction

<!-- Items rejetés (evidence absente), evidence non lue (cap M16 god-unit),
     gaps de complétude résiduels, décisions de cap de confiance. -->
{ExtractionNotes}
