# Spec: reinitialisation

Status: Draft
Spec ID: spec-reinitialisation

## Context
Un employé peut perdre son mot de passe et doit pouvoir le réinitialiser sans intervention manuelle. Cette spec décrit le flux complet : demande de réinitialisation par email, réception d'un lien sécurisé, saisie d'un nouveau mot de passe, retour à `/login` (couvert par spec-connexion).

## Objective
L'employé qui a oublié son mot de passe peut réinitialiser son accès via un lien envoyé par email et revenir à `/login` avec un nouveau mot de passe valide.

## Actors
- Employé : assistante maternelle ayant un compte existant en table `Employee` et ayant oublié son mot de passe

## Functional Needs
- SFD-1: L'utilisateur accède à la page `/forgot-password` depuis le lien "Mot de passe oublié" de l'écran `/login`
- SFD-2: L'utilisateur saisit son email et soumet la demande de réinitialisation
- SFD-3: Le système génère un lien de réinitialisation à durée limitée et l'envoie par email à l'adresse fournie si elle correspond à un compte existant
- SFD-4: Le système affiche systématiquement le message "Si un compte existe, un email a été envoyé" sans révéler si l'email existe en base
- SFD-5: L'utilisateur clique sur le lien reçu par email et accède à la page de saisie d'un nouveau mot de passe
- SFD-6: L'utilisateur saisit un nouveau mot de passe et sa confirmation
- SFD-7: Le système valide la complexité du nouveau mot de passe et la cohérence de la confirmation
- SFD-8: Le système met à jour le mot de passe en table `Employee` (hashé) après validation
- SFD-9: Le lien de réinitialisation est invalidé après usage
- SFD-10: L'utilisateur est redirigé vers `/login` après succès et peut s'y connecter avec son nouveau mot de passe
- SFD-11: Un lien de réinitialisation expiré ou déjà consommé déclenche un message d'erreur clair invitant à recommencer la demande

## Business Rules
- BR-1: le message de succès affiché après demande de réinitialisation est générique et ne révèle jamais l'existence d'un compte
- BR-2: le lien de réinitialisation a une durée de vie limitée et est invalidé après usage
- BR-3: le nouveau mot de passe est stocké uniquement sous forme de hash sécurisé, jamais en clair
- BR-4: le nouveau mot de passe doit respecter la même politique de complexité que celle de la création de compte
- BR-5: aucune information technique (stack trace, identifiant interne, exception) n'est exposée dans les messages d'erreur visibles à l'utilisateur

## Acceptance Criteria
- AC-1: la page `/forgot-password` affiche un champ email et un bouton "Envoyer le lien"
- AC-2: après soumission, l'utilisateur voit le message "Si un compte existe, un email a été envoyé" quel que soit le résultat backend
- AC-3: un email est envoyé à l'adresse fournie si elle correspond à un compte existant et contient un lien de réinitialisation
- AC-4: un clic sur un lien valide affiche la page de saisie d'un nouveau mot de passe avec champ et confirmation
- AC-5: une confirmation différente du nouveau mot de passe affiche un message de validation
- AC-6: un nouveau mot de passe ne respectant pas la complexité affiche un message de validation
- AC-7: après succès, l'utilisateur est redirigé vers `/login` et peut s'y connecter avec son nouveau mot de passe
- AC-8: un lien expiré ou déjà consommé affiche un message d'erreur clair invitant à recommencer la demande
- AC-9: un lien valide ne peut être utilisé qu'une seule fois

## Dependencies
- spec-connexion : navigation depuis et vers `/login`

## Functional Deliverables
- FD-1: écran `/forgot-password` avec formulaire email
- FD-2: envoi d'un email contenant un lien de réinitialisation à durée limitée
- FD-3: écran de saisie d'un nouveau mot de passe accessible via le lien reçu
- FD-4: mise à jour persistante du mot de passe en table `Employee` (hashé)
- FD-5: redirection automatique vers `/login` après succès

## Out of Scope
- réinitialisation par SMS ou téléphone
- codes OTP / authenticator
- récupération d'identifiant (login oublié)
- modification du mot de passe par l'utilisateur déjà connecté (changement volontaire en session)
- rôles Admin et Parent (extensions futures)
