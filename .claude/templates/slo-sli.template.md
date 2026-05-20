# SLO / SLI — {ServiceName}

> Service Level Objectives + Indicators. À définir avant ship.
> Source : SDD_Pro `.claude/templates/slo-sli.template.md`

**Service** : {ServiceName}
**Owner team** : {TeamOrPerson}
**Period** : {monthly | quarterly}
**Last reviewed** : {YYYY-MM-DD}

---

## 1. Définitions

- **SLI** (Service Level Indicator) : métrique mesurable observable
  (latence p95, taux d'erreur, disponibilité)
- **SLO** (Service Level Objective) : cible quantitative d'un SLI
  (ex. "99.5% des requêtes < 300ms sur 30 jours")
- **Error budget** : marge tolérée = `1 - SLO`. Ex. SLO 99.5% → 0.5%
  d'erreurs acceptées = 219 min/mois.

## 2. SLO matrix

| SLI | Mesure | SLO target | Error budget | Owner |
|---|---|---|---|---|
| **Availability** | `success_requests / total_requests` sur `GET /health` | **99.9%** sur 30j | 43 min/mois | {DevOps} |
| **Latency API (p95)** | `histogram_quantile(0.95, http_request_duration_seconds)` | **< 300 ms** | 5% des reqs > 300ms tolérés | {Tech Lead} |
| **Latency API (p99)** | idem p99 | **< 1000 ms** | 1% des reqs > 1s tolérés | {Tech Lead} |
| **Error rate** | `5xx_responses / total_responses` | **< 0.5%** | 50/10000 reqs | {Tech Lead} |
| **Login success rate** | `login_200 / login_total` | **> 98%** sur 1h glissante | 200/10000 logins | {Tech Lead} |
| **DB query latency p95** | `pg_stat_statements` p95 query time | **< 100 ms** | — | {DBA} |
| **Frontend LCP (p75)** | Lighthouse CI ou RUM | **< 2500 ms** (WCAG AA) | — | {Frontend} |
| **Frontend CLS** | RUM | **< 0.1** | — | {Frontend} |

## 3. Alerting strategy (multi-burn-rate)

Inspiré Google SRE handbook ch. 5 — alerter sur la **vitesse de
consommation** du budget d'erreur, pas sur valeur instantanée.

| Burn rate | Window | Action |
|---|---|---|
| **14.4× budget** | 1h | PagerDuty SEV1 (consomme 1 mois en 2h) |
| **6× budget** | 6h | PagerDuty SEV2 (consomme 1 mois en 5j) |
| **3× budget** | 24h | Slack #ops (warning, pas page) |
| **1× budget** | 7j | Email weekly review |

**Exemple availability 99.9% SLO** :
- Budget = 0.1% requests
- Burn 14.4× = > 1.44% errors sur 1h → page immédiate

## 4. Reporting

### 4.1 Dashboard (Grafana)

Panels obligatoires :
1. Availability % (30 jours glissants) vs SLO
2. Latency p95/p99 (histogramme, 7 derniers jours)
3. Error rate % (1h granularity, 30j)
4. Error budget remaining (gauge)
5. Top 10 endpoints par error rate

Lien : `{grafana-url}/d/{dashboard-uid}`

### 4.2 Weekly review

Tous les lundis, le Tech Lead :
1. Check error budget consumption (Grafana panel #4)
2. Si budget < 50% remaining → freeze des feature deploys, focus
   reliability cette semaine
3. Si budget < 10% remaining → SEV2 escalation, all-hands reliability
4. Si SLO breached → post-mortem obligatoire

## 5. SLO review (trimestriel)

Tous les 3 mois, re-évaluer :
- [ ] Le SLO reflète-t-il l'attente user actuelle ?
- [ ] Le budget consommé est-il aligné avec le risque accepté ?
- [ ] De nouveaux SLIs sont-ils nécessaires (ex. nouvelle feature) ?
- [ ] Anciens SLIs encore pertinents ?

## 6. Anti-patterns à éviter

- ❌ **SLO 100%** : impossible à atteindre, démotivant. Toujours ≤ 99.99%.
- ❌ **SLI sans owner** : personne ne le surveille.
- ❌ **Alerte sur valeur instantanée** : flapping, alert fatigue.
  Toujours multi-burn-rate.
- ❌ **SLO sur métrique non visible user** (ex. CPU utilisation).
  Toujours user-facing.
- ❌ **Pas de error budget policy** : sans freeze deploy quand budget bas,
  pas d'incitation à reliability.

---

> Ce SLO/SLI est régénéré à chaque évolution majeure du service
> (nouveaux endpoints, nouveaux SLA contractuels). Source de vérité :
> `.claude/templates/slo-sli.template.md` + complétion humaine.
