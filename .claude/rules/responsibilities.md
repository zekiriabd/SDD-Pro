# Règle — Responsabilités SDD_Pro

## Principe

Chaque rôle (humain ou agent) a un périmètre strict. Aucun chevauchement.

---

## 1. PO Humain — Allowed

- Écrire ou faire écrire les SPECs fonctionnelles dans `workspace/input/specs/`
  (manuellement ou via `/spec-generate`)
- Remplir les sections du template SPEC : Context, Objective, Actors,
  Functional Needs (SFD-N préfixés), Business Rules, Acceptance Criteria,
  Dependencies, Functional Deliverables (FD-N préfixés), Out of Scope

## 2. PO Humain — Forbidden

- Écrire des User Stories structurées (`US-1`, `US-2`, format `As a...
  I want... So that...`) dans la SPEC. Le découpage en US est la
  responsabilité de l'agent PO.
- Imposer un découpage technique (endpoints, services, DTOs, fichiers).
- Choisir le design system ou le stack (responsabilité du Tech Lead via
  `workspace/input/stack/stack.md`).
- Déposer les mockups HTML (responsabilité de l'UX Designer humain).

---

## 3. UX Designer Humain — Allowed (depuis v4)

- Déposer les **mockups HTML statiques** dans `workspace/input/ui/{n}-{m}-{Name}.html`
  où `{n}-{m}-{Name}` correspond exactement au basename d'une US dans
  `workspace/output/us/`.
- Le mockup HTML doit être **autonome** : ouvrable dans un navigateur,
  contenant les libellés français définitifs, la structure DOM exacte
  attendue, et idéalement les couleurs (en `style="..."` inline ou
  dans un bloc `<style>`).
- L'UX Designer peut utiliser n'importe quelle approche pour produire
  ces HTML (export depuis Figma/Sketch, écriture manuelle, IA
  externe), tant que le fichier final est un HTML statique valide.

## 4. UX Designer Humain — Forbidden

- Écrire du code applicatif (Pages Razor, composants React/Vue,
  services). Le mockup HTML est statique.
- Modifier les SPECs ou les US (read-only).
- Choisir le design system (responsabilité du Tech Lead).

---

## 5. Agent PO — Allowed

- Lire `workspace/input/specs/{n}-{Name}.md` (la SPEC parente)
- Lire les règles `.claude/rules/us-granularity.md` et `responsibilities.md`
- Découper la SPEC en User Stories selon `us-granularity.md`
  (**cible 1-3, warning 4-6, hard cap 6 US par SPEC**)
- Écrire `workspace/output/us/{n}-{m}-{Name}.md` pour chaque US, conforme à
  `.claude/templates/us.template.md`
- Garantir la traçabilité 100% (chaque SFD/BR/AC/FD couvert par au moins
  une US)

## 6. Agent PO — Forbidden

- Lire ou modifier `workspace/input/stack/` (responsabilité du Tech Lead)
- Lire ou modifier `workspace/input/ui/` (mockups HTML — responsabilité UX
  Designer humain ; consommation par dev-frontend uniquement)
- Inventer des SFD, BR, AC, FD non présents dans la SPEC parente
  (anti-derive strict)
- Décider d'un design système, d'une lib, d'une architecture
- Modifier la SPEC parente (read-only)
- Demander une intervention utilisateur pendant l'exécution (autonomous)

---

## 7. Agent Arch — Allowed

L'agent Arch couvre **deux phases** dans une seule invocation :

### Phase A — Bootstrap des projets

- Lire `workspace/input/stack/stack.md` (intégralité)
- Lire les fichiers `.claude/stacks/**/*.md` listés sous `## Active …`
  (sélectif) — récupérer §2.2 (commandes Build/project_file), §2.2.1
  (Init Commands), §3-§4 (commande de scaffolding DB), §5.1 (pattern
  connection string)
- Lire `.claude/rules/responsibilities.md` (la politique librairies
  est inlined dans `agents/arch.md` depuis SDD_Pro v2.2)
- Glob `workspace/output/src/**/*.csproj`, `workspace/output/src/**/package.json`,
  `workspace/output/src/**/pyproject.toml` pour la détection d'idempotence
- Exécuter (`Bash`) les Init Commands documentées en §2.2.1 avec
  substitution `{AppName}`, `{BackendName}`, `{LibName}`,
  `{AppNamespace}` du `Project Config`
- Créer le fichier solution `.sln` et ajouter les projets (stacks .NET)
- Exécuter le build de validation (§2.2 du stack) — exit code 0 attendu

### Phase B — Schéma DB + scaffolding (si `DatabaseType ≠ none`)

- Lire les valeurs des 5 variables d'environnement canoniques
  (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`) et
  composer la connection string en RAM
- Exécuter une **introspection READ-ONLY** des métadonnées
  (`INFORMATION_SCHEMA` / `pragma` selon DatabaseType)
- Exécuter le scaffolding Database-First incrémental du stack actif
  (ex. `dotnet ef dbcontext scaffold`)
- Écrire `workspace/output/db/schema.json` (machine-readable) et
  `workspace/output/db/schema.md` (humain)
- Écrire les entities générées dans `workspace/output/src/{BackendName}/Entities/`

## 8. Agent Arch — Forbidden

- Lire ou modifier les SPECs, US, mockups HTML
- Générer du code applicatif (Page, Component, Endpoint, Service, DTO,
  Mapper, Migration) — réservé aux agents dev-*
- Exécuter une commande non documentée dans §2.2.1 d'un stack actif
  (anti-derive : pas de `npm install <pkg>` arbitraire, pas de
  `dotnet add package <pkg>` arbitraire)
- **Contrat DB READ-ONLY** : exécuter toute requête SQL au-delà de
  l'introspection : `INSERT/UPDATE/DELETE/CREATE/ALTER/DROP/TRUNCATE/
  EXECUTE` interdits
- Écrire la connection string dans un fichier du repo (jamais)
- Logger `DB_PASSWORD` ou la connection string complète
- Supprimer un fichier existant (idempotence stricte) — y compris une
  entité scaffoldée (le `--force` est incrémental)
- Demander une intervention utilisateur (autonomous)

---

## 9. Agent Dev-Backend — Allowed

Lecture **sélective par US courante** uniquement. Pour matérialiser
l'US `{n}-{m}-{Name}` côté serveur :

- Lire **uniquement** l'US ciblée `workspace/output/us/{n}-{m}-{Name}.md`
- Lire **uniquement** le mockup HTML correspondant
  `workspace/input/ui/{n}-{m}-{Name}.html` s'il existe (lecture passive pour
  identifier les endpoints/DTOs déclenchés par les `<form>`,
  `<table>`, exports/imports ; jamais pour générer du markup côté
  backend)
- Lire `workspace/input/stack/stack.md` (intégralité)
- Lire les fichiers `.claude/stacks/backend/*.md` et
  `.claude/stacks/auth/*.md` listés sous `## Active …` (sélectif)
- Lire `workspace/output/db/schema.json` (si présent) pour les Mappers/DTOs
- Lire `.claude/rules/responsibilities.md`
- **Planifier inline** la liste des fichiers serveur à produire à
  partir de l'US, du mockup HTML éventuel, du schéma DB et du stack
- **OU** consommer un plan existant (mode From Plan) :
  si `workspace/output/plans/{n}-{m}-*.back.md` existe, l'agent lit ce plan
  et code à partir de lui sans re-planifier
- **OU** produire le plan sans coder (mode Plan Only, suffixe `:plan`
  dans l'argument) : écrit `workspace/output/plans/{n}-{m}-*.back.md` puis STOP
- Écrire le code serveur sous `workspace/output/src/{BackendName}/...` selon le
  mapping `couche → répertoire` du stack actif
- Exécuter le `Build Command` du stack (§2.2) avec build loop max 3
  itérations
- Exit silencieux avec ligne `dev-backend {n}-{m}-{Name}: skipped
  (frontend-only US)` si l'US n'a aucune contrepartie backend

## 10. Agent Dev-Backend — Forbidden

- Lire d'autres US, d'autres mockups HTML, les SPECs
- Lire les stacks `frontend/*.md` ou `ui/*.md` (hors famille)
- Modifier l'US ou le mockup HTML (read-only)
- Inventer une lib non déclarée dans `.claude/stacks/backend|auth/*.md`
  actifs
- Inventer un pattern (Repository, CQRS, Mediator) non déclaré dans le
  stack
- Générer des tests, fixtures, mocks, fichiers de test (QA hors scope)
- Refactoriser des fichiers existants au-delà des `preserves:` /
  `adds:` qui matérialisent l'US courante
- Tenter d'initialiser le projet (responsabilité de Arch)
- Demander une intervention utilisateur (autonomous)

---

## 11. Agent Dev-Frontend — Allowed

Lecture **sélective par US courante** uniquement. Pour matérialiser
l'US `{n}-{m}-{Name}` côté client :

- Lire **uniquement** l'US ciblée `workspace/output/us/{n}-{m}-{Name}.md`
- **Lire le mockup HTML `workspace/input/ui/{n}-{m}-{Name}.html` directement
  (texte)** s'il existe — c'est la **source de vérité visuelle** pour
  les libellés exacts, la structure des zones, les classes CSS, les
  couleurs (depuis SDD_Pro v4). Aucun autre mockup HTML d'aucune
  autre US.
- Lire `workspace/input/stack/stack.md` (intégralité)
- Lire les fichiers `.claude/stacks/frontend/*.md`,
  `.claude/stacks/ui/*.md` (mapping §2 + §7) et (si auth active)
  `.claude/stacks/auth/*.md` listés sous `## Active …` (sélectif)
- Lire `.claude/rules/responsibilities.md`
- **Planifier inline** la liste des fichiers client à produire à partir
  de l'US + du mockup HTML + des stacks frontend/ui actifs
- **OU** consommer un plan existant (mode From Plan) :
  si `workspace/output/plans/{n}-{m}-*.front.md` existe, l'agent lit ce plan
  et code à partir de lui sans re-planifier
- **OU** produire le plan sans coder (mode Plan Only, suffixe `:plan`
  dans l'argument) : écrit `workspace/output/plans/{n}-{m}-*.front.md` puis STOP
- Écrire le code client sous `workspace/output/src/{AppName}/...` selon le
  mapping du stack frontend
- Traduire chaque primitive HTML brute en composant natif du DS via le
  mapping §2 + §7 du stack UI (`<table>` → `RadzenDataGrid`,
  `<button>` → `RadzenButton`, etc.)
- Matérialiser les overrides de tokens (couleurs extraites du HTML)
  dans le fichier theme global de l'app
- Insérer les placeholders `<img data-ui-asset="{role}" ...>` pour les
  images non-icône en attente
- Exécuter le `Build Command` du stack (§2.2) avec build loop max 3
  itérations
- Vérifier la fidélité textuelle (tokens hex + **fidelity check
  text-based** STEP 11 : grep des libellés/composants extraits du HTML
  source dans le markup généré)
- Exit silencieux avec ligne `dev-frontend {n}-{m}-{Name}: skipped
  (backend-only US)` si l'US n'a aucune contrepartie frontend

## 12. Agent Dev-Frontend — Forbidden

- Lire d'autres US, les SPECs, les **autres** mockups HTML (seul le
  mockup de l'US courante `workspace/input/ui/{n}-{m}-*.html` est lu)
- Lire les stacks `backend/*.md` (hors famille — sauf consultation
  passive du stack auth pour les patterns d'injection client)
- Modifier l'US ou le mockup HTML (read-only)
- Inventer un composant non listé dans le mapping
  `.claude/stacks/ui/{stack}.md §2` ou §7
- Inventer une lib hors `.claude/stacks/frontend/*.md` actif
- Inventer un libellé, une couleur ou une icône non présente dans le
  mockup HTML ou dans l'US
- Générer des tests, fixtures, mocks (QA hors scope)
- Tenter d'initialiser le projet (responsabilité de Arch)
- Demander une intervention utilisateur (autonomous)
- **Inventer une route HTTP backend** : tout client HTTP (Refit,
  HttpClient typé, axios instance, fetch wrapper, RTK Query, etc.)
  doit cibler **exclusivement des endpoints qui existent dans le code
  backend matérialisé** (`workspace/output/src/{BackendName}/Endpoints/`,
  `Controllers/`, équivalent par stack). Avant d'écrire un appel,
  l'agent vérifie par grep que la route + verbe HTTP existe (ex.
  `MapGet("/api/pointsvente"`). Si une fonctionnalité requiert un
  endpoint absent (ex. `/count`, `/export`, `/search`), deux options
  uniquement :
  1. **Dériver côté client** depuis les données déjà retournées (ex.
     `PagedOutput.TotalCount` → pas de `/count` séparé)
  2. STOP + ERROR `[FRONTEND_BACKEND_CONTRACT_GAP]` 3 lignes pointant
     l'endpoint manquant + l'US de référence
  Anti-pattern strict : créer un `[Get("/api/v1/...")]` ou
  `axios.get("/api/...")` "par symétrie attendue" ou par convention
  REST sans vérifier la signature backend réelle (URL exacte, verbe,
  forme de retour). Chaque mismatch génère un 404 silencieux runtime,
  build vert, bug visible seulement à l'usage.

---

## 13. Convention de nommage cross-fichiers

Pour une même US, le **basename `{n}-{m}-{Name}` est rigoureusement
identique** à travers les artefacts :

| Artefact          | Chemin                                       |
|-------------------|----------------------------------------------|
| Mockup HTML       | `workspace/input/ui/{n}-{m}-{Name}.html` (optionnel)   |
| User Story        | `workspace/output/us/{n}-{m}-{Name}.md`                |

C'est cette convention qui permet la lecture sélective : pour
matérialiser l'US `1-2-Menu-Navigation`, l'agent dev-frontend lit
UNIQUEMENT `workspace/output/us/1-2-Menu-Navigation.md` +
`workspace/input/ui/1-2-Menu-Navigation.html`, jamais les autres fichiers.

---

## 14. Contrat final

- **PO Humain** = besoin métier (SPEC, SFD bullets, max 4 SFD bullets
  regroupables en max 6 US, cible 1-3)
- **Agent PO** = découpage en User Stories structurées (cible 1-3,
  warning 4-6, hard cap 6 US par SPEC ; ACs + Covers, traçabilité 100%)
- **UX Designer Humain** = dépose les **mockups HTML statiques**
  `workspace/input/ui/{n}-{m}-{Name}.html` (libellés exacts, structure DOM,
  couleurs)
- **Tech Lead Humain** = sélection du stack dans `workspace/input/stack/stack.md`
- **Agent Arch** = bootstrap solution + projets vides (Phase A,
  idempotent) **+** scaffolding Database-First READ-ONLY (Phase B,
  si `DatabaseType ≠ none`)
- **Agent Dev-Backend** = lit l'US (+ mockup HTML passif) + stack
  backend → planifie inline → écrit le code serveur + build loop
- **Agent Dev-Frontend** = lit l'US + mockup HTML (texte direct) +
  stacks frontend/ui → traduit HTML→composants DS via §2/§7 →
  planifie inline → écrit le code client + build loop + vérif
  fidélité textuelle
