---
name: starting-a-new-feat
description: Use when the user expresses intent to add a new feature, capability, or functionality to the project. Triggers on phrases like "I want to add", "we need a", "new feature", "let's build", "implement X", "ajouter une fonctionnalité", "nouvelle feature". Routes to the SDDPro /feat-generate pipeline instead of letting the agent jump into coding. Captures Phase 0 Discovery if the project is greenfield with no Discovery artifacts.
---

# Skill — Starting a New FEAT in SDDPro

> **Auto-trigger** : intention "nouvelle fonctionnalité" détectée.
> **But** : empêcher Claude de coder directement sans cadrage.
> Forcer le passage par `/feat-generate` (3-6 questions élicitor).

## Décision tree

### Étape 1 : vérifier l'état du projet

```bash
python .sdd/python/sdd_scripts/sdd_state.py status --json
```

Cas selon état détecté :

| État | Action |
|---|---|
| Pas de `stack.md` | STOP. "Le projet n'est pas bootstrappé. Lancer `python bootstrap.py` ou `/sdd-bootstrap` d'abord." |
| `stack.md` OK, 0 FEAT, projet ≥ moyen (estimation ≥ 3 FEATs à venir) | Proposer Phase 0 Discovery avant `/feat-generate` (cf. §2 ci-dessous) |
| `stack.md` OK, 0 FEAT, petit projet (1-2 FEATs) | Aller direct `/feat-generate <Nom>` |
| ≥ 1 FEAT existante | Vérifier si la nouvelle demande est une nouvelle FEAT OU une US à ajouter à une FEAT existante (cf. §3) |

### Étape 2 : Phase 0 Discovery (optionnelle mais recommandée)

Si projet moyennement complexe (≥ 3 FEATs à venir, audience ≥ 2 personas),
proposer au Tech Lead :

```
Avant de cadrer la 1ʳᵉ FEAT, veux-tu un Discovery rapide ? (10-30 min)
- /sdd-help "phase 0" pour les templates
- product-brief.template.md : sections classiques (vision, personas, KPIs, hypothèses)
- prfaq.template.md : Amazon "Working Backwards" (1 page communiqué + FAQ)

Bénéfice : éviter le scope creep en FEATs parasites.
```

Si oui → guider vers `.sdd/templates/{product-brief,prfaq}.template.md`.
Si non → aller §3.

### Étape 3 : nouvelle FEAT ou US dans FEAT existante ?

Avant de spawner `/feat-generate`, **lire les FEATs existantes** pour
détecter si la demande est :

- **Vraie nouvelle FEAT** : nouveau domaine métier, nouveaux acteurs,
  ≥ 3 User Stories prévisibles → `/feat-generate <Nom>`
- **US dans FEAT existante** : extension d'un domaine déjà cadré
  (ex. "ajouter le SSO" alors que FEAT Auth existe) → ajouter une US
  manuellement dans `workspace/us/{n}-{m}-{Name}.md` puis
  `/dev-run {n}` (ou compléter la FEAT puis `/us-generate {n}`)

Si ambigu : demander au Tech Lead, ne pas trancher seul.

### Étape 4 : `/feat-generate` (cadrage)

```
/feat-generate <NomDeLaFeature>
```

L'agent `po` pose 3-6 questions élicitor pour capturer :
- Acteurs concernés
- Functional Needs (SFD-N stable)
- Business Rules (BR-N stable)
- Acceptance Criteria (AC-N stable)
- Quantified Goal (KPI + target + deadline)
- Non-Functional Constraints (volume, SLA, GDPR, etc.)

**Ne JAMAIS** :
- Coder avant que `/feat-generate` ait produit `workspace/feats/{n}-*.md`
- Inventer des AC à la place de l'utilisateur
- Skipper l'élicitor (`/feat-deepen` pour approfondir si besoin)

### Étape 5 : suite du pipeline

Après `/feat-generate` → guider vers la suite :

```
/us-generate {n}        # découpe FEAT en User Stories
/feat-validate {n}      # gate GO/NO-GO avant code
/sdd-full {n}           # pipeline A→Z (recommandé pour projet complet)
/sdd-help {n}           # guidance contextuelle si bloqué
```

## Red flags — refuser les rationalizations

| Rationalization | Bonne réponse |
|---|---|
| "Je vais coder direct, c'est juste 1 endpoint" | NON. Pour 1 endpoint, créer une US dans FEAT existante ou `/sdd-poc`. Pas de code sans US. |
| "L'utilisateur veut juste une démo rapide" | `/sdd-poc {n}` est pour ça (pipeline minimaliste). Mais cadrage minimal requis quand même. |
| "Je connais ce qu'il veut, pas besoin de poser les questions" | NON. L'élicitor capture ce que TU ne sais pas. Q/R = signal de gaps. |
| "Je vais écrire la FEAT manuellement et skipper /feat-generate" | OK si Tech Lead expert, à condition de respecter le contrat de « Rédaction manuelle » ci-dessous. |

## Rédaction manuelle

Écrire la FEAT à la main au lieu de `/feat-generate` est acceptable pour un
Tech Lead expert. Le contrat ci-dessous est celui que `/feat-validate` vérifie
de manière déterministe — il n'y a pas de tolérance.

**Fichier** — `workspace/feats/{n}-{Nom}.md`, un seul fichier par préfixe `{n}-`.

**Pas de frontmatter.** Une FEAT *forward* n'en a pas : le gate lit `^FEAT ID:`
dans le CORPS (`generate_specbook.py` : « frontmatter-less FEATs use body
lines »). Seules les FEAT *reverse* portent un frontmatter.

**Titres exacts, jamais annotés.** `section_body()` compile
`^##\s+{titre}\s*$`. `## Quantified Goal (v7.0.0)` n'est PAS
`## Quantified Goal` : la section est declarée absente. Copier les titres de
`.sdd/templates/feat.template.md` à l'identique.

**Sections bloquantes** — absentes, vides, ou sans identifiant : NO-GO.

| Section | Identifiants | Absente / vide | Couverture par les US |
|---|---|---|---|
| `## Functional Needs` | `SFD-N` | NO-GO | bloquante |
| `## Functional Deliverables` | `FD-N` | NO-GO | bloquante |
| `## Acceptance Criteria` | `AC-N` | NO-GO | WARN |
| `## Business Rules` | `BR-N` | non bloquante | WARN |

Format d'un identifiant : `- SFD-1: <texte>`, numérotation continue à partir
de 1, sans doublon. Ne jamais réordonner ni renuméroter après génération des
US — ajouter en fin de liste.

**Couverture** — chaque `SFD-N` et `FD-N` doit être cité par au moins une US
(`Covers:`), sinon NO-GO. Les `AC-N` et `BR-N` non couverts sortent en WARN :
défaut de traçabilité, pas FEAT invalide.

**Enchaînement** — `/us-generate {n}` puis `/feat-validate {n}`. Ne pas lancer
`/dev-run` avant un verdict GO.

## Pointeurs

- `@.claude/commands/feat-generate.md` — détail STEPs élicitor
- `@.claude/agents/po.md` — agent en charge du cadrage
- `@.sdd/templates/feat.template.md` — template FEAT (référence)
- `@.sdd/docs/principles/us-granularity.md` — granularité US (1-6 par FEAT)
