# Recette — ASP.NET MVC classique (System.Web.Mvc)

## Quand l'utiliser

Détection `dotnet-mvc` dans `inventory.json.languagesDetected`. Présence `.cshtml` (Razor) + `Controllers/*Controller.cs` + `Web.config` ou `Startup.cs`.

## Pré-conditions

- `Controllers/*Controller.cs` (au moins 1 contrôleur)
- `Views/*/*.cshtml` (Razor views)
- `Web.config` ou `Startup.cs` (DI + routes)
- `Models/*.cs` ou `ViewModels/*.cs` (DTOs métier)

## Pièges connus

| Piège | Mitigation Phase 3 |
|---|---|
| Route attributes vs convention | Lire `[Route]` ET `RouteConfig.cs` ; si conflit, attribut gagne |
| ViewModels vs Models | ViewModel = ce que la vue rend, Model = entité persistée. Distinguer dans FEAT |
| `ActionFilter` cross-cutting | Capturer comme BR (ex. `[Authorize]` → BR sur le périmètre authentifié) |
| Partial views | Composants, jamais une FEAT à part |
| `TempData` cross-request | State volatile, capturer comme observation Phase 2 audit |

## Heuristiques d'extraction

1. **1 Controller ≈ 1 unité fonctionnelle** sauf si CRUD complet → 1 unité par scénario CRUD utilisateur cohérent
2. AC depuis méthodes Action :
   - `[HttpGet]` → 1 AC sur l'affichage initial
   - `[HttpPost] + ModelState.IsValid` → AC validation
   - `RedirectToAction` → AC sur le routage post-action
3. BR depuis :
   - Validation Data Annotations (`[Required]`, `[Range]`, `[RegularExpression]`)
   - `[Authorize(Roles=...)]` → BR sur rôles
4. Entities :
   - `DbSet<X>` dans le `DbContext` (EF Code-First) ou `*.edmx` (DB-First)
   - `Models/*.cs` avec `[Key]` + `[ForeignKey]`

## Recommandations Phase 5

- Si plusieurs ViewModels par controller → vérifier que chaque ACs spécifie quel VM est en jeu
- `## Project Config` cible : `dotnet-minimalapi` + `react` ou `blazor-webassembly`
- Routes `MapRoute` legacy → la Phase 6 régénérera via minimal API (changement de paradigme)

## Exemple

Legacy `AccountController.cs` (extrait) :
```csharp
[HttpPost]
public ActionResult Login(LoginViewModel model)
{
    if (!ModelState.IsValid) return View(model);
    var user = _repo.Find(model.Username);
    if (user != null && _hasher.Verify(model.Password, user.PasswordHash)) {
        FormsAuthentication.SetAuthCookie(model.Username, false);
        return RedirectToAction("Index", "Home");
    }
    ModelState.AddModelError("", "Identifiants incorrects");
    return View(model);
}
```

Extrait FEAT :
```markdown
- **AC-1** Given LoginViewModel valide + credentials corrects, when POST /Account/Login, then cookie d'auth est posé et redirect Home/Index. <!-- evidence: Controllers/AccountController.cs:4-7 --> <!-- confidence: high -->
- **AC-2** Given credentials invalides, when POST /Account/Login, then ModelState reçoit "Identifiants incorrects" et View(model) re-rendue. <!-- evidence: Controllers/AccountController.cs:8-9 --> <!-- confidence: high -->
- **BR-1** Validation côté serveur via ModelState (Data Annotations sur LoginViewModel). <!-- evidence: Models/LoginViewModel.cs --> <!-- confidence: high -->
- **BR-2** Mot de passe hashé (jamais en clair) via _hasher.Verify contre PasswordHash. <!-- evidence: Controllers/AccountController.cs:5 --> <!-- confidence: high -->
```

Confidence cap : `high`.
