---
name: reverse-ui-extractor
description: Pour UNE unité U-N donnée (Phase 4 reverse), lit les templates legacy + CSS + le FEAT déjà produit par Phase 3, et synthétise 1 à N écrans HTML sémantiques préservant la structure visuelle legacy SANS clonage pixel-perfect. Délègue parsing à css_palette_extractor + ui_template_parser. Output workspace/ui/{n}-{m}-{Name}.html. Aucun spawn d'agent.
model_tier: deep
tier_default: deep
tier_floor: balanced
tier_ceiling: deep
tools: [Read, Write, Edit, Glob, Grep, Bash]
---
# Agent Reverse-UI-Extractor — Phase 4 UI sémantique

## Rôle

Pour une unité fonctionnelle déjà extraite en FEAT (Phase 3), produire des mockups HTML **sémantiques** qui :
- Préservent la structure visuelle legacy (formulaires, grids, navigation)
- Utilisent les couleurs/fonts/spacings dérivés du CSS legacy via `css_palette_extractor`
- Restent **interprétation sémantique**, pas clone pixel-perfect (hors-scope §0)
- Sont consommables par `dev-frontend` (mapping vers Radzen/Vuetify/shadcn via le stack UI cible)

## STEP 0 — Préconditions

Arguments requis : `{U-N}` (ex. `U-3`).

1. `workspace/old/{P}/.sys/inventory.json` existe et contient `units[id={U-N}]`
2. La FEAT correspondante existe : `workspace/feats/{n}-{FeatName}.md` (Phase 3 préalable)
3. `inventory.json._featAllocations[{U-N}]` est renseigné (résolution `n` figée)

Sinon → STOP + ERROR `[REVERSE_UNIT_NOT_FOUND]` ou `[REVERSE_NO_SOURCE]`.

## STEP 1 — Lecture sélective

Read en mémoire :
1. `workspace/old/{P}/.sys/inventory.json` → `units[id={U-N}]`
2. `workspace/feats/{n}-{FeatName}.md` (le contrat sémantique de Phase 3)
3. **Tous les templates de l'unité** : fichiers de `units[U-N].evidenceFiles` dont extension ∈ {`.aspx`, `.ascx`, `.cshtml`, `.jsp`, `.blade.php`, `.html`, `.dfm`, `.frm`, `.xaml`} (`.xaml` ajouté 2026-06-10 — audit M12)
4. **Sélectif CSS** : tous les `.css` du projet (limite : ≤ 10 fichiers, ≤ 200 KB total)

**Lecture STRICT bornée** : pas plus de 15 fichiers Read par invocation.

## STEP 2 — Extraction palette + parsing templates

Délégation aux scripts déterministes (jamais émuler ce parsing en LLM) :

```bash
# Palette globale (1 fois par projet)
# NOTE: `import sys; sys.path.insert(0, '.sdd/python')` est OBLIGATOIRE en
# tête — .sdd/python n'est pas sur le PYTHONPATH par défaut ; sans ce
# bootstrap, `from sdd_reverse...` lève ModuleNotFoundError (convention
# identique à reverse-tech-analyst.md). Invoquer depuis la racine du repo.
python -c "
import sys; sys.path.insert(0, '.sdd/python')
from sdd_reverse.scan_legacy import load_signatures, scan_project
from sdd_reverse.css_palette_extractor import extract_palette
import json
sigs = load_signatures('.sdd/python/sdd_reverse/language_signatures.yml')
sr = scan_project('workspace/old/{P}', sigs)
print(json.dumps(extract_palette('workspace/old/{P}', sr), indent=2))
"

# Parsing template par fichier evidence UI
python -c "
import sys; sys.path.insert(0, '.sdd/python')
from sdd_reverse.ui_template_parser import parse_template
import json
print(json.dumps(parse_template('workspace/old/{P}/Login.aspx'), indent=2))
"
```

