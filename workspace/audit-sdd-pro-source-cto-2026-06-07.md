# AUDIT SDD_Pro v7.0.0 GA — Source CTO 2026-06-07

> Audit indépendant complet (lecture du code source, pas des rapports existants).
> 7 sub-agents auditeurs en parallèle + analyse performance + comparatif marché.
> Périmètre : 12 agents, 20 commandes, 8 règles, ~105 scripts Python, 34 stacks, 26 templates, 35+ docs.

---

## 0. Verdict exécutif

| Question | Réponse |
|---|---|
| Techniquement solide ? | 🟡 Oui partiellement. Base saine + déterminisme réel + taxonomie riche. 5 bugs bloquants + dette structurelle 3 commandes critiques. |
| Vendable à un DSI ? | 🟡 Oui-avec-réserves majeures. Pas en l'état. 10-15 jours-homme hardening avant pitch. |
| Supérieur à Superpowers/BMAD/Agent OS ? | 🟢 Techniquement supérieur sur 5 axes décisifs DSI régulé. 🔴 Inférieur commercialement (licence, adoption, multi-harness). |
| Marché ? | 🟢 Oui niche : ESN / éditeur logiciel / DSI banque-assurance-santé-public. |

**Score** : 6.8/10 (technique 8/10, commercial 4/10).

---

## 1. Bloquants commerciaux

### B1 — Licence non publiée 🔴 BLOQUANT ABSOLU
`docs/WHY-SDD-PRO.md:116` = `Licence : (à clarifier)`. Aucune DSI compliance (RGPD/ISO 27001) ne signe sans. Concurrents = MIT.
**Fix** : publier Apache 2.0 ou MIT, < 1 jour.

### B2 — Freeze v6.10.4 rompu en 4 jours 🔴 Crédibilité gouvernance
`VERSIONING.md` annonce freeze 2026-05-19 → 2026-06-18. Tag git réel `v7.0.0` daté 2026-05-23 (commit e18edf3). Freeze rompu sans post-mortem ni extension. `CHANGELOG.md` affiche encore banner FREEZE actif.
**Fix** : retirer banner OU acter rupture + extension.

### B3 — Taxonomie "174 classes" arithmétiquement fausse 🔴 Faute commerciale
CLAUDE.md §73 + `error-classification.md §0` annoncent **174 classes**. Recompte réel : **162 strict scope ou 189 avec legacy A11Y/PERF**. Test CI `test_error_classification_count.py` revendiqué soit n'existe pas, soit ment. Sections §1.9 (A11Y 11) et §1.12 (PERF 16) sont des stubs comptés dans le quick-ref.
**Fix** : recompter, fixer le test, propager.

### B4 — Combo C1 (validated) cassé par drift `.libs.json` 🔴 Démo plantera
`dotnet-minimalapi.libs.json:11` pin `ef-core: "10.0.0"`. Le `.md` §2.4.a indique `9.0.4`. Le changeLog du `.libs.json` documente EXPLICITEMENT le post-mortem CMSPrint 2026-05-22 : NU1608 + MissingMethodException. **Quelqu'un a bumpé sans re-sync, réactivant la régression**.
**Fix** : revert ef-core à 9.0.4 + `sync_stack_md.py`.

### B5 — SLA Tier 2 sur rapport inexistant 🔴 Fausse pub
`BENCH-GLOBAL-REPORT.md` référencé par 4 docs, n'existe pas. `known-gaps.md:12-22` avoue : *"3 sub-agents inaccessibles → 23 combinaisons runtime 🟢 mais pas pipeline 🟢 validated"*.
**Fix** : publier rapport OU retirer SLA Tier 2.

### B6 — CVE actives dans 4 combos SLA bench-validated 🔴 Scandale
- `node-express` → `multer 1.4.5-lts.1` : CVE-2025-7338, 47935, 47944 (DoS) — impacte C3
- `python-fastapi` → `python-jose 3.3.0` : CVE-2024-33663, 33664 (algorithm confusion + DoS), non maintenu depuis 2021 — impacte C4, C12, C13
- `python-fastapi` → `passlib 1.7.4` : non maintenu depuis 2020
- `frontend/vue` → `xlsx 0.18.5` : CVE-2023-30533 + CVE-2024-22363 (Prototype Pollution + ReDoS)
**Fix** : bump/remplacer puis re-bench.

