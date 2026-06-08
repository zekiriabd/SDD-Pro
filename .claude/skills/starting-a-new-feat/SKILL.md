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
python .claude/python/sdd_scripts/sdd_state.py status --json
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

Si oui → guider vers `.claude/templates/{product-brief,prfaq}.template.md`.
Si non → aller §3.

### Étape 3 : nouvelle FEAT ou US dans FEAT existante ?

Avant de spawner `/feat-generate`, **lire les FEATs existantes** pour
détecter si la demande est :

- **Vraie nouvelle FEAT** : nouveau domaine métier, nouveaux acteurs,
  ≥ 3 User Stories prévisibles → `/feat-generate <Nom>`
- **US dans FEAT existante** : extension d'un domaine déjà cadré
  (ex. "ajouter le SSO" alors que FEAT Auth existe) → ajouter une US
  manuellement dans `workspace/output/us/{n}-{m}-{Name}.md` puis
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
- Coder avant que `/feat-generate` ait produit `workspace/input/feats/{n}-*.md`
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
| "Je vais écrire la FEAT manuellement et skipper /feat-generate" | OK si Tech Lead expert, à condition de respecter `feat.template.md` (frontmatter + sections SFD/BR/AC). |

## Pointeurs

- `@.claude/commands/feat-generate.md` — détail STEPs élicitor
- `@.claude/agents/po.md` — agent en charge du cadrage
- `@.claude/templates/feat.template.md` — template FEAT (référence)
- `@.claude/docs/principles/us-granularity.md` — granularité US (1-6 par FEAT)
