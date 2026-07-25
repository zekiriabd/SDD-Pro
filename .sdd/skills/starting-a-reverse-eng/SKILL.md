---
name: starting-a-reverse-eng
description: Use when the user expresses intent to reverse engineer a legacy codebase, convert an existing legacy system into SDD_Pro FEATs, or has uploaded code under workspace/old/. Triggers strictly on phrases like "reverse engineering", "convertir l'ancien système", "migrer le legacy", "j'ai un legacy", "workspace/old". Does NOT trigger generically on "vieux code", "ancien code" or "rewrite this" — keep triggers conservative (D5 design doc).
loader: .claude/loader.reverse.yml
---

# Skill — Starting a Reverse Engineering workflow

## Quand cette skill se déclenche

Triggers **stricts** (D5 — conservatisme délibéré pour éviter interception abusive) :

- « reverse engineering »
- « convertir l'ancien système »
- « migrer le legacy »
- « j'ai un legacy »
- « workspace/old »
- « convertir un projet ASPX/Java/PHP/Delphi existant »
- « extraire les FEATs d'un projet legacy »

**Ne PAS déclencher sur** :
- « vieux code », « ancien code » (trop vague)
- « rewrite this » (peut être refactor SDD_Pro standard)
- « migrer vers .NET 9 » (c'est une montée de version, pas du reverse)

## Routage

Si le trigger matche, route vers le workflow reverse engineering **au lieu** de laisser l'agent improviser un audit de code ou un rewrite ad-hoc :

1. **Vérifier précondition source** (§0 design doc) :
   - Le code source legacy doit être dans `workspace/old/{LegacyProject}/`
   - Si binaire-only → STOP + escalade Tech Lead (hors-scope V3)
2. **Phase 0** (humain) : confirmer que les fichiers sont déposés
3. **`/sdd-reverse-init {LegacyProject}`** (Phase 0 bootstrap)
4. **`/sdd-reverse-inventory {LegacyProject}`** (Phase 1 cartographie)
5. **Lire `workspace/old/{LegacyProject}/.sys/inventory.md`** pour identifier les unités U-N pertinentes
6. **Pour chaque unité voulue** : `/sdd-reverse U-N` (Phase 3, séquentiel)
7. **Phase 5** (humain) : Tech Lead revue + complétion `## Project Config` des FEATs
8. **Pré-`/sdd-full`** : `python .sdd/python/sdd_reverse_scripts/check_reverse_feat_for_full.py --feat-path workspace/feats/{n}-*.md`
9. **`/sdd-full {n}`** (pipeline SDD_Pro standard — workflow EXISTANT inchangé)

## Décisions architecturales verrouillées (D1-D7)

À rappeler au Tech Lead s'il pose des questions :

- **D1 Language-agnostic** : détection auto via `language_signatures.yml`. 9+ langages supportés MVP. Confidence cap par langage dans le YAML, jamais hardcodé.
- **D2 Chunking fin** : 1 FEAT = 1 unité fonctionnelle. 1-4 FEATs par page. Grid CRUD = 1 FEAT, modale confirm = 0 FEAT.
- **D3 Tech audit** : optionnel, skippable, informational. Hors MVP (V2).
- **D4 Loader séparé** : `loader.reverse.yml` autonome. Aucune édition de `loader.yml`.
- **D5 Triggers stricts** : cette skill ne hijacke pas sur « vieux code » générique.
- **D6 Output français** : FEATs, inventory.md, tech-audit.md en FR. Commentaires evidence/confidence en EN.
- **D7 DB schema Phase 1** : extraction basique en Phase 1, source de vérité entities. Si absent → entities dégradées à `confidence: medium`.

## Garde-fous qualité (anti-hallucination)

- Chaque AC/SFD/BR/FD DOIT porter `<!-- evidence: path:line --> <!-- confidence: ... -->`
- `confidence` enum strict : `high|medium|low` (jamais `medium-high`)
- Bias toward present : si non visible dans le code → non documenté
- FEAT reverse `confidence: low` → revue humaine obligatoire avant `/sdd-full`
- Commentaire `<!-- REVERSE-GATE: ... -->` en début de FEAT (ADV-15) lisible par script CI

## Hors-scope rappel

- **Pas de reverse engineering binaire-only** (exécutables sans source) → palier V3 hors-scope MVP
- **Pas de migration runtime** : le reverse produit des FEATs, la (ré)implémentation suit le pipeline SDD_Pro standard
- **Pas de préservation pixel-perfect** : Phase 4 UI (V2) interprète sémantiquement, pas clone visuel

## Pointeurs

- Design doc complet : `.sdd/docs/reverse-engineering-workflow.md` (v0.4.1)
- Règle anti-derive REVERSE : `.sdd/rules/reverse-engineering.md`
- Loader autonome : `.claude/loader.reverse.yml`
- Module Python isolé : `.sdd/python/sdd_reverse/`
- 3 CLI scripts : `.sdd/python/sdd_reverse_scripts/`
- Fixture exemple : `.sdd/python/tests/fixtures/legacy-webforms-minimal/`
- 4 rapports adversariaux : `workspace/.sys/.validation/reverse-design-doc-adversarial*.md`
