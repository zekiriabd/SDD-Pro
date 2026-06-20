# /sdd-reverse-ui — Phase 4 : capture runtime de l'UI d'une unité legacy → HTML mockup sémantique

> ⚠️ **Commande du workflow reverse engineering** (séparé du pipeline SDD_Pro principal).
> Master prompt : `@.claude/docs/reverse-engineering-master-prompt.md`
> Design doc : `@.claude/docs/reverse-engineering-phase4-runtime.md`
> ADR : `@.claude/docs/adrs/ADR-20260609T221251-d3ce-reverse-phase4-runtime-capture.md`
> Loader : `@.claude/loader.reverse.yml` section `reverse-ui-extractor`
> Règle : `@.claude/rules/reverse-engineering.md` §6

Capture le rendu navigateur d'UNE unité legacy (HTML post-JS + CSS computed) et produit UN mockup HTML sémantique annoté dans `workspace/input/ui/{n}-{m}-{Name}.html`.

Le mockup généré est :
- Strictement compatible avec `dev-frontend` (consommé en Phase 6 par `/sdd-full`)
- Enrichi d'attributs `data-legacy-*` (source, component, lines) pour la traçabilité
- Accompagné d'une palette CSS extraite dans `workspace/input/ui/_legacy-style/tokens.css`
- Référencé dans `workspace/input/ui/_legacy-style/components-inventory.md`

**Usage** :
- `/sdd-reverse-ui {ProjectName} {unit-id}` (ex. `/sdd-reverse-ui AspxDemo unit-001`)
- `/sdd-reverse-ui {unit-id}` (legacy déduit du contexte courant)

**Précondition obligatoire** : Phase 1 (`inventory.json`) ET Phase 3 (`workspace/input/feats/{n}-{Name}.md`) doivent avoir tourné. Phase 2 (`db-schema.json`) optionnelle.

---

## STEP 1 — Résolution du chemin projet + unit-id

Arguments :
- `{arg1}` : ProjectName ou path (ex. `AspxDemo` ou `workspace/old/AspxDemo`)
- `{arg2}` (si présent) : `{unit-id}` (format `^unit-\d{3}$`)

Résolution `LEGACY_PATH` :
- Si `workspace/old/{arg1}/` existe → `LEGACY_PATH = workspace/old/{arg1}`
- Sinon si `{arg1}` est un chemin valide → `LEGACY_PATH = {arg1}`
- Sinon → ERROR `[REVERSE_PRECONDITION]`

Si un seul arg passé et qu'il matche `^unit-\d{3}$`, traiter comme `{unit-id}` et déduire `LEGACY_PATH` du dernier projet actif (lecture de `workspace/old/*/` modifié le plus récemment).

Vérifier que `{unit_id}` matche le pattern. Sinon → ERROR `[REVERSE_PRECONDITION]`.

---

## STEP 2 — Préconditions

```bash
INVENTORY_JSON="${LEGACY_PATH}/.sys/inventory.json"
```

Si absent → ERROR :
```
ERROR: /sdd-reverse-ui — Phase 1 inventory manquant
CAUSE: [REVERSE_PRECONDITION] {LEGACY_PATH}/.sys/inventory.json absent
FIX: lancer /sdd-reverse-inventory {ProjectName} d'abord
```

Parser inventory.json, chercher l'unité `{unit_id}`. Si absente → ERROR `[REVERSE_UNIT_NOT_FOUND]`.

Récupérer :
- `feat_number_proposed` → `{n}`
- `feat_name_proposed` → `{Name}`
- `page_path` (route HTTP à capturer, ex. `/Default.aspx`)
- `language_detected` (pour appel `legacy_runner`)

Vérifier que la FEAT correspondante existe :
```bash
TARGET_FEAT="workspace/input/feats/{n}-{Name}.md"
```

Si absente → ERROR :
```
ERROR: /sdd-reverse-ui — FEAT non extraite
CAUSE: [REVERSE_PRECONDITION] {n}-{Name}.md absent (Phase 3 pas executee)
FIX: lancer /sdd-reverse {unit-id} d'abord (Phase 3 produit la FEAT)
```

---

## STEP 3 — Idempotence : vérifier mockup existant

```bash
TARGET_UI="workspace/input/ui/{n}-1-{Name}.html"  # convention : m=1 pour 1ère unité
```

Si déjà existant :
1. Lire son commentaire de tête (`<!-- generated-by: sdd-reverse-ui -->`, `<!-- unit-hash: sha256:... -->`)
2. Si `unit-hash` identique au hash calculé maintenant → **SKIP silencieux**. Émettre :
   ```
   [REVERSE-UI] Mockup {n}-1-{Name}.html deja capture (hash inchange). SKIP. (100%)
   ```
   exit 0.
