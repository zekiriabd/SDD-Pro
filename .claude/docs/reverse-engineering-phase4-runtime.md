# Reverse Engineering Phase 4 — Runtime Capture (Design Doc, 2026-06-10)

> **Statut** : Draft pour validation Tech Lead, Sprint 1/4 du chantier Phase 4.
> **ADR** : `docs/adrs/ADR-20260609T221251-d3ce-reverse-phase4-runtime-capture.md`
> **Spec V1 originelle** : `docs/reverse-engineering-workflow.md §5` (format de sortie HTML sémantique)
> **Isolation** : nouveau fichier. Aucun fichier SDD_Pro existant modifié, hormis :
> - `rules/reverse-engineering.md` (extension §6 — explicitement autorisée car règle dédiée au workflow reverse)
> - `loader.reverse.yml` (extension — loader dédié au workflow reverse, déjà séparé du loader principal)

---

## TOC

- §1 — Vue d'ensemble du pipeline Phase 4
- §2 — Composant 1 : `legacy_runner.py` (détection + lancement)
- §3 — Composant 2 : `playwright_capture.py` (navigation + capture)
- §4 — Composant 3 : `css_palette_extractor.py` (palette → tokens.css)
- §5 — Composant 4 : `legacy_components_extractor.py` (inventaire composants)
- §6 — Composant 5 : Agent `reverse-ui-extractor` (Sonnet)
- §7 — Composant 6 : Commande `/sdd-reverse-ui {unit-id}`
- §8 — Contrats inter-composants (data flow)
- §9 — Configuration : `runner_signatures.yml`
- §10 — Auth : cookies pré-authentifiés via `inventory.json`
- §11 — Fallback static parse (si legacy non lançable)
- §12 — Format des outputs (HTML sémantique + tokens.css + components-inventory.md)
- §13 — Plan de tests
- §14 — Codes d'erreur `[REVERSE_UI_*]`
- §15 — Périmètre Sprint 1-4 (livrables détaillés)

---

## 1. Vue d'ensemble du pipeline Phase 4

```
Précondition : Phase 1 (inventory.json) + Phase 3 (FEAT.md) ont tourné.

/sdd-reverse-ui {unit-id}
  │
  ├─ STEP 1 : Lecture inventory.json + FEAT.md → identifie route + unit_hash
  │
  ├─ STEP 2 : legacy_runner.py
  │   ├─ détecte stack via inventory-raw.json (languages[].id)
  │   ├─ lance serveur (subprocess) :
  │   │   ├─ ASPX → iisexpress.exe /path:LEGACY_PATH /port:PORT
  │   │   ├─ MVC  → dotnet run --project LEGACY_PATH/*.csproj
  │   │   ├─ JEE  → mvn -f LEGACY_PATH/pom.xml spring-boot:run -Dserver.port=PORT
  │   │   └─ PHP  → php -S 127.0.0.1:PORT -t LEGACY_PATH
  │   ├─ attend ready (HTTP poll sur http://127.0.0.1:PORT/, max 60s)
  │   └─ retourne {base_url, process_handle}
  │
  ├─ STEP 3 : playwright_capture.py
  │   ├─ launch Chromium headless
  │   ├─ (optionnel) inject auth cookies depuis inventory.json
  │   ├─ goto {base_url}/{route} (route = inventory.unit.page_path stripé de l'extension)
  │   ├─ wait until networkidle (max 30s)
  │   ├─ capture outerHTML + computedStyle agrégé
  │   ├─ capture screenshot (référence designer, optionnel)
  │   └─ retourne {raw_html, computed_palette, screenshot_path}
  │
  ├─ STEP 4 : css_palette_extractor.py
  │   ├─ déduplique couleurs / fonts / spacings observés
  │   └─ produit/enrichit workspace/input/ui/_legacy-style/tokens.css
  │
  ├─ STEP 5 : legacy_components_extractor.py
  │   ├─ heuristique <table>, <form>, <dialog>, <nav>, <select>, <input>
  │   └─ produit/enrichit workspace/input/ui/_legacy-style/components-inventory.md
  │
  ├─ STEP 6 : agent reverse-ui-extractor (Sonnet)
  │   ├─ lit raw_html + FEAT.md + cookbook
  │   ├─ strip styles inline, scripts, attributs runtime (ViewState ASPX, csrf tokens)
  │   ├─ annote avec data-legacy-source/component/lines
  │   └─ produit HTML sémantique workspace/input/ui/{n}-{m}-{Name}.html
  │
  ├─ STEP 7 : cleanup legacy server (process_handle.terminate())
  │
  └─ STEP 8 : verdict 1L [DONE] UI mockup {n}-{Name} capturé ({approche}). (100%)

Si STEP 2 échoue (legacy non lançable) → fallback :
  └─ STEP 2b : static parse direct du template legacy (skip steps 3-5)
     → mockup HTML moins fidèle mais output garanti
```

