# PR/FAQ: {ProjectName}

> **Phase 0 — Discovery** (alternative ou complément à `product-brief.template.md`).
> Format **PR/FAQ Amazon "Working Backwards"** : rédiger d'abord le
> communiqué de presse fictif (PR) **comme si le produit était lancé
> aujourd'hui**, suivi du FAQ interne. Force à imaginer le résultat
> final avant de commencer le développement.
>
> **Owner** : Product Owner (humain). **Localisation** :
> `workspace/input/discovery/prfaq.md` (créer dossier si absent).
> **Taille cible** : PR ≤ 1 page, FAQ ≤ 2 pages. Si plus long, le
> produit est trop vague.

---

## Partie A — Press Release (1 page max, vue externe)

> Format : communiqué de presse fictif, daté du jour du lancement
> (futur). Public : utilisateur final, pas développeur. Style :
> simple, concret, bénéfices d'abord.

---

**FOR IMMEDIATE RELEASE**

**{Date de lancement cible : ex. 15 mars 2027}**

# {Titre accrocheur : "Acme lance {ProjectName}, le premier {catégorie} qui {bénéfice unique}"}

**{Ville}, {Date}** — {Société} annonce aujourd'hui la disponibilité
de **{ProjectName}**, {1 phrase de description du produit}.
{1 phrase de bénéfice principal pour l'utilisateur cible}.

## Le problème que ça résout (2-3 phrases)

<Décris le problème actuel du point de vue de l'utilisateur, sans
mentionner ta solution. Anecdotique mais concret. Ex : "Les directeurs
marketing de PME passent en moyenne 4 heures par semaine à compiler
manuellement des rapports Google Analytics, car les outils existants
exigent un data analyst pour leur setup initial.">

## Notre solution (2-3 phrases)

<Présente la solution. Bénéfice principal. **Pas de jargon technique**.
Ex : "{ProjectName} se connecte à Google Analytics en 2 clics et
génère automatiquement un dashboard temps-réel personnalisé selon
le rôle de l'utilisateur. Aucune configuration technique requise.">

## Citation du dirigeant (1 phrase)

> "{Citation aspirationnelle mais réaliste, qui exprime la mission.
> Ex : 'Nous croyons que chaque PME mérite l'accès aux mêmes outils
> de décision data que les Fortune 500, sans en payer le prix ni la
> complexité.'}" — {Nom du dirigeant, titre}

## Comment ça marche (3-5 bullets, vue utilisateur)

- {Étape 1 utilisateur, ex. "Connectez votre compte Google Analytics"}
- {Étape 2}
- {Étape 3}
- {Etc.}

## Citation client (1 phrase, fictive mais plausible)

> "{Citation d'un utilisateur cible, qui exprime un bénéfice concret.
> Ex : 'Avant {ProjectName}, je passais mes lundis matin à compiler
> des rapports. Maintenant, je commence ma semaine avec les insights
> sur mon téléphone, en 30 secondes.'}" — {Persona fictif, ex. "Marie
> Dupont, Directrice Marketing chez ExemplePME"}

## Comment démarrer

{ProjectName} est disponible dès aujourd'hui sur {URL fictive} à
partir de {prix ou "gratuit pour les 100 premiers utilisateurs"}.
{Lien CTA fictif}.

---

**À propos de {Société}**

{1-2 phrases sur la mission de l'entreprise.}

**Contact presse** : {nom fictif}, {email fictif}

---

## Partie B — FAQ interne (2 pages max, vue projet)

> Questions que l'équipe interne (dev, design, ventes, support) va
> poser avant et après le lancement. Les **réponses doivent être
> concrètes**, pas du marketing.

### B.1 Pour les clients

**Q : Combien ça coûte ?**
R : <ex. 49€/mois plan starter, 149€/mois pro, custom enterprise.
Free trial 14 jours sans CB.>

**Q : Qu'est-ce qui le différencie de {compétiteur 1} et {compétiteur 2} ?**
R : <ex. Looker exige 3 mois de setup et un data analyst ; Tableau
coûte 70€/utilisateur/mois ; {ProjectName} cible spécifiquement les
PME e-commerce avec un setup en 2 minutes et un pricing fixe.>

**Q : Mes données sont-elles sécurisées ?**
R : <ex. Hébergement EU (Scaleway Paris), chiffrement TLS 1.3 + AES-256
au repos, conformité RGPD article 28 (DPA signable), audit SOC2
prévu Q3 2027.>

**Q : Quels outils sont supportés au lancement ?**
R : <ex. Google Analytics 4 (priorité 1), Shopify (priorité 2),
Matomo (Q2 2027).>

### B.2 Pour l'équipe (questions difficiles à se poser HONNÊTEMENT)

**Q : Quelle est la métrique unique de succès qu'on mesurera 6 mois
après le lancement ?**
R : <Une seule métrique. Pas une liste. Ex : "MRR ≥ 5k€" ou "MAU
actifs ≥ 200 avec retention 30j ≥ 60%". Si > 1 métrique principale,
le produit n'a pas de focus.>

**Q : Que faisons-nous si on atteint 50% de la métrique principale
à 6 mois (signal faible) ?**
R : <Plan B explicite. Ex : "Pivoter vers vertical e-commerce X
si moins de 30% des utilisateurs viennent d'e-commerce", ou "Couper
les pertes et fermer le produit".>

**Q : Quelle est la plus grosse hypothèse non vérifiée ?**
R : <1 hypothèse claire. Ex : "Que les PME paieront 50€/mois pour
un outil analytics standalone, et pas juste 'gratuit avec leur CMS'".>

**Q : Quel est le concurrent qui pourrait nous tuer le plus vite et
pourquoi ?**
R : <Identifier honnêtement. Pas "personne". Ex : "Shopify Analytics
intégré natif — s'ils ajoutent les insights temps-réel, on perd notre
différenciation principale en 6 mois.">

**Q : Quel est le scénario où on ferme le produit dans 12 mois ?**
R : <Définition d'échec explicite, ex. "MRR < 2k€ à M12, ou
churn mensuel > 15% après stabilisation".>

### B.3 Out of scope explicite (anti-derive)

Ce que le produit **ne fera PAS** au lancement, et **pourquoi** :

| Out of scope v1 | Raison | Reconsidéré quand |
|---|---|---|
| <ex. Export PDF custom> | <ex. complexité pour 5% des users> | <ex. ≥ 100 demandes user feedback> |
| <ex. White label> | <ex. exige refonte CSS thèmes> | <ex. partenariat agences confirmé> |
| <ex. Mobile app native> | <ex. PWA suffit MVP> | <ex. > 40% MAU sur mobile> |

---

## Partie C — Prochaines étapes

Une fois PR + FAQ validés (humains) :

```bash
/feat-generate <NomDeLa1ʳᵉFEAT>     # cadrage 1ʳᵉ FEAT (3-6 questions élicitor)
/sdd-help                            # guidance contextuelle "what's next"
```

> **Anti-derive** : NE PAS modifier la PR (Partie A) une fois qu'elle
> est validée. Si la vision change → nouveau PR/FAQ, archive l'ancien
> avec date. Le PR est l'**Étoile du Nord** : si une FEAT proposée
> ne sert pas une promesse de la PR, c'est probablement du scope creep.

---

## Validation

| Section | Validé par | Date |
|---|---|---|
| PR (Partie A) | <Tech Lead + PO> | <YYYY-MM-DD> |
| FAQ B.1 (client) | | |
| FAQ B.2 (équipe) | | |
| Out of scope B.3 | | |

---

## Pointeurs

- `product-brief.template.md` — alternative plus classique (sections KPIs / personas / risques explicites)
- `feat.template.md` — template FEAT (Phase 1)
- @.claude/docs/quickstart.md — onboarding 10 min
- Méthode originale : [Working Backwards (Amazon)](https://www.amazon.science/working-backwards) — concept "imagine the press release before building"
