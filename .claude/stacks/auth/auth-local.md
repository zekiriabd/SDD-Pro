# Tech Spec: auth-local

Status: Draft  
Tech Spec ID: tech-auth-local  
Scope: authentification et autorisation locale via login / password + JWT — independant de toute stack ou langage. Chaque implementation (backend, SPA, monolithe, mobile) doit appliquer ces regles selon sa technologie.

---

## 1. Principe universel

- Authentification via identifiant utilisateur (email ou login) + mot de passe.
- Les comptes utilisateurs sont stockes dans une base de donnees applicative.
- Les mots de passe sont **toujours stockes sous forme de hash securise**.
- Aucun mot de passe en clair n’est jamais stocke, transmis ou logge.
- Authentification reussie → generation d’un **token JWT signe**.
- Le JWT est utilise comme **source unique de verite** pour :
  - l’identite
  - les informations utilisateur
  - les droits (roles, permissions si presentes)

- Utilisation d’un mecanisme standard :
  - Backend : generation et validation JWT
  - Frontend / client : stockage securise + envoi du token
  - Monolithe : session serveur ou JWT interne

- Toutes les configurations proviennent des variables d’environnement et de la configuration applicative (§2).
- Aucune logique dependante d’un framework specifique ne doit etre supposee.

---

## 2. Variables d’environnement

Chargees au demarrage. L’application doit s’arreter si une variable est absente.

### Variables obligatoires

- AUTH_JWT_SECRET : cle secrete utilisee pour signer les tokens JWT
- AUTH_JWT_ISSUER : emetteur du token
- AUTH_JWT_AUDIENCE : audience du token
- AUTH_JWT_EXPIRATION : duree de validite (en secondes ou minutes)

### Variables recommandees

- AUTH_HASH_ALGO : algorithme de hash (defaut : argon2id)
- AUTH_HASH_ITERATIONS : facteur de cout (selon algo)
- AUTH_HASH_MEMORY : memoire (argon2)
- AUTH_HASH_PARALLELISM : parallelisme (argon2)
- AUTH_SALT_LENGTH : taille du sel

### Contraintes

- aucune valeur ne doit etre hardcodee
- toutes doivent etre injectees via environnement ou config externe
- valeurs differentes par environnement (dev/test/prod)

---

## 3. Hash des mots de passe (CRITIQUE — cross-langage)

### 3.1 Algorithmes autorises (ordre de preference)

- argon2id (recommande)
- bcrypt
- pbkdf2 (HMAC-SHA256 minimum)

### 3.2 Format du hash (OBLIGATOIRE)

Le hash stocke doit etre auto-descriptif et contenir :

- algorithme
- parametres (cout, iterations, etc.)
- sel (salt)
- hash final

Format standard recommande (type PHC string) :

$argon2id$v=19$m=65536,t=3,p=2$<salt>$<hash>

- $argon2id → algorithme utilisé
- v=19 → version d’Argon2
- m=65536 → mémoire (64 MB)
- t=3 → nombre d’itérations
- p=2 → parallélisme
- <salt> → sel (aléatoire, encodé en base64)
- <hash> → résultat du hash (base64)


Ce format garantit la portabilite entre :

- .NET
- Java (Spring)
- Node.js
- Python
- Go
- autres

---

### 3.3 Regles universelles

- chaque mot de passe a un salt unique
- le salt est genere aleatoirement
- le hash inclut le salt (pas stocke a part sauf si format compatible)
- comparaison via fonction securisee (constant-time)

### Interdits

- SHA256 seul
- MD5 / SHA1
- hash sans salt
- comparaison simple (==)

---

### 3.4 Verification du mot de passe

- utiliser la librairie standard du langage
- ne jamais reimplementer l’algo
- parser automatiquement le format du hash
- comparer via fonction fournie par la lib

---

## 4. Validation du token (universel)

Tout composant recevant un token doit verifier :

- signature valide (AUTH_JWT_SECRET)
- issuer valide
- audience valide
- expiration valide
- structure JWT correcte

Regles :

- toute requete sans token → 401
- token invalide → 401
- token valide sans droits → 403

Logs (dev) :

- generation token
- validation token
- echec auth
- acces refuse

---

## 5. Authentification utilisateur

### 5.1 Source des identifiants

Base de donnees applicative uniquement :

- email ou login
- password_hash

---

### 5.2 Processus de login

1. recuperer utilisateur par login/email
2. verifier existence
3. verifier mot de passe via hash
4. si valide → generer JWT
5. sinon → erreur generique (ne pas reveler si user existe)

---

### 5.3 Generation du token

Le JWT contient :

- sub : userId
- login/email
- roles (si existants)
- iat / exp
- issuer / audience

Contraintes :

- aucune donnee sensible (mot de passe, hash)
- expiration obligatoire
- signature via AUTH_JWT_SECRET

---

## 6. Autorisation

### 6.1 Source des droits

- roles stockes en base
- permissions associees

---

### 6.2 Mapping

- aucun mapping en dur
- configurable dynamiquement
- resolu au login ou via service

Si aucun role :

- mode degrade (authentifie uniquement)

---

### 6.3 Enforcement

- backend = source de verite
- frontend = UX uniquement
- verification serveur obligatoire

---

## 7. Integration par type d’application

### 7.1 Backend (API)

- endpoint /auth/login :
  - input : login + password
  - output : JWT

- middleware obligatoire pour :
  - verification JWT
  - injection user context

- endpoints proteges :
  - exigent JWT valide

---

### 7.2 Frontend / client (SPA, mobile)

- formulaire login obligatoire
- appel HTTPS vers backend

Stockage :

- prefere : memory + refresh controlle
- acceptable : storage securise via lib

Regles :

- aucun stockage brut non protege
- aucun log du token
- ajout automatique via interceptor HTTP

---

### 7.3 Application monolithique

- login via formulaire interne
- session serveur OU JWT interne

Comportements :

- non authentifie → redirect login
- authentifie sans droits → 403

---

## 8. Comportements attendus

- utilisateur non authentifie :
  - aucun acces
  - redirect login

- utilisateur authentifie :
  - recoit JWT
  - acces selon droits

- utilisateur non autorise :
  - 403
  - pas de redirect login

- token expire :
  - 401
  - re-auth obligatoire

---

## 9. Symptomes courants

- login refuse :
  - mauvais password
  - hash incompatible

- token invalide :
  - secret incorrect
  - mauvaise config issuer/audience

- acces refuse :
  - roles insuffisants

- API refuse :
  - token absent
  - token non attache

---

## 10. Interdits projet

- mot de passe en clair
- hash faible ou custom
- JWT sans expiration
- secret en dur
- stockage non securise du token
- logique securite frontend uniquement
- duplication auth
- exposition hash/password
- absence validation serveur

---

## 11. Hors scope

- MFA
- federation externe
- SSO
- rotation automatique des cles JWT
- audit avancé
- gestion sessions distribuees
- RBAC dynamique avancé
