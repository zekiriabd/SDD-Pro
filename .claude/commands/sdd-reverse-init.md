---
description: Bootstrap workspace/old/{LegacyProject}/.sys/ pour le workflow reverse engineering. Crée le squelette de dossiers + un README minimal. Ne touche pas au framework. Read-only sur le legacy.
---
# /sdd-reverse-init {LegacyProject}

## Rôle

Pré-conditionner un projet legacy déposé dans `workspace/old/{LegacyProject}/` avant lancement Phase 1 (`/sdd-reverse-inventory`). Bootstrap purement structurel.

## Pré-conditions

- `workspace/old/{LegacyProject}/` existe et contient ≥ 1 fichier source (non vide, non binaire-only)

Si absent → STOP + ERROR `[REVERSE_NO_SOURCE]`.

Si binaire-only détecté (aucun fichier source lisible parmi `.cs/.aspx/.java/.php/.pas/.frm/.sql/...`) → STOP + ERROR `[REVERSE_BINARY_ONLY]` + escalade (hors-scope §0 design doc).

## Actions

1. Créer `workspace/old/{LegacyProject}/.sys/` si absent
2. Créer `workspace/old/{LegacyProject}/.sys/README.md` minimal :
   ```markdown
   # .sys/ — Artefacts reverse engineering
   Dossier généré par /sdd-reverse-init. Contient les outputs des phases 1-4 du workflow reverse.
   NE PAS éditer manuellement les .json (ownership scripts déterministes).
   Voir .sdd/docs/reverse-engineering-workflow.md
   ```
3. Émettre 1 ligne chat :
   ```
   [REVERSE] {LegacyProject} : .sys/ bootstrappé. Prochaine étape : /sdd-reverse-inventory {LegacyProject}. (3%)
   ```

## Anti-derive

- Aucune écriture hors `workspace/old/{LegacyProject}/.sys/README.md`
- Aucune lecture du legacy lui-même (read-only sur la structure, pas sur le contenu)
- No-spawn

## Idempotence

Re-lancer `/sdd-reverse-init {P}` sur un projet déjà initialisé est un no-op silencieux (le README est préservé).

Voir `.sdd/docs/reverse-engineering-workflow.md` §1 + §2 pour le contexte pipeline.
