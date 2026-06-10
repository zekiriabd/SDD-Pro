# Recette — Delphi (source .pas + .dfm)

## Quand l'utiliser

Détection `delphi-source` dans `inventory.json.languagesDetected`. Présence `.pas` (Pascal) + `.dfm` (Delphi Form Module) + `.dpr` (Delphi project).

## Pré-conditions

- `.pas` + `.dfm` co-localisés (même nom : `UnitLogin.pas` + `UnitLogin.dfm`)
- `*.dpr` (entry point)
- (Idéalement) accès au schéma DB natif Borland (BDE, FireDAC, ADO)

## Pièges connus

| Piège | Mitigation Phase 3 |
|---|---|
| **Composants visuels custom** dans `.dfm` (TMyGrid, TCustomEdit) | Conserver le nom de composant + commentaire `<!-- legacy: TMyGrid id=X -->` Phase 4 |
| **Database connections natives** (BDE/FireDAC/ADO) | Phase 2 audit : extraire connection strings ; entities via mapping `TDataset.FieldDefs` |
| **Triggers visuels** dans `.dfm` (`OnClick = ButtonClick`) | Le handler est dans le `.pas` correspondant — toujours suivre la pair |
| **Variables globales unit-scope** (`var X: Integer;`) | Capturer comme état observable — la migration Phase 6 devra les éliminer |
| **Sections `interface` vs `implementation`** | Capturer uniquement ce qui est public dans `interface` pour les "deliverables" |
| **Strings ressources externes** (.RES, .DRC) | Pas de scan deep, capturer comme dépendance externe |

## Heuristiques d'extraction

1. **1 fenêtre principale (TForm dans .dfm) ≈ 1 unité fonctionnelle**
2. AC depuis :
   - Event handlers `procedure TForm.ButtonClick(Sender: TObject)` → 1 AC par branche
   - `Application.MessageBox` → AC sur dialogues
   - `OnShow`/`OnClose` → init/teardown observable
3. BR depuis :
   - Composants `TQuery` / `TADOQuery` avec SQL inline (`SQL.Text`)
   - Composants validation (`TValidator`, `TMaskEdit.EditMask`)
   - Triggers DB sur `TDataset` (`BeforePost`, `AfterPost`)
4. Entities :
   - Définitions `TDataset` avec `FieldDefs` (champs + types)
   - Tables BDE/FireDAC référencées (cherche `.SQL.Text := 'SELECT ... FROM ...'`)
   - Schemas externes `*.dpr` + `*.sql` côté serveur si applicable

## Recommandations Phase 5

- Vérifier que chaque composant `TMyXyz` custom a une note Phase 4 — sinon `dev-frontend` ne saura pas mapper
- `## Project Config` cible : difficile (Delphi → toute stack moderne). Souvent `dotnet-minimalapi` + `blazor-webassembly` ou `node-express` + `react`. Décision Tech Lead
- Bibliothèques propriétaires (Indy, JediVCL, ExpressBars) : à reproduire en JS/.NET côté cible — Phase 6 décide
- Si le `.dfm` est en format binaire (legacy Delphi 5-7), exporter en text d'abord (`convert.exe`)

## Exemple

Legacy `UnitLogin.pas` + `UnitLogin.dfm` :

`.dfm` (extrait) :
```
object FormLogin: TFormLogin
  Caption = 'Connexion'
  object EditUser: TEdit
    Name = 'EditUser'
  end
  object EditPass: TEdit
    PasswordChar = '*'
  end
  object ButtonOK: TButton
    Caption = 'Se connecter'
    OnClick = ButtonOKClick
  end
end
```

`.pas` (extrait) :
```pascal
procedure TFormLogin.ButtonOKClick(Sender: TObject);
var UserId: Integer;
begin
  UserId := DataAccess.ValidateUser(EditUser.Text, EditPass.Text);
  if UserId > 0 then begin
    GlobalState.CurrentUserId := UserId;
    ModalResult := mrOk;
  end else
    ShowMessage('Identifiants incorrects');
end;
```

Extrait FEAT :
```markdown
- **AC-1** Given EditUser + EditPass remplis avec credentials valides, when ButtonOK cliqué, then GlobalState.CurrentUserId est assignée et ModalResult = mrOk (fermeture validée). <!-- evidence: UnitLogin.pas:4-7 --> <!-- confidence: high -->
- **AC-2** Given credentials invalides, when ButtonOK cliqué, then ShowMessage('Identifiants incorrects'). <!-- evidence: UnitLogin.pas:8 --> <!-- confidence: high -->
- **BR-1** Validation utilisateur déléguée à DataAccess.ValidateUser (logique métier dans unit DataAccess). <!-- evidence: UnitLogin.pas:4 + UnitDataAccess.pas:N --> <!-- confidence: high -->
- **BR-2** État global du user via singleton GlobalState (variable unit-scope partagée). <!-- evidence: UnitLogin.pas:6 --> <!-- confidence: high -->
- **FD-1** Formulaire FormLogin avec EditUser + EditPass (mask='*') + ButtonOK. <!-- evidence: UnitLogin.dfm:3-13 --> <!-- confidence: high -->
```

Confidence cap : `high` (Delphi source intact, mapping clair).
