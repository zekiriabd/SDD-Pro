# FEAT: Calc-Web-UI

FEAT ID: 2-Calc-Web-UI
Status: Draft

## Context
La FEAT 1 a livré un backend Kotlin Spring Boot exposant `POST /api/calc` (Calc-A-B-C). Pour valider le bench end-to-end full web (back + front), il manque une interface React minimaliste qui consomme cet endpoint depuis le navigateur. L'objectif est de prouver que SDD_Pro génère un front fonctionnel câblé sur un back déjà généré, avec CORS opérationnel et contrat HTTP cohérent.

## Objective
Servir une page web React unique qui affiche trois champs (A, B, C), permet à l'utilisateur de saisir A et B (entiers), envoie une requête `POST /api/calc` au backend Kotlin sur démarrage, et affiche la somme retournée dans le champ C en lecture seule, sans rechargement de page.

## Quantified Goal
- Metric: pourcentage d'utilisateurs ouvrant l'app, saisissant A=5 et B=5 puis voyant C=10 sans erreur console
- Target: 100 %
- Deadline: validation immédiate session bench 2026-06-05

## Non-Functional Constraints
- Expected volume: n/a (bench unitaire local)
- Performance SLA: latence affichage C < 200 ms après clic Calculate (réseau local, calcul trivial)
- Data retention: n/a (stateless, aucun stockage navigateur)
- Compliance: n/a
- Integration: backend Kotlin Spring Boot `http://localhost:44329/api/calc` (CORS requis côté back)
- Degraded mode: si backend down, afficher message d'erreur clair dans l'UI sans crash

## Actors
- Tech Lead: opérateur du bench, ouvre la page web et saisit A et B
- Système Front: SPA React qui collecte la saisie et appelle l'API
- Système Back: backend Kotlin Spring Boot qui calcule la somme (FEAT 1)

## Functional Needs
- SFD-1: afficher une page web avec trois champs nommés A, B, C dans cet ordre
- SFD-2: permettre la saisie d'entiers signés dans A et B
- SFD-3: envoyer la requête HTTP POST vers le backend lors d'une action utilisateur explicite (bouton)
- SFD-4: afficher le résultat C retourné par le backend en lecture seule
- SFD-5: afficher un message d'erreur lisible si la requête échoue (réseau ou validation 400)

## Business Rules
- BR-1: A et B doivent être des entiers signés 32 bits (validation côté front avant envoi pour éviter 400 silencieux)
- BR-2: C est calculé exclusivement par le backend (jamais en local côté front) — preuve que l'appel HTTP a bien eu lieu
- BR-3: aucune authentification requise (endpoint public, scope strict bench)
- BR-4: l'URL backend est lue depuis une variable d'environnement Vite (`VITE_API_BASE_URL`) avec fallback `http://localhost:44329`

## Acceptance Criteria
- AC-1: étant donné l'app React démarrée sur `http://localhost:5186` et le backend Kotlin démarré sur `http://localhost:44329`, lorsque je saisis `A=5` et `B=5` puis je clique sur le bouton Calculate, alors je vois la valeur `C=10` affichée dans le champ C en lecture seule en moins de 1 seconde
- AC-2: étant donné l'app React démarrée et le backend down (port 44329 fermé), lorsque je clique sur Calculate, alors je vois un message d'erreur "Impossible de joindre l'API" (ou équivalent) sans crash de l'app
- AC-3: étant donné l'app React démarrée et le backend up, lorsque je laisse A vide et clique Calculate, alors le bouton est désactivé OU un message "veuillez saisir A et B" apparaît (validation front avant appel)

## Dependencies
- 1-Calc-A-B-C (FEAT backend Kotlin)

## Functional Deliverables
- FD-1: page React unique à la racine `/` avec layout 3 champs + 1 bouton Calculate
- FD-2: client HTTP typé qui appelle `POST /api/calc` avec body JSON et parse la réponse
- FD-3: gestion d'erreur visible (réseau, 400 validation, 500 serveur)

## Out of Scope
- Routing multi-pages, navigation
- Persistance des calculs (historique, localStorage)
- Authentification, autorisation
- Internationalisation (FR/EN) — labels en français uniquement
- Tests E2E Playwright (vérification manuelle Swagger + UI suffisante pour bench)
- Mobile responsive (desktop only)
- Theming dark/light (light uniquement)
- Operations autres que addition
