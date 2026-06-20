# Bibliothèque de techniques d'élicitation / brainstorming

> **Nouveau v7.0.0+ (emprunt BMad-method)** : bibliothèque de 15
> techniques structurées que l'agent `elicitor` peut appliquer
> (via `/feat-deepen`). Avant v7.0.0, seules 5 techniques étaient
> codées en dur. La bibliothèque permet à l'agent de **choisir
> dynamiquement** la technique adaptée au gap détecté.
>
> **Source de vérité unique** : ce fichier. L'agent `elicitor`
> charge le tableau §0 (Quick Reference) au STEP 0 — coût context
> ~3 KB. Les techniques sont chargées **à la demande** (lecture
> ciblée de §1, §2, etc. selon technique sélectionnée).

## 0. Quick Reference — 15 techniques par catégorie

| # | Technique | Catégorie | Quand l'utiliser | Output type |
|---|---|---|---|---|
| §1 | Pre-mortem | Risques | Projet ambitieux ou compliance-sensitive | Liste risques + probabilité × impact |
| §2 | First Principles | Hypothèses | Quand "c'est comme ça" suspect | Liste hypothèses + validation method |
| §3 | Red Team | Adversarial | Avant prod, sécurité, fraude | Liste attaques + mitigation |
| §4 | Stakeholder Mapping (RACI) | Acteurs | ≥ 3 parties prenantes | Matrice RACI |
| §5 | Inversion | Modes de défaillance | UX critique, fault-tolerance | Liste "comment ça casse ?" |
| §6 | SCAMPER | Idéation produit | Améliorer produit existant | 7 prismes (Substitute, Combine, ...) |
| §7 | Reverse Brainstorming | Idéation problème | Quand idées s'épuisent | Lister "comment empirer" + inverser |
| §8 | 5 Whys | Cause racine | Bug récurrent, incident | Arbre cause-effet 5 niveaux |
| §9 | Customer Journey Mapping | UX | FEAT user-facing | Diagramme étapes + émotions |
| §10 | Empathy Map | Personas | Audience peu connue | 4 quadrants (Says/Thinks/Feels/Does) |
| §11 | Crazy 8s | Idéation rapide | Brainstorm divergent | 8 idées en 8 min |
| §12 | Six Thinking Hats | Décision multi-angle | Choix structurel polémique | 6 perspectives séquentielles |
| §13 | Cynefin Framework | Classification problème | Doute sur l'approche | Quadrant simple/compliqué/complexe/chaotique |
| §14 | OKR Decomposition | Objectifs | Aligner FEAT sur KPI business | Objectif + 3 Key Results mesurables |
| §15 | Lotus Blossom | Décomposition idée | Idée centrale à fouiller | Grille 3×3 imbriquée |

**Catégories** : Risques (§1,§3,§5,§8) · Hypothèses (§2,§13) · Acteurs (§4,§9,§10) · Idéation (§6,§7,§11,§15) · Décision (§12,§14)

---

## 1. Pre-mortem

**But** : identifier les risques qui peuvent faire échouer la FEAT
en imaginant rétrospectivement un échec.

**Question type** : "On est dans 6 mois. La FEAT a été déployée et
c'est un échec retentissant. Qu'est-ce qui a mal tourné ?"

**Output** : 3-7 risques, chacun avec probabilité (faible/moyenne/élevée)
× impact (mineur/majeur/critique) × mitigation possible.

**Quand l'utiliser** : projet ambitieux, FEAT avec compliance, première
FEAT d'un produit.

---

## 2. First Principles

