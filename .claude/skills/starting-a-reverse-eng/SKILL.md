---
name: starting-a-reverse-eng
description: Use when the user expresses intent to reverse-engineer a legacy application, convert old code into SDD_Pro specifications, or migrate a brownfield project. Triggers on phrases like "reverse engineering", "reverse engineer", "convertir l'ancien système", "convertir le legacy", "j'ai un legacy", "j'ai une vieille application", "rétroingénierie", "ingénierie inverse", "moderniser l'application legacy", "migrer le legacy", "migration legacy", "workspace/old", explicit "/sdd-reverse" mention. Routes to the SDD_Pro reverse engineering workflow (separate from the main /sdd-full pipeline) and prevents Claude from jumping into ad-hoc analysis without phased extraction. Conservative triggering: does NOT activate on generic "vieux code" or "convertir" alone.
---

# Skill — Starting a Reverse Engineering Workflow

> **Auto-trigger** : intention reverse-engineering détectée.
> **But** : router vers le workflow `/sdd-reverse-*` (séparé du pipeline SDD_Pro principal) plutôt que de laisser Claude lire ad-hoc le legacy.
> **Master prompt** : `@.claude/docs/reverse-engineering-master-prompt.md`
> **Design doc** : `@.claude/docs/reverse-engineering-workflow.md`

## Quand cette skill se déclenche

**Triggers explicites (haute priorité)** :
- "reverse engineering" / "reverse engineer"
- "rétroingénierie" / "ingénierie inverse"
- "convertir l'ancien système" / "convertir le legacy" / "convertir le code legacy"
- "j'ai un legacy" / "j'ai une vieille application" / "j'ai une ancienne app"
- "moderniser l'application legacy" / "moderniser le code legacy"
- "migrer le legacy" / "migration legacy"
- "workspace/old" (mention explicite du path)
- "/sdd-reverse" (mention explicite de la commande)

**Triggers qui NE déclenchent PAS cette skill** (collision avec `starting-a-new-feat`) :
- "vieux code" seul (trop générique)
- "convertir" sans qualificatif legacy
- "ajouter une feature" (route vers `starting-a-new-feat`)
- "moderniser" seul sans mention legacy

## Décision tree

### Étape 1 — Vérifier l'état du workspace reverse

```bash
ls workspace/old/ 2>/dev/null
```

| État | Action |
|---|---|
| `workspace/old/` n'existe pas | Aller §2 (bootstrap) |
| `workspace/old/` existe mais vide | Aller §2 (le Tech Lead doit déposer le legacy) |
| `workspace/old/{Project}/` contient du code, pas de `.sys/` | Aller §3 (lancer Phase 1 inventory) |
| `workspace/old/{Project}/.sys/inventory.json` existe | Aller §4 (Phase 3 extraction) |

### Étape 2 — Bootstrap d'un nouveau projet legacy

Demander au Tech Lead le nom du projet (ex. "AcmeCRM", "LegacyBilling"). Puis :

```
Pour démarrer le reverse engineering :

1. Lancer /sdd-reverse-init {ProjectName}
   → crée workspace/old/{ProjectName}/ et workspace/old/{ProjectName}/.sys/

2. Copier ou cloner le code legacy dans workspace/old/{ProjectName}/

3. Lancer /sdd-reverse-inventory {ProjectName}
   → produit l'inventaire des unités fonctionnelles candidates

4. Relire workspace/old/{ProjectName}/.sys/inventory.md (édition manuelle possible)

5. Lancer /sdd-reverse {ProjectName} unit-001 (puis unit-002, etc.)
   → produit workspace/input/feats/{n}-{Name}.md exploitable par /sdd-full

Documentation : @.claude/docs/reverse-engineering-workflow.md
```

### Étape 3 — Lancer Phase 1 (inventory)

Le legacy est déjà déposé dans `workspace/old/{Project}/` mais l'inventaire n'a pas tourné.

```
Le code legacy est en place. Lancement de la Phase 1 inventory :

/sdd-reverse-inventory {ProjectName}

Cela va :
- Scanner les langages détectés (ASPX, MVC, Java JEE, PHP, Delphi, jQuery, etc.)
- Identifier les pages, modules, unités fonctionnelles candidates
- Produire workspace/old/{ProjectName}/.sys/inventory.{md,json}

Tu pourras ensuite arbitrer les fusions/splits et lancer /sdd-reverse {unit-id} pour extraire les FEATs.
```

### Étape 4 — Phase 3 extraction

L'inventaire est prêt. Lister les unités candidates non encore extraites :

```bash
# Pseudo : parser inventory.json + lister workspace/input/feats/ pour voir ce qui reste
```

```
Inventaire prêt. Unités fonctionnelles disponibles à extraire :

| unit-id | feat_proposed | type | confidence | status |
|---|---|---|---|---|
| unit-001 | 1-Authentication-Login | form-login | high | À extraire |
| unit-002 | 2-Authentication-Logout | flow-logout | high | À extraire |
| unit-003 | 3-Navigation-Menu | navigation-menu | high | À extraire |
| unit-004 | 4-Customers-Grid-CRUD | grid-crud | high | À extraire |
| ... | | | | |

Recommandation : commencer par les unités les plus simples (auth, menu) :
  /sdd-reverse {ProjectName} unit-001

Ne pas faire de batch (1 invocation = 1 unité = 1 FEAT). Idempotent.
```

## Anti-derive

1. **Ne JAMAIS lire** directement le code legacy ad-hoc en dehors du workflow `/sdd-reverse-*`.
   Le workflow encadre la lecture sélective + l'anti-hallucination via `@.claude/rules/reverse-engineering.md`.

2. **Ne JAMAIS écrire** dans `workspace/input/feats/` à la main quand le legacy existe.
   Utiliser `/sdd-reverse {unit-id}` qui produit des FEATs avec evidence + confidence.

3. **Ne PAS confondre** avec `starting-a-new-feat` :
   - `starting-a-new-feat` : créer une feature greenfield (sans code source antérieur)
   - `starting-a-reverse-eng` : extraire une FEAT depuis un code legacy existant

4. **Ne PAS confondre** avec `/sdd-discover-stack` :
   - `/sdd-discover-stack` : détecter le stack d'un repo SDD_Pro brownfield (déjà compatible)
   - `/sdd-reverse-*` : extraire des FEATs depuis un legacy INcompatible (autre techno, autre archi)

5. **Ne JAMAIS modifier** un fichier existant SDD_Pro pour faire avancer le reverse. Le workflow est strictement isolé (cf. master prompt §3.1).

## Pointeurs

- Master prompt : `@.claude/docs/reverse-engineering-master-prompt.md`
- Design doc complet : `@.claude/docs/reverse-engineering-workflow.md`
- Règle anti-derive : `@.claude/rules/reverse-engineering.md`
- Loader autonome : `@.claude/loader.reverse.yml`
- Commandes : `/sdd-reverse-init`, `/sdd-reverse-inventory`, `/sdd-reverse`
- Cookbook : `@.claude/docs/reverse-engineering-cookbook/`
