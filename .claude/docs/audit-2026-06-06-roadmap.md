# Audit CTO — Roadmap consolidée (2026-06-06)

> Document de tracking issu de l'audit CTO complet du 2026-06-06.
> Centralise les décisions, actions et arbitrages issus du rapport
> d'audit (cf. session conversation `/clear → audit complet`).
>
> Statut : 13 items closés en session + 8 items documentation tracés ici
> pour les vagues v7.1 / v7.2 / v8.0.
>
> **Important** : ce fichier est **un trace décisionnel**, pas une
> documentation utilisateur. Les utilisateurs lisent `docs/quickstart.md`
> ou `docs/cookbook.md`.

---

## Index

- §1 — Items closés en session (référence)
- §2 — M1 — CLAUDE.md downstream load weight (prune plan v7.1)
- §3 — M3 — Constitution serialization gate (déjà en place — documenté)
- §4 — M5 — `/sdd-full` refactor (sub-procedures, v7.1)
- §5 — M7 — Versioning reconciliation v6.10.4 LTS vs v7.0.0-alpha
- §6 — M8 — Headless SDK gap (roadmap v8.0)
- §7 — m1 — FR/EN language policy (canonical FR, EN i18n best-effort)
- §8 — m7 — `/sdd-discover-stack` revalidation gap
- §9 — m8 — Doc bilingue scope (mkdocs-static-i18n)

---

## §1. Items closés en session (audit 2026-06-06)

| Item | Sévérité | Description | Trace |
|---|---|---|---|
| C4 | 🔴 | Bash deny patterns durcis (obfuscation, downloaders, persistence) | `.claude/settings.json` |
| C5 | 🔴 | ENV bypass audit log JSONL | `sdd_hooks/block_env_bypass.py` |
| C2 | 🔴 | Validation tiers clarifiés (validated / bench / experimental / POC) | `.claude/CLAUDE.md §6` |
| C3 | 🔴 | 8 stacks 🟡 marqués `Support: ⚠ Non supporté commercialement` | `.claude/stacks/**/*.md` |
| C1 | 🔴 | Cache manifest extractor + helper Python (v7.0.x infra) | `sdd_admin/cache_manifest.py`, `sdd_lib/loader_yml.py` |
| M2 | 🟡 | 2 ADR filenames `HHmm` → `HHmmss` ; `mint_adr_filename` forcé dans agent prompts | git mv + `agents/constitutioner.md` |
| M4 | 🟡 | Build loop adaptive fallback Opus → Sonnet sur retry final | `agents/dev-*.md` + `config.base.yml` |
| M6 | 🟡 | Framework CoverageMin 60% configuré (cible 80% v7.1) | `python/pyproject.toml` |
| m2 | 🟢 | `node-react` POC-only confirmé partout | `.claude/stacks/fullstack/node-react.md` |
| m3 | 🟢 | Template linter (15 templates validés) | `sdd_admin/validate_templates.py` |
| m4 | 🟢 | Pricing freshness check (90j) + 6 tests | `sdd_lib/pricing.py`, `tests/test_pricing_freshness.py` |
| m5 | 🟢 | CI étendu (coverage, drift, ADR format, pricing) | `.github/workflows/sdd-ci.yml` |
| m6 | 🟢 | Statusline TTL cache (750ms) | `sdd_admin/statusline.py` |
| m9 | 🟢 | Console web POC-only banner explicite | `.claude/stacks/fullstack/node-react.md` |
| m10 | 🟢 | `InlineRulesDriftMode` config flag (warn → strict CI) | `config.base.yml` + CI |

**Total** : 15/23 items closés en session.

---

## §2. M1 — CLAUDE.md downstream load weight

### Diagnostic

`CLAUDE.md` slim entry point (150 lignes max, ADR `governance-major-prompts-trim`)
est respecté **localement**. Mais les `@.claude/rules/*.md`, `@.claude/docs/*.md`,
`@.claude/stacks/{cat}/*.md` référencés cumulent ~88K lignes potentiellement
chargées au runtime selon l'agent invoqué.

### Mesure (à compléter v7.1)

| Agent | Read mandatory total | Cible v7.1 |
|---|---:|---:|
| `dev-backend` | ~140 KB | ≤ 80 KB |
| `dev-frontend` | ~150 KB | ≤ 80 KB |
| `arch` | ~60 KB | ≤ 50 KB |
| `qa` | ~70 KB | ≤ 50 KB |

### Plan v7.1

1. **Hoister** les fragments `## Active …` du `stack.md` directement dans
   le CLAUDE.md projet (`workspace/output/src/{Project}/CLAUDE.md`) →
   éviter re-lecture des stacks bruts par dev-* en mode From Plan.
2. **Stack digest** : `arch` Phase A génère un `digest.md` ≤ 5 KB par
   stack actif, dev-* lit le digest au lieu du `.md` complet (~30 KB).