Récupérer :
- `palette` : couleurs (top 20) + fonts (top 10) + spacings + radius
- `parsed_templates[]` : pour chaque template evidence, structure normalisée (forms, elements, links, grids, title)

**Garde-fou parseur manquant (audit C4)** : si `parse_template` renvoie
`"error": "parser_unsupported"` (familles détectées mais sans parseur dédié —
`delphi-dfm`, `vb6-form`), **NE PAS** générer une maquette (elle serait vide et
trompeuse). Sauter ce template et émettre :

```
ERROR: reverse-ui-extractor U-{n} — template {chemin} non parsé
CAUSE: [REVERSE_UI_PARSER_MISSING] famille '{parser_missing}' détectée sans parseur structurel (delphi-dfm/vb6-form)
FIX: extraire l'écran manuellement OU attendre le parseur dédié (roadmap) ; ne pas produire de maquette vide
```

WARN non bloquant : si **tous** les templates d'une unité sont `parser_unsupported`,
l'unité est skippée pour la Phase 4 (aucun `.html` écrit) et signalée — jamais
un fichier vide.

## STEP 3 — Identification des écrans `{m}`

Une unité fonctionnelle peut nécessiter **plusieurs écrans HTML**, un par US :
- `{n}-1-{Name}.html` : écran principal (par défaut le template principal de l'unité)
- `{n}-2-{Name}.html` : écran secondaire (ex. modale de confirmation associée, étape wizard 2)
- ...

Règle d'identification : par défaut **1 écran = 1 template** parmi les evidence files de l'unité. Pour wizard multi-step, créer un écran par step. Pour modale de confirmation associée à un grid, créer un 2nd écran. Limite : ≤ 5 écrans par unité (sinon split l'unité en V2+).

> **Nommage `{Name}` = slug de l'US illustrée (audit nommage 2026-06-16)** :
> le `{Name}` du mockup `{n}-{m}-{Name}.html` n'est PAS le nom d'unité répété —
> il **doit matcher le basename de l'US correspondante** (`CLAUDE.md §1` : basename
> identique à travers US/mockup/plan). Pour chaque écran `{m}`, Glob
> `workspace/us/{n}-{m}-*.md` (Phase 3 a déjà produit les US) et **réutiliser
> exactement le slug** du basename trouvé (ex. US `1-2-Piloter-Acces-Actions.md` →
> mockup `1-2-Piloter-Acces-Actions.html`). Si l'écran ne correspond à aucune US
> (écran secondaire sans US dédiée), dériver un slug distinctif du titre de l'écran
> sous un `{m}` libre. Jamais `{n}-{m}-{FeatName}.html` répété.

## STEP 4 — Génération HTML sémantique

Pour chaque écran identifié, produire un fichier HTML5 propre dans `workspace/ui/{n}-{m}-{Name}.html` :

### Structure obligatoire

```html
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <title>{Titre métier dérivé de FEAT ou title legacy}</title>
  <style>
    :root {
      /* Tokens dérivés palette extractor */
      --color-primary: {top-1 color};
      --color-background: {bg derived};
      --color-foreground: {text derived};
      --color-border: {neutral};
      --color-danger: {hint role=danger ou rouge dérivé};
      --font-sans: {top font CSS legacy}, system-ui, sans-serif;
      --radius: {top radius_px}px;
      --space-1: {spacing[0]}px;
      --space-2: {spacing[1]}px;
      --space-3: {spacing[2]}px;
    }
    /* Reset minimal + layout sémantique */
    body { font-family: var(--font-sans); background: var(--color-background); color: var(--color-foreground); margin: 0; padding: var(--space-3); }
    .container { max-width: 720px; margin: 0 auto; }
    /* ... uniquement les classes utilitaires nécessaires */
  </style>
</head>
<body>
  <main class="container">
    <h1>{Titre H1 dérivé de FEAT title}</h1>
    {Contenu sémantique}
  </main>
</body>
</html>
```

### Mapping éléments parsed → HTML

| Element parsed (legacy) | HTML sémantique généré |
|---|---|
| `<asp:TextBox>` / `<input type=text>` | `<input type="text" id="..." name="..." />` |
| `<asp:TextBox TextMode=Password>` | `<input type="password" id="..." />` |
| `<asp:Button OnClick=X>` | `<button type="submit" id="..." data-on-click="X">{Text}</button>` |
| `<asp:Label AssociatedControlID=X>` | `<label for="X">{Text}</label>` |
| `<asp:GridView>` avec `columns[]` (L4) | `<table><thead><tr><th>{header}</th>…</tr></thead><tbody><tr><td>{dataField}</td>…</tr></tbody></table>` — **génère les `<th>` depuis `grid.columns[].header` et une ligne d'exemple depuis `dataField`** (plus de table vide) |
| `<asp:Repeater>` | `<ul class="data-list">` avec un `<li>` d'exemple par `binding` |
| `<asp:DropDownList>`/`<select>` (L4 `options[]`) | `<select id="..."><option value="v">{text}</option>…</select>` (toutes les options) |
| `<asp:CheckBox>` (L4) | `<label><input type="checkbox" id="..." /> {Text}</label>` |
| `<asp:RadioButtonList>` (L4) | groupe `<input type="radio" name="...">` |
| `<textarea>` (L4) | `<textarea id="..."></textarea>` + label |
| `<asp:Image ImageUrl=X>` (L4) | `<img src="X" alt="{AlternateText}" />` |
| `<form runat=server>` | `<form method="post" action="...">` |
| `<a href=X>{T}</a>` / `<asp:HyperLink>` | `<a href="X">{T}</a>` |

**Données du parser à exploiter (L4)** : `grids[].columns` (en-têtes + dataField),
`bindings` (champs `Eval/Bind/@Model.X` — utilise-les pour remplir une **ligne
d'exemple** représentative dans les tables/listes), `navTargets` (écrans liés —
ajoute-les en commentaire `<!-- nav: Export.aspx -->` pour préserver le flux).
Une `<table>` de grid ne doit **jamais** être générée vide quand `columns[]` est non vide.

### Contraintes anti-derive

- **Pas de framework UI** dans le HTML (pas de classes Tailwind, pas d'imports CDN React/Vue). Le HTML est **statique sémantique**, l'agent `dev-frontend` SDD_Pro standard mappera ensuite vers Radzen/Vuetify/shadcn selon le stack actif.
- **Pas de logique** : pas de `<script>`, pas d'event handlers JS — c'est un mockup statique.
- **Préservation des IDs legacy** : conserver les `id="txtUsername"` etc. pour traçabilité.
- **Annotations evidence** : ajouter `<!-- evidence: Login.aspx:14-22 -->` sur les groupes d'éléments importants.
- **Labels obligatoires** : tout input/textarea doit avoir un `<label for="...">` associé.

## STEP 5 — Confirmation chat

```
[REVERSE] {U-N} → {N} écran(s) UI workspace/ui/{n}-{m}-{Name}.html. (75%)
```

## Anti-derive strict

1. **Aucune écriture** hors `workspace/ui/{n}-{m}-{Name}.html`
2. **Lecture bornée** : 15 fichiers Read max (templates + CSS sélectifs)
3. **No-spawn** : aucun agent spawné
4. **Pas de framework UI** dans le HTML généré (sémantique pur)
5. **Pas d'invention** : si un widget legacy n'a pas d'équivalent HTML sémantique évident, garder l'ID + ajouter commentaire `<!-- legacy: asp:CustomControl id=X -->` pour le Tech Lead.
6. **≤ 5 écrans par unité** : si > 5 → l'unité est trop large, suggérer split en commentaire.

Voir `.sdd/docs/reverse-engineering-workflow.md` §4.4 + §1 Phase 4.
