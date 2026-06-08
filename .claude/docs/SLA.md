# SLA — Engagement Support SDD_Pro v7.0.0 GA

> Service Level Agreement pour les 13 combos commercialisés (2026-06-07).
> Document contractuel : référencé par les bons de commande / RFP.
> Toute clause spécifique négociée prévaut sur ce document de cadre.

---

## 1. Périmètre du SLA

### 1.1 Combos éligibles SLA (13)

Voir `@.claude/docs/validated-combos.md §1.2` pour la liste détaillée.

**Tier 1 — Validated end-to-end (2 combos)** (SSoT : `validated-combos.md §1.2`) :
- **C1** : `dotnet-minimalapi + react + shadcn + dotnet-xunit + azure-ad + mvc` — PoC 2026-05-07
- **C2** : `kotlin-spring-boot + react + shadcn + kotlin-junit + node-vitest + azure-ad + mvc` — PoC 2026-05-11 (workspace CMSPrint)

**Tier 2 — Bench-validated runtime (11 combos SLA — sélection au sein du matrix bench 2026-06-05)** :
- Sélection de 11 combos `bench-validated` parmi les **23 combinaisons** testées au bench du 2026-06-05 (cf. `validated-combos.md §1.3`).
- Liste exacte : 13 combos `combos.json` (C1, C2 = Tier 1 ci-dessus + 11 combos C3-C13 = Tier 2).
- Source machine-readable : [`.claude/templates/combos.json`](../templates/combos.json) ; rapport humain : [`workspace/output/qa/bench/BENCH-GLOBAL-REPORT.md`](../../workspace/output/qa/bench/BENCH-GLOBAL-REPORT.md).
- ⚠️ Pour ces 11 combos, le scaffolding `/sdd-full` a été **partiellement manuel** côté mainteneur lors du bench (Gap 1 — `docs/benchmarks/known-gaps.md`). SLO Tier 2 best-effort, pas Tier 1 (cf. §2.2).

### 1.2 Hors périmètre SLA

- ⚠️ Les **8 stacks 🟡 experimental** (vuetify, ddd, microservice, auth-local,
  mutation-testing, angular-jasmine, python-pytest, playwright) — community
  preview, aucun SLA.
- ⚠️ Le stack **🟡 POC-only `node-react`** — usage interne SDD uniquement.
- ❌ Les combos non listés (run via `SDD_ALLOW_UNTESTED_COMBO=1` bypass).

---

## 2. Engagements de service

### 2.1 SLO opérationnels (combos Tier 1)

| Métrique | Engagement |
|---|---|
| Taux de succès `/sdd-full` end-to-end | ≥ 95 % sur FEATs S/M (1-3 US) |
| Build vert post-`dev-run` | ≥ 98 % (toléré 1 retry build_loop) |
| Coverage ≥ `CoverageMin` (défaut 80%) | ≥ 95 % des US |
| Acceptance Gate PASS | ≥ 90 % en mode `strict` |
| Coût par FEAT 2 US | $15-30 USD (médiane) |
| Durée `/sdd-full` FEAT 2 US | 8-18 minutes (médiane) |

### 2.2 SLO Tier 2 (bench-validated)

| Métrique | Engagement |
|---|---|
| Code généré compile + démarre | ≥ 90 % |
| AC servies (smoke browser OK) | ≥ 80 % |
| Idempotence `/sdd-full` complète | **non garantie** (best-effort) |
| Gaps connus | documentés dans `docs/benchmarks/known-gaps.md` |

### 2.3 Hors SLA mais commitment moral

- Réponse à un bug Critical (pipeline cassé sur combo Tier 1) : **48h ouvrées**
- Réponse à un bug Major : **5 jours ouvrés**
- Pull request mineure (typo, doc) : best-effort

---

## 3. Support

### 3.1 Niveaux

| Niveau | Canal | Réponse cible | Couverture combos |
|---|---|---|---|
| **L1 — Self-service** | Documentation + FAQ + `/sdd-status` | Instantané | Tous |
| **L2 — Community** | Issue tracker GitHub | 5 jours ouvrés | Tier 1 + Tier 2 |
| **L3 — Commercial** | Email dédié (contrat) | 48h ouvrées | Tier 1 + Tier 2 |
| **L4 — Engineering** | Audio/visio (contrat enterprise) | 24h ouvrées | Tier 1 uniquement |

### 3.2 Heures de service

- **L1 / L2** : 24/7 (self-service).
- **L3** : 9h-18h CET, lun-ven, hors jours fériés français.
- **L4** : 9h-18h CET, lun-ven + escalation on-call sur incident bloquant.

### 3.3 Périmètre du support

**Couvert** :
- Bugs framework SDD_Pro (agents, commandes, scripts Python, hooks).
- Régressions sur combos Tier 1 / Tier 2.
- Documentation incorrecte ou incomplète.
- Guidance sur les bonnes pratiques d'usage.

**Non couvert** :
- Bugs du code généré (sortie du LLM) — relèvent du Tech Lead client.
- Performance LLM (latence Anthropic, qualité Opus 4.7) — relève Anthropic.
- Bugs dans les libs externes utilisées par le code généré (EF Core, Spring,
  Prisma, etc.) — relèvent du vendor de la lib.
