# FEAT: Calc-A-B-C-Android

FEAT ID: 12-Calc-A-B-C-Android
Status: Draft

## Context
FEATs 1-11 ont validé runtime 17 combinaisons web (3 backends REST × 4 fronts SPA + 5 fullstack monolithes). Pour boucler le bench avec un pattern **mobile natif**, on enchaîne sur **Kotlin Android** : application native APK avec layout XML/Compose + Activity Kotlin.

**Note runtime** : le poste de bench n'a **pas** d'Android SDK installé (`ANDROID_HOME` vide, `adb` absent). Le scope est donc **scaffold + cohérence stack**, sans build APK ni test émulateur. La preuve runtime est reportée à un poste avec Android Studio.

## Objective
Scaffolder une application Android native Kotlin avec MainActivity affichant un layout 3 champs (EditText A, EditText B, EditText C readonly) + Button Calculate. Code stack-conforme prêt à builder sur poste avec Android SDK.

## Quantified Goal
- Metric: conformité scaffolding au stack `mobiles/kotlin-android.md` (structure répertoires, libs catalog, conventions)
- Target: 100 % stack-conforme, 0 % runtime testé (SDK absent)
- Deadline: 2026-06-05 (scaffold only)

## Non-Functional Constraints
- Expected volume: n/a (bench)
- Performance SLA: n/a (pas de runtime mesuré)
- Data retention: n/a
- Compliance: n/a
- Integration: aucune (app native autonome, pas de backend externe)
- Degraded mode: n/a

## Actors
- Tech Lead
- Système Mobile (Android): native app Kotlin compilée en APK

## Functional Needs
- SFD-1: MainActivity Kotlin avec `setContent` (Jetpack Compose) ou `setContentView` (XML layout)
- SFD-2: 3 champs A, B, C (Compose `TextField` ou XML `EditText`)
- SFD-3: bouton Calculate déclenche calcul Kotlin in-memory
- SFD-4: C affiché readonly après calcul
- SFD-5: structure projet Android Gradle (build.gradle.kts module:app + settings.gradle.kts + AndroidManifest.xml)

## Business Rules
- BR-1: A et B Int Kotlin (validation try/catch toIntOrNull)
- BR-2: calcul C=A+B in-memory côté app
- BR-3: pas d'authentification, pas de persistance, pas de Room
- BR-4: minSdk 24+ (Android 7+), targetSdk Android 14 (API 34) ou récent

## Acceptance Criteria
- AC-1 (scaffold only) : projet Android Kotlin scaffoldé conforme stack avec build.gradle.kts + MainActivity.kt + AndroidManifest.xml
- AC-2 (scaffold only) : MainActivity contient logique 3 champs + Button Calculate + calcul C=A+B
- AC-3 (deferred runtime) : build APK + lancement émulateur reportés à poste avec Android SDK installé

## Dependencies
- NONE (app native autonome)

## Functional Deliverables
- FD-1: `build.gradle.kts` module:app + plugin android.application + kotlin.android
- FD-2: `MainActivity.kt` avec Compose ou XML layout
- FD-3: `AndroidManifest.xml` déclarant MainActivity comme LAUNCHER
- FD-4: `activity_main.xml` (si XML) avec 3 EditText + Button

## Out of Scope
- Build APK runtime (Android SDK absent)
- Test émulateur ou device physique
- Compose preview (nécessite Android Studio)
- Lint Android (nécessite android-lint plugin runtime)
- Room DB, Hilt DI, Coil image loading (capabilities on-demand non-triggered)
- ngx-translate equivalent (string resources statiques en français)
