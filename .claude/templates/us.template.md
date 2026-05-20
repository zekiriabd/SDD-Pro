# US-{m}: {Name}

ID: {n}-{m}-{Name}
Parent FEAT: {n}-{FeatName}
Parent FEAT hash: sha256:{feat-hash-8}        # v7.0.0 P1-11 — détecte modification silencieuse de la FEAT
Status: Draft

<!-- Status valides (v6.8+, optionnel — backward-compat avec Draft/Done) :
     Draft | Ready | InProgress | Review | Done | Deferred | Cancelled
     Transitions valides : Draft → Ready → InProgress → Review → Done
     Sortie possible vers Deferred/Cancelled depuis tout état non terminal -->

## User Story
En tant que <acteur>
Je veux <action observable>
Afin de <valeur métier>

## Acceptance Criteria
- AC-1: <condition observable, testable>
- AC-N: <condition observable, testable>

## Covers
<Liste des éléments de la FEAT parente couverts par cette US.
 Chaque SFD / BR / AC / FD de la FEAT DOIT apparaître dans le Covers d'au moins une US.>
- SFD-<index>
- BR-<index>
- AC-<index>
- FD-<index>

## Dependencies
<!-- Liste des US dont celle-ci dépend (doit être complétée AVANT que dev-* la
     matérialise). Format : short id `{n}-{m}` (1 par ligne), ou `NONE`.
     Validé par sdd_scripts/validate_us_deps.py (cycles, refs manquantes,
     orphelins). Ordonne /dev-run STEP 6.2 via topological sort. -->
- NONE

## Metadata
<!-- Bloc JSON optionnel AI-safe (v6.8+). Survit aux re-runs et permet aux
     agents/Tech Lead d'attacher du contexte arbitraire à l'US sans casser
     le schéma. Agents lisent en optional (ignore si absent ou invalide).

     Conventions de clés (toutes optionnelles) :
     - complexity      : entier 1-10 (rempli par agent po, cf. T3)
     - effort_estimate : "S" | "M" | "L" | "XL"
     - notes           : string libre (Tech Lead)
     - flags           : array de strings ("blocked", "needs-review", ...)
     - custom.*        : namespace libre projet (non normé)
-->
```json
{}
```
