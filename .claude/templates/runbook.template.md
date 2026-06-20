# Runbook — {ServiceName}

> Procédure d'intervention pour l'on-call. À remplir avant la mise en production.
> Source : SDD_Pro `.claude/templates/runbook.template.md`

**Service** : {ServiceName}
**Owner team** : {TeamOrPerson}
**Last reviewed** : {YYYY-MM-DD}
**Severity matrix** : cf. §6 ci-dessous

---

## 1. Service overview

**What it does** : {1-2 phrases}
**Upstream dependencies** : {liste, ex. PostgreSQL, Redis, Azure AD, SMTP MailJet}
**Downstream consumers** : {liste, ex. frontend NounouJobFront, mobile app, partenaires API}
**Business impact si down** : {1 phrase, ex. "users ne peuvent plus se connecter"}

## 2. Health endpoints / monitors

| Endpoint / monitor | Fréquence check | Threshold | Alerte |
|---|---|---|---|
| `GET /health` | 30s | `200 OK` < 500ms | PagerDuty SEV3 |
| `GET /health/db` | 60s | `200 OK` | PagerDuty SEV2 |
| Lighthouse LCP front | 1h | < 2.5s p75 | Slack #ops |
| API p95 latency | 1m | < 300ms | Slack #ops si > 500ms |
| Disk usage VM | 5m | < 85% | PagerDuty SEV3 |

## 3. Common incidents et résolution

### 3.1 Login échoue avec 401 systématique

**Symptômes** : tous les users voient "Identifiants invalides" même avec mot de passe correct.
**Diagnostic** :
1. Check `GET /health` du backend
2. Check les logs `journalctl -u nounoujob-back` (chercher `JWT_SIGNING_KEY` ou `AUTH_LOCAL`)
3. Check connectivité DB : `psql ... -c "SELECT count(*) FROM Users;"`

**Cause probable** : `AUTH_JWT_SECRET` modifié sans rotation des sessions.
**Résolution** :
1. Restore l'ancienne valeur depuis `.env.backup`
2. Si la rotation était volontaire : forcer tous les users à se reconnecter via flag d'invalidation des sessions

### 3.2 API timeout > 5s sur GET /api/bebes

(template — à compléter)

### 3.3 DB connection pool exhausted

(template — à compléter)

## 4. Rollback procedure

**Conditions** : régression bloquante détectée < 15min après deploy.

```bash
# Step 1 — revert le dernier deploy
{rollback-command, ex. "kubectl rollout undo deployment/nounoujob-back"}

# Step 2 — vérifier que le service repart
curl -fsS https://nounoujob.fr/health || echo "FAIL"

# Step 3 — notifier
slack #ops "rollback executed by $USER at $(date -u +%FT%TZ)"
```

## 5. Escalation chain

| SEV | Délai escalation | Contacts |
|---|---|---|
| SEV1 (down complet) | immédiat | {primary on-call} → {tech lead} → {CTO} |
| SEV2 (degradation majeure) | 30 min | {primary on-call} → {tech lead} |
| SEV3 (degradation mineure) | next business day | {primary on-call} |

## 6. Severity matrix

| SEV | Définition | Exemples |
|---|---|---|
| **SEV1** | Service totalement indisponible OU data loss en cours | Login KO 100% users, DB corruption |
| **SEV2** | Service partiellement indisponible OU degradation > 50% users | Login KO 30% users, API p95 > 5s |
| **SEV3** | Bug fonctionnel, degradation < 20% users | UI cassée sur 1 page, latence p95 > 1s |
| **SEV4** | Cosmétique ou non bloquant | Typo, log warning bénin |

## 7. Communication template (status page)

```
[{SEV}] {ServiceName} — {1-line summary}

Started : {ISO timestamp UTC}
Impact  : {qui est affecté, combien}
Cause   : {sous investigation | identifiée : ...}
Mitigation : {en cours | appliquée : ...}
Next update : {dans 30 min | à la résolution}
```

## 8. Post-incident

À la fin de l'incident, créer un **post-mortem** depuis
`.claude/templates/postmortem.template.md` dans **48h max** (cf.
`source-first.md §5` — les fixes hotfix doivent produire un patch
source MD dans les 48h).

---

> Ce runbook est régénéré à chaque modification de l'architecture
> (nouveaux endpoints, nouveaux monitors). Source de vérité :
> `.claude/templates/runbook.template.md` + complétion humaine.
