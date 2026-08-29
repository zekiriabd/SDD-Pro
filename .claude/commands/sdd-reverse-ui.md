---
description: Phase 4 du workflow reverse — extraction UI sémantique d'UNE unité U-N en mockup(s) HTML statique. Spawn agent reverse-ui-extractor (Opus 4.8). Output workspace/ui/{n}-{m}-{Name}.html consommable par dev-frontend lors de /sdd-full.
---
# /sdd-reverse-ui {U-N} [--json]

## Rôle

Lancer la **Phase 4** : traduire les templates legacy d'une unité U-N en mockups HTML sémantiques préservant la structure visuelle (sans clonage pixel-perfect).

## Args

| Arg | Type | Description |
|---|---|---|
| `{U-N}` | string requis | Identifiant U-N stable, doit avoir une FEAT Phase 3 déjà produite |
| `--json` | flag | Émet rapport extraction en JSON |

## Pré-conditions

1. Phase 1 + Phase 3 préalables pour cette unité :
   - `workspace/old/{P}/.sys/inventory.json` contient `units[id={U-N}]`
   - `inventory.json._featAllocations[{U-N}]` renseigné → résolution `n` figée
   - `workspace/feats/{n}-{Name}.md` existe (sinon → ERROR `[REVERSE_NO_SOURCE]`)
2. Les `units[U-N].evidenceFiles` contiennent au moins 1 fichier UI (`.aspx`, `.ascx`, `.cshtml`, `.jsp`, `.blade.php`, `.html`, `.dfm`, `.frm`, `.xaml`). Sinon → SKIP silencieux (unité backend-only sans UI). (`.xaml` ajouté 2026-06-10 — audit M12 : WPF supporté en Phase 1 mais SKIPpé en silence en Phase 4.)

## Actions

1. **Spawn unique** `Agent(reverse-ui-extractor)` avec args = `{U-N}`
2. L'agent suit STEP 1 à 5 documenté dans `.claude/agents/reverse-ui-extractor.md`
3. Délégation scripts déterministes : `css_palette_extractor` + `ui_template_parser`
4. Génération 1-5 fichiers HTML par unité (selon écrans détectés)
5. Émission ligne chat finale `[REVERSE] {U-N} → {M} écran(s) UI. (75%)`

## Sortie

```
workspace/ui/
├── {n}-1-{Name}.html             (écran principal)
├── {n}-2-{Name}.html             (modale / wizard step 2 / écran secondaire, si applicable)
└── ...
```

Format : HTML5 sémantique pur (pas de framework UI inline). Mapping vers Radzen/Vuetify/shadcn fait par `dev-frontend` lors de `/sdd-full {n}`.

## Voie d'usage standard

Phase 4 est **optionnelle**. Elle s'invoque après Phase 3 :
```
/sdd-reverse-inventory MyLegacy
/sdd-reverse U-3              # Phase 3 → FEAT 7-Login.md
/sdd-reverse-ui U-3           # Phase 4 → workspace/ui/7-1-Login.html
```

Skip cohérent : si le Tech Lead préfère que `dev-frontend` regénère l'UI from scratch via le mapping FEAT-only (sans mockup HTML), ne pas lancer cette phase. La FEAT seule reste valide pour `/sdd-full`.

## Anti-derive

- Aucun spawn d'autre agent que `reverse-ui-extractor`
- Pas de framework UI dans le HTML généré (sémantique pur, le mapping vers DS cible est fait par `dev-frontend`)
- Pas de logique (zéro `<script>`, zéro event handler)
- Préservation IDs legacy pour traçabilité
- ≤ 5 écrans par unité (split l'unité si plus)

Voir `.sdd/docs/reverse-engineering-workflow.md` §4.4 + Phase 4 du pipeline §1.
