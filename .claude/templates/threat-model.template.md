# Threat Model — FEAT {n}-{Name}

> **Livrable humain** (introduit en v7.0.0). Remplace l'ancien mode
> `security-reviewer --mode threat-model` (retiré). Instancier en phase
> **pré-`/arch-init`** une fois la FEAT cadrée et les US générées, puis
> joindre au dossier de la FEAT (suggéré : `workspace/output/.sys/.threat-models/{n}-threat-model.md`).
>
> Le temps de remplissage cible est **15-30 min** pour une FEAT de
> taille moyenne. Si > 1h, c'est probablement que la FEAT est trop
> large — splitter avant de continuer.

---

## Méta

| Champ | Valeur |
|---|---|
| FEAT | `{n}-{Name}` |
| Date | `YYYY-MM-DD` |
| Auteur(s) | _Nom + rôle_ |
| Reviewers | _Nom + rôle (≥ 1 obligatoire en équipe ≥ 2)_ |
| Statut | Draft / In review / Approved / Superseded |
| Stack actif (lien `stack.md`) | _Backend / Frontend / UI / Auth / DB_ |
| Niveau de criticité projet | Standard / Élevé / Critique |

---

## 1. Assets à protéger

> Lister chaque actif (data, secret, capability) avec sa **classification** et son **propriétaire**. Sources recommandées : constitution §3-§4-§7, FEAT §Business Rules, schema.json.

| ID | Asset | Type | Classification | Propriétaire | Lieu de stockage |
|---|---|---|---|---|---|
| A-1 | _ex. : Liste des contacts_ | data | Sensitive (PII) | Métier RH | `workspace/output/db/console.db` table `contacts` |
| A-2 | _ex. : JWT signing key_ | secret | Critical | DevOps | env var `JWT_SECRET` (KeyVault) |
| A-3 | _ex. : Session cookie_ | credential | Sensitive | Backend | HttpOnly cookie, SameSite=Lax |
| A-4 | _ex. : Endpoint export Excel_ | capability | Standard | Backend | `POST /api/contacts/export` |

**Classifications** : `Public` / `Internal` / `Sensitive` / `Critical`.

---

## 2. Acteurs (modèle simplifié)

> Tirer de `constitution.md §3 Acteurs` + FEAT §Actors. Inclure aussi les acteurs **hostiles** modélisés.

| ID | Acteur | Légitime ? | Capabilities supposées |
|---|---|:---:|---|
| AC-1 | _Utilisateur métier_ | ✅ | Lire ses propres données, exporter |
| AC-2 | _Admin RH_ | ✅ | Lire toutes les données, gérer comptes |
| AC-3 | _Système externe (Azure AD)_ | ✅ | Émettre JWT, fédération identité |
| AC-4 | _Attaquant externe non authentifié_ | ❌ | Scan ports, fuzzing endpoints, brute force login |
| AC-5 | _Attaquant interne (compte légitime compromis)_ | ❌ | Privilege escalation, exfiltration, deletion |
| AC-6 | _Insider malveillant (admin)_ | ❌ | Accès logique légitime, intention malveillante |

---

## 3. Surfaces d'attaque

> Tirer du plan technique `{n}-{m}-*.{back,front}.md` (depuis 2026-06-01) ou des ACs de chaque US si plan absent.

| ID | Surface | Description | Acteurs impactants |
|---|---|---|---|
| S-1 | HTTP endpoints publics | `POST /api/login`, `GET /api/contacts`, `POST /api/export` | AC-4, AC-5 |
| S-2 | Formulaires upload | Import CSV `POST /api/contacts/import` | AC-4, AC-5 |
| S-3 | Query params utilisateur | `?search=`, `?filter=` (risque injection) | AC-4 |
| S-4 | Cookies / Storage frontend | Session token, JWT refresh | AC-4 (XSS) |
| S-5 | Connexion DB | Connection string, credentials | AC-5, AC-6 |
| S-6 | Logs (rotation, archivage) | Risque de fuite PII / credentials | AC-6 |

---

## 4. Threats (STRIDE light)

> Pour chaque combinaison (Asset × Surface × Acteur), évaluer les 6 catégories STRIDE et estimer **Likelihood × Impact**.

| ID | Asset | Surface | Acteur | Catégorie STRIDE | Description du threat | Likelihood | Impact | Risque |
|---|---|---|---|---|---|:---:|:---:|:---:|
| T-1 | A-2 (JWT key) | S-5 | AC-5/AC-6 | **S**poofing | Vol clé via accès DB → forgery JWT | Low | Critical | 🔴 |
| T-2 | A-1 (contacts) | S-3 | AC-4 | **T**ampering | SQL injection via `?filter=` | Medium | High | 🔴 |
| T-3 | A-1 (contacts) | S-1 | AC-5 | **I**nfo disclosure | IDOR `GET /api/contacts/{id}` sans check ownership | Medium | High | 🔴 |
| T-4 | A-3 (session) | S-4 | AC-4 | **T**ampering | XSS → vol token via DOM | Low | High | 🟡 |
| T-5 | A-4 (export) | S-1 | AC-4 | **D**oS | Export 1M lignes sans pagination → OOM backend | Medium | Medium | 🟡 |
| T-6 | A-1 (contacts) | S-6 | AC-6 | **I**nfo disclosure | Logs contiennent PII en plaintext | High | Medium | 🟡 |
| T-7 | All | S-1 | AC-4 | **R**epudiation | Logs absents → impossible de prouver qui a fait quoi | Low | Medium | 🟢 |
| T-8 | A-4 (export) | S-1 | AC-5 | **E**levation | Endpoint admin accessible sans `[Authorize(Roles="Admin")]` | Low | High | 🟡 |