- Sécurité applicative au-delà du scan `security-reviewer`.
- Personnalisation de combos hors catalogue.

---

## 4. Maintenance & versions

### 4.1 Politique de version

Cf. `@.claude/docs/VERSIONING.md` (SSoT).

- **v7.x LTS** : support sécurité **12 mois** à partir du tag GA (2026-06-07
  → 2027-06-07).
- **v6.10.4 LTS** : conservée jusqu'au **2026-12-31** pour migration douce.
- **PATCH** (v7.0.x) : tous les ~2 semaines (bug fixes).
- **MINOR** (v7.x) : tous les 2-3 mois (features non-breaking).
- **MAJOR** (v8) : ≥ 12 mois (breaking changes, MIGRATION.md fourni).

### 4.2 Cycle de release

- **Freeze window** entre MINOR : 7 jours (gel des merges hors PATCH).
- **CHANGELOG.md** mis à jour à chaque release (entry obligatoire).
- **MIGRATION.md** mis à jour à chaque MINOR/MAJOR.
- Test suite `python -m pytest .claude/python/tests/` doit passer (~700 cas).
- `framework_smoke.py --strict` doit passer (89/92 checks OK, 0 FAIL).

### 4.3 Backward compatibility

- Les **artefacts utilisateur** (FEATs, US, stack.md, console.db) sont
  garantis compatibles MINOR.
- Les **commandes user-facing** (13 slash commands) sont stables MINOR.
- Les **agents nommés** (12 stables MINOR + `complexity-router` opt-in v7.0.0+ stable PATCH) sont stables MINOR.
- Les **classes d'erreur** `[CLASS]` sont stables MINOR (additions OK,
  suppressions = MAJOR).
- Les **commandes internes** (8 commandes debug) peuvent évoluer en PATCH.
- Les **scripts Python** privés (`sdd_lib/`) ne sont pas API publique.

---

## 5. Mesure & reporting

### 5.1 Métriques disponibles côté client

Via `console.db` local + `python .claude/python/sdd_scripts/report_roi.py` :

- Durée par phase / agent / US
- Coût USD par run / FEAT / US
- Tokens consommés (input/output/cache hit)
- Verdicts gates (PASS/WARN/FAIL/SKIPPED)
- Top classes d'erreur émises

### 5.2 Reporting commercial (sur contrat L4)

Sur demande, rapport mensuel agrégé contenant :
- Volume runs / FEATs livrées
- Taux de succès vs SLO
- Tendances coût / durée
- Top 5 incidents

---

## 6. Pénalités & escalation

### 6.1 Non-atteinte SLO Tier 1 (combos C1, C2)

| Drift | Compensation |
|---|---|
| Succès `/sdd-full` < 95 % sur ≥ 10 runs consécutifs | Pull request fix prioritaire dans la version PATCH suivante |
| Build vert post-`dev-run` < 98 % | Investigation root cause + ADR de correction |
| Indisponibilité support L3 > 5 jours | Crédit support étendu (montant à négocier) |

### 6.2 Escalation

L3 → L4 : sur incident bloquant production client, escalation par email.
L4 → Engineering directe : sur incident framework Critical (cf. `error-classification.md`).

---

## 7. Limitations explicites

### 7.1 Mono-IDE

SDD_Pro v7.0.0 fonctionne **exclusivement avec Claude Code** (Anthropic).
Pas de support Cursor / Aider / Codex / Gemini. Une roadmap v8 multi-IDE
est envisageable mais non engagée commercialement.

### 7.2 Langages

Backends supportés Tier 1 : .NET 10, Java/Kotlin 21+, Node 22 LTS,
Python 3.12+. **Go, Rust, PHP, Ruby ne sont PAS supportés** (roadmap v8).

### 7.3 Anti-derive vs créativité

SDD_Pro priorise la **discipline anti-derive** (gates bloquants, ownership
strict, libs catalog). Conséquence : moins de flexibilité créative qu'un
pair-programming Cursor / Aider. C'est un choix de positionnement
assumé — voir `WHY-SDD-PRO.md §4`.

### 7.4 Coût par FEAT

Le coût USD est sensible au prompt cache hit rate Anthropic. Variance
mesurée : $15-30 par FEAT 2 US sur combo C2. Pas de garantie de plafond
strict — utiliser `MaxCostPerRun` (défaut $50) comme gate de protection.

---

## 8. Signature & validité

| Champ | Valeur |
|---|---|
| Version SLA | v1.0 (alignée v7.0.0 GA) |
| Date effet | 2026-06-07 |
| Durée validité | 12 mois (renouvelable) |
| Évolution | Annonce 60 jours avant changement de SLO |

**Ce document est un cadre.** Un contrat client spécifique peut renforcer
ou adapter les engagements (heures de service étendues, on-call dédié,
combos custom). Contacter l'éditeur pour devis.

---

## 9. Liens

- `@.claude/docs/VERSIONING.md` — politique de version (SSoT)
- `@.claude/docs/validated-combos.md` — détail combos Tier 1 + Tier 2
- `@.claude/docs/COMPLIANCE.md` — RGPD, sécurité, audit trail
- `@.claude/docs/KNOWN-LIMITATIONS.md` — limites techniques connues
- `@.claude/docs/WHY-SDD-PRO.md` — positionnement vs concurrents