3. Sinon (hash diff ou pas d'annotation reverse) → continuer + WARN :
   ```
   🟡 [REVERSE-UI/WARN] Mockup {n}-1-{Name}.html existe (hash diff ou non-reverse). Re-capture en cours.
   ```

---

## STEP 4 — Lancement du runtime legacy (Phase 4a)

```bash
python -m sdd_reverse_scripts.legacy_runner \
  --project-path "{LEGACY_PATH}" \
  --json
```

Parser la sortie JSON :
- Si `ok: true` ET `mode: runtime` → continuer Phase 4b (Playwright capture)
- Si `ok: false` ET `mode: fallback-static` → basculer en mode fallback (cf. STEP 7)

Le subprocess legacy reste **vivant** entre STEP 4 et STEP 8 (le cleanup explicite est fait en STEP 8). Le pidfile vit dans `{LEGACY_PATH}/.sys/.runner.pid`.

Émettre :
```
[REVERSE-UI] Runtime legacy demarre sur {base_url} (runner: {runner_id}, pid: {pid}). (20%)
```

---

## STEP 5 — Capture Playwright (Phase 4b)

Calculer la route :
```python
route = derive_route_from_unit_path(unit.page_path)
# Ex: "Default.aspx" -> "/Default.aspx"
```

Si auth requise (présence de `{LEGACY_PATH}/.sys/auth-cookies.json`), charger les cookies via `load_auth_cookies()`.

Lancer la capture via le module Python :
```python
from sdd_reverse import playwright_capture as pc

result = pc.capture_url(
    base_url=base_url,
    route=route,
    unit_id=unit_id,
    auth_cookies=cookies,
    take_screenshot=True,
)
```

Si `result.ok == False` :
- Si `REVERSE_UI_PLAYWRIGHT_MISSING` → ERROR (instructions install) + cleanup STEP 8
- Si `REVERSE_UI_CAPTURE_EMPTY` → WARN + fallback static parse possible
- Si `REVERSE_UI_AUTH_REQUIRED` → WARN (cookies à fournir)
- Sinon → ERROR + cleanup STEP 8

Persister :
```python
pc.write_capture_outputs(result, Path("{LEGACY_PATH}/.sys/captures"))
```

Émettre :
```
[REVERSE-UI] HTML capture ({html_size} chars), palette extraite. (50%)
```

---

## STEP 6 — Extraction palette + composants (parallèle)

Ces 2 étapes peuvent tourner en parallèle (paths disjoints) :

### 6a. Palette CSS → tokens.css

```python
from sdd_reverse import css_palette_extractor as cpe

# Aggregate from all palette JSONs in .sys/captures/ (this unit + previous)
palette_files = list(Path("{LEGACY_PATH}/.sys/captures").glob("*-palette.json"))
agg = cpe.aggregate_from_files(palette_files)
cpe.write_tokens_css(
    agg,
    Path("workspace/input/ui/_legacy-style/tokens.css"),
    project_name="{ProjectName}",
    extraction_date="{ISO-8601}",
    routes=[unit.page_path for unit in captured_units],
)
```

### 6b. Components inventory → components-inventory.md

```python
from sdd_reverse import legacy_components_extractor as lce

# Same: aggregate from all captured HTMLs in .sys/captures/
inv = lce.GlobalInventory()
for html_file in Path("{LEGACY_PATH}/.sys/captures").glob("*.html"):
    unit_id_str = html_file.stem
    html_content = html_file.read_text(encoding="utf-8")
    page_path = lookup_page_path(unit_id_str, inventory.json)
    components = lce.detect_components_in_html(html_content)
    inv.pages.append(lce.PageInventory(unit_id=unit_id_str, page_path=page_path, components=components))

lce.write_components_inventory(
    inv,
    Path("workspace/input/ui/_legacy-style/components-inventory.md"),
    project_name="{ProjectName}",
    extraction_date="{ISO-8601}",
)
```

Émettre :
```
[REVERSE-UI] Palette + composants extraits. (65%)
```

---

## STEP 7 — Spawn agent reverse-ui-extractor

```
Agent: reverse-ui-extractor
  args: {LEGACY_PATH} {unit_id}
  task: |
    Lis le HTML brut capture par Playwright dans
    {LEGACY_PATH}/.sys/captures/{unit_id}.html.

    Applique le STEP 0-7 de @.claude/agents/reverse-ui-extractor.md :
    1. Preflight + lecture FEAT correspondante (workspace/input/feats/{n}-{Name}.md)
    2. Lecture HTML brut + palette + components-inventory
    3. Strip runtime artifacts (ViewState, scripts dynamiques, styles inline)
    4. Annote la structure (data-legacy-source, data-legacy-component, data-legacy-lines)
    5. Normalise les composants (table, form, button, input — labels conserves)
    6. Auto-validation (HTML bien forme, structure semantique, refs tokens.css)
    7. Write atomique workspace/input/ui/{n}-1-{Name}.html

    Output francais. Anti-derive REVERSE-UI strict (cf. règle §6). Aucune invention.

    Mode fallback : si le STEP 4-5 a bascule en static (legacy non lancable),
    l'HTML d'entree est le template legacy brut, pas la capture. Le flag
    `<!-- capture-mode: static -->` est ajoute dans le mockup.
```

L'agent émet ses updates `[REVERSE-UI] ... (X%)` puis un verdict 1L `[DONE]`.

---

## STEP 8 — Cleanup legacy runtime

**Obligatoire**, même en cas d'erreur des STEPs 5-7 :

```bash
python -m sdd_reverse_scripts.legacy_runner \
  --cleanup "{LEGACY_PATH}" \
  --json
```

Termine le process subprocess + supprime le pidfile.

Émettre :
```
[REVERSE-UI] Cleanup runtime termine. (95%)
```

---

## STEP 9 — Vérification post-execution

Vérifier la présence des outputs :
1. `workspace/input/ui/{n}-1-{Name}.html` (mockup sémantique)
2. `workspace/input/ui/_legacy-style/tokens.css` (palette)
3. `workspace/input/ui/_legacy-style/components-inventory.md` (composants)
4. `{LEGACY_PATH}/.sys/captures/{unit_id}.{html,png,palette.json}` (artefacts bruts)
5. `{LEGACY_PATH}/.sys/modules/{module-id}/ui-extraction-{unit-id}.md` (rapport agent)

Si l'un des 3 premiers manque → l'agent a STOP. Propager l'ERROR (les 2 derniers sont des artefacts, leur absence est un WARN).

---

## STEP 10 — Verdict final

```
[DONE] /sdd-reverse-ui {unit-id} — Mockup UI capture (mode: {runtime|static}).
       Mockup       : workspace/input/ui/{n}-1-{Name}.html
       Tokens CSS   : workspace/input/ui/_legacy-style/tokens.css
       Composants   : workspace/input/ui/_legacy-style/components-inventory.md
       Screenshot   : {LEGACY_PATH}/.sys/captures/{unit-id}.png

Prochaines etapes :
  - Si mode: runtime, fidelite max (HTML post-JS) — consommable direct par /sdd-full {n}
  - Si mode: static, fidelite reduite — relire le mockup, completer manuellement si besoin
  - Pour capturer l'unite suivante : /sdd-reverse-ui {ProjectName} {next-unit-id}
```

---

## Mode fallback static (legacy non lançable)

Si `legacy_runner.py` retourne `ok: false` (runner unavailable, binary missing, port conflict, ready timeout) :

1. **Pas d'ERROR** : on bascule en mode static parse (le mockup est moins fidèle mais produit quand même)
2. Skip STEP 5 (pas de Playwright)
3. Au STEP 6 : palette extraite des fichiers `.css` du legacy (pas du computed)
4. Au STEP 7 : l'agent reçoit le **template legacy brut** au lieu du HTML capturé
5. Le mockup généré porte `<!-- capture-mode: static -->`
6. Le verdict mentionne `mode: static` explicitement

Le Tech Lead peut basculer en runtime manuellement plus tard (relancer `/sdd-reverse-ui` après avoir corrigé le runner).

---

## Anti-derive

- 1 invocation = 1 unité = 1 mockup. Pas de batch.
- Idempotent : re-run avec hash unité inchangé = skip silencieux.
- Strictement orchestrante : aucune logique métier ici, tout dans les scripts Python + l'agent.
- Cleanup obligatoire en STEP 8, même en cas d'erreur (try/finally implicite — pas de pidfile orphelin).
- Aucun fichier SDD_Pro existant modifié. Lectures uniquement (FEAT, inventory).
- Aucune mutation de la FEAT.md (lecture passive seulement).

## Exit codes

- `0` : success (mockup capturé, runtime OU static)
- `1` : précondition échouée (project introuvable, unit-id invalide, FEAT absente)
- `2` : inventory.json absent (Phase 1 pas exécutée)
- `3` : capture vide (HTML < 500 chars) — page erreur, redirect, etc.
- `4` : agent reverse-ui-extractor STOP avec ERROR
- `5` : cleanup runtime échoué (pidfile orphelin — investiguer manuellement)

## Préconditions stack-spécifiques

### ASP.NET WebForms (`dotnet-webforms`)
- IIS Express dans PATH (Windows uniquement)
- Sinon : fallback static parse

### ASP.NET MVC / Razor (`dotnet-mvc`)
- .NET SDK installé (`dotnet --version` OK)
- `*.csproj` présent sous `{LEGACY_PATH}`

### Java JEE Spring Boot (`java-jee`, `java-jee-gradle`)
- Maven OU Gradle dans PATH
- `pom.xml` ou `build.gradle[.kts]` présent

### PHP procédural (`php-procedural`)
- PHP CLI dans PATH (`php --version` OK)

### Playwright (toutes stacks runtime)
- `pip install playwright` + `python -m playwright install chromium` (~150 MB)
- Détection automatique au STEP 5 ; install non automatique

Détail : `@.claude/docs/reverse-engineering-phase4-runtime.md` §9 + §10
