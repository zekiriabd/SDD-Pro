# Règle — Granularité des User Stories

## Principe

En méthode Agile, une **User Story décrit un flux utilisateur distinct avec
une valeur métier observable**. Pas un comportement technique, pas un effet
de bord, pas une configuration par défaut.

Les **détails techniques** sont planifiés inline par les agents
`dev-backend` et `dev-frontend` à partir de l'US, pas dans l'US elle-même.

Cette règle s'applique au moment où l'agent PO transforme les SFD bullets
d'une FEAT en User Stories structurées.

---

## 1. Seuils (depuis SDD_Pro v7.0.0 — hard cap relevé à 10, warn dès 7)

- **Min 1 US par FEAT** : une feature triviale a une seule US.
- **Cible 1-3 US** pour la plupart des features bien scopées.
- **Zone WARNING 4-6 US** : tolérée, mais l'agent PO émet un WARNING
  invitant à reconsidérer le découpage. Le pipeline continue.
- **Warn at 7 US** : signal renforcé (zone 7-10 — accepté mais
  recommandation forte de splitter la FEAT).
- **Hard cap 10 US** (default v7.0.0 `UsGranularityHardCap: 10`) :
  au-delà, STOP + ERROR. La FEAT est trop large et doit être splittée
  en plusieurs FEATs au niveau PO humain.

Comportement de l'agent PO selon le nombre `N` d'US générées :

| N         | Action                                                                 |
|-----------|------------------------------------------------------------------------|
| 1-3       | Génération normale, pas de message                                     |
| 4-6       | Génération + WARNING émis dans la sortie de l'agent (non bloquant)     |
| 7-10      | Génération + WARNING renforcé (splitter recommandé)                    |
| 11+       | STOP + ERROR (pas d'écriture des US)                                   |

WARNING (zone 4-6) :
```
WARNING: FEAT {n}-{Name} génère {N} US (zone 4-6 — tolérée mais à reconsidérer)
HINT: vérifier si certaines US ne sont pas des comportements dérivés (ACs) ou des détails techniques (plan inline dev-*)
```

WARNING renforcé (zone 7-10) :
```
WARNING: FEAT {n}-{Name} génère {N} US (zone 7-10 — splitter fortement recommandé)
HINT: regrouper les SFD bullets par flux utilisateur OU splitter la FEAT en plusieurs FEATs
```

ERROR (> 10) :
```
ERROR: FEAT {n}-{Name} produces {N} US (> 10 hard cap, default UsGranularityHardCap)
CAUSE: FEAT trop large OU découpage 1:1 SFD → US au lieu de regrouper par flux
FIX: regrouper les SFD bullets par flux utilisateur OU splitter la FEAT en plusieurs FEATs
```

---

## 2. Règle de regroupement — flux utilisateur, pas bullet 1:1

Pour chaque SFD bullet de la FEAT, classifier :

1. **Action utilisateur distincte** (verbe actif : se connecter, consulter,
   créer, exporter) → candidat US
2. **Comportement dérivé** (le système valide, le backend enforce, la session
   se réutilise, mode dégradé) → AC d'une US existante
3. **Détail technique** (nom de service, chemin de fichier, config librairie)
   → tâche technique (pas US, pas AC)

**Test mental** : *"Si l'utilisateur métier ne le voit pas, ce n'est pas une US."*

### Exemple — 11 SFD bullets → 3 US

FEAT `1-Auth.md` avec 11 SFD bullets décrivant authentification Azure AD :
- Mauvais : 11 US (1:1)
- Bon : **3 US** (Connexion, Déconnexion, Autorisation par groupes)
- Chaque SFD reste couvert via le champ `Covers` d'au moins une US.

---

## 3. Comportements dérivés → ACs (jamais US)

| SFD bullet | Classification |
|---|---|
| "Le système valide X" | AC de l'US qui déclenche X |
| "La session est réutilisée automatiquement" | AC de l'US Connexion |
| "Mode dégradé si config absente" | AC de robustesse de l'US concernée |
| "Un message s'affiche si erreur" | AC de l'US qui déclenche l'erreur |
| "Validation d'entrée / regex" | AC de l'US qui accepte l'entrée |
| "Redirection vers X après Y" | AC de l'US Y |

---

## 4. Anti-patterns interdits

L'agent PO REFUSE de générer ces patterns :

### 4.1 Anti-pattern "1 SFD = 1 US"
SFD : 8 bullets → 8 US ❌
Correct : regrouper par flux utilisateur ✓

### 4.2 Anti-pattern "US technique"
US-2 : *"Le backend valide le JWT à chaque requête"* ❌
→ C'est une AC de l'US Connexion ou Autorisation.

### 4.3 Anti-pattern "US par couche"
US-1 Backend de connexion / US-2 Frontend de connexion ❌
→ Une seule US Connexion. Backend + Frontend = tâches.

### 4.4 Anti-pattern "US de configuration"
US-X : *"Configuration des policies"* ❌
→ Tâche technique, pas US.

### 4.5 Anti-pattern "US de fallback"
US-X : *"Mode dégradé si mapping absent"* ❌
→ AC de robustesse d'une US existante.

---

## 5. Traçabilité 100% (non négociable)

Chaque élément de la FEAT parente DOIT apparaître dans le `Covers` d'au moins
une US :
- Tous les **SFD bullets** (`## Functional Needs` de la FEAT, préfixés `SFD-N:`)
- Toutes les **Business Rules** (`## Business Rules`)
- Tous les **Acceptance Criteria** de la FEAT (`## Acceptance Criteria`)
- Tous les **Functional Deliverables** (`## Functional Deliverables`)

Si un élément FEAT n'est couvert par aucune US → STOP + ERROR :
```
ERROR: FEAT {n}-{Name} traceability gap
CAUSE: {SFD-3, BR-2} non couverts par les US générées
FIX: ajouter ces éléments au Covers d'une US existante OU créer une US dédiée
```