### B7 — `mobiles/kotlin-android` annoncé 🟢 reference mais Kotlin 2.3.21 n'existe pas 🔴
`.md` annonce `🟢 reference (Kotlin 2.3.21)`. **Kotlin 2.3.21 n'existe pas** dans le registre Maven (max 2026-06 : 2.1.x). Le stack n'a jamais compilé. `combos.json` le reclasse en `scaffold-validated`. **Compte "14 reference" gonflé de 1 → 13 réels**.
**Fix** : downgrader à `🟡 experimental` ou `scaffold-validated`.

---

## 2. Bugs production

### T1 — `arch.md` STEP 12.5 : sentinel JSON malformé
[`agents/arch.md:509-512`](.claude/agents/arch.md) : `${FEAT_NUMBER}` non défini → JSON cassé → `constitutioner` ne démarre pas.

### T2 — `po.md` + `elicitor.md` : frontmatter sans `Bash`
[`agents/po.md:5`](.claude/agents/po.md) et [`agents/elicitor.md:5`](.claude/agents/elicitor.md) déclarent tools sans Bash. STEP HARD-GATE invoque `python context_budget.py` → **HARD-GATE inopérant** → ledger console.db incomplet, anti-coût-runaway désactivé.

### T3 — `qa.md` STEP 10 : verdict GREEN/YELLOW/RED legacy
[`agents/qa.md:431-449`](.claude/agents/qa.md) utilise triplet legacy. `build-and-loop.md §A.1.3` normalisé sur 5 statuts canoniques PASS|WARN|FAIL|SKIPPED|INFRA_BLOCKED.

### T4 — `dev-frontend.md` STEP 4.1 : 3 sources contradictoires
HTML > Stack vs Stack §7.0 > HTML vs matrice §7.0 > §7.bis > HTML → résultat non-déterministe sur boutons custom.

### T5 — `sdd-full.md` : 2 paradigmes coexistants (43 KB / 976L)
Thin-wrapper Python + 19 STEPs pseudo-bash sans indication de priorité.

### T6 — `dev-run.md` (48 KB / 1102L) : pseudo-Python mélangé bash
STEP 6.4.1 (auditor batch, point névralgique) dépend de transcription LLM ambiguë.

### T7 — `elicitor.md` Q/R wishful thinking timeout/EOF
Concepts inexistants dans runtime Claude Code.

### T8 — `sdd-review.md:227` invoque `query_console_db.py adversarial`
Sous-commande **inexistante** dans le script. Tool adversarial cassé silencieusement.

### T9 — `cleanup_orphans.py:112,192` : `datetime.utcnow()` deprecated Python 3.14
DeprecationWarning bloquante en Python 3.14.

### T10 — `arch.md:263-265` : duplication §3.5 (copy-paste bug)

---

## 3. Performance — pourquoi 1h pour FEAT simple ?

### Cause #1 — Architecture "fork-per-agent" sans cache partagé (60% du surcoût)

Pour 1 FEAT simple (2 US back+front) : **8-14 sub-agents séquentiels**. Chaque sub-agent recharge :
- Prompt système (10-27 KB)
- Rules (~150 KB cumulés : build-and-loop 745L + library-and-stack 750L + error-classification 562L + ownership 537L + quality 458L + loader 812L)
- Contexte projet (CLAUDE.md, stack.md)

**Calcul sans cache** : ~205 KB × 12 invocations × 2-3 build_loop iter = **5-7 MB tokens input par FEAT**.
À Sonnet 4.6 $3/MTok = **$15-21**. Opus $15/MTok = **$75-105**.

**MAIS** `loader.yml:41` documente cache_layer stratégie ANNONCÉE mais NON IMPLÉMENTÉE : *"Implémentation effective des cache_control markers : v7.1 (refacto harness)"*.
Cache hit baseline : **40.8%** au lieu de **99% atteignable**.

### Cause #2 — Markdown obèses (15%)
- `dev-run.md` 1102L / 48 KB
- `sdd-full.md` 976L / 43 KB
- `build-and-loop.md` 745L (chargé par 11 agents)
- `library-and-stack.md` 750L
- `error-classification.md` 562L
- `ownership.md` 537L (avec ~80L dupliquées Partie A↔B)

### Cause #3 — Reads redondants (10%)
- `dev-backend.md` STEP 4 contredit STEP 3.bis : double Read archi pattern
- `arch.md:263-265` duplication §3.5
- 4 portes onboarding (README + getting-started + cookbook + quickstart)

### Cause #4 — Pipeline séquentiel strict (10% temps)
po → arch → dev-backend ALL US → API Gate → dev-frontend ALL US → qa → 5 reviewers.

