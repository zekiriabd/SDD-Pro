---
# TOK-C1 (audit 2026-06-12) : chargement paresseux (path-scoped rule). Consommée par les
# 5 reviewers + l'orchestrateur two-stage ; s'injecte au contact des rapports de validation.
paths:
  - "workspace/.sys/.validation/**"
  - "workspace/db/**"
---

# Règle — Auditor Coordination (matrice d'ownership des findings, v7.0.1-dev)

> **Créée 2026-06-11 (audit consolidé P1)** : la coordination entre les
> 5 reviewers LLM + `quality_scan.py` + ingests CI était dispersée
> (code-reviewer §6, security-reviewer STEP 6, error-classification §1.10-§1.13,
> adversarial-reviewer §2.5) — chaque agent déclarait ses frontières par
> négation, sans vue d'ensemble. Cette règle est la **matrice SSoT** :
> 1 domaine de finding = 1 owner unique. Les agents y réfèrent au lieu
> de dupliquer leurs frontières inline.
>
> **Lecteurs** : les 5 agents reviewers (STEP contexte), `/sdd-review`,
> Tech Lead. ~3 KB.

## 1. Matrice d'ownership (1 domaine = 1 owner)

| Domaine de finding | Owner UNIQUE | Classes | Les autres font |
|---|---|---|---|
| Lint trivial : TODO/FIXME, magic numbers, `console.log`, méthodes longues simples, naming trivial, hex hardcodé | `quality_scan.py` (0 token) | `qa_quality` | aucun reviewer LLM ne re-scanne ces patterns |
| Secrets hardcodés | `security-reviewer` | `[SEC_SECRET_HARDCODED]` (hard-blocking CWE-798), `[SEC_SECRET_DEV_CONFIG]` | code-reviewer émet `issues.minor` informationnel + pointeur ; dédup post-hoc clé `SECRET_HARDCODED` |
| OWASP Top 10 (injections, XSS, authz/authn, crypto, CORS, cookies, headers, logging, SSRF, deserialization) | `security-reviewer` | `[SEC_*]` (23 classes, §1.11) | code-reviewer ne scanne PAS ces catégories |
| Anti-patterns cross-fichier (N+1, blocking async, sync-IO-in-async, key index React, useEffect deps), error handling, duplicate code, nesting, naming non-trivial | `code-reviewer` | `[REVIEW_*]` (§1.10) | arch-reviewer ne re-flagge pas le niveau fichier |
| Contract drift front↔back (route vers endpoint inexistant, DTO désynchronisé) | `code-reviewer` | `[FRONTEND_BACKEND_CONTRACT_GAP]` (hard-blocking) | dev-frontend détecte aussi en STEP 5 (pré-emit) — même classe, dédup post-hoc |
| Layer violation **intra-fichier** (DbContext dans UI, business dans controller) | `code-reviewer` | `[LAYER_VIOLATION]` | — |
| Layer bypass **cross-fichier** + patterns archi (MVC/DDD), drift ADR, constitution gap | `arch-reviewer` (opt-in `ArchReviewMode: full`) | `[ARCH_*]` (§1.14) | code-reviewer s'arrête au niveau fichier |
| Conformité AC-by-AC (chaque AC implémentée dans le code matérialisé) | `spec-compliance-reviewer` (Stage A gate) | `[SPEC_*]` (§1.13) | aucun autre reviewer ne lit les ACs |
| Edge cases, hypothèses fragiles, dette masquée, failure modes, UX confusion | `adversarial-reviewer` (opt-out — actif par défaut, informational) | `[ADV_*]` (§1.15) | drop obligatoire de toute attaque chevauchant un finding déjà émis (même file:line) |
| Accessibilité WCAG / Perf Core Web Vitals | ingests CI déterministes (`ingest_axe.py`, `ingest_lighthouse.py`) | `[A11Y_*]`/`[PERF_*]` (héritage) | aucun agent LLM (retraits v7.0.0) |
| Coverage, tests unitaires, API gate | agent `qa` | `[QA_*]` (§1.7) | reviewers ne lancent jamais de tests |

## 2. Mécanique de dé-duplication (2 niveaux)

1. **Post-hoc authoritative** : `sdd_review.py::compute_report` →
   `deduplicate_findings()` + table `CANONICAL_CLASS` (`_review_fetch.py`).
   Deux findings même file:line dont les classes mappent à la même clé
   canonique (ex. `[REVIEW_SECRETS_HARDCODED]` ↔ `[SEC_SECRET_HARDCODED]`
   → `SECRET_HARDCODED`) sont fusionnés, sévérité max conservée.
2. **Pré-emit best-effort** : un reviewer Stage B peut Read le rapport
   d'un pair s'il existe déjà au démarrage et exclure les findings
   couverts (ex. security-reviewer lit `{n}-code-review.json`). En
   parallèle `/dev-run §6.4.B` le fichier est souvent absent → skip
   silent, le post-hoc prend le relais. **Jamais bloquant.**

## 3. Règles mentales

- **Un finding sans owner unique dans la matrice §1 = bug de cette règle**
  → l'ajouter ICI d'abord, puis ajuster l'agent (jamais l'inverse).
- Un reviewer qui rencontre un finding hors de son domaine émet au plus
  une note `issues.minor` informationnelle avec pointeur vers l'owner —
  jamais un finding bloquant dupliqué.
- `quality_scan.py` est toujours exécuté AVANT les reviewers (`/sdd-review`
  re-scan) : tout ce qu'il détecte est hors périmètre LLM par définition.

## 4. Pointeurs

- Séquencement two-stage (Stage A gate → Stage B batch) :
  `@.sdd/rules/auditor-orchestration.md`
- Taxonomie complète des classes : `@.sdd/rules/error-classification.md §1.10-§1.15`
- Détail par agent : `agents/{code,security,spec-compliance,arch,adversarial}-reviewer.md`
