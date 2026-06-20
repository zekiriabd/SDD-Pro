# Product Brief: {ProjectName}

> **Phase 0 — Discovery** (avant `/feat-generate`). Document amont
> facultatif mais recommandé pour projets > 3 FEATs. Capture le
> "pourquoi" et le "pour qui" du produit avant de plonger dans le
> "quoi" (FEATs). Source d'inspiration : BMad `product-brief`.
>
> **Owner** : Tech Lead + Product Owner (humains, pas agent).
> **Localisation** : `workspace/input/discovery/product-brief.md`
> (créer le dossier si absent — gitignored par défaut, ajouter
> au repo si validation client requise).
> **Mode d'écriture** : Markdown libre, 1-3 pages max. Pas
> obligatoire de remplir toutes les sections — privilégier
> qualité sur exhaustivité.

---

## 1. Vision (1-2 phrases)

<En une phrase, qu'est-ce que ce produit ? À qui s'adresse-t-il ?
Format : "Pour {audience cible}, {ProjectName} est {catégorie produit}
qui {bénéfice principal}, contrairement à {alternative actuelle}.">

Exemple : "Pour les directeurs marketing de PME e-commerce,
RetailAnalytics est un dashboard temps-réel qui transforme leur Google
Analytics en décisions actionnables sans dépendre d'un data analyst,
contrairement à Looker ou Tableau qui exigent 3 mois de setup."

---

## 2. Problème à résoudre (3-5 bullets)

<Quels problèmes concrets vivent les utilisateurs aujourd'hui ?
Avec quelles conséquences mesurables ? Évite "manque X" — préférer
"perd Y heures/semaine à cause de Z".>

- <problème 1, observable, mesurable>
- <problème 2>
- <problème 3>

---

## 3. Utilisateurs cibles (2-4 personas)

| Persona | Rôle / contexte | Objectif principal | Frustration actuelle |
|---|---|---|---|
| <persona 1> | <ex. Directeur Marketing PME 10-50 salariés> | <ex. décisions hebdo basées sur data> | <ex. dépend du dev pour 1 rapport custom> |
| <persona 2> | | | |

> **Anti-pattern** : "tout le monde" / "les entreprises". Si > 3 personas
> distincts, le scope est trop large — découper en sous-produits.

---

## 4. Proposition de valeur (différenciation)

### 4.1 Ce qu'on fait (et pas les autres)
- <feature/approche unique 1>
- <feature/approche unique 2>

### 4.2 Ce qu'on NE fait PAS (out of scope explicite)
- <non-feature 1 — ex. pas d'export PDF custom>
- <non-feature 2 — ex. pas de white-label v1>

> Le **out-of-scope** est aussi important que le scope. Documente les
> tentations qu'on a refusées et pourquoi (sinon elles reviennent en
> FEATs parasites).

---

## 5. Métriques de succès (KPIs business)

<3-5 KPIs business mesurables. Pas de KPIs techniques (coverage,
latence, etc.) — ceux-là vivent dans les FEATs.>

| KPI | Baseline | Target 6 mois | Target 12 mois |
|---|---|---|---|
| <ex. NPS> | <ex. 0 (pas mesuré)> | <ex. ≥ 30> | <ex. ≥ 50> |
| <ex. MAU> | <baseline> | <target> | <target> |
| <ex. taux conversion trial→paid> | | | |

---

## 6. Hypothèses fortes (à valider tôt)

<Tout produit nouveau repose sur 2-5 hypothèses qui, si fausses,
invalident le projet. Lister explicitement pour pouvoir les tester
en priorité (POC, user research, etc.).>

| # | Hypothèse | Comment la valider | Statut |
|---|---|---|---|
| H1 | <ex. les directeurs marketing PME paieraient 50€/mois pour ce dashboard> | <ex. interview 10 prospects + landing page test> | À valider |
| H2 | <ex. l'API Google Analytics permet de récupérer X données en temps réel> | <ex. POC technique 2 jours> | À valider |
| H3 | | | |

---

## 7. Contraintes & dépendances

### 7.1 Contraintes
- Budget : <ex. ≤ 50k€ MVP / ≤ 200€/mois infra>
- Délai : <ex. MVP démontrable sous 8 semaines>
- Équipe : <ex. 1 dev fullstack, 0.2 designer, 0 ops>
- Réglementaires : <ex. RGPD, hébergement EU>

### 7.2 Dépendances externes
- <ex. API Google Analytics 4 — quotas + reliability>
- <ex. Stripe pour paiements>

---

## 8. Risques principaux (top 3)

| # | Risque | Probabilité | Impact | Mitigation |
|---|---|:---:|:---:|---|
| R1 | <ex. Google change tarification API GA4> | Faible | Critique | <ex. abstraire le data source, POC fallback Matomo> |
| R2 | | | | |
| R3 | | | | |

---

## 9. Prochaines étapes (Phase 1 — FEATs)

Une fois ce brief validé (humains), démarrer Phase 1 :

```bash
/feat-generate <NomDeLa1ʳᵉFEAT>     # cadrage 1ʳᵉ FEAT (3-6 questions élicitor)
/sdd-help                            # guidance contextuelle "what's next"
```

Ordre suggéré de découpage FEATs (≤ 5 pour MVP) :
1. <FEAT 1 — ex. Auth + signup flow>
2. <FEAT 2 — ex. Connexion source data>
3. <FEAT 3 — ex. Dashboard temps-réel basique>
4. <FEAT 4 — optionnelle MVP>
5. <FEAT 5 — optionnelle MVP>

---

## 10. Validation

| Aspect | Validé par | Date | Note |
|---|---|---|---|
| Vision §1 | <Tech Lead / PO> | <YYYY-MM-DD> | |
| Personas §3 | | | |
| KPIs §5 | | | |
| Hypothèses §6 | | | |
| Risques §8 | | | |

> **Anti-derive** : ne JAMAIS commencer `/feat-generate` avant que les
> sections 1, 2, 3, 5 soient validées. Sinon FEATs construites sur
> hypothèses non-testées = re-travail garanti.

---

## Pointeurs

- `prfaq.template.md` — version Amazon "working backwards" (alternative ou complément)
- `feat.template.md` — template FEAT (Phase 1, sortie `/feat-generate`)
- `@.claude/docs/quickstart.md` — onboarding 10 min
