# UI Design System: shadcn/ui (React)

> §2.4 (Librairies) régénérée depuis `shadcn.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id shadcn`).

Status: Stable
Validation: 🟢 reference (validated combo CMS — kotlin-spring-boot + react + shadcn + azure-ad, 2026-05-13)
UI FEAT ID: shadcn-ui
Scope: design system shadcn/ui — composants UI pour applications React (Next.js, SPA, dashboards, applications métier)

---

## 1. Identité du design system

- Nom : shadcn/ui
- Framework cible : React 18+ / 19 (Vite, Next.js, Remix, Astro indifferents)
- Type : UI Component System (headless Radix + styled via Tailwind)
- Philosophie : composants copiables sous `components/ui/` + contrôle total du code
- Base design : Radix UI primitives + Tailwind CSS + Lucide icons
- Distribution : CLI `npx shadcn@latest` (pas un package npm runtime)

### Objectif pour l'IA

- Comprendre shadcn/ui comme un design system modulaire
- Utiliser les composants fournis avant toute création custom
- Respecter les patterns Radix (accessibilité + interactions)
- Ne pas réinventer les composants existants
- Ne jamais main-edit un fichier sous `components/ui/` (regenerer via CLI)

---

## 1.bis Setup obligatoire (Init Commands shadcn-ready)

shadcn/ui n'est PAS un package npm — c'est un **CLI qui copie des composants
React TS dans le projet**. Le setup integre Tailwind, des CSS variables, un
helper `cn()`, et la configuration des path aliases. Les agents qui generent
du code utilisant `import { Button } from "@/components/ui/button"` SUPPOSENT
que ces fichiers existent — d'ou l'obligation d'executer ce setup AVANT
toute generation feature.

### 1.bis.1 Prerequis

- React 18+ ou 19 dans `package.json`
- TypeScript configure (path aliases `@/*` → `./src/*`)
- Vite OU Next.js OU Remix OU Astro — `shadcn init` detecte automatiquement

### 1.bis.2 Init Commands canoniques (Vite + React 19 + TS)

Le frontend stack `react.md §2.2.1` integre deja ces commandes — voir la-bas
pour la sequence complete. Resume des etapes shadcn-specifiques :

```bash
# 1. TS path aliases (requis par shadcn pour @/components/ui)
#    tsconfig.json + tsconfig.app.json :
#      "baseUrl": "."
#      "paths": { "@/*": ["./src/*"] }
#    vite.config.ts :
#      resolve: { alias: { "@": path.resolve(__dirname, "./src") } }
npm install --save-dev @types/node

# 2. Tailwind v4 (preferred)
npm install tailwindcss @tailwindcss/vite

# 3. shadcn init (genere components.json + lib/utils.ts + index.css avec
#    tokens shadcn + tailwind config si v3 + path aliases verifies)
npx shadcn@latest init -d -y

# 4. Pulled automatiquement par init :
#    - class-variance-authority (variantes typees)
#    - clsx (concat classes)
#    - tailwind-merge (resolution conflits Tailwind)
#    - tailwindcss-animate (v3 only ; v4 native)
#    - lucide-react (pack icones officiel)

# 5. Components shadcn de base (couvre 80% des UI)
#    Chaque add pulle les @radix-ui/* deps necessaires
npx shadcn@latest add button card input label textarea select checkbox switch \
    form dialog dropdown-menu badge avatar tabs tooltip toast skeleton \
    alert progress separator
```

### 1.bis.3 Fichiers attendus apres setup

Apres `shadcn init`, le projet DOIT contenir :

```
{AppName}/
├── components.json           # manifest shadcn (style, tailwind config, aliases)
├── tailwind.config.ts        # SI Tailwind v3 ; absent en v4
├── postcss.config.js         # SI Tailwind v3 ; absent en v4
└── src/
    ├── index.css             # @import "tailwindcss" + variables CSS shadcn
    ├── lib/
    │   └── utils.ts          # cn() helper : twMerge + clsx
    └── components/
        └── ui/               # primitives shadcn copiees (Button, Card, ...)
            ├── button.tsx
            ├── card.tsx
            └── ...
```

### 1.bis.4 Contenu canonique des fichiers cles

**`src/lib/utils.ts`** (genere automatiquement par `shadcn init`) :

```ts
import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

**`src/index.css`** (Tailwind v4, format CSS-first 2026) :

```css
@import "tailwindcss";

