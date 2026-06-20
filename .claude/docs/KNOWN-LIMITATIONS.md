# Limites connues — SDD_Pro v7.0.0 GA

> Liste honnête des limitations techniques de SDD_Pro v7.0.0 (2026-06-07).
> **Lire avant d'évaluer le framework** : ce qu'il ne fait PAS est aussi
> important que ce qu'il fait. Consolide les limites éparpillées dans
> `validated-combos.md §6`, `library-and-stack.md §B.7`,
> `roadmap-v7-v8.md §5`, `architecture.md §5`.

---

## 1. Limites de scope

### 1.1 Mono-IDE Claude Code

SDD_Pro est conçu pour **Claude Code uniquement** (Anthropic). Hooks,
agents, sub-agent tool, skills, settings.json — tout exploite des APIs
spécifiques au runtime Claude Code.

**Impact** : pas utilisable avec Cursor, Aider, Codex, Gemini CLI,
Copilot CLI, Factory Droid, OpenCode.

**Mitigation** : les artefacts (FEATs, US, plans, code généré, console.db)
restent réutilisables si vous quittez SDD_Pro. Une roadmap v8 multi-IDE
est envisageable mais non engagée.

### 1.2 Langages supportés limités

| Catégorie | Supportés (v7.0.0) | NON supportés |
|---|---|---|
| Backend | .NET 10, Java/Kotlin 21+, Node 22 LTS, Python 3.12+ | Go, Rust, PHP, Ruby, Elixir, Clojure |
| Frontend | React 19, Vue 3.5, Angular 19, Blazor WASM | Svelte, SolidJS, Qwik, Preact |
| Mobile | MAUI, React Native, Kotlin Android | Flutter, Native iOS Swift, Xamarin |
| Fullstack | Next, Nuxt, Angular Universal, Blazor Server, Kotlin Mustache | Phoenix LiveView, Rails, Django templates |

**Roadmap v8** : Go (gin/echo) + PHP (Symfony/Laravel) prioritaires.

### 1.3 Domaines métier

SDD_Pro est conçu pour les **applications business web standard** :
CRUD, REST APIs, dashboards, formulaires, auth. Hors scope :

- ❌ Algorithmes scientifiques / ML / numerical computing
- ❌ Embedded / systèmes temps-réel
- ❌ Jeux vidéo (Unity, Unreal)
- ❌ Drivers / OS kernel
- ❌ Smart contracts / blockchain
- ❌ Realtime streaming (WebRTC, video processing)

---

## 2. Limites runtime documentées (post-mortem bench)

Cf. `library-and-stack.md §B.7` pour le détail.

### 2.1 CORS `localhost` ≠ `127.0.0.1` (post-mortem bench FEAT 2)
Allowlist multi-host requise. Documenté et appliqué par arch v7.0.0+.

### 2.2 `<input type=number>` coerce en `number` (Vue 3, Angular 18)
Type state framework doit être `number | null`, pas `string`.
Documenté pour FEAT impliquant des forms numériques.

### 2.3 JMustache rejette `null` keys strict (Spring Boot + Mustache)
Populer `Model` avec strings vides + flags `hasX`. Documenté.

### 2.4 `pydantic-core` no-wheel sur Python 3.14+
Pin `pydantic>=2.11` si Python ≥ 3.13.

### 2.5 bUnit `.Change()` ≠ `@bind:event="oninput"`
Tests doivent utiliser `.Input("value")` pour binding immediate.

---

## 3. Limites architecturales

### 3.1 Pas de support multi-projet par workspace

Un workspace SDD_Pro contient **un seul stack `stack.md`**. Pour gérer
plusieurs micro-services dans un même monorepo, il faut **un workspace
par service**. Pattern microservice (stack 🟡 experimental) est plus une
intention qu'une garantie.

**Workaround** : `workspace/output/src/{BackendName}` + `{AppName}` +
`{LibName}` permettent une isolation back/front/shared dans le même
workspace, mais pas N backends.

### 3.2 Pas de "blue/green" code generation

`/sdd-full` régénère par-dessus l'existant (mode Edit-augment + ownership
matrix). Pas de génération "shadow" à comparer avant d'écraser.

**Workaround** : `git checkout -b sdd-regen` avant `/sdd-full`, diff
manuel ensuite.

### 3.3 Pas de génération incrémentale par ticket

L'unité de travail est la **FEAT** (1-3 US idéalement, hard cap 10).
Pour des modifications spot ("ajouter un champ à un DTO existant"),
SDD_Pro est sur-dimensionné — utilisez l'agent `dev-backend` standalone
sans le pipeline complet.

### 3.4 État partagé console.db non-distribué

`console.db` est **local au workspace**. Pas de réconciliation cross-machine
si plusieurs Tech Leads travaillent sur le même projet en parallèle. Les
métriques ROI agrégées requièrent une consolidation manuelle.

---

## 4. Limites des LLM

### 4.1 Dépendance Anthropic Claude

Si Anthropic indisponible (panne API, modification policy, retrait
modèle), SDD_Pro est inutilisable. Cf. `COMPLIANCE.md §8 Q2`.

### 4.2 Variance qualité Opus 4.7 / Sonnet 4.6

