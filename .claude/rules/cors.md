# Règle — CORS (cross-origin obligatoire SPA ↔ backend)

## Principe

Dès qu'une SPA (React/Vue/Angular/Blazor WebAssembly) est servie sur
une origin différente du backend (typiquement dev `:5173` ↔ `:8080`,
prod `app.example.com` ↔ `api.example.com`), une **configuration CORS
explicite côté backend est OBLIGATOIRE**.

Sans elle, **toute requête `fetch`/`XHR` échoue silencieusement** avec
`TypeError: Failed to fetch` côté navigateur, page blanche error
boundary, backend logs vides (le préflight `OPTIONS` est rejeté avant
d'atteindre les handlers applicatifs).

Cette règle est **load-bearing** pour tout projet `appType: back-front`
avec `frontendKind: web` ou `mobile`. Sans elle, le contrat front↔back
est cassé en runtime.

---

## 1. Quand cette règle s'applique

| Cas | CORS requis ? |
|---|:---:|
| SPA + API séparés (`backend/*` + `frontend/*`) | ✅ OBLIGATOIRE |
| Mobile + API (`backend/*` + `mobiles/*`) | ✅ OBLIGATOIRE (origins `capacitor://`, `ionic://`, etc.) |
| Fullstack monolithique (`fullstack/blazor-server`, `next` SSR) | ❌ N/A (même origin) |
| Backend headless (sans SPA) | ❌ N/A |

L'agent `arch` détecte le cas à partir de `## Active Tech Specs` du
`stack.md` (cf. CLAUDE.md §7 matrice de détection AppType).

### 1.bis Auto-injection arch (depuis v6.10.4)

L'agent `arch` STEP 4.5.6 propage automatiquement l'origin du frontend dev dans
la config backend (allowlist explicite, jamais de wildcard). Mapping :

| Frontend stack | Port dev | Origin injectée |
|---|---:|---|
| `react`, `vue` | 5173 | `http://localhost:5173` |
| `angular` | 4200 | `http://localhost:4200` |
| `blazor-webassembly` | 5097 | `http://localhost:5097` |

**Override possible** dans `## Project Config` de `stack.md` :
```yaml
Cors:AllowedOrigins: "http://localhost:5173,http://localhost:4173"
```
Si la clé est posée explicitement → arch préserve la valeur (User-set wins).

Détail algorithme : `agents/arch.md §4.5.6`.

---

## 2. Pattern correct par stack backend

### 2.1 .NET (dotnet-minimalapi)

`Program.cs` :
```csharp
var allowedOrigins = builder.Configuration["Cors:AllowedOrigins"]?
    .Split(',', StringSplitOptions.RemoveEmptyEntries)
    ?? ["http://localhost:5173"];

builder.Services.AddCors(options => options.AddPolicy("Spa", policy =>
    policy.WithOrigins(allowedOrigins)
          .AllowAnyHeader()
          .AllowAnyMethod()
          .AllowCredentials()));

// après UseRouting, avant UseAuthorization
app.UseCors("Spa");
```

`appsettings.json` / env `Cors__AllowedOrigins=http://localhost:5173,http://localhost:4173`.

### 2.2 Spring Boot (kotlin-spring-boot)

Bean dédié `CorsConfig.kt` :
```kotlin
@Configuration
class CorsConfig(
    @Value("\${APP_CORS_ALLOWED_ORIGINS:http://localhost:5173,http://localhost:4173}")
    private val allowedOriginsCsv: String,
) {
    @Bean
    fun corsConfigurationSource(): CorsConfigurationSource {
        val config = CorsConfiguration().apply {
            allowedOrigins = allowedOriginsCsv.split(",").map { it.trim() }
            allowedMethods = listOf("GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH")
            allowedHeaders = listOf("*")
            allowCredentials = true
            maxAge = 3600
        }
        return UrlBasedCorsConfigurationSource().apply { registerCorsConfiguration("/**", config) }
    }
}
```

Activer dans `SecurityConfig.kt` :
```kotlin
http.cors { } // utilise le bean ci-dessus
```

### 2.3 FastAPI (python-fastapi)

`main.py` :
```python
from fastapi.middleware.cors import CORSMiddleware
import os

allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 2.4 Node Express (node-express)

`server.ts` :
```typescript
import cors from "cors";

const allowedOrigins = (process.env.CORS_ALLOWED_ORIGINS ?? "http://localhost:5173").split(",");

app.use(cors({
  origin: allowedOrigins,
  credentials: true,
  methods: ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
}));
```

---

## 3. Alternative dev — Vite proxy (sans CORS backend)

Si le projet veut éviter la config CORS backend en dev (mais doit
quand même la faire en prod), Vite peut proxifier l'API :

`vite.config.ts` :
```typescript
export default defineConfig({
  server: {
    proxy: {
      "/api": { target: "http://localhost:8080", changeOrigin: true },
    },
  },
});
```

**Limite stricte** : cette alternative ne supprime PAS le besoin CORS en
prod (où le proxy Vite n'existe pas). Garder la config CORS backend
même si proxy actif en dev — sinon dérive prod garantie.

---

## 4. Anti-patterns rejetés

| Anti-pattern | Pourquoi rejeté |
|---|---|
| `@CrossOrigin` annotation Spring sur controllers individuels | Fragmente la policy, oubli systématique sur nouveaux endpoints |
| `Access-Control-Allow-Origin: *` avec `AllowCredentials: true` | Spec CORS interdit cette combinaison (cookies refusés) |
| Allowed origins hardcodés dans le code | Doit venir de config/env (différent dev/prod) |
| Pas de `OPTIONS` preflight en allowed methods | Requêtes credentialled échouent silencieusement |
| Wildcard `*` sur `allowedHeaders` en prod avec credentials | Refusé par les navigateurs récents |
| CORS uniquement via reverse proxy (nginx, IIS) sans backup applicatif | Casse en dev local + tests intégration |

---

## 5. Vérification dev-backend / arch

### Pattern à grep en STEP build

```bash
# Backend Spring (Kotlin)
grep -r "@CrossOrigin" workspace/output/src/{BackendName}/ && WARN

# Backend .NET
grep -r "AddCors\|UseCors" workspace/output/src/{BackendName}/ || ERROR (manquant)

# FastAPI
grep -r "CORSMiddleware" workspace/output/src/{BackendName}/ || ERROR

# Node Express
grep -r "cors()" workspace/output/src/{BackendName}/ || ERROR
```

### Format ERROR

Préfixe `[SECURITY_CORS_MISSING]` (cf. `error-classification.md §1.6`
ou §1.11 selon contexte) :

```
ERROR: dev-backend {n}-{m} — CORS non configuré
CAUSE: [SECURITY_CORS_MISSING] backend SPA-facing sans config CORS — toute requête front échouera
FIX: ajouter Program.cs/CorsConfig.kt/main.py selon stack §2.{1..4}
     configurer CORS_ALLOWED_ORIGINS env var (csv des origins SPA dev + prod)
HINT: cf. .claude/rules/cors.md §2 pour le pattern stack-aware
```

---

## 6. Test d'acceptation

Toute FEAT impliquant un appel SPA→backend doit avoir au moins 1 AC
implicite couvert par cette règle :

> Given une SPA servie sur origin `X` et un backend sur origin `Y`,
> when la SPA envoie une requête fetch credentialled vers Y,
> then le préflight OPTIONS retourne 204/200 avec les headers
> `Access-Control-Allow-Origin: X` et `Access-Control-Allow-Credentials: true`,
> et la requête principale aboutit.

À matérialiser dans la phase QA API Gate (cf. `backend-first.md §1.1`).

---

## 7. Lien avec autres règles

- `backend-first.md` : la QA API Gate doit inclure ≥ 1 test CORS
  preflight (OPTIONS avec Origin) par endpoint exposé à la SPA.
- `source-first.md §1` : tout bug CORS en runtime → patch ce
  `rules/cors.md` (si gap) AVANT le fix code.
- `stack-completeness.md` : la lib CORS (Microsoft.AspNetCore.Cors,
  spring-security-config, fastapi[all], cors npm) est CORE de tout
  backend SPA-facing.

---

## 8. Source historique

Convention extraite du post-mortem CMS-Back 2026-05-11 (cf.
`source-first.md §1`) où CORS oublié sur Spring Boot avait causé
3 jours de debug sur projet client. Pattern canonique inliné aussi dans
`stacks/auth/azure-ad.md §5.2.7.9`.
