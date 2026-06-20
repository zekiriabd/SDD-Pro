# ADR-20260609T221251-d3ce — Reverse Engineering Phase 4 : Runtime Capture (vs Static Parse)

- **Statut** : Proposed
- **Date** : 2026-06-10
- **Auteur** : Tech Lead (élicité en session) — implémentation à venir
- **Phase** : 3-UI (workflow reverse engineering)

---

## Context

Le workflow reverse engineering SDD_Pro (cf. `docs/reverse-engineering-workflow.md`) prévoit en Phase 4 la génération automatique de mockups HTML sémantiques à partir d'un legacy déposé dans `workspace/old/{Project}/`. La spec V1 (§5 design doc) décrit le format de sortie mais laisse ouverte la stratégie d'extraction. Deux approches sont possibles :

1. **Static parse** — lire les templates serveur (`.aspx`, `.cshtml`, `.jsp`, `.php`) + CSS, produire le mockup HTML sans lancer le legacy.
2. **Runtime capture** — démarrer l'application legacy (IIS Express / Tomcat / php -S / Kestrel), naviguer chaque page via Playwright headless, capturer `outerHTML` post-JS + computed CSS.

Le legacy de référence courant (`workspace/old/AspxDemo`) illustre la limite du static parse : 3 des 4 pages utilisent jQuery DataTable pour injecter le HTML tabulaire au runtime à partir d'un fetch JSON externe. Le static parse ne voit que `<table id="tbl">` vide ; le rendu réel observé par l'utilisateur final n'est récupérable qu'en exécutant le JS dans un navigateur.

Le Tech Lead a explicitement demandé la fidélité maximale (« récupérer le HTML/CSS compilé existant sur le navigateur »).

---

## Decision

La Phase 4 du workflow reverse engineering est implémentée en **mode runtime capture** comme approche principale, avec un fallback static parse pour les cas où le legacy n'est pas lançable.

**Composants livrés** :

1. Script Python `legacy_runner.py` : détecte le stack legacy (via `inventory-raw.json`), lance le serveur approprié (IIS Express pour ASPX, `dotnet run` pour MVC, Tomcat embedded pour JEE, `php -S` pour PHP), attend la disponibilité HTTP (200 OK sur `/`), retourne l'URL de base + un handle de cleanup.
2. Script Python `playwright_capture.py` : pour chaque unité fonctionnelle dans `inventory.json`, navigue vers la route correspondante en Playwright headless (Chromium par défaut), capture `outerHTML` après quiescence réseau (`networkidle`), capture les `getComputedStyle()` agrégés en palette.
3. Script Python `css_palette_extractor.py` : déduplique les couleurs/fonts/spacing observés, produit `workspace/input/ui/_legacy-style/tokens.css` au format de la spec §5.4 du design doc.
4. Script Python `legacy_components_extractor.py` : analyse heuristique du HTML capturé pour détecter `<table>`/`<form>`/`<dialog>`/`<nav>`, produit `_legacy-style/components-inventory.md`.
5. Agent LLM `reverse-ui-extractor` (Sonnet 4.6) : transforme le HTML capturé brut en HTML sémantique avec annotations `data-legacy-source`, `data-legacy-component`, `data-legacy-lines`. Strip les attributs `style=` inline, normalise la structure.
6. Commande orchestrante `/sdd-reverse-ui {unit-id}` : enchaîne `legacy_runner.py` → `playwright_capture.py` → agent `reverse-ui-extractor` → write atomique de `workspace/input/ui/{n}-{m}-{Name}.html`.

**Périmètre stacks supportés V1** (alignés sur language_signatures.yml) :
- ASP.NET WebForms (`.aspx`) — IIS Express / Kestrel ASP.NET legacy
- ASP.NET MVC (`.cshtml`, `.razor`) — `dotnet run`
- Java JEE (`.jsp`, `.jspx`) — Tomcat embedded via `mvn spring-boot:run` ou `gradle bootRun`
- PHP procedural (`.php`) — `php -S`

Stacks **hors V1** (fallback static parse uniquement) : Delphi, langages exotiques (VB6, Cobol, etc.).

---

## Consequences

**Positifs :**
- Fidélité maximale : le mockup reflète exactement ce que l'utilisateur final voit (JS injecté, données dynamiques, layout flexbox/grid résolu).
- Découvre automatiquement les composants conditionnels (boutons d'admin masqués si user non admin, par exemple — possible si l'agent peut se loguer).
- `_legacy-style/tokens.css` exact (couleurs résolues, pas spéculées depuis du CSS partiellement appliqué).
- Détection automatique des erreurs runtime du legacy (page 500 → marquée `<!-- review-needed: page error 500 -->` dans le mockup).

**Négatifs / dette acceptée :**
- Dépendance Playwright (Python `playwright` package ~150 MB avec Chromium bundlé). Mitigation : install opt-in déclenché par `/sdd-reverse-ui` au premier run (`python -m playwright install chromium`).
- Le legacy doit être lançable (binaries, DB de dev, env vars). Si pas lançable → fallback static parse (capacités réduites).
- Premier run lent (~30-60s : download Playwright + démarrage legacy + navigation). Runs suivants ~5-10s.
- Auth basique uniquement V1 : si une page est derrière un login complexe (OAuth, SSO), capture impossible. Mitigation : config `auth_cookies` dans `inventory.json` pour fournir des cookies pré-authentifiés.
- Limité aux stacks lançables sur la machine du Tech Lead. Pas de Docker en V1 (V2 envisageable).

---

## Alternatives considérées

- **Static parse uniquement (approche A)** : écartée car ne couvre pas le cas jQuery DataTable / SPA-like injection présent dans AspxDemo et la majorité des legacys modernes (post-2010).
- **Capture via curl + JSDOM** : écartée car ne rend pas le JS de façon fidèle (JSDOM ≠ Chromium, manque APIs DOM modernes utilisées par DataTables, Bootstrap, etc.).
- **Capture via screenshot + OCR** : écartée car perd la structure HTML sémantique (résultat = image, non parsable par dev-frontend en aval).
- **Docker compose pour chaque stack** : écartée V1 (surcomplique le bootstrap, V2 envisageable si besoin de reproducibilité cross-machine).
- **Implémenter d'abord static parse, puis runtime en V2** : écartée car le Tech Lead a explicitement demandé la fidélité maximale ; static parse seul donnerait des mockups inexploitables sur AspxDemo (le legacy de référence).

---

## Liens

- Design doc V1 : `docs/reverse-engineering-workflow.md §5` (format de sortie HTML sémantique + tokens.css)
- Design doc V2 (à créer) : `docs/reverse-engineering-phase4-runtime.md` (détail implémentation runtime capture)
- Master prompt : `docs/reverse-engineering-master-prompt.md §3.1` (isolation stricte — nouveau code uniquement dans paths reverse-only)
- Règle anti-derive : `rules/reverse-engineering.md` (à étendre §6 pour Phase 4)
- Spec stacks détection : `python/sdd_reverse/language_signatures.yml`
- Legacy de référence : `workspace/old/AspxDemo/`
- ADRs liés : —