Les LLM ne sont pas déterministes. Sur 2 runs identiques de `/sdd-full`,
le code généré peut différer (naming variables, ordering d'imports,
structure d'helpers). Les **gates déterministes** Python compensent en
refusant les écarts hors AC, mais la créativité interne du LLM reste
imprévisible.

**Mitigation** : tests unitaires + Acceptance Gate forcent un
comportement observable identique même si le code intern diffère.

### 4.3 Limite de contexte

Claude Opus 4.7 supporte 1M tokens. Le framework limite le **context
budget par agent** (ledger `console.db` table `context_budget`) pour
éviter l'explosion. Une FEAT trop grosse (> 10 US, > 50k LOC code
existant à lire) peut hitter la limite.

**Mitigation** : découpe en sous-FEATs, lecture sélective par US (pattern
appliqué).

---

## 5. Limites de l'audit & sécurité

### 5.1 `security-reviewer` scan ≠ pentest

Le scan automatique couvre **23 classes `[SEC_*]`** mappées OWASP/CWE,
mais ne remplace pas un pentest professionnel. Notamment :

- ❌ Pas de fuzzing automatique
- ❌ Pas de scan dépendances transitives (uniquement directes)
- ❌ Pas de scan binaires compilés
- ❌ Pas de scan secrets dans l'historique Git

**Pour pentest** : intégrer Snyk, Semgrep, Trivy, etc. dans le CI client.

### 5.2 Adversarial review opt-in

L'`adversarial-reviewer` produit des attaques **informationnelles**, jamais
bloquantes. Le Tech Lead doit lire le rapport et arbitrer si un finding
mérite une US de remédiation.

### 5.3 Pas de garantie sur le code legacy

Le framework est conçu pour la **génération from-scratch** ou la
**brownfield init** via `/sdd-discover-stack`. Une fois le projet généré,
les modifs incrémentales (US 2, 3, 4...) restent gated, mais le code
**ajouté manuellement par l'équipe** hors pipeline n'est pas couvert par
les reviews automatiques.

**Mitigation** : exécuter `/sdd-review {n}` régulièrement sur les FEATs
maintenues.

---

## 6. Limites du modèle commercial

### 6.1 Pas de SaaS

SDD_Pro n'a pas (encore) de version cloud / managed. Cf. `COMPLIANCE.md §1`.
Chaque équipe doit installer le framework localement.

### 6.2 Pricing dépendant d'Anthropic

Le coût USD par FEAT dépend du pricing Claude API (Opus 4.7 + Sonnet 4.6 +
cache hit rate). Si Anthropic change ses tarifs, le ROI varie. Voir
`cache-strategy.md` pour les optimisations cache.

### 6.3 Adoption marché à 0

SDD_Pro v7.0.0 vient de sortir (2026-06-07). Aucune communauté établie,
0 stars GitHub (à publier OSS), 0 plugin Claude Code marketplace.
Concurrents : Superpowers 93k-150k ⭐, BMAD 48k ⭐.

**Conséquence pratique** : peu de tutoriels tiers, peu de stack overflow
answers, peu d'extensions communautaires.

---

## 7. Roadmap v7.1 / v8 (limitations qui seront levées)

| Limitation actuelle | Roadmap | Effort estimé |
|---|---|---|
| Mono-IDE Claude Code | v8 : multi-LLM via abstraction provider | ~6 mois |
| Pas de Go / PHP / Ruby | v7.1 : Go + PHP stacks | ~2-3 semaines |
| `dispatch_fixes.py` dormant (Phase B) | v7.2 : `/sdd-review --fix` câblé | ~1 semaine |
| Pas de plugin Claude Code packaging | v7.1 : `/plugin install sdd-pro` | ~3 jours |
| Personas LLM non humanisées | v7.2 : option personas (Léo, Sophie...) | ~2 jours |
| Pas de SaaS managé | non roadmap (positionnement self-hosted assumé) | — |
| `console.db` non-distribué | v8 : sync optionnel via API client | ~2-3 semaines |
| Variance ROI non mesurée sur 3+ runs | v7.1 : 3 runs supplémentaires CMS-Back + nouveau projet | ~3 jours |

---

## 8. Comment signaler une nouvelle limite

Si vous découvrez une limite non documentée ici :

1. Capturer un reproductible minimal (FEAT + stack.md + commande
   `/sdd-full N`).
2. Vérifier qu'elle ne figure pas déjà dans `validated-combos.md §6`,
   `library-and-stack.md §B.7`, ou ce document.
3. Ouvrir une issue avec template `KNOWN-LIMIT`.
4. La limite sera ajoutée ici ou marquée roadmap.

---

## 9. Liens

- `@.claude/docs/WHY-SDD-PRO.md` — positionnement vs concurrents
- `@.claude/docs/COMPLIANCE.md` — sécurité / RGPD / audit trail
- `@.claude/docs/SLA.md` — engagement support
- `@.claude/docs/validated-combos.md §6` — risques par combo
- `@.claude/rules/library-and-stack.md §B.7` — pièges runtime documentés
- `@.claude/docs/roadmap-v7-v8.md` — items planifiés

---

*Document mis à jour à chaque nouvelle limite découverte. Honnêteté
commerciale : un acheteur DSI préfère savoir avant d'acheter, pas après.*