### Cause #5 — Build loop & incidents tokens (5% explosif)
Post-mortem `spec-compliance-reviewer` : 11.8M tokens / $35 sur 1 run.

### Calcul wall-clock réaliste
```
PO + arch + bootstrap :         3-5 min
dev-backend × 2 US (Opus) :    10-15 min
API Gate QA :                   5-8 min
dev-frontend × 2 US (Opus) :   12-18 min
qa final :                      5-8 min
4-5 reviewers parallèles :      5-10 min
sdd-review consolidé :          3-5 min
                                ────────
                        TOTAL : 43-69 min   ← VOILÀ pourquoi 1h
```

---

## 4. Plan de remédiation par ROI

| # | Action | Effort | Gain temps | Gain coût |
|---|---|---|---:|---:|
| P0 | **Activer prompt caching Anthropic** (annotations cache_layer + cache_control:ephemeral) | 1-2j | **-50%** | **-70%** |
| P1 | Trim agressif Markdown (dev-run, sdd-full, ownership doublons) | 2-3j | -10% | -15% |
| P2 | Dé-dupliquer Reads agents | 1j | -5% | -8% |
| P3 | Consolider 5 reviewers (fusion ou async CI) | 2-3j | -15% | -10% |
| P4 | Fast-path FEAT triviale via `/sdd-poc` par défaut | 1j | -30% (simple) | -25% |
| P5 | BuildLoop hardening (max iter 2, downgrade Sonnet plus tôt) | 1j | -5% | -10% |
| P6 | Python > LLM sur tâches déterministes | 2-4j | -10% | -15% |
| P7 | Hooks consolidation | 1j | -5% | 0% |

**Cible** : 45-60 min / $15-30 → **12-20 min / $3-6** après P0+P1+P2+P4 (5-7 jours-homme).

---

## 5. Comparatif marché (GitHub vérifié 2026-06-07)

| Produit | Stars | Licence |
|---|---:|---|
| obra/Superpowers | 220 170 | MIT |
| BMAD-METHOD | 48 712 | NOASSERTION |
| buildermethods/agent-os | 4 784 | MIT |
| **SDD_Pro** | 0 (privé) | **non publiée** |

**🟢 SUPÉRIEUR sur** : déterminisme (63 scripts Python gates), stack-awareness machine (34 `.libs.json`), cost cap run+US, taxonomie 174 classes, file ownership atomique.

**🔴 INFÉRIEUR sur** : adoption, mono-harness Claude Code, licence absente.

**Marché cible** : ESN / éditeur logiciel / DSI banque-assurance-santé-public (régulés). 5-10% du segment en 18-24 mois si fixes commerciaux.

---

## 6. Fichiers à supprimer (cleanup)

| Fichier | Raison |
|---|---|
| `.claude/python/sdd_admin/cache_manifest.py` | Pre-shipped v7.1, jamais câblé — `_future/` |
| `.claude/python/sdd_admin/rotate_audit_logs.py` | CLI manuel jamais invoqué — câbler ou supprimer |
| `.claude/docs/audit-2026-06-06-roadmap.md` | 0 ref entrante — déplacer `workspace/output/.sys/.audit/` |
| `arch.md:263-265` | Duplication §3.5 anti-derive (copy-paste) |
| `loader.yml:763-772` | 10L commentaires v4.0.0 historiques |
| `error-classification.md` `[PLAN_NOT_STRICT_READY]` + `[PLAN_DIGEST_INSUFFICIENT]` | Classes dépréciées listées 2× |
| `commands/dev-plan.md` STEP 4.5 stub (14L) | Script retiré 2026-05-22 |
| `dev-run.md` ~~PlanCacheStrict~~ mentions | No-op v7.0.0 |
| Pseudo-Python `dev-run.md:788-822` | Extraire en `dev_run_helpers.py` |
| Pseudo-bash 19 STEPs `sdd-full.md` | Consolider sur thin-wrapper Python |

---

## 7. Action immédiate prioritaire

**Si UNE seule chose à faire** : **ACTIVER LE PROMPT CACHING ANTHROPIC**.

`loader.yml` documente la stratégie mais le harness ne l'applique pas. Dette technique annoncée v7.1 qui coûte aujourd'hui 70% des tokens et 50% du temps. Tout le reste est marginal à côté.

**Second levier** : `/sdd-poc` par défaut quand détecteur de simplicité estime feature < 1h-homme. CRUD basique n'a pas besoin de 5 reviewers OWASP + Pre-mortem.