3. **Annotation cache_layer** sur les 11 agents restants (cf. §1 C1).
4. **Mesure réelle** post-implémentation via `context_budget.py` ledger.

### Status

🟡 **Tracé v7.1** — pas faisable en session (refacto multi-fichiers).

---

## §3. M3 — Constitution serialization gate

### Diagnostic

`ownership.md §2` sérialise déjà les writes sur `constitution.md` par
phase (po → arch → elicitor → constitutioner). Les dev-* sont exclus
explicitement. La spec est cohérente.

Le **gap réel** signalé par l'audit était sur les **ADRs** : nommage
timestamp seconde + `rand4` non implémenté → collisions possibles si
2 agents minent dans la même seconde.

### Résolution (closée — M2)

Le helper `mint_adr_filename` (`sdd_lib/adr_id.py`) est désormais imposé
par `agents/constitutioner.md` STEP 2 (audit M2 ci-dessus). Probabilité
de collision : 1 / 65 536 ≈ 0.0015 %. Pour la marge restante : le
caller doit utiliser `atomic_write_text` (déjà en place `sdd_lib/atomic_write.py`).

### Action documentation

Cette section formalise que **M3 est en réalité couvert par M2** —
pas de gate supplémentaire à ajouter.

### Status

🟢 **Closé via M2** (audit cross-référence).

---

## §4. M5 — `/sdd-full` refactor

### Diagnostic

`.claude/commands/sdd-full.md` = 795 lignes. `.claude/commands/dev-run.md`
= 1018 lignes. Toute évolution coûte 1 jour de re-lecture pour un
mainteneur. Anti-pattern « giant prompt ».

### Plan v7.1 (non-breaking)

Extraire 3 sous-procédures partagées dans `rules/` :

1. **`rules/preflight-pipeline.md`** (~100 lignes) :
   - resolve FEAT slug + glob disambiguation
   - validate `feat-validate` gate
   - resolve current `RunId` + console.db init
   - extraits depuis sdd-full STEP 1-3 + dev-run STEP 1-2
2. **`rules/orchestration-gates.md`** (~150 lignes) :
   - phase planner invocation (`phase_planner.py`)
   - cost cap pre-check
   - parallelism batching
   - extraits depuis sdd-full STEP 4-6 + dev-run STEP 5-7
3. **`rules/finalize-pipeline.md`** (~100 lignes) :
   - verdict aggregation
   - `/sdd-review` invocation
   - `[DONE]` emission protocol
   - extraits depuis sdd-full STEP 7-9 + dev-run STEP 8-10

### Status

🟡 **Tracé v7.1** — réduction estimée -40 % (1813 lignes → ~1100).

---

## §5. M7 — Versioning reconciliation

### État actuel (2026-06-06)

| Branche | Version | Status | Use case |
|---|---|---|---|
| `main` | v6.10.4-LTS | **FREEZE 2026-06-18** | Production stable (clients existants) |
| `next` | v7.0.0-alpha | Active development | Tech preview + audit feedback |

### Risque commercial

Vendre v7.0.0-alpha en l'état pendant la fenêtre v6 freeze = ambiguïté
contractuelle. Si client signe sur la base de docs v7, mais que le
support se fait sur v6 LTS, gap d'attentes garanti.

### Plan

1. **Avant FREEZE lift (2026-06-18)** : geler la surface DSL v7.0.0
   (agents/commands/rules/stacks). Aucun nouveau breaking change.
2. **Tag v7.0.0 GA** = la branche `next` + tous les fixes audit
   2026-06-06 (15 items closés ci-dessus).
3. **`v7-LTS` policy** : décider si v7.0.0 devient le nouveau LTS
   ou si on continue à maintenir v6.10.4 6 mois.
4. **Page `/versioning`** publique avec matrice claire `support
   matrix v6/v7 × FEATs/stacks/SLAs`.

### Status

🟡 **Action commerciale CTO** — pas un fix code.

---

## §6. M8 — Headless SDK gap

### Diagnostic

100 % du framework couplé au Claude Code CLI :
- Slash commands invocables uniquement via Claude Code
- Sub-agents = primitive Claude Code
- Hooks = primitive Claude Code
- Sub-agent matchers, PreToolUse/PostToolUse = Claude Code-specific

### Impact client B2B

Un client qui veut intégrer SDD_Pro dans :
- CI/CD (GitHub Actions, GitLab CI, Jenkins) → ❌ impossible
- IDE custom (VSCode extension non Claude Code, JetBrains) → ❌ impossible
- Cron / scheduled jobs → ❌ impossible (requires Claude Code REPL)
- Pipeline d'auto-déploiement (Vercel, Render, Fly.io) → ❌ impossible

### Plan v8.0

1. Extraire `sdd-core` Python package (commands + hooks logic, sans
   Claude Code CLI dependency).
