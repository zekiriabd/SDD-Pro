# Rules Digest — SDD_Pro v6.10.5

> **Compiled digest** extrait des 11 rules `.claude/rules/*.md` (~2 840 L source → ~280 L digest = compression ×10).
> Source de vérité : `.claude/rules/*.md`. Régénération recommandée à chaque MAJ rule (`make digest` post-v7).
> Généré : 2026-05-19.

---

## 1. Anti-derive (8 interdictions cross-agent)

1. Ne JAMAIS lire d'autres US, ni les FEATs.
2. Ne JAMAIS écrire de fichier hors plan inline ou hors mapping du stack actif.
3. Ne JAMAIS introduire une lib non déclarée dans `.claude/stacks/{cat}/*.libs.json` actifs (§2.4.a CORE ou §2.4.b ON-DEMAND triggered).
4. Ne JAMAIS générer de tests, fixtures, mocks, fichiers de test (QA hors scope, propriété agent `qa`).
5. Ne JAMAIS modifier l'US (read-only) ni le mockup HTML (lecture passive).
6. Ne JAMAIS poser de question à l'utilisateur (agents autonomes).
7. Si ambiguïté irrécupérable → STOP + ERROR 3 lignes (ERROR/CAUSE/FIX avec préfixe `[CLASS]`).
8. Pas de TODO/FIXME/stub/placeholder/secret hardcodé.

---

## 2. Format ERROR canonique (3 lignes obligatoires)

**Chat** (1L succès, 2L max erreur) :
```
🔴 {agent} {n}-{m} — {résumé}
CAUSE: [{CLASS}] {détail 1L} → {pointer fichier rapport}
```

**Rapport** (3 lignes structurées) :
```
ERROR: {feat/us/task or pipeline-step} failed
CAUSE: [{CLASS}] {détail 1L}
FIX: {action 1L}
```

---

## 3. Classes d'erreur (taxonomie §1 — codes effectivement émis)

| Famille | Préfixes principaux | Action build_loop |
|---|---|---|
| Runtime | `[NETWORK]`, `[AUTH]`, `[PERMISSION]`, `[NOT_FOUND]`, `[TIMEOUT]`, `[DISK]`, `[ENV_MISSING]`, `[ENV_PROPAGATION_FAILED]` | fail-fast |
| Pipeline | `[STACK_MALFORMED]`, `[SCHEMA_MISMATCH]`, `[FEAT_REJECTED]`, `[FEAT_NOT_FOUND]`, `[GRANULARITY_VIOLATION]`, `[TRACEABILITY_GAP]`, `[READINESS_NO_GO]`, `[PLAN_*]` (12 codes) | fail-fast (sauf retry compatibles) |
| Contrat | `[PRESERVES_VIOLATED]`, `[ADDS_VIOLATED]`, `[LAYER_VIOLATION]`, `[FILE_OWNERSHIP*]`, `[STATUS_FLIP_FAILED]`, `[US_*]` (8 codes), `[BREAKING_CLEANUP_FAILED]` | fail-fast |
| Build | `[BUILD_CORRECTIBLE]` (itère), `[BUILD_BLOCKING]` (fail-fast), `[BUILD_LOOP_EXHAUSTED]` (terminal), `[DEP_MISSING]`, `[CIRCULAR_DEP]` | mixte |
| Anti-derive | `[DERIVE_VIOLATION]`, `[OPTIMIZATION_PROACTIVE]`, `[UNDECLARED_DECISION]`, `[STACK_LIBRARY_MISSING]`, `[STACK_LIBRARY_VULNERABLE]`, `[STACK_RUNTIME_NOT_LTS]`, `[RUNTIME_STS_EXCEPTION]`, `[STACK_EXPERIMENTAL]` | fail-fast |
| UI | `[UI_FIDELITY_GAP]`, `[UI_TOKEN_VIOLATION]`, `[FRONTEND_BACKEND_CONTRACT_GAP]` | narrow retry / fail-fast |
| QA | `[QA_TEST_FAILED]`, `[QA_COVERAGE_GAP]`, `[QA_FRAMEWORK_MISSING]`, `[QA_INIT_FAILED]`, `[QA_TEST_INVALID]`, `[QA_OUTPUT_INVALID]`, `[QA_PRECONDITION_FAILED]`, `[QA_OWNERSHIP_VIOLATION]`, `[API_GATE_RED]` | fail-fast |
| Parallélisme | `[LIBNAME_LOCK_HELD]`, `[LIBNAME_SIGNATURE_CONFLICT]`, `[LOCK_HELD]` | fail-fast |
| Auditors | `[A11Y_*]` (10), `[REVIEW_*]` (11), `[SEC_*]` (21), `[PERF_*]` (16), `[SPEC_*]` (6), `[ARCH_*]` (6) | rapport seul |
| Discover/Checkpoint/Config | `[DISCOVER_*]` (7), `[CHECKPOINT_*]` (3), `[CONFIG_SECURITY_DOWNGRADE]`, `[PROFILE_*]`, `[DRIFT_SUSPECTED]` | informationnel ou bloquant ponctuel |

**Règle mentale** : "Pas de bloc ERROR sans préfixe `[CLASS]`. Si rien ne matche → `[UNKNOWN]`."

---

## 4. File ownership matrix (sérialisation parallèle)