---

## 2. Composant 1 : `legacy_runner.py`

### 2.1 Emplacement et rôle

`.claude/python/sdd_reverse_scripts/legacy_runner.py`

Détecte le stack legacy depuis `inventory-raw.json`, lance le serveur correspondant en subprocess, attend la disponibilité HTTP, retourne base URL + handle de cleanup.

### 2.2 Signature CLI

```bash
python -m sdd_reverse_scripts.legacy_runner \
  --project-path workspace/old/AspxDemo \
  --port 5099 \
  --timeout 60 \
  [--mode static]   # bypass runtime, retourne static-parse marker
  [--keep-running]  # ne kill pas le process à la sortie (debug)
```

Sortie stdout JSON :
```json
{
  "ok": true,
  "mode": "runtime",
  "stack": "dotnet-webforms",
  "runner": "iisexpress",
  "base_url": "http://127.0.0.1:5099",
  "pid": 12345,
  "ready_at": "2026-06-10T10:32:18Z",
  "warnings": []
}
```

En cas d'échec :
```json
{
  "ok": false,
  "mode": "fallback-static",
  "stack": "dotnet-webforms",
  "errors": [
    { "code": "REVERSE_UI_RUNNER_UNAVAILABLE", "detail": "iisexpress.exe not found in PATH" }
  ]
}
```

### 2.3 Détection du stack

Lit `{project-path}/.sys/inventory-raw.json`, prend `languages[0].id` (langage dominant) :

| Language detected | Runner | Détection présence | Commande |
|---|---|---|---|
| `dotnet-webforms` | IIS Express | `where iisexpress.exe` | `iisexpress.exe /path:{abs_path} /port:{port}` |
| `dotnet-mvc` | Kestrel via dotnet CLI | `where dotnet` | `dotnet run --project {csproj} --urls http://127.0.0.1:{port}` |
| `java-jee` | Tomcat embedded | `where mvn` ou `where gradle` | `mvn spring-boot:run -Dserver.port={port}` ou `gradle bootRun --args="--server.port={port}"` |
| `php-procedural` | PHP built-in | `where php` | `php -S 127.0.0.1:{port} -t {abs_path}` |
| Autre | Aucun | — | Exit 2 + `[REVERSE_UI_RUNNER_UNSUPPORTED]` |

### 2.4 Ready check (HTTP poll)

```python
def wait_ready(base_url: str, timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(base_url, timeout=2)
            if r.status_code < 500:  # 200/302/401 = process up
                return True
        except (requests.ConnectionError, requests.Timeout):
            pass
        time.sleep(1)
    return False
```

### 2.5 Cleanup atomique

Le runner emploie `atexit` + handlers SIGINT/SIGTERM pour garantir le `process.terminate()` du subprocess legacy même en cas d'interruption. Un `pidfile` est écrit dans `{project-path}/.sys/.runner.pid` pour permettre `cleanup` manuel via `python -m sdd_reverse_scripts.legacy_runner --cleanup {project-path}`.