2. Wrapper Anthropic SDK direct (`anthropic` package, message API).
3. Agent spawning via `messages.create()` programmatique.
4. Hooks invoqués comme fonctions Python sync.
5. CLI alternatif : `sdd-pro feat-generate Auth` (pipx install).

### Effort estimé

3-6 personne-mois. Pas avant v8.0 (Q1 2027).

### Status

🟡 **Tracé v8.0** — différenciateur commercial majeur (déverrouille
CI/CD, multi-tenant, scheduled).

---

## §7. m1 — FR/EN language policy

### Décision SDD_Pro (canonique)

| Surface | Langue | Justification |
|---|---|---|
| Identifiants techniques (`US`, `AC`, `SFD`, `FD`, `BR`, `ADR`, classes `[STACK_LIBRARY_MISSING]`) | **EN** | Universel agile + parsing scripts |
| Code généré (C#, Razor, TS, Kotlin) | **EN** | Convention industrie |
| Mockups HTML libellés métier | **FR** | Métier francophone (cible initiale) |
| Docs utilisateur (CLAUDE.md, docs/, rules/, prompts agents) | **FR canonique** | Tech Lead francophone (cible v6.x-v7.x) |
| **Docs i18n** (mkdocs-static-i18n) | EN traduit | best-effort, ne casse pas si gap |
| Templates `risks-assumptions`, `runbook`, `postmortem`, `feat` | **FR canonique** avec patterns EN fallback | template linter v7.0.0+ accepte les 2 |

### Engagement support v7.0.0

- **FR** : 100 % couverture, support officiel.
- **EN** : best-effort, gaps documentés dans `docs/known-gaps-i18n.md` (v7.1).

### Status

🟢 **Closé** (cette section = decision officielle).

---

## §8. m7 — `/sdd-discover-stack` revalidation gap

### Diagnostic

`/sdd-discover-stack` génère `workspace/input/stack/stack.md.candidate`
sur projet brownfield (scan manifests existants). Mais **aucun pipeline
de re-validation auto** — le mainteneur doit copier `.candidate` → `stack.md`
manuellement, puis lancer `/sdd-full` qui peut découvrir d'autres gaps.

### Plan v7.1

1. `--auto-validate` flag : après scan, exécute `validate_stack_combo.py`
   sur la candidate ET émet un rapport `discover-validation.md`.
2. `--apply` flag : si validation 🟢, copie candidate → stack.md
   automatiquement (audit-loggué).
3. Hook `discover-followup` qui suggère la prochaine étape selon le
   verdict (Tech Lead arbitre).

### Status

🟡 **Tracé v7.1** — quality-of-life amélioration.

---

## §9. m8 — Doc bilingue scope

### Périmètre actuel (commit `4e8f98e`, mkdocs-static-i18n)

| Fichier | FR | EN | Source de vérité |
|---|:---:|:---:|---|
| `docs/README.md` | ✅ | `README.en.md` | FR canonique |
| `docs/getting-started.md` | ✅ | `getting-started.en.md` | FR canonique |
| `docs/quickstart.md` | ✅ | ❌ | FR uniquement (gap) |
| `docs/cookbook.md` | ✅ | ❌ | FR uniquement (gap) |
| `docs/architecture.md` | ✅ | ❌ | FR uniquement (gap) |
| `docs/CHANGELOG.md` | ✅ | ❌ | FR uniquement (intentional) |
| `docs/MIGRATION.md` | ✅ | ❌ | FR uniquement (intentional) |
| Templates `.md` | bilingue inline | bilingue inline | template linter accepte les 2 (audit m3) |
| Stacks `.md` | mix FR/EN | mix FR/EN | OK |
| Agents/Rules `.md` | FR canonique | ❌ | FR uniquement (intentional) |

### Plan v7.1 EN coverage

Priorité : `quickstart.md` + `cookbook.md` + `architecture.md` traduits EN.
Reste FR-only par design (CHANGELOG/MIGRATION sont historiques internes).

### Status

🟡 **Tracé v7.1** — i18n best-effort.

---

## §10. Synthèse audit

| Sévérité | Total | Closés | Tracés v7.1+ |
|---|---:|---:|---:|
| 🔴 Critique | 5 | 5 | 0 |
| 🟡 Majeur | 8 | 4 | 4 (M1, M5, M7, M8) |
| 🟢 Mineur | 10 | 10 | 0 |
| **Total** | **23** | **19** | **4** |

**Verdict** : 83 % closés en session ; les 4 majeurs résiduels (M1, M5,
M7, M8) sont des refactos / décisions commerciales nécessitant un sprint
dédié.

### Prochaines actions Tech Lead

1. Review + accepter les 19 fixes via `git diff` + commit
2. Décider M7 (geler v7.0.0 GA ou prolonger v6.10.4-LTS)
3. Planifier sprint v7.1 (M1 cache + M5 refactor + m7 + m8)
4. Roadmap v8.0 = M8 headless SDK (différenciateur commercial)
