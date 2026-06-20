# Project Stack — AspxDemo Migration (C1)

## Project Config
# AspxDemo legacy migration vers combo C1 SDD_Pro (2026-06-10).
# Mobile stack precedent sauvegarde : stack.md.bak-mobile-2026-06-10.
# Backup C1 ant'erieur si existait : stack.md.bak-pre-mobile.
AppName: AspxDemoFront
FrontendName: AspxDemoFront
FrontendLocalPort: 5173
BackendName: AspxDemoBack
BackendLocalPort: 5099
LibStrategy: shared          # back-front separes => Lib DTO partagee (C1 standard)
LibName: AspxDemoLib
PlanReviewDefault: false

# Pas de DB local — AspxDemo consomme dummyjson.com + jsonplaceholder.com
# Le backend agit en proxy/cache HTTP simple (capability http-client).
Capabilities: http-client

QAMode: full
CoverageMin: 80
MaxParallel: 2

# Caps fail-fast pour POC reproductible
MaxCostPerRun: 30
BuildLoopMaxCostUsd: 10
BuildLoopMaxIter: 2

CodeReviewFailOn: serious
SecurityFailOn: critical
SpecComplianceFailOn: critical
ArchReviewFailOn: serious

UsGranularityTarget: 3
SecurityScanEnabled: true
CodeReviewMode: full
SecurityMode: full
SpecComplianceMode: full
ArchReviewMode: manual
A11yMode: "off"
PerfMode: "off"
PlanCacheStrict: true

## Active Architecture Pattern
 - .claude/stacks/archi/mvc.md

## Active Tech Specs
# Combo C1 = backend .NET MinimalAPI + frontend React + UI shadcn + QA xUnit + auth local
 - .claude/stacks/backend/dotnet-minimalapi.md
 - .claude/stacks/frontend/react.md

## Active UI Specs
 - .claude/stacks/ui/shadcn.md

## Active QA Specs
 - .claude/stacks/qa/dotnet-xunit.md
 - .claude/stacks/qa/node-vitest.md
 - .claude/stacks/qa/code-quality.md

## Active Auth Specs
# Auth-local pour le POC migration (azure-ad activable en prod plus tard).
 - .claude/stacks/auth/auth-local.md
 - AUTH_JWT_AUDIENCE: AspxDemo
 - AUTH_JWT_EXPIRATION: 8
 - AUTH_JWT_ISSUER: AspxDemoBack
 - AUTH_JWT_SECRET: AspxDemoSuperSecret@2026-06-10!ChangeMeBeforeProd

## Active Database
# AspxDemo legacy ne persiste aucune donnee (consomme APIs externes).
# DatabaseType: none disable l'integration EF Core / migrations DB.
 - DatabaseType: none

## Active External APIs
# Sources de donnees consommees par les FEATs reverse-engineered :
 - EXTERNAL_API_DUMMYJSON: https://dummyjson.com
 - EXTERNAL_API_JSONPLACEHOLDER: https://jsonplaceholder.typicode.com