### 2.6 Configuration de port

Port par défaut = `5099`. Override possible via `--port`. Le runner essaie 5 ports successifs (5099-5103) en cas de conflit avant d'abandonner.

### 2.7 Sécurité

- Listen sur `127.0.0.1` uniquement (jamais `0.0.0.0`)
- Subprocess lancé sans shell (liste args)
- Pas d'execution de scripts arbitraires depuis le legacy (pas de PHP avec eval injecté, pas de classloading dynamique JEE)
- Le `cwd` du subprocess est `{project-path}` strict — pas d'évasion path

---

## 3. Composant 2 : `playwright_capture.py`

### 3.1 Emplacement et rôle

`.claude/python/sdd_reverse_scripts/playwright_capture.py`

Lance Playwright Chromium headless, navigue chaque route, capture HTML rendu post-JS + palette CSS.

### 3.2 Signature CLI

```bash
python -m sdd_reverse_scripts.playwright_capture \
  --base-url http://127.0.0.1:5099 \
  --route /Default.aspx \
  --output-html workspace/old/AspxDemo/.sys/captures/unit-001.html \
  --output-palette workspace/old/AspxDemo/.sys/captures/unit-001-palette.json \
  --output-screenshot workspace/old/AspxDemo/.sys/captures/unit-001.png \
  --wait-network-idle 30 \
  [--auth-cookies-file workspace/old/AspxDemo/.sys/auth-cookies.json]
```

### 3.3 Logique

```python
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    ctx = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="SDDPro-Reverse-Capture/1.0",
    )
    if auth_cookies:
        await ctx.add_cookies(auth_cookies)
    page = await ctx.new_page()
    await page.goto(f"{base_url}{route}", wait_until="networkidle", timeout=wait_network_idle * 1000)

    raw_html = await page.content()  # full outerHTML including post-JS injection
    palette = await page.evaluate(EXTRACT_PALETTE_JS)
    screenshot_bytes = await page.screenshot(full_page=True)

    await browser.close()
```

### 3.4 Script JS d'extraction palette

```javascript
const EXTRACT_PALETTE_JS = `
  () => {
    const allEls = document.querySelectorAll('*');
    const colors = new Set();
    const bgs = new Set();
    const fonts = new Set();
    const spacings = new Set();
    allEls.forEach(el => {
      const cs = getComputedStyle(el);
      if (cs.color && cs.color !== 'rgba(0, 0, 0, 0)') colors.add(cs.color);
      if (cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)') bgs.add(cs.backgroundColor);
      if (cs.fontFamily) fonts.add(cs.fontFamily);
      if (cs.padding) spacings.add(cs.padding);
      if (cs.margin) spacings.add(cs.margin);
    });
    return {
      colors: [...colors],
      backgrounds: [...bgs],
      fonts: [...fonts],
      spacings: [...spacings].slice(0, 20),  // cap
    };
  }
`;
```

### 3.5 Installation Playwright (opt-in)

Au premier run, si `playwright` Python n'est pas installé ou si Chromium n'est pas téléchargé :
```bash
pip install playwright
python -m playwright install chromium
```

Le script `playwright_capture.py` détecte l'absence et émet `[REVERSE_UI_PLAYWRIGHT_MISSING]` avec FIX exécutable par le Tech Lead.

---

## 4. Composant 3 : `css_palette_extractor.py`

### 4.1 Rôle

Prend en entrée 1+ palettes JSON (issues de `playwright_capture.py`), déduplique, normalise (RGB → HSL), produit `workspace/input/ui/_legacy-style/tokens.css`.

### 4.2 Format de sortie (cf. spec V1 §5.4)

