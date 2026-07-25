---
generated-by: agent arch
generated-at: {ISO-8601 UTC}
stack-md-hash: {sha256-8-chars}
project-type: shared-lib
project-name: {LibName}
active-stacks: []
---

# {LibName} — Shared Library Context

## Rôle
Bibliothèque partagée entre {BackendName} et {AppName} (.NET) : contrats DTOs / Models / Inputs / Outputs.

## Layer → Path Mapping
- DTOs            → DTOs/                  (objets de transport API)
- Inputs          → Inputs/                (payloads de requêtes)
- Outputs         → Outputs/               (payloads de réponses)
- Models          → Models/                (modèles partagés)

## Build Command
{build command — ex. dotnet build {LibName}.csproj --nologo}

## Conventions
- Aucune dépendance vers EF Core, ASP.NET, ou frameworks UI.
- Aucune logique métier — uniquement des structures de données et validations Data Annotations.
- Référencé par {BackendName}.csproj et {AppName}.csproj (Blazor).

## Notes
- Ce fichier est régénéré à chaque /arch-init.
