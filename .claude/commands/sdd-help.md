# /sdd-help — Aide contextuelle "what's next"

> **Nouveau v7.0.0+** (emprunt `bmad-help`) : guidance contextuelle
> orientée action — pas un diagnostic brut comme `/sdd-status`, mais
> une **recommandation de la prochaine commande logique** selon
> l'état détecté du projet.
>
> **Lecture seule**, aucune écriture, aucune invocation d'agent.
> Coût : ~0 token (délégation à `sdd_state.py` + `query_console_db.py`).

**Usage :**
- `/sdd-help` — guidance globale projet (où on en est + quoi faire)
- `/sdd-help {n}` — guidance focalisée sur FEAT `{n}`
- `/sdd-help "comment X ?"` — réponse FAQ (matching mots-clés)

**Différence avec `/sdd-status`** : `/sdd-status` rend un tree ASCII
de l'état complet (snapshot). `/sdd-help` fait la même introspection
mais retourne **1-3 lignes de guidance actionnable** : la commande
suivante à lancer + son but. Pour les utilisateurs qui ne connaissent
pas les 13 commandes par cœur.

---

## STEP 1 — Détection du mode

| Argument | Mode |
|---|---|
| absent | **global** : scanner toutes les FEATs, identifier le plus gros gap |
| entier ≥ 1 | **focused** : focus sur FEAT `{n}`, suggérer prochaine étape |
| commence par `"` ou `'` ou contient un `?` | **FAQ** : matcher mots-clés contre §FAQ ci-dessous |

Si argument numérique mais aucune FEAT `{n}-*.md` trouvée →
```
Aucune FEAT {n} dans workspace/input/feats/.
Pour la créer : /feat-generate {NomDeLaFeature}
```

---

## STEP 2 — Collecte d'état déterministe (0 LLM)

```bash
# État global (FEATs, US, mockups, ARCH, DB, CLAUDE.md projets)
python .claude/python/sdd_scripts/sdd_state.py status [--feat-number {n}] --json

# Métriques QA (si FEAT donnée)
python .claude/python/sdd_scripts/query_console_db.py feat-stats --feat {n} 2>/dev/null
```

Latence cumulée ~100 ms. Échec script → fallback minimal : retourner
la commande `/sdd-status` et inviter Tech Lead à diagnostiquer.

---

## STEP 3 — Décision (arbre)

### 3.A — Mode global (aucune FEAT en argument)

Évaluer dans l'ordre, premier match gagne :

| Condition détectée | Recommandation (1L) |
|---|---|
| 0 FEAT dans `workspace/input/feats/` | `/feat-generate <Nom>` — démarrer la 1ʳᵉ FEAT (3-6 questions, ~2 min) |
| ≥ 1 FEAT, 0 US générée pour ≥ 1 FEAT | `/us-generate {n}` — découper la FEAT en User Stories testables |
| ≥ 1 FEAT avec US, aucun rapport readiness `workspace/output/.sys/.validation/{n}-readiness.md` | `/feat-validate {n}` — vérifier la maturité avant de coder (gate GO/NO-GO) |
| ≥ 1 FEAT validée, aucun projet sous `workspace/output/src/` | `/sdd-full {n}` — pipeline A→Z (arch + back + API gate + front + QA + review) |
| Projet bootstrappé mais ≥ 1 FEAT avec US `Status: Ready` sans code | `/dev-run {n}` — matérialiser le code (back → API gate → front) |
| Code généré, QA non exécutée (`coverage.json` absent) | `/qa-generate {n}` — générer tests + coverage + quality scan |
| QA OK, pas de `/sdd-review` récent (> 24h ou absent) | `/sdd-review {n}` — audit consolidé style Sonar |
| Toutes FEATs en 🟢 ✓ | `/sdd-status` — voir le récap, ou créer une nouvelle FEAT avec `/feat-generate` |

### 3.B — Mode focused (FEAT `{n}` donnée)

Évaluer dans l'ordre pour la FEAT cible :

| État FEAT `{n}` | Recommandation |
|---|---|
| FEAT existe mais 0 US sous `workspace/output/us/{n}-*.md` | `/us-generate {n}` |
| US présentes, readiness absent ou NO-GO | `/feat-validate {n}` (puis corriger §3 du rapport) |
| Readiness GO/WARN mais aucun code | `/dev-run {n}` (ou `/sdd-full {n}` pour pipeline complet) |
| Code OK, API Gate RED (`status: FAIL`) | Lire `workspace/output/qa/feat-{n}/api-tests.md` puis `/dev-backend {n}-{m}` sur l'US fautive |
| Code OK, coverage < seuil | `/qa-generate {n}` + ajouter tests dans `*.Tests/Unit/` |
| Code OK + QA 🟢, pas d'audit récent | `/sdd-review {n}` |
| Spec-compliance RED (Stage A gate échouée) | Lire `{n}-spec-compliance.md` §Findings + `/dev-{backend|frontend} {n}-{m}` sur AC non vérifié |
| Tout 🟢 | Rien à faire — `/sdd-status {n}` pour voir le récap |

### 3.C — Mode FAQ (question libre)

Matcher l'argument (lowercase) contre les mots-clés ci-dessous. Premier
match retourne sa réponse 2-4 lignes. Aucun match → suggérer `/sdd-help`
sans argument.

