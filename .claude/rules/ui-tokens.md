# Règle — UI Tokens (variables CSS, anti-hex-hardcode)

## Principe

Toute couleur, espacement, rayon ou typo de l'UI générée **DOIT** passer
par des **tokens CSS** (variables) et **JAMAIS** par des valeurs hex
hardcodées dans les composants. Cette discipline garantit :

1. **Fidélité au design** : la palette FEAT.md §8 et les mockups HTML
   se traduisent en un set fini de variables que tous les composants
   consomment.
2. **Theming multi-mode** : light/dark/HC via override des tokens à la
   racine `:root` / `[data-theme="dark"]`.
3. **Maintenance** : un changement de marque édite N tokens, pas N×100
   composants.

Cette règle est **load-bearing** pour l'agent `dev-frontend` et le
build_loop (un hex hardcode trouvé en STEP build → STOP +
`[UI_TOKEN_VIOLATION]`).

---

## 1. Vocabulaire des tokens

Tokens normés (compatibles shadcn + Vuetify + Radzen) :

### 1.1 Couleurs sémantiques
- `--background`, `--foreground` (page entière)
- `--card`, `--card-foreground`
- `--popover`, `--popover-foreground`
- `--primary`, `--primary-foreground`
- `--secondary`, `--secondary-foreground`
- `--accent`, `--accent-foreground`
- `--muted`, `--muted-foreground`
- `--destructive`, `--destructive-foreground`
- `--success`, `--warning`, `--info` (extensions projet)
- `--border`, `--input`, `--ring`

### 1.2 Espacements
- `--radius` (rayon de base, dérivés `calc(var(--radius) - 2px)` etc.)
- Espacements via Tailwind scale (`gap-4`, `px-6`, …) — **pas de tokens
  dédiés** sauf cas exceptionnel.

### 1.3 Typo
- `--font-sans`, `--font-mono` (déclarés `:root`, consommés par
  `font-family`)
- Tailles via Tailwind scale (`text-sm`, `text-lg`, …)

---

## 2. Structure des fichiers (stack frontend)

| Stack | Fichier tokens | Convention |
|---|---|---|
| `react` + `shadcn` | `src/index.css` | `@layer base { :root { --background: 0 0% 100%; ... } }` (HSL space-separated, format shadcn) |
| `vue` + `vuetify` | `src/styles/theme.ts` | Object `{ light: { colors: { primary: "#...", ... } } }` consommé par `createVuetify` |
| `angular` + radzen | `src/styles.css` | `:root { --rz-primary: #...; }` (préfixes radzen) |
| `blazor-webassembly` + `radzen-blazor` | `wwwroot/css/site.css` | idem radzen |

L'agent `arch` génère le squelette de tokens lors du scaffold. L'agent
`dev-frontend` n'édite que `theme.css` / `index.css` pour matérialiser
la palette FEAT.md §8 — **jamais** les composants individuels.

---

## 3. Override projet (FEAT-driven)

Quand FEAT.md §8 déclare une palette spécifique (couleurs marque,
typo, rayon), l'agent `dev-frontend` :

1. Mappe chaque token logique vers une valeur de la palette
2. Édite **uniquement** le fichier de tokens (cf. tableau §2)
3. Préserve les tokens shadcn/vuetify/radzen standards (override, pas
   remplacement intégral)
4. Documente le mapping dans un commentaire en tête de fichier

Exemple `src/index.css` (combo react+shadcn) :

```css
@layer base {
  :root {
    /* Tokens projet — override FEAT.md §8 palette "Nounou Care" */
    --background: 210 40% 98%;
    --foreground: 222 47% 11%;
    --primary: 217 91% 60%;          /* Bleu marque #2563eb */
    --primary-foreground: 0 0% 100%;
    --radius: 0.5rem;
    /* ... rest préservé du shadcn init standard */
  }

  [data-theme="dark"] {
    --background: 222 47% 11%;
    --foreground: 210 40% 98%;
    --primary: 217 91% 65%;
    /* ... */
  }
}
```

---

## 4. Anti-patterns rejetés

| Anti-pattern | Détection | Fix |
|---|---|---|
| `style={{ color: "#2563eb" }}` inline | grep `#[0-9a-fA-F]{3,8}` dans composants | utiliser `text-primary` ou `bg-primary` |
| `className="bg-[#2563eb]"` Tailwind arbitrary value | grep `\[#[0-9a-fA-F]{3,8}\]` | déclarer token + utiliser `bg-primary` |
| `rgba(37, 99, 235, 0.5)` hardcode | grep `rgba?\(` dans composants | utiliser `bg-primary/50` Tailwind ou token alpha |
| Token redéfini par composant (`--my-blue: ...`) | grep `--[a-z-]+:` hors fichier tokens | déclarer au niveau `:root` global |
| CSS-in-JS (styled-components, emotion) avec hex | architecture | hors scope SDD_Pro — utiliser Tailwind + tokens |
| `!important` pour bypass cascade | grep `!important` | resoudre via spécificité ou token dédié |

---

## 5. Vérification dev-frontend (STEP build / post-Edit)

```bash
# Cherche hex hardcode dans composants (hors fichier tokens)
grep -rE '#[0-9a-fA-F]{6}\b' workspace/output/src/{AppName}/src/components/ workspace/output/src/{AppName}/src/pages/ \
  | grep -v 'src/index.css\|src/styles/theme\|src/styles.css' \
  && ERROR [UI_TOKEN_VIOLATION]

# Cherche arbitrary values Tailwind avec hex
grep -rE 'bg-\[#|text-\[#|border-\[#' workspace/output/src/{AppName}/src/ \
  && ERROR [UI_TOKEN_VIOLATION]
```

### Format ERROR

Préfixe `[UI_TOKEN_VIOLATION]` (cf. `error-classification.md §1.6`) :

```
ERROR: dev-frontend {n}-{m} — hex hardcode dans composant
CAUSE: [UI_TOKEN_VIOLATION] {path}:{line} contient {hex} au lieu d'un token
FIX: déclarer le token dans src/index.css :root (ou theme.ts) puis
     remplacer par bg-primary / text-foreground / etc. (cf. ui-tokens.md §1)
```

---

## 6. Test d'acceptation

Toute FEAT §8 (palette projet) doit produire un PR diff visible **uniquement**
dans le fichier de tokens (§2) + éventuellement quelques composants qui
référencent de nouveaux tokens projet. Si le diff touche > 3 composants
avec des hex différents → violation §4.

---

## 7. Lien avec autres règles

- `source-first.md §1` : tout bug de fidélité visuelle → patcher cette
  règle (si gap) AVANT le composant.
- `file-ownership.md §1` : seul `dev-frontend` édite `theme.css` /
  `index.css` (réservé en augment, pas réécriture intégrale).
- Stacks UI : `stacks/ui/shadcn.md §3`, `vuetify.md §3`, `radzen-blazor.md §3`
  inlinent la syntaxe spécifique. Cette rule est la spec cross-stack.