```css
/* Extracted from AspxDemo runtime capture, 2026-06-10 */
/* Aggregated from 4 routes: /Default.aspx, /Login.aspx, /Posts.aspx, /Products.aspx, /UsersServer.aspx */
:root {
  --legacy-primary: rgb(44, 90, 160);
  --legacy-text: rgb(51, 51, 51);
  --legacy-bg: rgb(247, 247, 247);
  --legacy-border: rgb(204, 204, 204);
  --legacy-font: "Tahoma", "Arial", sans-serif;
  --legacy-spacing-sm: 4px;
  --legacy-spacing-md: 8px;
  --legacy-radius: 0;
}
```

### 4.3 Algorithme déduplication

- Couleurs : K-means clustering sur l'espace RGB, K = 8 (cap visuel raisonnable). Garde le centroïde le plus représentatif par cluster + sa fréquence d'apparition.
- Fonts : top 3 par fréquence, formattées en CSS `font-family` stack.
- Spacings : top 5 valeurs distinctes (4, 8, 12, 16, 24px typiquement).

### 4.4 Idempotence

Le script lit le `tokens.css` existant s'il existe, merge intelligemment (un re-run sur une nouvelle FEAT enrichit sans casser). Hash des inputs stocké en commentaire `/* sources-hash: sha256:... */` pour skip silencieux si inchangé.

---

## 5. Composant 4 : `legacy_components_extractor.py`

### 5.1 Rôle

Analyse heuristique du HTML capturé pour produire `workspace/input/ui/_legacy-style/components-inventory.md` (référence designer).

### 5.2 Heuristiques détectées

| Composant détecté | Pattern HTML | Mapping DS moderne suggéré |
|---|---|---|
| Grille / DataTable | `<table>` avec ≥ 5 lignes ou class contenant `datatable\|grid\|table` | `<Table>` shadcn / `<DataTable>` Radzen |
| Formulaire CRUD | `<form>` avec ≥ 3 `<input>`/`<select>` + bouton submit | `<Form>` + `<Field>` shadcn |
| Menu navigation | `<nav>` ou `<ul>` avec ≥ 3 liens dans `<header>` ou `master/layout` | `<NavigationMenu>` shadcn / `<Sidebar>` |
| Modal / Dialog | `<div>` avec class `modal\|dialog\|popup` ou attribut `aria-modal=true` | `<Dialog>` shadcn |
| Pagination | `<ul>` ou `<nav>` avec class contenant `pagination\|pager` | `<Pagination>` shadcn |
| Filter panel | `<div>` avec ≥ 2 `<input>` + bouton "Rechercher\|Search\|Filter" | `<Card>` + champs shadcn |

### 5.3 Format de sortie (cf. spec V1 §5.5)

```markdown
# Composants UI legacy détectés — AspxDemo

> Référence designer pour mapping vers DS moderne (capture runtime du 2026-06-10)

| Composant legacy | Occurrences | Pages | Suggestion DS moderne |
|---|---|---|---|
| DataTable (jQuery) | 3 | /Default, /Posts, /Products | `<Table>` shadcn |
| GridView (server) | 1 | /UsersServer | `<DataTable>` shadcn (pagination server-side) |
| asp:Menu / SiteMap | 1 | Site.Master (toutes pages) | `<NavigationMenu>` shadcn |
| Login form | 1 | /Login.aspx | `<Form>` + `<Field>` shadcn |
```

---

## 6. Composant 5 : Agent `reverse-ui-extractor` (Sonnet)

### 6.1 Emplacement et rôle

`.claude/agents/reverse-ui-extractor.md`

Transforme le HTML brut capturé en HTML sémantique annoté (data-legacy-*). Strip les éléments runtime, normalise la structure, préserve les labels et textes UI.

### 6.2 Inputs

- `{LEGACY_PATH}/.sys/captures/{unit-id}.html` (HTML brut capturé)
- `workspace/input/feats/{n}-{Name}.md` (FEAT correspondante, pour cohérence intentions)
- `workspace/input/ui/_legacy-style/tokens.css` (palette extraite, si présente)
- `@.claude/docs/reverse-engineering-cookbook/{language}.md` (cookbook si présent)
- `@.claude/rules/reverse-engineering.md` (anti-derive)