@theme {
  --color-background: hsl(0 0% 100%);
  --color-foreground: hsl(222.2 84% 4.9%);
  --color-primary: hsl(222.2 47.4% 11.2%);
  --color-primary-foreground: hsl(210 40% 98%);
  --color-card: hsl(0 0% 100%);
  --color-card-foreground: hsl(222.2 84% 4.9%);
  --color-border: hsl(214.3 31.8% 91.4%);
  --color-muted: hsl(210 40% 96.1%);
  --color-muted-foreground: hsl(215.4 16.3% 46.9%);
  --color-destructive: hsl(0 84.2% 60.2%);
  --color-destructive-foreground: hsl(210 40% 98%);
  --radius: 0.5rem;
  /* ... voir https://ui.shadcn.com/themes pour les variantes */
}

/* Dark mode */
@media (prefers-color-scheme: dark) {
  @theme {
    --color-background: hsl(222.2 84% 4.9%);
    --color-foreground: hsl(210 40% 98%);
    /* ... */
  }
}
```

**`components.json`** (genere par `shadcn init`) :

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/index.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

### 1.bis.5 Bibliotheques runtime requises

Installees automatiquement par `shadcn init` + `shadcn add` :

| Lib | Version min | Role |
|-----|-------------|------|
| tailwindcss | 4.0+ (ou 3.4+) | Utility-first CSS |
| @tailwindcss/vite | 4.0+ | Plugin Vite (v4 only) |
| class-variance-authority | 0.7+ | Variantes typees |
| clsx | 2.1+ | Concat classes |
| tailwind-merge | 2.5+ | Resolution conflits |
| tailwindcss-animate | 1.0+ | Animations (v3 only) |
| lucide-react | 0.460+ | Pack icones |
| @radix-ui/react-* | per-component | Primitives accessibles |

### 1.bis.6 Verification post-setup

```bash
# 1. Build doit passer
npm run build

# 2. Test d'import resolu
echo 'import { Button } from "@/components/ui/button"' > src/test-import.tsx
npx tsc --noEmit
rm src/test-import.tsx
```

Si `import { Button } from "@/components/ui/button"` echoue → setup
incomplet, relancer `npx shadcn@latest init -d -y` puis
`npx shadcn@latest add button`.

---

## 2. Principes fondamentaux

- Composants accessibles basés sur Radix UI
- Styling via Tailwind CSS
- Code local (pas de dépendance runtime lourde)
- Composition via props + children
- Dark mode natif (via Tailwind)
- Design system flexible et extensible

Règles IA :

- Toujours privilégier un composant shadcn/ui existant
- Ne jamais recréer un composant déjà disponible
- Respecter la structure Tailwind + Radix
- Composer les composants plutôt que reconstruire

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/ui/shadcn.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id shadcn`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| tailwindcss | 4.0.0 | Utility-first CSS (Tailwind v4 native). |
| @tailwindcss/vite | 4.0.0 | Plugin Vite Tailwind v4. |
| class-variance-authority | 0.7.0 | Variantes typées pour composants shadcn (cva). |
| clsx | 2.1.1 | Concaténation conditionnelle de classes CSS. |
| tailwind-merge | 2.5.5 | Résolution conflits classes Tailwind (helper cn()). |
| lucide-react | 0.469.0 | Pack icônes officiel shadcn (iconLibrary='lucide'). |
| @radix-ui/react-slot | 1.1.0 | Primitive Radix utilisée par Button asChild. |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| dialog | @radix-ui/react-dialog | 1.1.2 | dialog, modal, popup, fenetre.*modale |
| dropdown-menu | @radix-ui/react-dropdown-menu | 2.1.2 | dropdown, menu contextuel, menu deroulant |
| label | @radix-ui/react-label | 2.1.0 | label, form.*label |
| select | @radix-ui/react-select | 2.1.2 | select, combobox, liste.*deroulante |
| tabs | @radix-ui/react-tabs | 1.1.1 | tabs?, onglets? |
| toast-radix | @radix-ui/react-toast (alt) | 1.2.2 | radix.*toast |
| toast | sonner | 1.7.1 | toast, notification, snackbar |
| tooltip | @radix-ui/react-tooltip | 1.1.4 | tooltip, infobulle, info.*bulle |
| checkbox | @radix-ui/react-checkbox | 1.1.2 | checkbox, case.*cocher |
| avatar | @radix-ui/react-avatar | 1.1.1 | avatar, photo.*profil |
| progress | @radix-ui/react-progress | 1.1.0 | progress, barre.*progression, loader |
| switch | @radix-ui/react-switch | 1.1.1 | switch, toggle, interrupteur |
| separator | @radix-ui/react-separator | 1.1.0 | separator, divider, separateur |
| popover | @radix-ui/react-popover | 1.1.2 | popover, popup |
| tw3-animations | tailwindcss-animate (alt) | 1.0.7 | tailwind.*v3, tailwindcss-animate |
<!-- LIBS_CATALOG_END -->