**But** : exposer les hypothèses implicites du PO ("c'est comme ça
qu'on fait") et les questionner depuis zéro.

**Question type** : "Si tu n'avais aucune contrainte historique
(legacy code, conventions équipe, choix tech passés), comment
ferais-tu cette FEAT ? Que changerait-on ?"

**Output** : 3-5 hypothèses listées + pour chacune : preuve qu'elle
est vraie OU méthode de validation rapide.

**Quand l'utiliser** : FEAT qui "ressemble à ce qu'on fait toujours"
mais où l'on sent que quelque chose cloche.

---

## 3. Red Team

**But** : adopter perspective adversaire (attaquant, fraudeur,
utilisateur malveillant) pour découvrir edge cases.

**Question type** : "Tu es un attaquant qui veut casser cette FEAT
ou la détourner. Quelles attaques tu tentes en priorité ?"

**Output** : 3-7 attaques avec scénario concret + mitigation
recommandée (technique OU process).

**Quand l'utiliser** : avant prod, security-sensitive, paiement,
authentification, FEAT impliquant données utilisateur.

---

## 4. Stakeholder Mapping (RACI)

**But** : identifier toutes les parties prenantes et leur rôle
(Responsible, Accountable, Consulted, Informed).

**Question type** : "Qui sont les ≥ 3 personnes qui doivent valider
cette FEAT avant prod ? Qui peut bloquer ? Qui doit être informé ?"

**Output** : tableau RACI complet, 1 ligne par activité × 1 colonne
par stakeholder.

**Quand l'utiliser** : FEAT touchant ≥ 3 départements, projet
multi-équipes, FEAT avec dépendance équipe externe.

---

## 5. Inversion

**But** : au lieu de demander "comment ça doit marcher ?", demander
"comment ça peut casser ?". Découvre les modes de défaillance que
le bonheur cas ne révèle pas.

**Question type** : "Liste 5 manières dont cette FEAT peut casser
silencieusement (sans crash visible) en production."

**Output** : 3-7 modes de défaillance + détection associée
(logs, alerting, métriques) + comportement dégradé.

**Quand l'utiliser** : FEAT critique pour la disponibilité,
fault-tolerance importante, FEAT avec intégrations externes.

---

## 6. SCAMPER

**But** : améliorer une idée existante en appliquant 7 prismes.

**Prismes** (1 par lettre) :
- **S**ubstitute : remplacer un composant
- **C**ombine : fusionner avec une autre fonctionnalité
- **A**dapt : adapter d'un autre domaine
- **M**odify / Magnify : changer une caractéristique (taille, fréquence...)
- **P**ut to another use : nouvel usage de la même fonctionnalité
- **E**liminate : supprimer une partie, simplifier
- **R**everse / Rearrange : inverser ou réorganiser

**Output** : 3-5 variantes de l'idée originale, une par prisme
activé. Tech Lead arbitre.

**Quand l'utiliser** : FEAT itérative sur produit existant, "on
peut faire mieux que ça mais comment ?".

---

## 7. Reverse Brainstorming

**But** : quand les idées s'épuisent, lister comment **empirer** le
problème, puis inverser pour trouver de nouvelles solutions.

**Question type** : "Comment garantir que cette FEAT soit un échec
total ? Liste 10 manières de la saboter."

**Output** : liste de "comment empirer" + son inverse (= solution).
Souvent débloque des idées originales.

**Quand l'utiliser** : session brainstorm bloquée, équipe en burnout
de créativité, FEAT vue 100 fois.

---

## 8. 5 Whys

**But** : remonter à la cause racine d'un problème en demandant
"pourquoi ?" 5 fois.

**Question type** : "Pourquoi cette FEAT est-elle nécessaire ?"
→ réponse 1 → "Pourquoi ce besoin existe ?" → réponse 2 → ... × 5.

**Output** : arbre cause-effet avec 5 niveaux. La cause finale est
souvent organisationnelle (pas technique).

**Quand l'utiliser** : bug récurrent ou FEAT proposée plusieurs fois
sans aboutir — signal qu'on traite un symptôme, pas la cause.

---

## 9. Customer Journey Mapping

**But** : tracer l'expérience utilisateur étape par étape avec ses
émotions et frictions.

**Étapes type** : Discovery → Onboarding → Premier usage → Usage
régulier → Friction / Bug → Support → Renouvellement.

**Output** : tableau ou diagramme avec colonnes : Étape × Action
utilisateur × Pensée × Émotion × Touchpoint × Opportunité.

**Quand l'utiliser** : FEAT user-facing, première impression compte,
audience nouvelle.

---

## 10. Empathy Map

**But** : approfondir 1 persona avec 4 quadrants :
- **Says** : ce qu'il dit en réunion / interview
- **Thinks** : ce qu'il pense vraiment (souvent différent)
- **Feels** : émotions, frustrations, désirs
- **Does** : comportements observables

**Output** : 1 empathy map par persona important.

**Quand l'utiliser** : audience peu connue, début de produit,
validation persona suspecte.

---

## 11. Crazy 8s

**But** : générer 8 idées en 8 minutes pour forcer la divergence
créative avant de converger.

**Process** : timer 8 min, 1 idée toutes les minutes, croquis ou
1L texte, pas de jugement.

**Output** : 8 idées brutes (la plupart à jeter). Les 1-2
intéressantes deviennent base de SCAMPER ou Lotus Blossom.

**Quand l'utiliser** : phase divergente d'un brainstorm, équipe
en mode "tunnel" sur 1 idée.

---

## 12. Six Thinking Hats (De Bono)

**But** : analyser une décision sous 6 perspectives séquentielles
au lieu d'un débat général chaotique.

**Chapeaux** :
- 🟦 **Bleu** : process / méta (qui parle, qui décide)
- ⚪ **Blanc** : faits, données objectives
- 🟥 **Rouge** : émotions, intuitions
- 🟨 **Jaune** : bénéfices, points positifs
- ⚫ **Noir** : risques, points négatifs
- 🟩 **Vert** : créativité, alternatives

**Output** : pour chaque chapeau, 2-5 bullets. Synthèse finale chapeau bleu.

**Quand l'utiliser** : décision structurelle où l'équipe est divisée,
besoin d'un débat structuré sans s'enliser.

---

## 13. Cynefin Framework

**But** : classifier le problème pour choisir l'approche adaptée.

**Domaines** :
- **Simple** (clair) : cause-effet évident → best practice
- **Complicated** : cause-effet analysable → bonne pratique (expertise)
- **Complex** : cause-effet émergent → expérimentation
- **Chaotic** : pas de cause-effet → agir, observer, stabiliser

**Output** : domaine identifié + approche adaptée.

**Quand l'utiliser** : doute sur "faut-il prototyper ou architecter
d'abord ?", FEAT dans un domaine peu maîtrisé.

---

## 14. OKR Decomposition

**But** : aligner la FEAT sur un objectif business mesurable.

**Format** :
- **Objectif** : aspirationnel, qualitatif, motivant (1 phrase)
- **Key Results** : 3 KRs mesurables avec valeur cible + deadline

**Question type** : "Quel KPI business cette FEAT doit-elle faire
bouger ? De combien ? D'ici quand ?"

**Output** : 1 Objectif + 3 KRs, qui alimente la section
`## Quantified Goal` de la FEAT.

**Quand l'utiliser** : FEAT dont l'impact business est flou, demande
"pourquoi on fait ça ?".

---

## 15. Lotus Blossom

**But** : décomposer une idée centrale en 8 sous-idées, puis chacune
en 8 sous-sous-idées. Génère 64 idées structurées.

**Format** : grille 3×3 centrale (1 idée + 8 sous-idées) × 8 grilles
3×3 satellites (1 sous-idée + 8 raffinements).

**Output** : carte mentale 64 cellules. À élaguer aux 5-10 plus
prometteuses.

**Quand l'utiliser** : FEAT centrale ambitieuse à décomposer en
US, exploration large d'un thème.

---

## Workflow recommandé selon contexte

| Contexte FEAT | Techniques recommandées (ordre) |
|---|---|
| Greenfield product (B2C) | §10 Empathy → §9 Journey → §1 Pre-mortem → §14 OKR |
| Greenfield product (B2B) | §4 Stakeholder RACI → §1 Pre-mortem → §14 OKR |
| Compliance / Security | §3 Red Team → §5 Inversion → §1 Pre-mortem |
| Bug fix / Incident | §8 5 Whys → §5 Inversion |
| FEAT itérative sur produit existant | §6 SCAMPER → §11 Crazy 8s |
| Choix structurel polémique | §12 Six Hats → §13 Cynefin |
| FEAT IA / R&D | §13 Cynefin → §11 Crazy 8s → §2 First Principles |
| FEAT peu claire / "on ne sait pas trop" | §15 Lotus Blossom → §2 First Principles |

---

## Modes d'invocation

### Mode interactif (défaut)

`/feat-deepen {n}` (sans flag) → l'agent `elicitor` :
1. Lit la FEAT + détecte le contexte (compliance ? B2C ? IA ?)
2. Recommande 2-3 techniques adaptées (cf. tableau workflow ci-dessus)
3. Tech Lead choisit (ou accepte le défaut)
4. Pour chaque technique sélectionnée : 1-2 questions Q/R
5. Synthèse finale → 5 sections fin de FEAT + constitution §7

### Mode one-shot rapide

`/feat-deepen {n} --quick` → inférence directe sans Q/R utilisateur,
techniques par défaut (§1 Pre-mortem + §3 Red Team + §5 Inversion).
Plus rapide, moins précis.

### Mode technique-spécifique

`/feat-deepen {n} --technique scamper` (futur v7.1+) → applique une
seule technique. Utile pour itérer sur une FEAT existante.

---

## Anti-patterns

- ❌ **Appliquer toutes les 15 techniques** : 2-3 ciblées valent mieux
  que 15 superficielles
- ❌ **Forcer une technique inadaptée** : Empathy Map sur FEAT
  infra-backend = bruit
- ❌ **Skipper la synthèse** : l'output brut d'une technique n'a pas
  de valeur sans synthèse en bullets exploitables par le PO
- ❌ **Confondre techniques d'idéation (§6,§7,§11) avec techniques de
  validation (§1,§2,§3)** : ne mélange pas divergence et convergence
  dans la même session

---

## Pointeurs

- `@.claude/commands/feat-deepen.md` — commande qui invoque l'agent
- `@.claude/agents/elicitor.md` — agent en charge
- `@.claude/templates/feat.template.md` — template FEAT (sections enrichies)
- `@.claude/docs/principles/us-granularity.md` — granularité résultante