### 6.3 Outputs

- `workspace/input/ui/{n}-{m}-{Name}.html` (mockup sémantique consommable par `dev-frontend`)
- `workspace/old/{P}/.sys/modules/{module-id}/ui-extraction-{unit-id}.md` (rapport agent)

### 6.4 Transformations appliquées

1. **Strip runtime artifacts** :
   - Supprime tous les `<input type="hidden">` ViewState ASPX, csrf tokens
   - Supprime les `<script>` (sauf ceux marqués `data-keep="true"`)
   - Strip attributs `data-aspnetform`, `__VIEWSTATE`, `__EVENTVALIDATION`
   - Strip styles inline (`style="..."`) — la palette vit dans `tokens.css`

2. **Annote la structure** :
   - Wrappe `<main data-legacy-source="{file}" data-legacy-component="Page">`
   - Pour chaque composant détecté par §5, ajoute `data-legacy-component="..."` + `data-legacy-lines="..."` (lignes dans le template legacy source)

3. **Normalise les composants** :
   - `<table>` GridView/DataTable → garde 1 ligne d'exemple + commentaire `<!-- example row, structure répétée -->`
   - `<form>` → ajoute `<label for="...">` si manquant (a11y)
   - `<button>` ASPX (asp:Button) → `<button type="submit">` standard
   - `<input type="text">` ASPX (asp:TextBox) → `<input type="text">` standard

4. **Préserve les libellés français** : aucune traduction, aucune réécriture des textes UI.

### 6.5 Anti-derive strict

Mêmes bullets que `reverse-functional-extractor` (cf. agent §Anti-derive strict) :
1. JAMAIS lire d'autres unités
2. JAMAIS modifier la FEAT.md
3. JAMAIS inventer une section UI absente du HTML capturé
4. JAMAIS proposer de redesign (ce sera le rôle du designer humain Phase 5)
5. Si capture HTML vide ou < 500 chars → STOP + `[REVERSE_UI_CAPTURE_EMPTY]`

---

## 7. Composant 6 : Commande `/sdd-reverse-ui {unit-id}`

### 7.1 Emplacement

`.claude/commands/sdd-reverse-ui.md`

Commande orchestrante : enchaîne les composants §2-§6, gère le cleanup, retourne verdict 1L.

### 7.2 Signature

```bash
/sdd-reverse-ui {unit-id}             # legacy déduit du dernier projet actif
/sdd-reverse-ui {Project} {unit-id}   # legacy explicite
```

### 7.3 Flow

```
STEP 1 — Résolution chemin + unit-id (cf. /sdd-reverse pattern)
STEP 2 — Préconditions : inventory.json présent, FEAT.md présente, port libre
STEP 3 — Spawn legacy_runner.py (subprocess)
STEP 4 — Spawn playwright_capture.py (subprocess)
STEP 5 — Spawn css_palette_extractor.py + legacy_components_extractor.py (parallèle)
STEP 6 — Spawn agent reverse-ui-extractor
STEP 7 — Cleanup legacy_runner (process.terminate)
STEP 8 — Vérification outputs + verdict 1L
```

### 7.4 Verdict

```
[DONE] /sdd-reverse-ui unit-001 — mockup UI capturé (runtime, Playwright).
       Mockup : workspace/input/ui/1-1-Employees-Grid-DataTable.html
       Palette : workspace/input/ui/_legacy-style/tokens.css
       Composants : workspace/input/ui/_legacy-style/components-inventory.md
       Screenshot : workspace/old/{P}/.sys/captures/unit-001.png

Prochaines étapes :
  - Relire le mockup HTML, ajuster si besoin (designer optionnel)
  - Lancer /sdd-full {n} (qui consommera le mockup automatiquement)
```

---

## 8. Contrats inter-composants (data flow)

