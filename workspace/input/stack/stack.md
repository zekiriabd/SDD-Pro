# Project Stack

## Project Config
# FrontendName/BackendName = nom des projets ; AppNamespace/BackendNamespace
# auto-dérivés (= nom de projet, cf. CLAUDE.md §1 + file-ownership.md §1.bis).
# Pour fullstack : drop le suffixe "Front" (ex. CMSPrintFront → CMSPrint).
AppName: CMSPrintFront
FrontendName: CMSPrintFront
FrontendLocalPort: 5185
BackendName: CMSPrintBack
BackendLocalPort: 44328
LibStrategy: openapi-codegen
PlanReviewDefault: true
QAMode: full
CoverageMin: 80
MaxParallel: 4
SecurityScanEnabled: false
# v6.10.5 audit 2026-05-19 — activation chemin From-Plan Strict (Sonnet 4.6)
# Fallback Opus automatique si plan v1 ou ## Inline Digest manquant via
# validate_plan.py --strict. Cf. config.base.yml et ADR governance-major-
# devstar-strict-dry.
PlanCacheStrict: true

# v6.10.5 fix CRIT-1 (2026-05-19) — auditors manquants en CMSPrint.
# Defaults phase_planner.py = "manual" pour code_review et spec_compliance
# → auditors skippés silencieusement. On les force à "full" côté projet.
# A11yMode/PerfMode déjà à "full" par défaut planner (cohérent avec
# a11y-report.md + perf-report.md déjà produits pour les 4 FEATs).
# SecurityMode reste "manual" (SecurityScanEnabled: false explicite).
# ArchReviewMode pris en compte uniquement par /sdd-review (sdd-full.md L560).
CodeReviewMode: full
SpecComplianceMode: full
ArchReviewMode: full
A11yMode: full
PerfMode: full

## Active Architecture Pattern
# 1 seul pattern actif. Scope = backend/* déclaré.
 - .claude/stacks/archi/ddd.md
# - .claude/stacks/archi/mvc.md
# - .claude/stacks/archi/microservice.md



## Active Tech Specs
# AppType auto-détecté depuis les stacks ci-dessous (v6.7.7+) :
 - .claude/stacks/backend/kotlin-spring-boot.md
 - .claude/stacks/frontend/react.md
# - .claude/stacks/fullstack/kotlin-spring-boot.md
# - .claude/stacks/backend/dotnet-minimalapi.md 
# - .claude/stacks/mobiles/react-native.md
# - .claude/stacks/mobiles/maui.md
# - .claude/stacks/fullstack/blazor-server.md
# - .claude/stacks/fullstack/next.md
# - .claude/stacks/fullstack/nuxt.md
# - .claude/stacks/fullstack/angular-universal.md
# - .claude/stacks/fullstack/kotlin-mustache.md
# - .claude/stacks/fullstack/node-react.md

## Active UI Specs
# Requis uniquement pour back-front + frontend web. Ignoré pour mobile/fullstack.
 - .claude/stacks/ui/shadcn.md
# - .claude/stacks/ui/vuetify.md
# - .claude/stacks/ui/radzen-blazor.md

## Active QA Specs
# Frameworks de test auto-détectés depuis les stacks runtime déclarés ci-dessus (v6.7.7+) :
 - .claude/stacks/qa/kotlin-junit.md
 - .claude/stacks/qa/node-vitest.md
 - .claude/stacks/qa/code-quality.md

#  - .claude/stacks/qa/dotnet-xunit.md
# - .claude/stacks/qa/python-pytest.md
# - .claude/stacks/qa/angular-jasmine.md
# - .claude/stacks/qa/blazor-bunit.md

## Active Auth Specs
# 1 seul profil auth actif (azure-ad et auth-local mutuellement exclusifs).
# - .claude/stacks/auth/auth-local.md
# - AUTH_JWT_AUDIENCE:Demo
# - AUTH_JWT_EXPIRATION:4
# - AUTH_JWT_ISSUER:DemoBack
# - AUTH_JWT_SECRET:DemoSuperSecretKey@2024!XYZ789AbcDef012345678

 - .claude/stacks/auth/azure-ad.md
 - AZ_TENANTID:"<AZ_TENANTID>"
 - AZ_CLIENTID:"<AZ_CLIENTID>"
 - AZ_DOMAIN:"demo.com"
 - AZ_AUDIENCES:"'<AZ_CLIENTID>', '<AUDIENCE_ID>'"
 - AZ_BE_CALLBACKPATH:"/signin-oidc"
 - AZ_FE_CALLBACKPATH:"/login-callback"

## Active Database
# DatabaseType ∈ {none, SqlServer, PostgreSql, MySql, Sqlite, MariaDb, Oracle, MongoDb}
 - DatabaseType: postgres
 - DB_HOST:127.0.0.1
 - DB_NAME:CMSPrint
 - DB_PASSWORD:***REMOVED***
 - DB_PORT:5432
 - DB_USER:postgres

## Active SMTP Server
# Optionnel. Activé si une AC d'US mentionne email/notification/contact.
 - SMTP_HOST:${SMTP_HOST}
 - SMTP_PORT:587
 - SMTP_USER:***REMOVED***
 - SMTP_PASSWORD:***REMOVED***
 - SMTP_FROM:no-reply@demoapp.fr
 - SMTP_FROM_NAME:Demo
 - SMTP_USE_STARTTLS:true