**Échelle Likelihood** : `Low` (rare, exploit complexe) / `Medium` (réaliste) / `High` (probable).
**Échelle Impact** : `Low` (gêne) / `Medium` (incident) / `High` (perte data ou compliance) / `Critical` (compromise totale).
**Code risque** : 🔴 RED (action obligatoire avant prod) / 🟡 YELLOW (mitigation requise sprint+1) / 🟢 GREEN (résiduel acceptable, monitorer).

---

## 5. Controls recommandés

> Pour chaque threat 🔴 et 🟡, **DOIT** avoir au moins un control mappé. Préférer les controls déjà présents dans le stack actif (rules + stacks/auth/*).

| Threat | Control | Mapping stack / rule | Owner | Statut |
|---|---|---|---|---|
| T-1 | KeyVault rotation 90j + audit log accès clé | `stacks/auth/azure-ad.md §5.2.7.5` | DevOps | Planifié S+2 |
| T-2 | Parameterized queries obligatoires + EF Core LINQ (pas de raw SQL utilisateur) | `rules/error-classification.md [SEC_SQL_INJECTION]` | dev-backend | Auto (stack) |
| T-3 | Filter `.Where(c => c.OwnerId == userId)` sur tous les endpoints listant/single | `rules/error-classification.md [SEC_IDOR]` | dev-backend | À implémenter US-1-3 |
| T-4 | CSP strict + cookies HttpOnly + sanitize all user-rendered text | `rules/error-classification.md [SEC_XSS_RISK] [SEC_COOKIE_INSECURE]` | dev-frontend | Auto (DS shadcn escape) |
| T-5 | Pagination forcée serveur (`take ≤ 1000`), export → background job + email résultat | FEAT §AC-X | dev-backend | À implémenter US-1-N |
| T-6 | Masquer email/phone dans logs via Serilog destructuring + structured logging | `rules/error-classification.md [SEC_LOGGING_SECRETS]` | dev-backend | Auto (stack §3) |
| T-7 | Audit log table `audit_events` insertée sur chaque mutation | Décision projet | Architect | ADR à créer |
| T-8 | `[Authorize(Policy="AdminOnly")]` + tests d'auth dans `*.Tests/Api/AuthTests.cs` | `rules/error-classification.md [SEC_BROKEN_AUTHZ]` | dev-backend + qa | Auto (stack auth) |

---

## 6. Risques résiduels (acceptés)

> Threats 🟢 ou explicitement acceptés par le métier. Justifier l'acceptation.

| Threat | Justification de l'acceptation | Accepté par | Revue |
|---|---|---|---|
| T-7 (residual) | Audit logs full nécessitent infra additionnelle (~3 j/h) — décision : log basique en v1, full audit en v2 si compliance le demande | Tech Lead + Métier | Q+1 |

---

## 7. Décisions ADR à créer

> Toute décision structurante issue de cette analyse doit produire un ADR. Liste à instancier post-review.

- [ ] `ADR-{ts}-jwt-signing-key-rotation` (T-1)
- [ ] `ADR-{ts}-export-async-pattern` (T-5)
- [ ] `ADR-{ts}-audit-events-table` (T-7)

---

## 8. Revue

| Reviewer | Date | Verdict | Commentaires |
|---|---|---|---|
| _Nom 1_ | YYYY-MM-DD | ✅ Approved / 🔁 Changes requested | _libre_ |
| _Nom 2_ | YYYY-MM-DD | ... | ... |

**Statut final** : `Approved` (toutes les actions 🔴 ont un owner + date) / `Blocked` (≥ 1 🔴 sans plan).

---

## Annexes

### A1. Outils complémentaires (déterministes)

- **Static analysis** : `semgrep --config p/owasp-top-ten` sur le code généré post-`/dev-run`
- **SCA (deps)** : `npm audit --omit=dev`, `dotnet list package --vulnerable`, `pip-audit`
- **Secrets scan** : `gitleaks detect --redact` avant chaque PR
- **Dynamic** : `OWASP ZAP` baseline contre l'app déployée en staging

### A2. Pourquoi STRIDE et pas autre

STRIDE est suffisant en première passe pour le périmètre SDD_Pro (apps web/mobile simples). Pour des cas critiques (banking, santé), passer en **LINDDUN** (privacy-focused) ou **PASTA** (risk-centric).

### A3. Sources canoniques

- OWASP Top 10 2021 — référencé dans `error-classification.md §1.11`
- NIST SP 800-30 Rev. 1 (Risk Assessment)
- Microsoft STRIDE original paper (Howard, LeBlanc — Writing Secure Code, 2002)