| De → vers | Artefact | Format | Owner write |
|---|---|---|---|
| `legacy_runner.py` → `playwright_capture.py` | `base_url` (string) | stdout JSON | runner |
| `playwright_capture.py` → `css_palette_extractor.py` | `{unit-id}-palette.json` | JSON | playwright |
| `playwright_capture.py` → `reverse-ui-extractor` (agent) | `{unit-id}.html` | HTML brut | playwright |
| `css_palette_extractor.py` → fichier final | `_legacy-style/tokens.css` | CSS | extractor |
| `legacy_components_extractor.py` → fichier final | `_legacy-style/components-inventory.md` | MD | extractor |
| `reverse-ui-extractor` (agent) → fichier final | `workspace/input/ui/{n}-{m}-{Name}.html` | HTML sémantique | agent |
| `reverse-ui-extractor` (agent) → rapport | `.sys/modules/{module-id}/ui-extraction-{unit-id}.md` | MD | agent |

---

## 9. Configuration : `runner_signatures.yml`

`.claude/python/sdd_reverse/runner_signatures.yml` (nouveau fichier compagnon de `language_signatures.yml`).

```yaml
schema_version: 1

runners:
  - language: dotnet-webforms
    runner: iisexpress
    detect_cmd: ["where", "iisexpress.exe"]
    launch_cmd: ["iisexpress.exe", "/path:{abs_project_path}", "/port:{port}"]
    ready_url: "http://127.0.0.1:{port}/"
    default_port: 5099
    timeout_s: 60

  - language: dotnet-mvc
    runner: dotnet
    detect_cmd: ["dotnet", "--version"]
    launch_cmd: ["dotnet", "run", "--project", "{csproj_path}", "--urls", "http://127.0.0.1:{port}"]
    ready_url: "http://127.0.0.1:{port}/"
    default_port: 5100
    timeout_s: 90

  - language: java-jee
    runner: maven-spring-boot
    detect_cmd: ["mvn", "--version"]
    launch_cmd: ["mvn", "-f", "{pom_path}", "spring-boot:run", "-Dserver.port={port}"]
    ready_url: "http://127.0.0.1:{port}/"
    default_port: 8081
    timeout_s: 120

  - language: php-procedural
    runner: php-builtin
    detect_cmd: ["php", "--version"]
    launch_cmd: ["php", "-S", "127.0.0.1:{port}", "-t", "{abs_project_path}"]
    ready_url: "http://127.0.0.1:{port}/"
    default_port: 8000
    timeout_s: 30
```

Extensible sans modification de code (mêmes principes que `language_signatures.yml`).

---

## 10. Auth : cookies pré-authentifiés via `inventory.json`

Pour les pages derrière un login, le Tech Lead peut fournir des cookies pré-authentifiés dans `workspace/old/{P}/.sys/auth-cookies.json` :

```json
{
  "version": 1,
  "comment": "Cookies obtenus manuellement via DevTools Network après login dans le legacy en cours d'exécution.",
  "cookies": [
    {
      "name": "ASP.NET_SessionId",
      "value": "abc123def456",
      "domain": "127.0.0.1",
      "path": "/"
    }
  ]
}
```

`playwright_capture.py` détecte ce fichier et injecte les cookies via `context.add_cookies()` avant `page.goto()`.

V2 envisageable : auto-login via formulaire (script Playwright dédié à Login.aspx + capture session cookie).

---

## 11. Fallback static parse (legacy non lançable)

Si `legacy_runner.py` retourne `ok: false`, la commande `/sdd-reverse-ui` bascule en mode static parse :

1. Skip `playwright_capture.py`
2. Skip `css_palette_extractor.py` (palette extraite des `.css` files directement)
3. Skip `legacy_components_extractor.py` (heuristiques sur templates statiques)
4. Agent `reverse-ui-extractor` reçoit le template legacy brut (au lieu du HTML capturé) avec un flag `mode: static`

