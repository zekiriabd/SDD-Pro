# FEAT: Calc-A-B-C-ReactNative

FEAT ID: 16-Calc-A-B-C-ReactNative
Status: Draft

## Context
FEAT 15 a livré MAUI Windows desktop (workloads .NET MAUI installés → build natif réussi). Pour boucler les 3 stacks `mobiles/*`, on enchaîne sur **React Native via Expo** (`create-expo-app`), qui supporte Android + iOS + **Web** out-of-box. Sans Android SDK ni Xcode, on peut quand même runtime-tester via `expo start --web`.

## Objective
Scaffolder une app React Native + Expo avec composante calc (3 champs A/B/C), démarrer en mode web sur :44399, consommer le backend FastAPI :44329 via `fetch`. Démontre le pattern cross-platform JS (1 codebase RN → iOS + Android + Web).

## Quantified Goal
- Metric: app Expo runtime en mode web, fetch backend FastAPI fonctionnel
- Target: `npx expo start --web --port 44399` → page web avec form Calc → fetch C OK
- Deadline: 2026-06-05

## Non-Functional Constraints
- Expected volume: n/a
- Performance SLA: page web Expo chargée < 5s (Metro bundler)
- Data retention: n/a
- Compliance: n/a
- Integration: FastAPI :44329 — mode web peut nécessiter CORS allowlist :44399 (différent vs apps natives)
- Degraded mode: backend down → alerte UI

## Actors
- Tech Lead
- Système Mobile (React Native Expo): cross-platform RN web/iOS/Android

## Functional Needs
- SFD-1: scaffold `npx create-expo-app@latest`
- SFD-2: composante React Native avec `<TextInput>` × 3 + `<Button>`
- SFD-3: `fetch('http://localhost:44329/api/calc')` côté composant
- SFD-4: mode web Expo testé runtime (port :44399)
- SFD-5: TypeScript via template par défaut Expo

## Business Rules
- BR-1: A et B int (parseInt avec validation)
- BR-2: calcul C côté backend FastAPI
- BR-3: pas d'auth
- BR-4: Expo SDK 53+ (latest) + React Native 0.76+ (architecture nouvelle Fabric/TurboModules)

## Acceptance Criteria
- AC-1: scaffolding `create-expo-app` OK + npm install
- AC-2: `npx expo start --web --port 44399` démarre Metro + sert la web app sur :44399
- AC-3: saisir A=5 B=5 dans web app → Calculate → fetch :44329/api/calc → C=10 affiché

## Dependencies
- 1-Calc-A-B-C
- 13-Calc-Backend-Python (FastAPI actif :44329)

## Functional Deliverables
- FD-1: scaffolding Expo + template default
- FD-2: `app/index.tsx` ou `App.tsx` customisé Calc
- FD-3: CORS allowlist FastAPI étendue à :44399 (si web Expo nécessite)

## Out of Scope
- Build APK/iOS natif (Android SDK/Xcode absents)
- Tests E2E Detox
- Expo Router routing avancé
- Auth Expo Authentication
