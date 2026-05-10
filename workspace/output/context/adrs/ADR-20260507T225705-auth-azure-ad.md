# ADR-20260507T225705 -- Auth -- Azure AD OAuth2

- **Statut** : Accepted
- **Date** : 2026-05-07
- **Auteur** : arch
- **Phase** : 4-ARCH

---

## Context

L'application doit etre securisee via Azure Active Directory. Le Tech Lead a selectionne le stack `auth/azure-ad.md`. Le backend expose une API REST protegee par JWT Bearer, le frontend utilise MSAL React pour l'acquisition des tokens.

---

## Decision

L'authentification est implementee via Azure AD: Spring Security OAuth2 Resource Server (backend) + MSAL React (frontend). Variables d'environnement: AZURE_ISSUER_URI (backend), VITE_AZURE_CLIENT_ID et VITE_AZURE_TENANT_ID (frontend).

---

## Consequences

**Positifs :**
- Securite enterprise-grade avec Azure AD.
- JWT validation automatique par Spring Security.
- MSAL React gere l'acquisition et le refresh des tokens.

**Negatifs / dette acceptee :**
- Dependance a Azure AD -- tests unitaires necessitent un TestAuthHandler mock.
- Configuration env vars requise avant tout deploiement.

---

## Alternatives considerees

- NONE -- impose par workspace/input/stack/stack.md (## Active Auth Specs).

---

## Liens

- Stack : `.claude/stacks/auth/azure-ad.md`
