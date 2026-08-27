# 📚 Documentation SDD_Pro

> **Développement piloté par la spécification, multi-harness** (Claude Code, Codex,
> Gemini CLI, Antigravity) — un framework multi-agent qui transforme des spécifications
> fonctionnelles en code prêt-à-livrer via **29 agents spécialisés**, une orchestration
> Python déterministe (**80 scripts, 0 token**) et **5 reviewers qualité**.

C'est le hub de documentation. Chaque doc a un objectif et une audience cible.
Choisis ton parcours ci-dessous.

> 🇫🇷 **Documentation FR canonique.** Les pages EN existantes sont suffixées `.en.md`
> (ex. `getting-started.en.md`). Quand une page EN manque, la version FR fait référence —
> le contenu technique (identifiants, classes `[CLASS]`, flags) y est identique.

---

## 🚀 Je veux commencer à utiliser SDD_Pro

| Étape | Objectif | Doc |
|---|---|---|
| **1** | Comprendre SDD_Pro en 5 minutes | [getting-started.md](getting-started.md) |
| **2** | Obtenir un projet fonctionnel en 30 minutes | [cookbook.md](cookbook.md) |
| **3** | Apprendre le vocabulaire | [glossary.md](glossary.md) |
| **4** | Configurer un repo brownfield | [quickstart.md](quickstart.md) |
| **5** | Choisir une combo de stacks | [validated-combos.md](validated-combos.md) |
| **6** | Travailler sous Codex ou Gemini CLI | [multi-llm-getting-started.md](multi-llm-getting-started.md) |

---

## 🗄️ J'ai du legacy à récupérer (reverse engineering)

| Point de départ | Ce que ça produit | Doc |
|---|---|---|
| **Une base de données** (procédures, fonctions, vues, triggers, jobs) | 1 objet SQL = 1 User Story · 1 module = 1 FEAT | [reverse-engineering-workflow.md](reverse-engineering-workflow.md) *(Annexe D)* |
| **Du code source legacy** (WebForms, PHP, Delphi, monolithes) | escalier 3a analyse → 3b US → 3c FEAT | [reverse-engineering-workflow.md](reverse-engineering-workflow.md) |
| Recettes par techno legacy | Exemples concrets d'extraction | [reverse-engineering-cookbook/](reverse-engineering-cookbook/index.md) |
| Décisions d'audit du module SGBD | Ce qui a été arbitré et pourquoi | [reverse-db-audit-2026-07.md](reverse-db-audit-2026-07.md) |
| Règles anti-derive du reverse | Taxonomie `[REVERSE_*]`, evidence, confidence | [../rules/reverse-engineering.md](../rules/reverse-engineering.md) |
| Socle d'expertise SQL partagé | Pièges `MERGE` / `NULL` / atomicité, équivalences multi-dialecte | [../rules/db-reverse-tsql.md](../rules/db-reverse-tsql.md) |