Le mockup produit est moins fidèle (pas de HTML JS-injecté visible) mais reste exploitable par `dev-frontend`. La FEAT générée mentionnera ce fallback dans son `## Reverse Engineering Notes`.

---

## 12. Format des outputs

### 12.1 Mockup HTML sémantique `workspace/input/ui/{n}-{m}-{Name}.html`

Cf. spec V1 §5.3. Exemple complet runtime capture sur unit-001 (Employees Grid) :

```html
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>Grille Employees</title>
  <link rel="stylesheet" href="_legacy-style/tokens.css">
</head>
<body>
  <main data-legacy-source="Default.aspx" data-legacy-component="Page" data-capture-mode="runtime">
    <header data-legacy-component="MasterPageNav" data-legacy-source="Site.Master">
      <nav>
        <a href="/">Employees</a>
        <a href="/Products.aspx">Products</a>
        <a href="/Posts.aspx">Posts</a>
        <a href="/UsersServer.aspx">Users GridView</a>
      </nav>
    </header>

    <section data-legacy-component="GridDataTable" data-legacy-lines="4-13">
      <table id="tbl" class="display">
        <thead>
          <tr>
            <th>First Name</th>
            <th>Last Name</th>
            <th>Email</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Terry</td>
            <td>Medhurst</td>
            <td>atuny0@sohu.com</td>
          </tr>
          <!-- example row from runtime capture, structure répétée 30x dans la capture -->
        </tbody>
      </table>
      <div class="dataTables_paginate" data-legacy-component="Pager">
        <span>Précédent</span>
        <span>1</span>
        <span>2</span>
        <span>Suivant</span>
      </div>
    </section>
  </main>
</body>
</html>
```

### 12.2 Tokens CSS — cf. §4.2

### 12.3 Components inventory — cf. §5.3

---

## 13. Plan de tests

### 13.1 Tests unitaires Python

| Fichier testé | Couverture cible | Cas couverts |
|---|---|---|
| `legacy_runner.py` | ≥80% | Détection stack, port conflict (5099 occupé → fallback 5100), ready timeout, cleanup atexit, missing runner cmd |
| `playwright_capture.py` | ≥70% (Playwright stub) | Navigate, networkidle wait, auth cookies inject, screenshot, palette extract, page 500 |
| `css_palette_extractor.py` | ≥85% | Dedup K-means, merge tokens.css existant, idempotence (sources-hash inchangé), invalid RGB |
| `legacy_components_extractor.py` | ≥85% | Détection table/form/nav/modal, components-inventory merge |

### 13.2 Tests intégration

| Test | Setup | Assertion |
|---|---|---|
| `test_e2e_aspxdemo_unit001` | Legacy AspxDemo, runner IIS Express disponible | `/sdd-reverse-ui unit-001` produit `workspace/input/ui/1-1-Employees-Grid-DataTable.html` non vide |
| `test_fallback_static_when_runner_missing` | Stub `where iisexpress` = exit 1 | Mode bascule en static, mockup produit avec `data-capture-mode="static"` |
| `test_idempotence_unit_hash_unchanged` | Re-run sur même unit après capture | Skip silencieux (verdict `unchanged`) |
| `test_cleanup_on_sigint` | Lancement legacy + SIGINT pendant capture | Subprocess legacy terminé, pas d'orphelin |

### 13.3 Tests anti-régression isolation

```bash
git diff .claude/agents/ .claude/commands/ .claude/rules/ .claude/skills/ \
        .claude/python/sdd_lib/ .claude/python/sdd_scripts/ .claude/python/sdd_admin/ .claude/python/sdd_hooks/ \
        .claude/loader.yml .claude/INVARIANTS.yml .claude/CLAUDE.md .claude/settings.json \
        bootstrap.py workspace/console/
# DOIT être vide, sauf :
# - rules/reverse-engineering.md (extension §6 explicite)
# - agents/reverse-ui-extractor.md (création nouvelle)
# - commands/sdd-reverse-ui.md (création nouvelle)
```

