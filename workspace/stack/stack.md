# Project Stack

## Project Config
AppName: test-admin
FrontendName: test-admin
FrontendLocalPort: ${FrontendLocalPort}
BackendName: bff-admin
BackendLocalPort: ${BackendLocalPort}
LibStrategy: openapi-codegen
PlanReviewDefault: false

# POC test : pas de prisma (stack actif = dotnet-minimalapi + SQLite, EF Core natif)
# Capabilities: prisma  # désactivé v2 stack
# QAMode: full obligatoire pour ROI PoC (mesure coverage exigée critère §5.2)
QAMode: full
CoverageMin: 80
# 2026-07-01 — gaps infra pré-existants (pas de script test/e2e dans package.json)
# Débloqué en warn le temps d'ajouter les scripts manquants (FIX: §7.1 QA report feat-2)
AcceptanceGate: warn
MaxParallel: 10

# Caps fail-fast conservateurs pour bench reproductible
MaxCostPerRun: 30
BuildLoopMaxCostUsd: 10
BuildLoopMaxIter: 2

# Sélectivité audits — focus verdicts bloquants
CodeReviewFailOn: serious
SecurityFailOn: critical
SpecComplianceFailOn: critical
ArchReviewFailOn: serious

# Granularité US — cible 3 US (FEAT M = 3 US par design)
UsGranularityTarget: 3

# Audits actifs (ROI exige scan sécurité réel)
SecurityScanEnabled: true
CodeReviewMode: full
SecurityMode: full
SpecComplianceMode: full
ArchReviewMode: manual
A11yMode: "off"
PerfMode: "off"

## Active Architecture Pattern
  - .sdd/stacks/archi/mvc.md

## Active Tech Specs
 - .sdd/stacks/frontend/react.md
 - .sdd/stacks/backend/kotlin-spring-boot.md

## Active UI Specs
 - .sdd/stacks/ui/shadcn.md

## Active QA Specs
 - .sdd/stacks/qa/node-vitest.md
 - .sdd/stacks/qa/code-quality.md
 - .sdd/stacks/qa/kotlin-junit.md

## Active Auth Specs
# Azure AD (app interne consent-admin)
 - .sdd/stacks/auth/azure-ad.md
 - AZ_TENANTID: ${AZ_TENANTID}
 - AZ_CLIENTID: ${AZ_CLIENTID}
 - AZ_DOMAIN: ${AZ_DOMAIN}
 - AZ_AUDIENCES: ${AZ_AUDIENCES}
 - AZ_BE_CALLBACKPATH: ${AZ_BE_CALLBACKPATH}
 - AZ_FE_CALLBACKPATH: ${AZ_FE_CALLBACKPATH}

## Active Database
# SQL Server (reverse SGBD, lecture seule)
 - DatabaseType: sqlserver
 - DB_HOST: ${DB_HOST}
 - DB_PORT: ${DB_PORT}
 - DB_NAME: ${DB_NAME}
 - DB_USER: ${DB_USER}
 - DB_PASSWORD: ${DB_PASSWORD}

## Active SMTP Server
 - SMTP_HOST: ${SMTP_HOST}
 - SMTP_PORT: ${SMTP_PORT}
 - SMTP_USER: ${SMTP_USER}
 - SMTP_PASSWORD: ${SMTP_PASSWORD}
 - SMTP_FROM: ${SMTP_FROM}
 - SMTP_FROM_NAME: Softweb
 - SMTP_USE_STARTTLS: true