> ⚠️ **Phase 0 obligatoire** depuis 2026-08-26 : `/sdd-db-context` construit le *Database
> Context* (faits déterministes + hypothèses de l'architecte, versionnés) **avant** toute
> remontée en User Story. Sans lui, un objet composite produit une spec fausse mais
> crédible.

---

## 📖 Je veux comprendre le framework en profondeur

| Sujet | Audience | Doc |
|---|---|---|
| Visualisation du pipeline (mermaid) | Architecte / Tech Lead | [workflow.md](workflow.md) |
| Modèle de composants (agents, rules, hooks) | Architecte / Tech Lead | [architecture.md](architecture.md) |
| Carte des gates (qui bloque quoi, quand) | Tech Lead | [gates-map.md](gates-map.md) |
| Pourquoi ces choix de conception | Tous | [principles/source-first.md](principles/source-first.md) |
| Règles de granularité des User Stories | PO / Tech Lead | [principles/us-granularity.md](principles/us-granularity.md) |
| Anti-derive + idempotence + plans | Tech Lead | [conventions.md](conventions.md) |
| Hooks et protections runtime | Tech Lead | [hooks-and-protections.md](hooks-and-protections.md) |

---

## 🔧 J'ai besoin d'une référence (fiches)

| Référence | Objet | Doc |
|---|---|---|
| **29 agents** (13 forward + 16 reverse) | Rôle / Modèle / Entrées / Sorties / Verdicts | [agents-reference.md](agents-reference.md) |
| **41 commandes** (13 user-facing + 9 internes + 19 reverse) | Args / Flags / Agents / Sorties | [commands-reference.md](commands-reference.md) |
| **Project Config** | Config en couches + defaults + plages | [configuration-reference.md](configuration-reference.md) |
| **Classes d'erreur** | Taxonomie de **191 préfixes** `[CLASS]` en 16 familles | [../rules/error-classification.md](../rules/error-classification.md) |
| **Invariants load-bearing** | 14 forward + 17 reverse, chacun avec son *enforcer* | [../INVARIANTS.yml](../INVARIANTS.yml) · [../INVARIANTS.reverse.yml](../INVARIANTS.reverse.yml) |
| **Hooks de protection** | Les 20 hooks câblés (preflight, ownership, cost cap…) | [hooks-and-protections.md](hooks-and-protections.md) |
| **Prérequis par stack** | Runtimes, SDK, drivers | [prerequisites-matrix.md](prerequisites-matrix.md) |

---

## 🛟 J'ai une erreur / une question

| Situation | Doc |
|---|---|
| Erreurs courantes + récupération | [troubleshooting.md](troubleshooting.md) |
| Pièges runtime connus | [runtime-pitfalls.md](runtime-pitfalls.md) |
| Précédence de config (base ← team ← project) | [config-precedence.md](config-precedence.md) |
| Nettoyer les fichiers orphelins | [orphan-cleanup-policy.md](orphan-cleanup-policy.md) |
| Décalage de version de stack | [validated-combos.md](validated-combos.md) |
| Ce que SDD_Pro **ne fait pas** | [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md) |

---

## 💼 Je dois arbitrer (CTO / DSI)

| Doc | Objet |
|---|---|
| [WHY-SDD-PRO.md](WHY-SDD-PRO.md) | Argumentaire et comparatif marché |
| [SLA.md](SLA.md) | Engagements de service (13 combos) |
| [COMPLIANCE.md](COMPLIANCE.md) | Conformité et traitement des données |
| [poc-roi-methodology.md](poc-roi-methodology.md) | Comment valider un nouveau stack |
| [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md) | Limites assumées |

---

## 🤝 Je veux contribuer

| Contribution | Doc |
|---|---|
| Accord de travail (working agreement) | [WORKING-AGREEMENT.md](WORKING-AGREEMENT.md) |
| Politique de versioning | [VERSIONING.md](VERSIONING.md) |
| Ajouter un nouveau stack | [../stacks/README.md](../stacks/README.md) |
| Décisions d'architecture | [adrs/](adrs/) |

---

## 📜 Je consulte l'historique / les changelogs

| Doc | Contenu |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | Notes de version (par release) |
| [MIGRATION.md](MIGRATION.md) | Guides de mise à niveau v6 → v7 |
| [adrs/](adrs/) | Architecture Decision Records |
| [roadmap-v7-v8.md](roadmap-v7-v8.md) | Ce qui arrive après |

---

## 📊 ROI & benchmarks

| Doc | Objet |
|---|---|
| [poc-roi-methodology.md](poc-roi-methodology.md) | Comment valider un nouveau stack |
| [benchmarks/](benchmarks/) | Rapports de runs + gaps connus |
| [cache-strategy.md](cache-strategy.md) | Plan de cache des prompts |

---

## 🏛 Sous-systèmes

| Sous-système | Doc |
|---|---|
| **Phases arch** (A/B/C en profondeur) | [arch/phase-a-config-propagation.md](arch/phase-a-config-propagation.md) · [arch/phase-b-db-scaffolding.md](arch/phase-b-db-scaffolding.md) · [arch/phase-c-claude-md-generation.md](arch/phase-c-claude-md-generation.md) |
| **Codebase Python** | [../python/README.md](../python/README.md) |
| **Catalogue des stacks** | [../stacks/README.md](../stacks/README.md) |
| **Les 12 règles opérationnelles** | [../rules/](../rules/) |
| **Façades multi-harness** | [harness-codex.md](harness-codex.md) · [harness-gemini.md](harness-gemini.md) |

---

## ❓ Toujours perdu ?

- **Nouveau contributeur ?** Lis `getting-started.md` + `cookbook.md` (1 h au total).
- **Onboarding d'un repo brownfield ?** Lance `/sdd-discover-stack`, puis lis `quickstart.md`.
- **Du legacy à récupérer ?** Base de données → `/sdd-db-context` puis `/sdd-db-reverse-full`.
  Code source → `/sdd-reverse-full`.
- **Pipeline qui plante ?** Ouvre `troubleshooting.md` et cherche ta classe d'erreur `[XXX]`.
- **Ajouter un stack ?** Lis d'abord `poc-roi-methodology.md` (le critère de validation est réel).

> 💡 **Astuce** : l'entry-point `.claude/CLAUDE.md` (~150 lignes) est un index slim —
> chaque section pointe vers les docs détaillées listées ici. Si tu ne lis que 2 fichiers,
> choisis `CLAUDE.md` + cette page.

---

## 🌐 Statut des traductions

Les pages EN vivent à côté des pages FR, suffixées `.en.md` :

| Page | FR | EN |
|---|:---:|:---:|
| README (cette page) | ✅ canonique | ✅ [README.en.md](README.en.md) |
| Getting Started | ✅ canonique | ✅ [getting-started.en.md](getting-started.en.md) |
| README racine du dépôt | ✅ [../../README.fr.md](../../README.fr.md) | ✅ [../../README.md](../../README.md) |
| Toutes les autres pages | ✅ canonique | 🟡 lire la version FR |

> Contributions EN bienvenues : ajouter `page.en.md` à côté de `page.md`, puis mettre à
> jour ce tableau **et** la table équivalente de [README.en.md](README.en.md).