---

## 3. Architecture UI shadcn/ui

### 3.1 Structure standard d'application (framework-agnostic)

- **Root app** :
  - Vite + React Router → `src/main.tsx` + `src/App.tsx` + `src/router.tsx`
  - Next.js App Router → `app/layout.tsx` + `app/page.tsx`
  - Astro → `src/pages/*.astro` + `src/layouts/*.astro`
- **Layout global** : header + sidebar + content (composition libre,
  utiliser `<Sidebar>`, `<NavigationMenu>` ou primitives)
- **Contenu** : pages / components

shadcn/ui est **agnostique du routing** — il fournit des composants UI
purs, pas une convention de routing.

---

### 3.2 Organisation logique (cross-framework)

- **`pages/`** ou **`app/`** → routes principales (selon framework)
- **`components/ui/`** → composants shadcn generes (READ-ONLY, jamais main-edit)
- **`components/`** → composants metier (composition de primitives shadcn)
- **`lib/`** → utilitaires (`utils.ts` avec `cn()` helper, generes par CLI)
- **`hooks/`** → logique reutilisable (custom React hooks)
- **`store/`** → etat global (Zustand recommande)

**Regle critique** : `components/ui/*` est genere par `npx shadcn add`.
Toute surcharge se fait soit via les variants de `class-variance-authority`,
soit via re-generation et patch CLI, soit via wrapping dans un composant
metier sous `components/`. Jamais d'edition manuelle de `components/ui/*`.

---

## 4. Mapping fonctionnel → composants shadcn/ui

| Fonction UI | Composant |
|-------------|----------|
| bouton | Button |
| icône | Lucide Icons |
| champ texte | Input |
| zone texte | Textarea |
| select | Select |
| autocomplete | Command |
| checkbox | Checkbox |
| radio | RadioGroup |
| switch | Switch |
| date picker | Calendar |
| formulaire | Form |
| carte | Card |
| tableau de données | DataTable |
| pagination | Pagination |
| dialog / modal | Dialog |
| tooltip | Tooltip |
| toast | Toast |
| alert | Alert |
| tabs | Tabs |
| badge / chips | Badge |
| avatar | Avatar |
| progress | Progress |
| skeleton loading | Skeleton |
| dropdown | DropdownMenu |

---

## 5. Data handling (patterns obligatoires)

### 5.1 DataTable

Fonctionnalités :

- tri (sorting)
- pagination
- filtrage
- sélection
- intégration avec TanStack Table

Règles :

- utiliser server-side pour gros volumes
- ne jamais charger de gros datasets côté client
- utiliser hooks + API layer

---

### 5.2 Forms

- utiliser Form (react-hook-form recommandé)
- validation via Zod ou équivalent
- champs contrôlés

Interdit :

- validation manuelle dispersée
- logique métier dans JSX

---

## 6. Layout system

Basé sur Tailwind CSS :

- container → wrapper
- grid / flex → layout
- spacing via utility classes

Layouts standards :

- Dashboard layout
- Auth layout
- Full page

---

## 7. Navigation

- Sidebar custom + navigation structurée
- DropdownMenu pour actions
- Command pour recherche/navigation rapide

Règles :

- navigation centralisée
- pas de duplication
- routing via Next.js / React Router

---

## 8. Theming system

- basé sur Tailwind config
- support dark/light mode
- variables CSS

Règles :

- respecter design tokens
- éviter styles inline incohérents
- limiter overrides

---

## 9. Interactions UI

- Dialog → modales
- Toast → notifications
- Tooltip → aides
- DropdownMenu → actions

Règles :

- aucune modal custom hors Dialog
- aucune notification hors Toast
- interactions standardisées

---

## 10. State management

Recommandé :

- Zustand / React Context

Règles :

- état global centralisé
- pas de logique métier dans UI
- éviter duplication état

---

## 11. Accessibilité et UX

- Radix garantit accessibilité
- support clavier natif
- focus management intégré
- ARIA compliant

---

## 12. Règles de développement UI

### Obligatoire

- utiliser composants shadcn/ui
- respecter structure Tailwind
- séparation UI / logique métier
- composants réutilisables si nécessaire

