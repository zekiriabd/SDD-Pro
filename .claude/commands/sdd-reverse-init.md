# /sdd-reverse-init — Bootstrap workspace/old/{LegacyProject}/

> ⚠️ **Commande du workflow reverse engineering** (séparé du pipeline SDD_Pro principal).
> Master prompt : `@.claude/docs/reverse-engineering-master-prompt.md`
> Design doc : `@.claude/docs/reverse-engineering-workflow.md`

Initialise un nouveau projet legacy pour reverse engineering :
1. Crée `workspace/old/{LegacyProject}/` si absent
2. Crée `workspace/old/{LegacyProject}/.sys/` (dossier de sortie pour `inventory-raw.json`, `inventory.md`, etc.)
3. Crée `workspace/old/{LegacyProject}/.sys/.gitignore` pour ignorer les outputs générés
4. Affiche les prochaines étapes au Tech Lead

**Usage** : `/sdd-reverse-init {ProjectName}`

---

## STEP 1 — Valider les arguments

Arguments :
- `{ProjectName}` (obligatoire) : nom du projet legacy. Convention : Capitale initiale, sans accents, tirets pour espaces (ex. `AcmeCRM`, `LegacyBilling`).

Si absent ou contient des caractères invalides → ERROR :
```
ERROR: /sdd-reverse-init — argument invalide
CAUSE: [REVERSE_PRECONDITION] ProjectName manquant ou contient des caractères invalides
FIX: relancer avec /sdd-reverse-init {Name} (lettres, chiffres, tirets uniquement)
```

---

## STEP 2 — Vérifier l'existence

```bash
LEGACY_PATH="workspace/old/{ProjectName}"
```

Si `workspace/old/{ProjectName}/` existe **et** contient déjà des fichiers (autres que `.sys/`) :
- Émettre WARN : `🟡 [REVERSE/WARN] workspace/old/{ProjectName}/ existe déjà avec du contenu — bootstrap idempotent.`
- Ne pas écraser le contenu existant
- Continuer à STEP 3 (créer/compléter `.sys/` si manquant)

Sinon, créer le répertoire `workspace/old/{ProjectName}/` (vide, prêt à recevoir le code legacy).

---

## STEP 3 — Créer la structure `.sys/`

```bash
mkdir -p workspace/old/{ProjectName}/.sys/modules
```

Créer `workspace/old/{ProjectName}/.sys/.gitignore` avec le contenu :
```
# SDD_Pro Reverse Engineering — outputs générés automatiquement
# Ces fichiers sont produits par /sdd-reverse-* et peuvent être régénérés.
# Si tu veux les versionner, supprime ce .gitignore.
*.json
*.md
modules/
```

---

## STEP 4 — Émettre les prochaines étapes

Affichage chat :

```
[DONE] Workspace reverse initialisé pour {ProjectName}. (100%)

  📁 workspace/old/{ProjectName}/        ← dépose ici le code legacy
  📁 workspace/old/{ProjectName}/.sys/   ← outputs générés par /sdd-reverse-*

Prochaines étapes :
  1. Copie ou clone le code legacy dans workspace/old/{ProjectName}/
  2. Lance /sdd-reverse-inventory {ProjectName} pour scanner et identifier les unités fonctionnelles
  3. Valide inventory.md (édite si besoin)
  4. Lance /sdd-reverse {unit-id} pour extraire chaque FEAT
```

---

## Anti-derive

- Ne JAMAIS modifier ou supprimer du contenu déjà présent dans `workspace/old/{ProjectName}/`.
- Ne JAMAIS toucher à un autre projet legacy (idempotent par projet).
- Ne JAMAIS écrire dans `workspace/input/` ou `workspace/output/` — réservé Phase 3+.

## Exit codes

- `0` : success (création ou idempotent OK)
- `1` : argument invalide
- `2` : erreur I/O (permission refusée, disk full)
