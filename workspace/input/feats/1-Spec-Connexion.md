# Spec: connexion

Status: Draft
Spec ID: spec-connexion

## Context
Demo est une application destinée aux employés (assistantes maternelles) qui doivent accéder à un espace personnel sécurisé. Aucun mécanisme d'authentification n'existe aujourd'hui. Cette spec couvre le flux de connexion par email + mot de passe et la gestion de la session JWT, en lien navigationnel avec spec-inscription (création de compte) et spec-reinitialisation (mot de passe oublié) accessibles depuis l'écran de login.

## Objective
L'employé peut se connecter à Demo avec son email et son mot de passe, accéder à son espace personnel, rester connecté tant que le token JWT est valide, et se déconnecter explicitement.

## Actors
- Employé : assistante maternelle déjà inscrite, possédant un compte stocké en table `Employee`

## Functional Needs
- SFD-1: L'utilisateur accède à la page `/login` et saisit son email et son mot de passe
- SFD-2: Le système vérifie l'existence du compte en table `Employee` et compare le mot de passe au hash stocké
- SFD-3: Un token JWT est généré côté serveur et stocké de manière sécurisée côté client en cas de succès
- SFD-4: L'utilisateur est redirigé vers la page d'accueil `/` après authentification réussie
- SFD-5: L'utilisateur reste connecté entre deux visites tant que le token JWT est valide
- SFD-6: L'utilisateur peut se déconnecter explicitement, ce qui supprime le token côté client et le redirige vers `/login`
- SFD-7: Un message d'erreur générique "Email ou mot de passe incorrect" est affiché si la connexion échoue
- SFD-8: Un message "Veuillez remplir tous les champs" est affiché si email ou mot de passe est vide
- SFD-9: Un message "Une erreur est survenue, veuillez réessayer" est affiché en cas d'erreur serveur
- SFD-10: Le bouton "Se connecter" est désactivé pendant le traitement pour empêcher toute double-soumission
- SFD-11: Toute tentative d'accès à une page protégée sans token valide redirige automatiquement vers `/login`
- SFD-12: Un token JWT expiré déclenche une redirection vers `/login` accompagnée du message "Session expirée"
- SFD-13: L'écran `/login` propose un lien "Créer un compte" qui redirige vers `/register` (couvert par spec-inscription)
- SFD-14: L'écran `/login` propose un lien "Mot de passe oublié" qui redirige vers `/forgot-password` (couvert par spec-reinitialisation)
- SFD-15: Le token JWT est automatiquement transmis pour chaque appel à une API protégée
- SFD-16: L'écran `/login` (et symétriquement `/register`) affiche en partie haute le logo de l'application Demo — l'image officielle servie depuis `/icon-512.png` (PNG 512×512 de la PWA) — sur fond transparent, sans aucune carte/halo translucide derrière le logo, accompagné du nom « Demo » et du sous-titre « Assistantes maternelles ». L'ancien marqueur graphique en forme de cœur (SVG décoratif) est explicitement remplacé par le logo applicatif

## Business Rules
- BR-1: le mot de passe utilisateur n'est jamais stocké en clair, uniquement sous forme de hash sécurisé
- BR-2: les messages d'erreur ne révèlent jamais si un email existe ou non en base
- BR-3: aucun appel API protégé n'est accepté sans token JWT valide
- BR-4: le token JWT est validé côté backend pour chaque requête à une route protégée
- BR-5: aucune information technique (stack trace, identifiant interne, exception) n'est exposée dans les messages d'erreur visibles à l'utilisateur

## Acceptance Criteria
- AC-1: la page `/login` affiche, dans cet ordre vertical : (a) le logo applicatif Demo — image `/icon-512.png` sur fond transparent (aucun fond/carte/halo translucide derrière), (b) le nom « Demo » et le sous-titre « Assistantes maternelles », (c) un champ email, (d) un champ mot de passe, (e) un bouton "Se connecter", (f) un lien "Créer un compte" et un lien "Mot de passe oublié"
- AC-1bis: aucun icône en forme de cœur (ou autre marqueur SVG décoratif) ne doit subsister à l'emplacement du logo — la seule image attendue est `/icon-512.png` (ou un fallback équivalent du même asset PWA tel que `/icon-192.png`)
- AC-2: un employé existant qui saisit ses bons identifiants est redirigé vers `/` et obtient un token JWT côté client
- AC-3: un employé qui saisit des identifiants invalides voit le message "Email ou mot de passe incorrect" et reste sur `/login`
- AC-4: un champ vide à la soumission affiche le message "Veuillez remplir tous les champs"
- AC-5: le bouton "Se connecter" est désactivé pendant le traitement pour empêcher toute double-soumission
- AC-6: une tentative d'accès à une URL protégée sans token déclenche une redirection vers `/login`
- AC-7: un token JWT expiré déclenche une redirection vers `/login` avec le message "Session expirée"
- AC-8: un clic sur "Se déconnecter" supprime le token côté client et redirige vers `/login`
- AC-9: après connexion réussie, l'employé reste connecté lors d'une nouvelle visite tant que le token JWT est valide

