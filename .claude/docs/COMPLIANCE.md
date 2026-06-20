# Compliance & Sécurité — SDD_Pro v7.0.0 GA

> Document compliance pour DSI / RSSI / acheteur grand compte (2026-06-07).
> Couvre RGPD, data residency, sécurité, audit trail, certifications.

---

## 1. Modèle d'exécution

SDD_Pro est un **framework local self-hosted** qui s'exécute sur la machine
du développeur via Claude Code. **Aucun service SaaS SDD_Pro n'existe** —
le framework est constitué de :

- Fichiers `.md` (agents, commandes, règles, stacks) — read by LLM
- Scripts Python locaux (`sdd_scripts/`, `sdd_hooks/`, `sdd_admin/`) — déterministes
- `console.db` SQLite local (`workspace/output/db/`) — télémétrie locale

**Le seul flux réseau** est celui de Claude Code vers l'API Anthropic (le LLM)
sous le contrôle direct de l'utilisateur (clé API ou compte org Anthropic).

```
┌──────────────────────┐       ┌──────────────────────┐
│ Poste Dev / CI       │──────▶│ API Anthropic        │
│ (Claude Code +       │◀──────│ (Claude Opus 4.7 /   │
│  SDD_Pro framework)  │ HTTPS │  Sonnet 4.6)         │
└──────────────────────┘       └──────────────────────┘
       │
       │ Reads/Writes
       ▼
┌──────────────────────┐
│ workspace/ local     │  ◀── Aucun upload externe
│ (FEATs, US, src,     │      hors API Anthropic
│  console.db)         │
└──────────────────────┘
```

---

## 2. RGPD / GDPR

### 2.1 Données traitées par SDD_Pro lui-même

Aucune. SDD_Pro est un framework de **génération de code** — il ne traite
pas de données personnelles end-user. Les artefacts produits :

- `workspace/input/feats/` — spécifications fonctionnelles (rédigées par le
  Tech Lead, contenu sous contrôle du client).
- `workspace/output/src/` — code source généré.
- `workspace/output/db/console.db` — télémétrie technique (tokens, gates,
  cost) — **aucune PII**.

### 2.2 Données envoyées à l'API Anthropic

