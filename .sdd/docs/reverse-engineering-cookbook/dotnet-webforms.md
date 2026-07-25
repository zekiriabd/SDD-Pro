# Recette — ASP.NET WebForms (.NET Framework legacy)

## Quand l'utiliser

Détection `aspx-webforms` dans `inventory.json.languagesDetected`. Présence `.aspx` + `.aspx.cs` + `Web.config`.

## Pré-conditions

- `.aspx` + `.aspx.cs` code-behind associés (sans CB, extraction incomplète)
- `Web.config` (auth Forms, connection strings)
- Idéalement `App_Code/*.cs` + `Scripts/*.sql`

## Pièges connus

| Piège | Mitigation Phase 3 |
|---|---|
| ViewState magique entre postbacks | Bias toward present : ne pas extrapoler, capturer uniquement `Session[]` + `OnClick` observables |
| Code-behind > 1000 LOC | Unité trop large → suggérer split via `<!-- recommandation: split U-N -->` |
| UpdatePanel AJAX | Chaque UpdatePanel = écran Phase 4 distinct |
| Master pages | Composant transverse, jamais une FEAT à part |
| Server controls custom | Conserver IDs legacy + commentaire HTML legacy |
| `Page_Load(!IsPostBack)` | 2 chemins distincts : GET initial vs postback |

## Heuristiques d'extraction

1. 1 page `.aspx` ≈ 1 unité (sauf grid+form = 2, wizard = 1 avec N écrans)
2. AC depuis évènementiel : `btnX_Click` → 1 AC par chemin handler
3. BR depuis `Web.config` : `<authentication>` + `<authorization>`
4. Entities depuis `App_Code/DataAccess.cs` (ADO.NET) + `Scripts/*.sql` + `DbSet<X>` (EF)

## Recommandations Phase 5

- Vérifier couverture handlers (10 handlers → ≥ 10 ACs probablement)
- `## Project Config` cible : `dotnet-minimalapi` + `blazor-webassembly` ou `react`
- ViewState n'a pas d'équivalent moderne — accepter omission

## Exemple

Legacy `Login.aspx.cs` :
```csharp
protected void btnLogin_Click(object sender, EventArgs e) {
    int? userId = DataAccess.ValidateUser(txtUsername.Text, txtPassword.Text);
    if (userId.HasValue) {
        Session["UserId"] = userId.Value;
        Response.Redirect("Default.aspx");
    } else { lblError.Text = "Identifiants incorrects"; }
}
```

Extrait FEAT :
```markdown
- **AC-1** Given Username + Password valides, when btnLogin cliqué, then Session["UserId"] créée et redirect Default.aspx. <!-- evidence: Login.aspx.cs:3-6 --> <!-- confidence: high -->
- **AC-2** Given identifiants invalides, when btnLogin cliqué, then lblError affiche "Identifiants incorrects". <!-- evidence: Login.aspx.cs:7 --> <!-- confidence: high -->
- **BR-1** Auth via DataAccess.ValidateUser comparant PasswordHash table Users. <!-- evidence: App_Code/DataAccess.cs:18-32 --> <!-- confidence: high -->
```

Confidence cap : `high` (cf. `language_signatures.yml`).
