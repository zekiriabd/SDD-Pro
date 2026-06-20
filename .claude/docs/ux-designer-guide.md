# UX Designer Guide — Mockups HTML pour SDD_Pro

> Audience : UX/UI designers fournissant des mockups consommés par
> l'agent `dev-frontend`. Objectif : produire des HTML statiques qui
> accélèrent la convergence du frontend généré (vs descriptions
> textuelles dans la FEAT).

---

## 1. Pourquoi un mockup HTML statique (et pas Figma) ?

L'agent `dev-frontend` lit le mockup comme **donnée passive** :
- Structure DOM → squelette des composants Vue/React/Angular/Blazor
- Classes utilitaires (Tailwind) → mapping vers DS actif (shadcn/Vuetify/Radzen)
- Labels et textes → strings i18n / props par défaut
- Couleurs hex → conversion vers tokens CSS (`--primary`, `--accent`)

Avantages vs Figma :
- **Inline dans le repo** (traçable, versionable, git diff)
- **Lecture LLM directe** (pas d'API Figma, pas de connecteur tiers)
- **Validation visuelle facile** (`open workspace/input/ui/1-1-Login.html`)
- **Pas de licence** (HTML/CSS = standard ouvert)

Limite : pas d'animations, pas d'interactions. Le code généré
matérialise interactions selon les ACs de l'US.

---

## 2. Convention de nommage

Path strict : `workspace/input/ui/{n}-{m}-{Name}.html`

| Élément | Règle | Exemple |
|---|---|---|
| `{n}` | numéro FEAT (entier) | `1` |
| `{m}` | numéro US dans la FEAT (entier) | `2` |
| `{Name}` | basename CamelCase (pas d'accents, tirets pour espaces) | `Reset-Password` |
| Extension | `.html` (pas `.htm`) | — |

**Exemples valides** :
- `workspace/input/ui/1-1-Login.html`
- `workspace/input/ui/1-2-Reset-Password.html`
- `workspace/input/ui/3-1-Liste-Commandes.html`

**Invalides** :
- `Login.html` (manque `{n}-{m}-`)
- `1-Login.html` (manque `{m}`)
- `1-2-LoginScreen.html` (mockup et US doivent partager le même `{Name}`)
- `1-2-réinitialisation.html` (accents interdits)

> **Propagation `{Name}`** : si vous nommez votre mockup `1-2-Login.html`,
> l'agent `po` réutilisera exactement `Login` comme `{Name}` de l'US
> `workspace/output/us/1-2-Login.md` (cf. po-guide §6 — convention CRIT-9
> audit 2026-06-07).

---

## 3. Structure d'un mockup canonique

### 3.1 Squelette minimal

```html
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Login — Softwe3 SaaS</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 min-h-screen flex items-center justify-center">

  <main class="w-full max-w-md p-8 bg-white rounded-lg shadow-md">
    <h1 class="text-2xl font-semibold text-slate-900 mb-6">Connexion</h1>

    <form class="space-y-4">
      <div>
        <label for="email" class="block text-sm font-medium text-slate-700">Email</label>
        <input id="email" type="email" required
               class="mt-1 w-full px-3 py-2 border border-slate-300 rounded-md
                      focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
      </div>

      <div>
        <label for="password" class="block text-sm font-medium text-slate-700">Mot de passe</label>
        <input id="password" type="password" required minlength="8"
               class="mt-1 w-full px-3 py-2 border border-slate-300 rounded-md">
      </div>

      <button type="submit"
              class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium
                     py-2 px-4 rounded-md transition">
        Se connecter
      </button>
    </form>

    <p class="mt-4 text-sm text-center text-slate-600">
      <a href="/reset-password" class="text-blue-600 hover:underline">Mot de passe oublié ?</a>
    </p>
  </main>

</body>
</html>
```

### 3.2 Éléments parsés par dev-frontend

| Élément HTML | Mapping côté code généré |
|---|---|
| `<h1>`, `<h2>` | Titre de page (`<PageHeader>` shadcn / Vuetify equivalent) |
| `<form>` | Composant form lié à validation Zod/yup (côté React/Vue) ou FormGroup (Angular) |
| `<input required>` | Validation côté client + AC backend (`@NotNull` Jakarta) |
| `<input type="email">` | Validation regex email (mirrored back↔front, cf. library-and-stack.md §6.bis.2) |
| `<input minlength="8">` | Validation length identique back↔front |
| `<button type="submit">` | Handler `onSubmit` + état `loading` |
| `<a href="/path">` | Route Vue Router / React Router / Angular Router |
| `data-ui-asset="..."` | Asset à intégrer (image, icône SVG inline) |

---

## 4. Conventions de design

### 4.1 Couleurs — utiliser des tokens, pas des hex hardcodés
Le mockup peut utiliser des hex (`bg-[#2563eb]`) ou des classes Tailwind
prédéfinies (`bg-blue-600`). L'agent `dev-frontend` **convertira** automatiquement
en tokens CSS du DS actif :
- shadcn (React) : `bg-primary`
- Vuetify (Vue) : `color="primary"`
- Radzen (Blazor/Angular) : `Style="background: var(--rz-primary)"`

Si vous avez une palette de marque, l'inscrire dans `## Design Tokens` de
la FEAT et tous les mockups la réutiliseront cohéremment.

### 4.2 Responsive — mobile-first par défaut
- `w-full max-w-md` (mobile small, tablet medium)
- `md:grid-cols-2` (desktop 2 colonnes)
- `lg:px-8` (large screen extra padding)

L'agent dev-frontend préserve la responsivité.

### 4.3 Accessibilité — atteindre WCAG 2.2 AA dès le mockup
- Tous `<input>` ont un `<label for="id">` associé
- Boutons `<button>` ont du texte (pas seulement une icône)
- Couleurs avec ratio contraste ≥ 4.5:1 (texte normal) / ≥ 3:1 (texte large)
- Pas de `tabindex` positif
- `lang="fr"` (ou la langue cible) sur `<html>`

Le CI ingère `axe-core` au build (cf. error-classification-legacy.md §1)
→ violations → verdict 🔴.

---

## 5. Mockups multi-état (formulaires complexes)

Pour les écrans avec plusieurs états visuels (loading, error, success,
empty), créer **plusieurs sections** dans le même HTML, séparées par
`<section data-state="X">` :

```html
<main>
  <!-- État "initial" -->
  <section data-state="initial">
    <form>...</form>
  </section>

  <!-- État "loading" -->
  <section data-state="loading" hidden>
    <div class="animate-spin">⏳ Connexion en cours...</div>
  </section>

  <!-- État "error" -->
  <section data-state="error" hidden>
    <p class="text-red-600">Email ou mot de passe incorrect.</p>
  </section>

  <!-- État "success" -->
  <section data-state="success" hidden>
    <p class="text-green-600">Bienvenue ! Redirection...</p>
  </section>
</main>
```

L'agent `dev-frontend` génère un state machine simple (useState React,
ref Vue, signal Angular) qui bascule entre ces états selon les ACs.

---

## 6. Assets externes (images, icônes)

### Recommandé : SVG inline
```html
<svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
  <path d="M10 2a1 1 0 011 1v6h6a1 1 0 110 2h-6v6a1 1 0 11-2 0v-6H3a1 1 0 110-2h6V3a1 1 0 011-1z"/>
</svg>
```
✅ Pas de dépendance, taille fixe, recolorable via `currentColor`.

### Acceptable : `data-ui-asset` placeholder
```html
<img data-ui-asset="logo-softwe3" alt="Logo Softwe3" class="h-8">
```
L'agent dev-frontend conserve le `data-ui-asset` et insère un commentaire
indiquant au Tech Lead qu'il doit fournir le fichier dans
`public/assets/{name}.svg|png`.

### À éviter : URLs externes
```html
<img src="https://example.com/logo.png">  <!-- ❌ pas de dependency runtime sur CDN tiers -->
```

---

## 7. Exemples canoniques

Voir `workspace/input/ui/_examples/` (à créer lors de l'onboarding).
3 exemples typiques :
1. `_examples/login-simple.html` — form auth basique (le squelette §3.1)
2. `_examples/dashboard-cards.html` — layout grid de cards métriques
3. `_examples/wizard-multi-step.html` — formulaire wizard 3 étapes avec
   états navigation

Ces exemples sont copyables comme point de départ.

---

## 8. Workflow recommandé

1. **Brouillon papier** (3-5 min) — wireframe sur post-it
2. **HTML statique** (15-30 min selon complexité) — copier le squelette §3.1
3. **Validation visuelle** (`open workspace/input/ui/{n}-{m}-{Name}.html`
   dans navigateur) — vérifier rendu sur mobile (Chrome DevTools responsive)
4. **`/feat-validate {n}`** — vérifier que le mockup matche le `{Name}` US
5. **`/sdd-full {n}`** — laisse l'agent matérialiser

À la livraison, le code généré ne sera **pas pixel-perfect** identique au
mockup : il sera **fidèle structurellement** et stylé via le DS actif
(qui peut diverger esthétiquement de Tailwind brut). C'est intentionnel —
les tokens CSS du projet vivent dans `theme.css` / `index.css` et
prennent le dessus.

---

## 9. Limites connues

- **Pas de JS dans le mockup** : aucun comportement interactif, juste DOM
  statique. L'interactivité vient des ACs de l'US.
- **Pas de @import CSS externe** : tout doit être inline ou via CDN Tailwind
  uniquement.
- **Pas de Web Components custom** : l'agent ne les comprendra pas — utiliser
  HTML natif + classes Tailwind.
- **Pas de `<template>` ou `<slot>`** : éléments incompréhensibles hors framework.

---

## 10. Support

- **Companion PO guide** : `@docs/po-guide.md` (rédaction FEAT)
- **Stack UI actifs** : `.claude/stacks/ui/*.md` (shadcn / Vuetify / Radzen)
- **Règle tokens** : `@.claude/rules/quality.md §B` (anti-hex-hardcode)
- **Cookbook** : `@docs/cookbook.md` (workflow bout-en-bout 10 min)