| Mots-clés | Réponse |
|---|---|
| `bootstrap`, `démarrer`, `commencer`, `nouveau projet`, `greenfield` | `python bootstrap.py` (interactif, 3-4 questions) ou `/sdd-bootstrap` depuis Claude Code. Crée `workspace/input/stack/stack.md` + arborescence complète. |
| `phase 0`, `discovery`, `vision`, `brief`, `avant les feats` | Phase 0 facultative (projets > 3 FEATs) : copier `.claude/templates/product-brief.template.md` ou `prfaq.template.md` dans `workspace/input/discovery/`. Définir vision + personas + KPIs + hypothèses fortes AVANT `/feat-generate`. |
| `prfaq`, `pr/faq`, `working backwards`, `amazon` | `.claude/templates/prfaq.template.md` — format Amazon "imagine le communiqué de presse comme si le produit était lancé aujourd'hui". Force le focus client avant d'écrire du code. |
| `product brief`, `personas`, `kpi business` | `.claude/templates/product-brief.template.md` — format classique 10 sections (vision, problème, personas, KPIs, hypothèses, risques). 1-3 pages max. |
| `brownfield`, `repo existant`, `scan`, `découvrir` | `/sdd-discover-stack` — scanne le repo et génère `stack.md.candidate` que tu peux promouvoir en `stack.md`. |
| `cost`, `coût`, `budget`, `token`, `usd` | Cap par défaut `MaxCostPerRun: 50` USD dans Project Config. Bypass one-shot : `SDD_DISABLE_COST_CAP=1`. Cf. `error-classification.md §1.2 [COST_CAP_EXCEEDED]`. |
| `cors`, `front + back ne se parlent pas`, `failed to fetch` | Cf. `library-and-stack.md §B` (CORS stack-aware). arch auto-injecte la config dev. En prod : `Cors:AllowedOrigins` env var. |
| `secrets`, `mot de passe`, `password`, `env var` | `stack.md` = SSoT unique pour `DB_PASSWORD`, `AUTH_JWT_SECRET`, `AZ_TENANTID`. Fichier gitignored. Code lit via `IConfiguration` / `@Value` / `Settings()` — **jamais** `process.env` direct (sinon `[SEC_ENV_VAR_FORBIDDEN]`). |
| `coverage`, `couverture`, `seuil` | `CoverageMin: 80` dans Project Config (obligatoire). `0` = désactivé. RED bloquant si `coverage_lines_pct < seuil`. |
| `gate`, `api gate`, `bloqué` | Cf. `build-and-loop.md §A`. Statuts canoniques v7.0.0 : PASS/WARN/FAIL/SKIPPED/INFRA_BLOCKED. Bypass strict : `GatedWorkflow: false` (déconseillé, audit-loggué). |
| `review`, `audit`, `sonar` | `/sdd-review {n}` — audit consolidé (quality + code-review + security + spec-compliance + arch-reviewer si full). Verdict 🟢/🟡/🔴 selon `ReviewFailOn`. |
| `pipeline poc`, `prototype`, `démo`, `minimaliste` | `/sdd-poc {n}` — pipeline minimaliste (skip US détaillées + QA + review + API gate). Pour validation rapide d'une idée. |
| `combo`, `stack`, `validé` | 13 combos SLA v7.0.0 (2 reference C1/C2 + 11 bench-validated C3-C13). Cf. `docs/validated-combos.md`. Bypass non-listé : `SDD_ALLOW_UNTESTED_COMBO=1`. |

---

## STEP 4 — Format de sortie

**Cible : 1-5 lignes total**, format direct :

```
SDDPro — {résumé d'état en 1L}

→ {commande suggérée}        # {but en 1L}
   (puis : {commande suivante optionnelle})
```

Exemples concrets :

```
SDDPro — 1 FEAT créée (Auth), 0 US générée.

→ /us-generate 1             # découper Auth en User Stories testables
```

```
SDDPro — FEAT 1 Auth : code généré, QA 🟢, jamais audité.

→ /sdd-review 1              # audit consolidé style Sonar (quality + code + security + spec)
```

```
SDDPro — FEAT 3 RetailAnalytics : spec-compliance gate RED (3 ACs non vérifiées).

→ Lire workspace/output/.sys/.validation/3-spec-compliance.md §Findings
→ /dev-backend 3-2           # corriger AC-2 (non implémenté côté API)
   (puis /dev-run 3 pour re-run two-stage)
```

---

## Règles de cette commande

- **Lecture seule.** Aucun Write/Edit, aucune invocation d'agent.
- **Délégation pure** vers scripts déterministes (`sdd_state.py`,
  `query_console_db.py`). Coût LLM ~0.
- **1 commande recommandée** à la fois (pas d'arbre touffu) — la
  prochaine étape **utile**, pas exhaustive.
- **Pas de Q/R utilisateur.** Sortie déterministe en 1 passe.
- **FAQ minimale** — pas un substitut à la doc complète
  (`@.claude/docs/`), juste les questions fréquentes.

---

## Chat Output Protocol

Applique `@.claude/rules/output-protocol.md`. Label `[ANALYSIS]`
(diagnostic read-only). Sortie 1 passe, pas de chunking. Le bloc
final de recommandation est considéré "rendu" — sans préfixe.
Erreurs : 1L `🔴 [ANALYSIS/FAIL] résumé`. Bypass `SDD_CHAT_VERBOSE=1`.

---

## Pointeurs

- `/sdd-status [{n}]` — pour le tree ASCII complet (diagnostic brut)
- `@.claude/CLAUDE.md §3` — liste exhaustive des 13 commandes user-facing
- `@.claude/docs/quickstart.md` — onboarding 10 min
- `@.claude/docs/cookbook.md` — recettes pratiques