## Dependencies
- NONE (spec-inscription et spec-reinitialisation sont liées navigationnellement mais non bloquantes pour la livraison de spec-connexion)

## Functional Deliverables
- FD-1: écran de connexion `/login` avec logo applicatif Demo (image `/icon-512.png` sur fond transparent — pas d'icône cœur), formulaire email + mot de passe et liens vers `/register` et `/forgot-password`
- FD-2: redirection automatique vers `/` après authentification réussie
- FD-3: session persistante via token JWT côté client
- FD-4: bouton de déconnexion explicite avec retour à `/login`
- FD-5: redirection automatique vers `/login` pour toute route protégée sans token valide
- FD-6: gestion d'expiration de session avec message dédié

## Out of Scope
- création de compte (couverte par spec-inscription)
- réinitialisation du mot de passe (couverte par spec-reinitialisation)
- rôles Admin et Parent (extensions futures)
- authentification multi-facteurs / SSO / OAuth
- "Se souvenir de moi" / cookies long terme spécifiques
- information : id, nom, prénom, téléphone rest dans un variable memeoir sengloton la duré d'utlisation de l'application.

---

## Risques Identifiés

| ID | Risque | Sévérité | Mitigation |
|---|---|---|---|
| RISK-1 | Le stockage du token JWT côté client (localStorage vs cookie httpOnly) expose à des attaques XSS si localStorage est choisi | high | Décider explicitement la stratégie de stockage (cookie httpOnly recommandé) et la documenter dans un ADR avant l'implémentation |
| RISK-2 | Absence de limite de tentatives de connexion (brute-force) : un attaquant peut tester des milliers de combinaisons email/mot de passe sans blocage | high | Ajouter un mécanisme de rate-limiting ou de verrouillage temporaire de compte (à ajouter dans BR ou spec dédiée) ; à valider avec PO |
| RISK-3 | La table `Employee` n'est pas encore créée ou son schéma (colonnes email, password_hash) n'est pas finalisé, bloquant l'implémentation de SFD-2 | medium | Vérifier que arch a scaffoldé la table `Employee` avant de lancer dev-backend |
| RISK-4 | Le secret de signature JWT (clé privée) n'est pas documenté dans les variables d'environnement du stack, risquant une config manquante en prod | medium | Déclarer `JWT_SECRET` (ou équivalent) dans `## Project Config` du stack et vérifier sa présence au démarrage |
| RISK-5 | La gestion du token expiré côté client (SFD-12, AC-7) peut générer des boucles de redirection si le frontend ne distingue pas "token absent" et "token expiré" | low | Implémenter deux chemins distincts dans le middleware de garde de routes ; couvrir par un test d'intégration |

---

## Hypothèses

| ID | Hypothèse | Statut | Validation requise |
|---|---|---|---|
| ASS-1 | La table `Employee` existe en base de données avec au minimum les colonnes `email` (unique) et `password_hash` | à valider | Confirmer le schéma DB via `workspace/output/db/schema.json` après scaffolding arch |
| ASS-2 | L'algorithme de hachage utilisé pour les mots de passe est bcrypt (ou équivalent robuste — Argon2, PBKDF2) et non MD5/SHA1 | à valider | Préciser l'algorithme dans BR-1 ou dans les conventions du stack backend |
| ASS-3 | Le secret de signature JWT est injecté via variable d'environnement (jamais hardcodé dans le code source) | à valider | Vérifier la présence d'une variable `JWT_SECRET` (ou `JWT_KEY`) dans `## Project Config` du stack |
| ASS-4 | La durée de validité du token JWT est définie et acceptable pour l'usage métier (assistantes maternelles qui ouvrent l'app quotidiennement) | à valider | Définir une valeur explicite (ex. 8h, 24h, 7j) dans la SPEC ou dans les conventions du stack |
| ASS-5 | Le frontend gère le token JWT via un intercepteur HTTP global (SFD-15) et non en l'ajoutant manuellement dans chaque appel | à valider | Confirmer le pattern (intercepteur Axios, HttpClient handler .NET, etc.) dans les conventions du stack frontend |
| ASS-6 | Tous les employés ont un compte email valide et y ont accès (pas de connexion par téléphone ou autre identifiant) | confirmée | Formulé explicitement dans `## Actors` : "possédant un compte stocké en table `Employee`" |
| ASS-7 | L'application Demo est mono-tenant (un seul espace employé, pas de séparation multi-entreprise) | à valider | Confirmer le périmètre avec PO avant l'implémentation des routes protégées |