`framework_smoke.py` doit rester vert (Phase 4 strictement additive).

---

## 14. Codes d'erreur `[REVERSE_UI_*]`

À ajouter dans `rules/reverse-engineering.md §5` (extension de la taxonomie existante) :

| Préfixe | Sévérité | Sens |
|---|---|---|
| `[REVERSE_UI_RUNNER_UNSUPPORTED]` | critical | Stack legacy non supporté par `runner_signatures.yml` |
| `[REVERSE_UI_RUNNER_UNAVAILABLE]` | warning | Runner détecté mais binaire absent du PATH → fallback static |
| `[REVERSE_UI_RUNNER_TIMEOUT]` | critical | Legacy démarré mais pas ready après `timeout_s` |
| `[REVERSE_UI_PORT_CONFLICT]` | warning | 5 ports successifs occupés → STOP |
| `[REVERSE_UI_PLAYWRIGHT_MISSING]` | critical | `playwright` Python ou Chromium absent — instructions install |
| `[REVERSE_UI_CAPTURE_EMPTY]` | critical | outerHTML < 500 chars (page erreur ou redirection inattendue) |
| `[REVERSE_UI_AUTH_REQUIRED]` | warning | Capture retourne 401/403 — fournir `auth-cookies.json` |
| `[REVERSE_UI_CAPTURE_FAILED]` | critical | Erreur Playwright (timeout networkidle, crash Chromium) |

---

## 15. Périmètre Sprint 1-4 (livrables détaillés)

### Sprint 1 — Design + isolation (4h)
- [x] ADR `ADR-20260609T221251-d3ce-reverse-phase4-runtime-capture.md`
- [x] Ce design doc (`reverse-engineering-phase4-runtime.md`)
- [ ] Validation Tech Lead → autorise Sprint 2

### Sprint 2 — Legacy Runner (1 jour)
- [ ] `python/sdd_reverse/runner_signatures.yml`
- [ ] `python/sdd_reverse_scripts/legacy_runner.py` (CLI + module Python)
- [ ] `tests/test_legacy_runner.py` (couverture ≥80%)

### Sprint 3 — Playwright capture + extraction (1 jour)
- [ ] `python/sdd_reverse_scripts/playwright_capture.py`
- [ ] `python/sdd_reverse_scripts/css_palette_extractor.py`
- [ ] `python/sdd_reverse_scripts/legacy_components_extractor.py`
- [ ] `tests/test_playwright_capture.py`, `test_css_palette.py`, `test_components_extractor.py`

### Sprint 4 — Agent + commande + E2E (1 jour)
- [ ] `agents/reverse-ui-extractor.md` (Sonnet)
- [ ] `commands/sdd-reverse-ui.md`
- [ ] `loader.reverse.yml` extension (section `reverse-ui-extractor`)
- [ ] `rules/reverse-engineering.md` extension §6 (UI extraction anti-derive)
- [ ] `tests/test_e2e_aspxdemo_ui.py` (E2E sur AspxDemo)
- [ ] Validation finale Tech Lead

---

## 16. Validation Tech Lead requise (Sprint 1)

Avant de lancer Sprint 2, valider :

1. [ ] Architecture runtime capture (vs static parse) acceptée
2. [ ] Périmètre stacks V1 (4 stacks : aspx, mvc, jee, php) suffisant
3. [ ] Dépendance Playwright (~150 MB + Chromium) acceptée
4. [ ] Format des outputs (HTML sémantique + tokens.css + components-inventory.md) conforme à la vision
5. [ ] Fallback static parse acceptable si legacy non lançable
6. [ ] 5 nouveaux scripts Python + 1 nouvel agent + 1 nouvelle commande = périmètre raisonnable

Une fois validé, Sprint 2 démarre par `runner_signatures.yml` + `legacy_runner.py`.

---

**FIN DU DESIGN DOC Phase 4 — Runtime Capture**