| Famille | Owner exclusif | Mode |
|---|---|---|
| `src/{BackendName}/**` | `dev-backend` (post-arch) | Edit-augment exclusif |
| `src/{AppName}/**` (alias `FrontendName`) | `dev-frontend` | Edit-augment exclusif |
| `src/{LibName}/**` (DTO/Models partagés) | `arch` create + lock `.locks/{Entity}.lock` (TTL 30 min) | First-write wins + lock |
| `src/{Project}/CLAUDE.md` | `arch` (création) ; `dev-*` (Edit narrow RESOLVED §6.bis) | Create + Edit-hash exclusif |
| `.sys/.context/constitution.md` | séquentiel : `/feat-generate` → `po` (§3) → `arch` (§4, §6) → `elicitor` (§7) | Append-only par section |
| `.sys/.context/adrs/ADR-*.md` | multi-writers | Numérotation atomique timestamp `ADR-{YYYYMMDDTHHmmss}-{slug}.md` |
| `.sys/.context/adrs/INDEX.md` | `dashboard` (depuis 2026-05-08) ; `arch` peut aussi écrire | Create overwrite (idempotent) |
| `output/us/{n}-{m}-*.md` | `po` | Create exclusif |
| `input/ui/{n}-{m}-*.html` | UX Designer humain | Read-only stricte côté agents |
| `output/plans/{n}-{m}-*.{back,front}.md` | `dev-*` mode `:plan` ou `/dev-plan` | Create exclusif |
| `console/status.json` | console + `/sdd-full` | Atomic write + `.status.lock` (TTL 10s, retry 5×) |

**Anti-pattern §1.bis** : projet front jamais imbriqué dans projet back (et inverse). `{AppName}` et `{BackendName}` vivent au même niveau sous `workspace/output/src/`.

---

## 5. Backend-first gated workflow

```
arch + DB → dev-backend ALL US → QA API Gate (in-memory) → dev-frontend ALL US
                                       │
                                       └─ 🔴 RED → STOP, humain corrige et relance
```

Tests API Gate (in-memory only, jamais DB réelle) :
- .NET : `WebApplicationFactory` + EF Core InMemory
- Node : `supertest` + Prisma SQLite `:memory:`
- Python : `httpx.AsyncClient` + SQLAlchemy SQLite `:memory:`
- Kotlin : `MockMvc` + `@DataJpaTest` H2

Critère : `gate_passed = (failed == 0) AND (total >= 2 × N_endpoints)`. Default 2 cas par endpoint (1 happy + 1 négatif).

---

## 6. QA coverage (seuil 80 %)

- `CoverageMin: int 0-100` **obligatoire** dans `## Project Config` (depuis v6.10.1).
- `coverage_lines_pct < CoverageMin` → `[QA_COVERAGE_GAP]` **RED bloquant** (depuis v6.1 hardening).
- Bypass explicite : baisser `CoverageMin` ou mettre `0` dans `## Project Config` (tracé git blame). JAMAIS via `--force`.
- Précédence : `[QA_TEST_FAILED] > [QA_COVERAGE_GAP]`.

---

## 7. CORS (cross-origin SPA ↔ backend)

Obligatoire dès qu'une SPA est servie sur origin différente du backend. Patterns inlinés par stack dans §2 de `rules/cors.md`. Auto-injection arch STEP 4.5.6 : propage origin frontend dev (`localhost:5173`/`4200`/`5097`) vers config backend allowlist.

---

## 8. UI tokens (anti-hex-hardcode)

Toute couleur/espacement/rayon/typo passe par CSS variables (`var(--primary)`, etc.). Jamais de hex inline dans composants. Détection STEP build dev-frontend via grep `#[0-9a-fA-F]{6}` hors fichier tokens → `[UI_TOKEN_VIOLATION]`.

---

## 9. US granularity (1-6 cap)

- Min 1, cible 1-3, WARN 4-6, hard cap 6 US par FEAT.
- > 6 → STOP + ERROR `[GRANULARITY_VIOLATION]`.
- Traçabilité 100 % : chaque SFD/BR/AC/FD couvert par ≥ 1 US (champ `Covers`).

---

## 10. Source-first discipline

**Tout bug code = trou dans une source MD** (FEAT, US, plan, stack, rule). Workflow correction :
1. Identifier source MD manquante
2. Patcher la source AVANT le code
3. Vérifier propagation cross-source

Patcher le code avant les MD = drift permanent. Anti-pattern "fix code-only récurrent" sur ≥ 2 projets → STOP, exiger patch source d'abord.

---

## 11. Stack completeness (§2.4 catalogue)

- Toute lib utilisée DOIT figurer §2.4.a (CORE) ou §2.4.b (ON-DEMAND triggered) du stack `.libs.json` actif.
- Absent → STOP + ERROR `[STACK_LIBRARY_MISSING]`.
- Runtime LTS only : .NET 10, Node 22, Java 21, Python 3.12, Kotlin 2.1. STS/prerelease → ADR `runtime-sts-exception` requis.
- CVE check post-install par `arch` : `dotnet list --vulnerable`, `npm audit`, `pip-audit`, `mvn dependency:check`.

---

*Digest régénérable : invoquer un futur `make rules-digest` ou script `compile_digests.py` (v7) lit les sources et reconstruit ce fichier.*