L'API Anthropic reçoit **le contenu de vos prompts** (FEATs, US, code lu en
contexte). Si vos FEATs contiennent des données personnelles :
- Anthropic est **DPO européen** (sous-traitant RGPD).
- Anthropic ne réentraîne pas les modèles sur les API calls par défaut.
- Cf. [Anthropic Data Privacy](https://www.anthropic.com/legal/privacy).

### 2.3 Recommandation Tech Lead

**Ne mettez pas de données personnelles réelles dans vos FEATs.** Utilisez
des données synthétiques (Faker, Mockaroo). SDD_Pro génère du code de
**production** ; les données de test relèvent du QA, pas du framework.

---

## 3. Data residency

| Composant | Où sont les données ? |
|---|---|
| Framework SDD_Pro | 100% local (`.claude/`, `workspace/`) |
| Code généré | 100% local (`workspace/output/src/`) |
| `console.db` télémétrie | 100% local |
| Logs audit | 100% local (`workspace/output/.sys/.audit/`) |
| Prompts LLM | Anthropic (datacenters US — cf. [Anthropic Trust Center](https://trust.anthropic.com/)) |

**Pour clients européens stricts** : Anthropic propose un endpoint Vertex AI
(Google Cloud) ou Bedrock (AWS) qui peut être configuré en région EU. Cf.
documentation Claude Code pour le routing.

---

## 4. Sécurité du framework

### 4.1 Surface d'attaque restreinte

- **Aucun serveur exposé** — pas de port ouvert, pas de socket TCP.
- **Aucun secret hardcodé** dans les sources framework (scan
  `security_patterns.yaml` + classe `[SEC_SECRET_HARDCODED]` hard-blocking).
- **Hooks bloquants** sur Bash dangereux (deny `curl http`, `wget`,
  `Invoke-WebRequest`, `certutil -urlcache`, `bitsadmin`, encoded
  PowerShell, etc. — cf. `settings.json` deny rules).

### 4.2 Hardening v7.0.0 (audit P0-security 2026-06-05)

| Mesure | Statut |
|---|:---:|
| Deny rules Bash anti-exfiltration | ✅ 100+ patterns |
| Deny rules anti-bypass `SDD_ALLOW_*` env vars | ✅ |
| Hook `block_env_bypass` (case-insensitive) | ✅ |
| Hook `preflight_glob_scope` (anti-token-explosion) | ✅ |
| Hook `validate_stack_consistency` (anti-multistack) | ✅ |
| `defaultMode: default` (prompt sur tools hors allowlist) | ✅ |
| Pre-write lint (forbidden patterns Kotlin `!!`, Vue raw HTML…) | ✅ |
| Pre-commit hooks anti-secrets | ⚠️ à wirer par l'équipe utilisatrice |

### 4.3 OWASP Top 10 (code généré)

SDD_Pro inclut un **`security-reviewer` agent** (Sonnet 4.6) qui scanne le
code généré contre les 23 classes `[SEC_*]` mappées OWASP/CWE :

- Hard-blocking : `[SEC_SQL_INJECTION]` (CWE-89), `[SEC_COMMAND_INJECTION]`
  (CWE-78), `[SEC_BROKEN_AUTHZ]` (CWE-862), `[SEC_BROKEN_AUTHN]` (CWE-287),
  `[SEC_DESERIALIZATION_UNSAFE]` (CWE-502), `[SEC_JWT_MISCONFIG]` (CWE-1004),
  `[SEC_SSRF_RISK]` (CWE-918), `[SEC_SECRET_HARDCODED]` (CWE-798).
- Verdict 🟢/🟡/🔴 selon `SecurityFailOn` du Project Config.

Cf. `agents/security-reviewer.md` et `error-classification.md §1.11`.

---

## 5. Audit trail

### 5.1 `console.db` (SQLite local)

Chaque run de pipeline persiste :
- Table `runs` : run_id, timestamp, FEAT, commande, durée totale
- Table `events` : phase, agent, status, cost USD, tokens
- Table `validation_reports` : verdicts des 5 reviewers (code, security,
  spec, arch, adversarial)
- Table `qa_coverage`, `qa_quality`, `qa_security`, etc.

Le Tech Lead peut tracer **tout l'historique technique** d'un projet sans
dépendance externe.

### 5.2 ADRs versionnés

`workspace/output/.sys/.context/adrs/ADR-{YYYYMMDDTHHmmss}-{rand4}-{slug}.md`
tracent les décisions structurantes (stack choisi, pattern archi, DB
strategy, exceptions runtime STS, etc.). Format Context / Decision /
Consequences inspiré de Michael Nygard.

### 5.3 Logs audit-loggués

`workspace/output/.sys/.audit/` :
- `legacy-parallel.log` — usage du mode legacy `GatedWorkflow: false`
- bypass `SDD_ALLOW_*` env vars tracés
- bypass `--force`/`--no-validate`/`--no-plan-on-warn` cumulés

---

## 6. Certifications

### 6.1 Anthropic (LLM provider)

- **SOC 2 Type II** : ✅ Anthropic certifié (cf. Trust Center)
- **ISO 27001** : ✅ Anthropic certifié
- **HIPAA** : ✅ via BAA Anthropic (sur demande)
- **GDPR DPA** : ✅ disponible

### 6.2 SDD_Pro lui-même

Le framework étant **local self-hosted sans serveur**, il n'est pas
certifiable en tant que tel. La certification du projet client utilisant
SDD_Pro relève du client (le code généré entre dans le périmètre des
certifications client habituelles).

**Recommandation** : intégrer SDD_Pro dans le pipeline CI/CD client
existant (déjà certifié) plutôt que comme service externe.

---

## 7. Gestion des secrets

### 7.1 Pattern B obligatoire (`stack.md` comme SSoT)

Les secrets de configuration (DB password, JWT secret, Azure tenant…) sont
déclarés en clair dans `workspace/input/stack/stack.md`, fichier
**`.gitignored`** par défaut. L'agent `arch` les propage dans la config
native du projet généré (`appsettings.json`, `application.yml`,
`config.toml`, etc.).

**Anti-pattern bloqué par hook** : `[SEC_ENV_VAR_FORBIDDEN]` interdit au
code applicatif généré de lire les env vars directement (`process.env.DB_*`,
`os.environ["DB_*"]`, etc.) — il doit lire la config native.

### 7.2 CI/CD

Pour le CI/CD client, les secrets sortent du périmètre SDD_Pro. Utiliser
GitHub Secrets, GitLab CI Variables, Azure Key Vault, AWS Secrets Manager
selon votre stack.

---

## 8. Réponse aux questions DSI courantes

### Q1 — "Le code généré est-il propriété du client ?"
Oui. SDD_Pro est un framework local sans cloud — vous gardez 100% du code
généré. Aucun upload externe hors prompts API Anthropic.

### Q2 — "Que se passe-t-il si Anthropic disparaît ?"
Le framework devient inutilisable (mono-IDE Claude Code). **Mitigation** :
les artefacts produits (code, ADRs, tests, console.db) restent
réutilisables. Une roadmap v8 multi-LLM est envisageable mais non
engagée.

### Q3 — "Y a-t-il un risque de fuite de propriété intellectuelle via le LLM ?"
Anthropic ne réentraîne pas sur les API calls par défaut (cf. Privacy
Policy). **Recommandation supplémentaire** : ne pas inclure d'algorithme
propriétaire critique dans les FEATs envoyées au LLM. SDD_Pro est conçu
pour générer du **code d'application standard** (CRUD, endpoints, UI), pas
des algorithmes core-business.

### Q4 — "Compatible RGPD pour un projet client ?"
Oui, à condition que :
- Les FEATs ne contiennent pas de données personnelles réelles
  (utiliser des données synthétiques pour les exemples de test).
- Le DPA Anthropic soit signé si vous traitez de la PII en prompt.

### Q5 — "Quelle est la politique de vulnérabilité ?"
Le scan CVE est intégré dans `arch` Phase A (`dotnet list package
--vulnerable`, `npm audit`, `pip-audit`, `mvn dependency:check`). Classe
`[STACK_LIBRARY_VULNERABLE]` bloquante si CVE ≥ moderate sur une lib §2.4
active. Les libs sont pinnées en versions LTS (cf. `library-and-stack.md §0`).

---

## 9. Liens

- `@.claude/docs/SLA.md` — engagement support
- `@.claude/docs/KNOWN-LIMITATIONS.md` — limites connues
- `@.claude/rules/library-and-stack.md` — gestion libs + LTS + CVE
- `@.claude/rules/error-classification.md §1.11` — classes `[SEC_*]` OWASP
- [Anthropic Trust Center](https://trust.anthropic.com/)
- [Anthropic Privacy Policy](https://www.anthropic.com/legal/privacy)

---

*Document maintenu à chaque release MAJOR. Référencé par RFP / Security
Questionnaire / DSI onboarding.*