---

## Cas Limites

| ID | Cas limite | Comportement attendu | Couvert par |
|---|---|---|---|
| EDGE-1 | Email saisi avec espaces avant/après (ex. " user@mail.com ") | Le champ doit être trimmé avant validation et comparaison en base | à ajouter (AC manquante) |
| EDGE-2 | Email valide syntaxiquement mais inexistant en base, mot de passe vide | Afficher "Veuillez remplir tous les champs" (priorité validation champ vide sur "identifiants incorrects") | AC-4 de US à générer |
| EDGE-3 | Double-clic rapide sur "Se connecter" avant que le bouton soit désactivé | Un seul appel API doit être émis (idempotence) | AC-5 de US à générer |
| EDGE-4 | Token JWT manipulé côté client (payload modifié mais signature invalide) | Le backend rejette le token (401), le frontend redirige vers `/login` | AC-6 de US à générer |
| EDGE-5 | Connexion réussie puis navigation vers `/login` avec un token encore valide | Redirection automatique vers `/` (pas d'affichage de la page login inutilement) | à ajouter (AC manquante) |
| EDGE-6 | Perte de connexion réseau au moment de la soumission du formulaire | Afficher "Une erreur est survenue, veuillez réessayer" (SFD-9 / AC cohérente) ; pas de double-soumission | AC-3 + SFD-9 (partiellement) |
| EDGE-7 | Token expiré pendant une session active (l'utilisateur est sur une page protégée) | L'intercepteur HTTP détecte le 401 retourné par le backend et redirige vers `/login` avec le message "Session expirée" | AC-7 de US à générer |
| EDGE-8 | Caractères unicode ou injections dans les champs email/mot de passe (ex. `admin'--`, `<script>`) | Les champs sont traités comme des chaînes opaques, le backend ne construit pas de requête SQL dynamique ; aucune injection possible | à ajouter (AC sécurité manquante) |

---

## Parties Prenantes

| Acteur | Rôle vs feature | RACI |
|---|---|---|
| Employé (assistante maternelle) | Utilisateur final de la fonctionnalité de connexion | I |
| PO Humain (***REMOVED***) | Valide les critères d'acceptation et les choix de message d'erreur | A |
| Tech Lead | Sélectionne la stratégie de stockage JWT, l'algorithme de hash, la durée de validité du token | A / C |
| Agent Dev-Backend | Implémente l'endpoint `/api/auth/login`, la vérification du hash, la génération JWT, les guards de routes | R |
| Agent Dev-Frontend | Implémente le formulaire `/login`, l'intercepteur HTTP, les gardes de navigation, la déconnexion | R |
| Agent QA | Génère les tests d'intégration API (happy path + 401 + 400) et les tests de composant du formulaire | C |
| UX Designer (si présent) | Dépose le mockup HTML `1-{m}-{Name}.html` pour la page de login | C |

---

## Modes de Défaillance

| ID | Mode de défaillance | Indicateur de défaillance | Critère succès en miroir |
|---|---|---|---|
| FAIL-1 | Les employés ne parviennent pas à se connecter en production (token invalide ou endpoint 500) | Taux d'erreur > 5% sur `POST /api/auth/login` en production | Taux d'erreur < 1% sur cet endpoint en production |
| FAIL-2 | Les employés abandonnent la page de connexion sans soumettre (UX trop complexe ou messages d'erreur confus) | Taux d'abandon du formulaire de login > 30% | Taux d'abandon < 10% ; taux de connexion réussie au premier essai > 80% |
| FAIL-3 | La session expire trop rapidement, forçant les employés à se reconnecter plusieurs fois par jour | Nombre moyen de reconnexions > 2 par jour par utilisateur | Nombre moyen de reconnexions < 1 par jour par utilisateur |
| FAIL-4 | Une fuite de tokens JWT (XSS ou stockage non sécurisé) expose les comptes employés | Incident de sécurité détecté (accès non autorisé avec token valide) | Aucun incident de sécurité lié au stockage JWT pendant les 3 premiers mois de production |