---

### Interdit

- recréer composants existants
- utiliser HTML brut à la place
- CSS non structuré
- duplication composants
- logique métier dans JSX
- mix avec autres UI kits

---

## 13. Philosophie IA (usage agentic)

Ce design system doit être interprété comme :

- un système UI modulaire
- une base pour génération UI contrôlée
- un ensemble de composants composables

L’IA doit :

- privilégier shadcn/ui
- composer au lieu de recréer
- respecter accessibilité Radix
- générer du code propre et maintenable

---

## 14. Hors scope

- autres UI frameworks (MUI, Bootstrap, etc.)
- logique backend
- auth system
- design tokens multi-brand avancés
- animations complexes hors scope

---

## 15. Mapping HTML → primitive shadcn (depuis SDD_Pro v4)

Quand `dev-frontend` lit un mockup HTML statique
(`workspace/input/ui/{n}-{m}-*.html`), il **traduit chaque primitive HTML brute
vers son pendant shadcn/ui**.

### 15.1 Layout

| HTML source                              | shadcn primitive                          |
|------------------------------------------|-------------------------------------------|
| `<header>`                               | `<header className="...">` natif + classes Tailwind |
| `<aside>` / sidebar nav                  | `<Sidebar>` (shadcn-ui sidebar block)     |
| `<main>`                                 | `<main>` natif                            |
| `<div class="card">`                     | `<Card>` + `<CardHeader>`/`<CardContent>` |
| Grille responsive                        | classes Tailwind `grid-cols-*`            |

### 15.2 Navigation

| HTML source                              | shadcn primitive                          |
|------------------------------------------|-------------------------------------------|
| `<nav>` horizontal                       | `<NavigationMenu>` ou `<Menubar>`         |
| `<nav>` latéral                          | `<Sidebar>` block                         |
| `<a href="...">`                         | `<Link>` (React Router) avec classes shadcn |
| `<ul>` onglets                           | `<Tabs>` + `<TabsList>` + `<TabsTrigger>` |

### 15.3 Actions et formulaires

| HTML source                              | shadcn primitive                          |
|------------------------------------------|-------------------------------------------|
| `<button>`                               | `<Button>`                                |
| `<button class="primary">`               | `<Button variant="default">`              |
| `<button class="secondary">`             | `<Button variant="secondary">`            |
| `<button class="ghost">`                 | `<Button variant="ghost">`                |
| `<input type="text">`                    | `<Input>`                                 |
| `<input type="email">`                   | `<Input type="email">`                    |
| `<textarea>`                             | `<Textarea>`                              |
| `<select>`                               | `<Select>` + `<SelectTrigger>` + `<SelectContent>` + `<SelectItem>` |
| `<input type="checkbox">`                | `<Checkbox>`                              |
| `<input type="radio">`                   | `<RadioGroup>` + `<RadioGroupItem>`       |
| `<input type="date">`                    | `<Calendar>` dans `<Popover>` (shadcn date-picker block) |
| `<form>`                                 | `<Form>` (react-hook-form integration)    |
| `<label>`                                | `<Label>`                                 |

### 15.4 Données et affichage

| HTML source                              | shadcn primitive                          |
|------------------------------------------|-------------------------------------------|
| `<table>`                                | `<Table>` + `<TableHeader>`/`<TableBody>`/`<TableRow>`/`<TableCell>` (combiné avec tanstack/react-table pour tri/pagination) |
| `<dialog>` / modal                       | `<Dialog>` + `<DialogContent>`            |
| Drawer latéral                           | `<Sheet>` + `<SheetContent>`              |
| Toast/notification                       | `<Toaster>` + `toast()` (sonner)          |
| Tooltip natif `title=`                   | `<Tooltip>` + `<TooltipContent>`          |
| Badge / pill                             | `<Badge>`                                 |
| Avatar                                   | `<Avatar>` + `<AvatarImage>` + `<AvatarFallback>` |

### 15.5 Règles de traduction

1. **Libellés verbatim** : repris tels quels.
2. **Couleurs** : converties en CSS variables `--background`,
   `--foreground`, `--primary`, etc. (cf. setup `globals.css` shadcn).
3. **Icônes** : traduites en composants `lucide-react` (`<Home />`,
   `<Settings />`, etc.).
4. **Classes Tailwind utilitaires** : conservées sur les wrappers.
5. **Composants `components/ui/`** : importés via `@/components/ui/...`
   après `npx shadcn add <component>` (responsabilité arch).
