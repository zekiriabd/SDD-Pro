# Spec: scheduled-jobs (Node.js cron infrastructure + nightly BebeStatut transition)

FEAT ID: 24-Spec-Scheduled-Jobs
Spec ID: spec-scheduled-jobs
Status: Draft

> **Supersedes FEAT 23 FD-7 (SQL Server Agent job `nj_flip_bebe_statut_pending_to_active`)** : déplace la bascule nightly `BebeStatut 1 → 2` de la couche DBA (SQL Server Agent / cron `sqlcmd`) vers la couche applicative Node.js. Justifications : (a) le backend Demo tourne sur Node.js (stack `fullstack/node-react` cf. `workspace/input/stack/stack.md`) — pas de dépendance externe à SQL Server Agent qui peut être absent (Express Edition, hosting managé), (b) observabilité unifiée avec les logs applicatifs (pino structuré), (c) tests d'intégration possibles côté backend (vitest + Prisma `:memory:`), (d) base réutilisable pour de futurs jobs scheduled (relances email, exports périodiques, agrégations de statistiques). Cette FEAT 24 **n'introduit aucun changement de schéma DB ni de contrat HTTP** — seule la mécanique d'exécution change.

## Context

La FEAT 23 `spec-bebe-dactive` a posé la sémantique complète de la colonne `dbo.Contrat.BebeStatut TINYINT NOT NULL DEFAULT 1` (valeurs `{1, 2, 3}` = `{en attente, en garde, clôturé}`). Trois chemins d'écriture coexistent : (1) le wizard de création/édition de contrat calcule `BebeStatut ∈ {1, 2}` côté client à partir de `DateEffetContrat` vs `today`, (2) l'endpoint `POST /cloturer` (FEAT 22) pose `BebeStatut = 3`, (3) un job nightly bascule `1 → 2` quand le jour `DateEffetContrat` est atteint. FEAT 23 SFD-18 proposait initialement de matérialiser ce job comme un SQL Server Agent (avec alternative `cron + sqlcmd`). Cette approche pose 3 problèmes opérationnels dans le contexte Demo :

- **Disponibilité variable** : SQL Server Agent n'est pas disponible sur SQL Server Express (édition gratuite encore utilisée en sandbox/dev) ni sur certaines offres SQL managées (Azure SQL Database serverless basic tier — `dbo.JobAuditLog` lui-même nécessiterait Elastic Jobs en complément, complexité supplémentaire). L'alternative `cron + sqlcmd` reporte le problème côté OS et requiert d'installer `sqlcmd` + de gérer un fichier `.sql` versionné séparément du code applicatif.
- **Observabilité fragmentée** : un job SQL Agent loggue dans MSDB (`sysjobhistory`) ou dans une table métier `dbo.JobAuditLog`. Les logs applicatifs Node.js (stdout structuré pino, agrégateur ELK/Datadog typiquement) ne reçoivent pas ces événements — la corrélation incident (« hier soir le job n'a pas tourné, pourquoi les cards `Noé` sont restées en attente ? ») demande un changement d'outil et de credentials DBA.
- **Couplage DBA / Dev** : chaque modification du script T-SQL (changement de filtre, ajout d'un nouveau job nightly comme une relance email automatique) nécessite une intervention DBA, un re-déploiement de la définition de job, et casse la traçabilité git d'une modification fonctionnelle.

Le backend Demo est un service Node.js (TypeScript) construit avec Express + Prisma (stack `fullstack/node-react`, capability `prisma` forcée cf. `workspace/input/stack/stack.md` ligne 15). Il dispose nativement d'un event loop, d'un système de logs structurés, d'un cycle de vie process gracieux (SIGTERM handler), et d'un orchestrateur de tests (vitest). Y greffer un **scheduler in-process** (ou un **worker process séparé** sous le même monorepo) résout les 3 problèmes ci-dessus avec un coût d'infrastructure nul (pas de service externe à provisionner).

La bibliothèque retenue est **`node-cron`** (~2 KB, sans dépendance native, mainteneu, ~3.5M downloads/semaine au 2026-05) qui expose une API minimaliste `cron.schedule(pattern, handler, options)` compatible avec la syntaxe crontab standard. Les alternatives évaluées et rejetées : (a) `node-schedule` — fonctionnalités équivalentes mais 10× plus de surface API non requise pour ce besoin, (b) `BullMQ` / `Bull` — nécessite Redis (provisioning externe), surdimensionné pour 1 job/jour, (c) `agenda` — nécessite MongoDB, hors stack, (d) cron OS externe (systemd timer / Windows Task Scheduler) — réintroduit le couplage Dev/Ops évité ci-dessus.

Le premier job scheduled implémenté est **`updateContractStatus`** (nom public canonique `UpdateContractStatus` cf. SFD-7) qui exécute chaque nuit à **01:00 heure serveur** la requête SQL paramétrée :

```sql
UPDATE [Contrat] SET [BebeStatut] = 2 WHERE [BebeStatut] = 1 AND [DateEffetContrat] = CAST(GETDATE() AS DATE);
```

Cette requête bascule chaque contrat dont la date d'effet est **le jour courant** (et seulement le jour courant — cf. BR-3 sur la décision `=` strict vs `<=`) de l'état `en attente` vers l'état `en garde`. Le job est **idempotent** par construction (re-exécution sur la même journée matche 0 ligne) et **non-bloquant** (UPDATE bulk paramétré, p95 < 5 secondes sur 10k contrats actifs — héritage NFC FEAT 23). Les transitions ne déclenchent ni notification utilisateur (les employées découvrent la bascule au prochain refresh de `/bebes`, cf. FEAT 23 SFD-17) ni audit applicatif (cf. FEAT 23 BR-11 — seul un audit système optionnel via log structuré pino + table optionnelle `dbo.JobAuditLog` est posé).

La FEAT 24 introduit 3 chantiers cohérents :

1. **Module `scheduler/` côté backend Node.js** — un orchestrateur in-process basé sur `node-cron` qui démarre au boot du serveur Express (après que la connexion DB Prisma est établie), maintient un registre des jobs enregistrés, expose un cycle de vie graceful (start/stop sur SIGTERM/SIGINT), et un endpoint admin optionnel `GET /api/admin/jobs` (read-only, derrière auth, hors scope strict v1 — cf. Out of Scope).
2. **Job concret `updateContractStatus`** — première implémentation utilisant le module scheduler. Pattern cron `0 1 * * *` (chaque jour à 01:00 heure serveur), exécution de la requête SQL paramétrée via Prisma `$executeRawUnsafe` (ou `$executeRaw` avec template literal — cf. SFD-7), logging structuré pino avant/après exécution avec count de lignes affectées, gestion d'erreur avec capture stack trace + log WARN niveau exception (pas de crash process).
3. **Mode d'exécution configurable** — variable d'environnement `SCHEDULER_MODE=embedded|worker|off` permettant : (a) `embedded` (défaut beta) : le scheduler tourne dans le même process que l'API HTTP — simple, robuste pour mono-instance, (b) `worker` : un process Node.js séparé (`npm run start:worker`) ne charge que le scheduler — recommandé si l'API est scalée horizontalement pour éviter N exécutions concurrentes, (c) `off` : le scheduler ne démarre pas — utile en environnement de test ou pour pre-déploiement.

## Objective

L'employée connectée signe un nouveau contrat via le wizard `/contrats/nouveau` (FEAT 6) en saisissant `DateEffetContrat = 15 août 2026` alors que le jour courant est le 30 mai 2026. Le frontend calcule `bebeStatut = 1` (cf. FEAT 23 SFD-16) et le backend INSERT la ligne `Contrat` avec `BebeStatut = 1`. Du 30 mai 2026 au 14 août 2026, la card de Noé apparaît dans `/bebes` en mode désaturé `baby-card--pending` (cf. FEAT 23 SFD-11). Le 15 août 2026 à **01:00 heure serveur**, le scheduler Node.js — qui tourne en mode `embedded` au sein du process Express principal — déclenche le job `updateContractStatus`. Le handler du job ouvre une connexion Prisma (réutilisation du pool existant), exécute la requête SQL paramétrée, récupère le `rowCount` retourné par Prisma (`@@ROWCOUNT` équivalent côté SQL Server via le pilote `tedious`), logge `info: { jobName: 'UpdateContractStatus', rowsAffected: 1, durationMs: 47 }` au format pino structuré, et libère la connexion. L'employée ouvre `/bebes` le 15 août 2026 à 07:30 (heure locale) → le GET `/api/bebes` retourne désormais Noé avec `bebeStatut: 2` → la card est rendue en mode normal avec les boutons `Arrivée` / `Départ` / `Appeler les parents` interactifs (cf. FEAT 23 SFD-11 variante normale). Le pointage de la première arrivée peut commencer.

Le scheduler tourne au démarrage du process backend Node.js (immédiatement après `app.listen()` du serveur Express, conditionné à `SCHEDULER_MODE !== 'off'`). Lors d'un redémarrage du serveur en cours de journée (deploy, restart manuel, crash recovery), le scheduler re-démarre et **n'exécute pas immédiatement le job en rattrapage** (`runOnInit: false` par défaut côté `node-cron`) — il attend la prochaine occurrence du pattern cron (donc le lendemain 01:00). Conséquence : si le serveur est down au moment T = 01:00 d'une date `D` où des contrats devraient basculer, **ces contrats restent en attente jusqu'à T + 24h** au pire. Cette fenêtre est jugée acceptable pour la beta Demo (volume faible, employées ne consultent pas `/bebes` à 01:00 du matin) et matche le compromis déjà accepté en FEAT 23 BR-2 (auto-correction au pire dans les 24h). Une recovery explicite est documentée (cf. SFD-11) : un endpoint admin `POST /api/admin/jobs/UpdateContractStatus/run` (hors scope v1) permet de déclencher manuellement le job une fois après un downtime.

## Quantified Goal (v7.0.0 — anti-GIGO)

- Metric: temps d'exécution `updateContractStatus` (1 requête SQL UPDATE filtrée par index `BebeStatut = 1`) ; coût mémoire du scheduler (1 timer node-cron par job enregistré + handler closure) ; latence de démarrage du backend avec scheduler activé (vs sans).
- Target: p95 `updateContractStatus` < 200 ms sur 100 lignes basculées (volume estimé beta Demo — cf. FEAT 23 NFC) ; consommation mémoire du module scheduler < 5 MB RSS additionnel (1 job, future extension jusqu'à 10 jobs sans dépassement) ; latence de démarrage backend +20 ms max (chargement `node-cron` + `cron.schedule()` register, mesuré sur dev box i7 16GB).
- Deadline: livraison stack `fullstack/node-react × ui/shadcn × auth/auth-local` au 2026-10-31 (aligné FEAT 23 Quantified Goal).

## Non-Functional Constraints (v7.0.0)

- Expected volume: 1 exécution par jour à 01:00 heure serveur (cron pattern `0 1 * * *`) ; volume de lignes basculées par exécution estimé entre 0 et 100 sur la beta Demo entière (toutes employées confondues — cf. FEAT 23 NFC) ; charge SQL Server par exécution équivalente à 1 UPDATE bulk filtré sur index PK, p95 < 5 s sur 10k contrats actifs.
- Performance SLA: l'exécution du job ne doit **jamais bloquer** l'event loop Node.js plus de 5 secondes (target p95 < 200 ms) ; en cas de dépassement, un log WARN est émis (cf. SFD-9) mais le process reste healthy ; aucune requête HTTP entrante n'est bloquée par l'exécution du job (Node.js single-thread mais Prisma utilise un pool I/O asynchrone non bloquant).
- Data retention: aucune nouvelle table créée par cette FEAT ; la table optionnelle `dbo.JobAuditLog` (déjà mentionnée FEAT 23 SFD-18) reste optionnelle et hors scope du code applicatif Node.js — si elle existe, le scheduler peut y écrire en best-effort (cf. SFD-9) ; aucun fichier log persistant côté Node.js (stdout structuré pino capturé par l'orchestrateur de runtime — PM2, Docker logs, systemd journal selon déploiement).
- Compliance: RGPD — le scheduler n'accède à aucune donnée personnelle directe (la requête UPDATE filtre sur `BebeStatut` et `DateEffetContrat`, ne lit ni n'écrit `Prenom` / `Nom` / `DateNaissance`) ; aucune donnée n'est exportée hors de la base ; les logs structurés du scheduler ne contiennent que des compteurs agrégés (`rowsAffected: number`, `jobName: string`, `durationMs: number`) — jamais d'identifiants enfant / parents.
- Integration: extension du process backend Node.js existant (ajout d'un module `scheduler/`) ; aucune nouvelle dépendance externe (Redis, MongoDB, etc.) ; ajout de la dépendance npm `node-cron@^3.0.3` (~2 KB minified, MIT, sans dépendances natives) ; aucun nouveau endpoint HTTP applicatif en v1 (l'endpoint admin `POST /api/admin/jobs/{jobName}/run` est noté Out of Scope).
- Degraded mode: si la connexion Prisma est indisponible au moment T = 01:00 (DB down, network partition), le handler `updateContractStatus` capture l'exception, logge `error: { jobName, error: { message, stack }, durationMs }` au niveau ERROR, et **ne re-tente pas** dans la même exécution (la prochaine occurrence aura lieu 24h plus tard) ; si le scheduler échoue à s'enregistrer au boot (cas conceptuel — pattern cron malformé), un log ERROR est émis et le process backend continue de servir l'API HTTP (le scheduler n'est pas un composant critique pour la disponibilité des endpoints applicatifs) ; si `SCHEDULER_MODE=off` est posé en env, aucune `cron.schedule()` n'est appelée et le module log `info: { schedulerMode: 'off', activeJobs: 0 }` au démarrage — comportement attendu en environnement de test (vitest) et en sandbox dev sans besoin de bascule automatique.

## Actors

- Backend service Node.js (acteur système) : process principal Express qui héberge le scheduler in-process (mode `embedded`) ou process worker dédié (mode `worker`). Identifié par `process.pid` dans les logs structurés. Démarre via `npm run start` (ou `node dist/server.js` en build prod), s'arrête sur SIGTERM/SIGINT avec un graceful shutdown (cf. SFD-12). Aucune interaction utilisateur — l'acteur opère cross-tenant sur toutes les lignes `Contrat` filtrées par `BebeStatut = 1 AND DateEffetContrat = today`.
- DBA / Ops (acteur humain, hors-pipeline) : opérationnel responsable du déploiement et de la supervision. Consulte les logs structurés via l'agrégateur log (ELK, Datadog, ou simplement `pm2 logs` / `docker logs` en beta). Peut désactiver le scheduler en posant `SCHEDULER_MODE=off` dans le fichier `.env` et en redémarrant le service. Peut déclencher manuellement le job une fois après un downtime via un appel direct SQL (`UPDATE Contrat SET BebeStatut = 2 WHERE BebeStatut = 1 AND DateEffetContrat <= CAST(GETDATE() AS DATE)` — recovery élargie avec `<=` au lieu de `=`) en attendant l'implémentation v2 de l'endpoint admin.

## Functional Needs

### Module scheduler — infrastructure cron Node.js

- SFD-1: **Module `scheduler/` créé** sous `workspace/output/src/DemoBack/src/scheduler/` (chemin canonique du stack `fullstack/node-react`). Le module expose une API publique TypeScript :
  ```typescript
  // src/scheduler/index.ts
  export interface ScheduledJob {
    name: string;                    // ID canonique du job (PascalCase, ex. "UpdateContractStatus")
    cronPattern: string;             // pattern crontab 5-segments (ex. "0 1 * * *")
    handler: () => Promise<void>;    // implémentation async, doit gérer ses propres erreurs
    timezone?: string;               // IANA TZ, défaut "Europe/Paris"
    runOnInit?: boolean;             // défaut false — pas d'exécution immédiate au register
  }
  export function registerJob(job: ScheduledJob): void;
  export function startScheduler(): { activeJobs: number; mode: SchedulerMode };
  export function stopScheduler(): Promise<void>;
  export type SchedulerMode = 'embedded' | 'worker' | 'off';
  ```
  Le module utilise `node-cron@^3.0.3` (déjà ajouté aux deps backend dans `package.json` — cf. FD-2). Les jobs sont stockés dans un `Map<string, cron.ScheduledTask>` interne au module (singleton). `registerJob` est idempotent (re-register du même `name` avec un pattern différent log WARN et remplace l'ancienne entrée — utile en hot-reload dev).
- SFD-2: **Initialisation au boot du serveur Express** — `src/server.ts` (entry point de `DemoBack`) appelle `startScheduler()` après le `app.listen()` réussi, dans le même tick d'event loop. La séquence canonique :
  ```typescript
  // src/server.ts (extrait après augment)
  import { registerJob, startScheduler, stopScheduler } from './scheduler';
  import { updateContractStatusJob } from './scheduler/jobs/updateContractStatus';
  // ... existing setup (express, middlewares, routes, Prisma client) ...
  registerJob(updateContractStatusJob);
  const server = app.listen(PORT, () => {
    const { activeJobs, mode } = startScheduler();
    logger.info({ event: 'scheduler.started', activeJobs, mode }, 'Scheduler initialized');
  });
  ```
  L'enregistrement des jobs précède le démarrage du scheduler — pattern « register-then-start » qui garantit qu'aucun timer n'est armé avant que toutes les jobs soient connues.
- SFD-3: **Mode d'exécution `SCHEDULER_MODE`** lu depuis `process.env.SCHEDULER_MODE` au boot via le helper de config existant (typiquement `src/config/env.ts` issu de `dotenv` cf. stack `node-react.md` capability env-vars). Validation Zod :
  ```typescript
  const SchedulerModeSchema = z.enum(['embedded', 'worker', 'off']).default('embedded');
  ```
  Comportement par mode :
  - **`embedded`** (défaut beta) : `startScheduler()` arme effectivement tous les `cron.schedule()` enregistrés. Le scheduler vit dans le process Express principal.
  - **`worker`** : `startScheduler()` log un WARN si appelé depuis le process Express principal (`process.env.NJ_PROCESS_KIND !== 'worker'`) et **ne démarre pas** les timers. Le mode est destiné à un process séparé démarré via `npm run start:worker` qui pose `NJ_PROCESS_KIND=worker` et ne charge **pas** Express (cf. SFD-13).
  - **`off`** : `startScheduler()` retourne `{ activeJobs: 0, mode: 'off' }` sans armer aucun timer. Aucun job ne s'exécutera. Utilisé en environnement vitest et en sandbox dev sans besoin de bascule automatique.
- SFD-4: **Logging structuré pino** — chaque cycle de vie du scheduler logge un événement structuré au format pino JSON :
  - `scheduler.started` : `{ activeJobs: N, mode: 'embedded'|'worker'|'off', timestamp }` au démarrage
  - `scheduler.job.registered` : `{ jobName, cronPattern, timezone }` à chaque `registerJob`
  - `scheduler.job.tick.start` : `{ jobName, scheduledAt: ISO8601 }` avant chaque exécution
  - `scheduler.job.tick.success` : `{ jobName, durationMs, payload }` après succès (`payload` libre, ex. `{ rowsAffected: 5 }` pour `updateContractStatus`)
  - `scheduler.job.tick.error` : `{ jobName, durationMs, error: { message, stack, code? } }` après exception
  - `scheduler.stopped` : `{ stoppedJobs: N, durationMs }` au shutdown
  Le logger pino est l'instance partagée du backend (configurée centralement dans `src/logger.ts` héritage stack `node-react.md`).
- SFD-5: **Timezone serveur** — tous les patterns cron sont interprétés en `Europe/Paris` (TZ heure de Paris, gère automatiquement la transition heure d'été/heure d'hiver). Le module scheduler force `timezone: 'Europe/Paris'` par défaut si non spécifié par le job, et passe cette valeur en option à `cron.schedule(pattern, handler, { timezone })`. Conséquence : `0 1 * * *` signifie 01:00 heure de Paris, donc 23:00 UTC en été (UTC+2) et 00:00 UTC en hiver (UTC+1). Le hosting beta Demo est supposé en France métropolitaine — cohérence avec la pendule des employées.

### Job concret — UpdateContractStatus

- SFD-6: **Fichier `src/scheduler/jobs/updateContractStatus.ts`** définit le job au format `ScheduledJob` :
  ```typescript
  // src/scheduler/jobs/updateContractStatus.ts
  import type { ScheduledJob } from '../index';
  import { prisma } from '../../db/client';  // singleton PrismaClient existant
  import { logger } from '../../logger';

  export async function updateContractStatus(): Promise<{ rowsAffected: number }> {
    const startedAt = Date.now();
    try {
      const rowsAffected = await prisma.$executeRaw`
        UPDATE [Contrat]
           SET [BebeStatut] = 2
         WHERE [BebeStatut] = 1
           AND [DateEffetContrat] = CAST(GETDATE() AS DATE)
      `;
      const durationMs = Date.now() - startedAt;
      logger.info(
        { event: 'scheduler.job.tick.success', jobName: 'UpdateContractStatus', durationMs, payload: { rowsAffected } },
        'updateContractStatus completed'
      );
      return { rowsAffected: Number(rowsAffected) };
    } catch (error) {
      const durationMs = Date.now() - startedAt;
      logger.error(
        { event: 'scheduler.job.tick.error', jobName: 'UpdateContractStatus', durationMs, error: { message: (error as Error).message, stack: (error as Error).stack } },
        'updateContractStatus failed'
      );
      // Ne pas re-throw — le scheduler doit rester armé pour la prochaine tick
      throw error;  // re-throw pour que node-cron logge aussi via son propre canal
    }
  }

  export const updateContractStatusJob: ScheduledJob = {
    name: 'UpdateContractStatus',
    cronPattern: '0 1 * * *',  // tous les jours à 01:00 heure Europe/Paris
    handler: async () => { await updateContractStatus(); },
    timezone: 'Europe/Paris',
    runOnInit: false,
  };
  ```
  La fonction `updateContractStatus()` est **exportée séparément du job** pour permettre des tests d'intégration directs (cf. AC-7) et un éventuel appel manuel depuis un endpoint admin v2.
- SFD-7: **Requête SQL canonique** strictement conforme à la formulation utilisateur :
  ```sql
  UPDATE [Contrat] SET [BebeStatut] = 2 WHERE [BebeStatut] = 1 AND [DateEffetContrat] = CAST(GETDATE() AS DATE);
  ```
  Notes d'exécution :
  - Pas de paramètre bindable — la fonction `CAST(GETDATE() AS DATE)` est évaluée côté SQL Server au moment de l'exécution, garantissant la cohérence horaire serveur (pas de drift si l'horloge Node.js diverge de l'horloge SQL Server).
  - `prisma.$executeRaw` retourne le nombre de lignes affectées (`@@ROWCOUNT` équivalent — le pilote `tedious` mappe ce compteur via le mécanisme `DONE_IN_PROC`/`DONE` du protocole TDS).
  - Aucune transaction explicite ouverte — l'UPDATE est auto-commit (1 statement = 1 transaction implicite côté SQL Server). Cohérent avec FEAT 23 BR-12 (tolérance zéro à l'incohérence partielle : un fail d'UPDATE rollback la transaction implicite entière).
- SFD-8: **Décision `=` strict vs `<=` recovery** — la requête utilise l'égalité stricte `[DateEffetContrat] = CAST(GETDATE() AS DATE)`. Conséquence : si le job ne tourne pas un jour donné `J` (serveur down, scheduler en mode `off`, exception non gérée — cf. SFD-9), les contrats dont `DateEffetContrat = J` **restent en attente à perpétuité** (la prochaine occurrence du job à `J+1` les filtrera car `DateEffetContrat ≠ J+1`). Cette décision est **load-bearing pour la correspondance littérale avec la spec utilisateur** — toute autre formulation serait une dérive. Mitigation opérationnelle documentée :
  - Un check de monitoring DBA hebdomadaire (out of scope code) doit lever une alerte si des lignes `BebeStatut = 1 AND DateEffetContrat < today` persistent (signal d'un job nightly raté).
  - Une recovery manuelle est possible par requête one-shot DBA `UPDATE [Contrat] SET [BebeStatut] = 2 WHERE [BebeStatut] = 1 AND [DateEffetContrat] <= CAST(GETDATE() AS DATE)` (filtre élargi `<=`) — à exécuter une fois après un downtime confirmé.
  - Un futur durcissement v2 (out of scope cette FEAT) pourrait élargir la requête à `<=` (rattrapage automatique des jours manqués) — décision intentionnelle déférée car non demandée par la spec utilisateur courante.
- SFD-9: **Gestion d'erreur — pas de crash process** — le handler `updateContractStatusJob.handler` enveloppe l'appel à `updateContractStatus()` dans un try/catch qui logge l'erreur au niveau ERROR mais **ne re-throw pas** vers le scheduler `node-cron`. Conséquence : une exception en cours d'exécution n'arrête pas le scheduler ni le process Express principal — la prochaine occurrence (24h plus tard) re-tentera. Si l'exception persiste 3 nuits consécutives, un alerting externe (out of scope cette FEAT — détectable par requête de monitoring sur les logs structurés `event: 'scheduler.job.tick.error'`) doit notifier les Ops. **Aucun retry intra-cycle n'est implémenté** (pas de back-off, pas de re-tentative immédiate) — la simplicité de l'opération (1 SQL UPDATE idempotent) ne justifie pas la complexité d'une stratégie de retry, et le job idempotent passera correctement à la prochaine occurrence.
- SFD-10: **Table d'audit optionnelle `dbo.JobAuditLog`** — si la table existe en base (cf. FEAT 23 SFD-18 DDL optionnel), le handler `updateContractStatus` peut écrire une entrée par exécution :
  ```sql
  INSERT INTO [JobAuditLog] (JobName, ExecutedAt, RowsAffected, Status, ErrorMessage)
  VALUES ('UpdateContractStatus', SYSDATETIMEOFFSET(), @rowsAffected, 'SUCCESS', NULL);
  ```
  En cas d'exception, `Status = 'FAILED'`, `ErrorMessage = <message tronqué à 2000 chars>`. **Best-effort uniquement** : si l'INSERT dans `JobAuditLog` échoue (table absente — code `Invalid object name 'JobAuditLog'`), le scheduler logge un WARN `scheduler.audit.unavailable` mais ne fait pas échouer le job lui-même. Détection d'existence : tenter l'INSERT, catch l'exception SQL spécifique, désactiver le flag interne `auditLogEnabled` pour le reste de la session pour éviter de re-tenter à chaque tick.

### Worker mode optionnel

- SFD-11: **Mode `worker` — process Node.js séparé** — si l'API backend Demo est déployée en cluster (multiple instances Express derrière un load balancer), le mode `embedded` exécuterait le job N fois à 01:00 (1× par instance), causant des UPDATE redondants (idempotents mais inutiles, et générant N rapports d'audit `JobAuditLog`). Pour ce cas, le mode `worker` est documenté :
  - Un script d'entrée séparé `src/worker.ts` ne charge **que** le scheduler (pas Express) :
    ```typescript
    // src/worker.ts
    import { registerJob, startScheduler, stopScheduler } from './scheduler';
    import { updateContractStatusJob } from './scheduler/jobs/updateContractStatus';
    import { logger } from './logger';
    import { prisma } from './db/client';

    process.env.NJ_PROCESS_KIND = 'worker';  // signal au scheduler que c'est le bon process
    registerJob(updateContractStatusJob);
    const { activeJobs, mode } = startScheduler();
    logger.info({ event: 'worker.started', activeJobs, mode, pid: process.pid }, 'Scheduler worker initialized');

    const gracefulShutdown = async () => {
      await stopScheduler();
      await prisma.$disconnect();
      process.exit(0);
    };
    process.on('SIGTERM', gracefulShutdown);
    process.on('SIGINT', gracefulShutdown);
    ```
  - Un script npm `"start:worker": "node dist/worker.js"` ajouté à `package.json` (build TypeScript déjà géré par `tsc -p tsconfig.build.json` héritage stack).
  - L'API backend principal pose `SCHEDULER_MODE=worker` dans son `.env` → le scheduler embedded est neutralisé (cf. SFD-3) → seul le process worker exécute les jobs.
  - **Recommandation déploiement** : 1 seul process worker par environnement (pas de scaling horizontal du worker). Pour éviter le risque d'oubli, un check de doublon au boot via `sp_getapplock` SQL Server peut être ajouté (out of scope v1).

### Cycle de vie process

- SFD-12: **Graceful shutdown** — le module scheduler expose `stopScheduler(): Promise<void>` qui :
  1. Itère sur le `Map<string, cron.ScheduledTask>` interne et appelle `task.stop()` sur chaque entrée (désarme le timer mais laisse une éventuelle tick en cours se terminer).
  2. Attend max 30 secondes que les ticks en cours se terminent (timeout configurable via env `SCHEDULER_SHUTDOWN_TIMEOUT_MS`).
  3. Logge `scheduler.stopped` avec le count de jobs stoppés et la durée.
  L'entry point `src/server.ts` enregistre un handler SIGTERM/SIGINT qui appelle `stopScheduler()` **avant** de fermer le serveur Express (séquence : stop scheduler → close server.listen → disconnect Prisma → process.exit(0)).
- SFD-13: **Démarrage idempotent multi-process (dev hot-reload)** — en mode dev avec `tsx watch` ou `nodemon`, le process redémarre à chaque modification de fichier. Le module scheduler est **stateless persistant** (aucun fichier lock côté Node.js, aucune table de leader election). Conséquence : chaque restart re-arme les timers depuis zéro avec un état propre. Si une tick était en cours au moment du restart, elle est **interrompue brutalement** (pas de continuation cross-process) — acceptable car l'UPDATE SQL idempotent peut être ré-exécuté sans dommage à la prochaine tick.

## Business Rules

- BR-1: **Pattern cron canonique** `0 1 * * *` (chaque jour à 01:00 heure `Europe/Paris`). Toute modification du pattern requiert un changement de code versionné (pas de config exposée pour bascule horaire — anti-tampering, traçabilité git). Format crontab standard 5 segments `minute hour day-of-month month day-of-week`.
- BR-2: **Le job est strictement borné à la transition `1 → 2`**. Aucun autre statut n'est touché. La transition `2 → 3` (clôture) reste exclusive à l'endpoint applicatif FEAT 22 `POST /cloturer`. La transition `1 → 3` (clôture d'un contrat jamais commencé) reste un cas conceptuel non couvert par cette FEAT — passe par FEAT 22 explicitement.
- BR-3: **Décision `=` strict** : la requête utilise l'égalité stricte sur `DateEffetContrat = today`, pas `<=`. Décision intentionnelle conforme à la formulation spec utilisateur. La conséquence (pas de rattrapage automatique des jours manqués) est mitigée par un monitoring DBA hebdomadaire (cf. SFD-8). Toute évolution vers `<=` doit faire l'objet d'une nouvelle FEAT documentée.
- BR-4: **Idempotence garantie par construction** — re-exécution du job sur la même journée matche 0 ligne (les lignes basculées la première passe ne matchent plus le filtre `BebeStatut = 1`). Aucun side-effect, aucune contention de lock. Cohérent avec FEAT 23 SFD-19.
- BR-5: **Pas de retry intra-cycle** — une exception en cours d'exécution n'est pas re-tentée immédiatement. La prochaine occurrence (24h plus tard) re-tentera naturellement. Pas de back-off exponentiel, pas de circuit breaker — la simplicité du SQL UPDATE ne justifie pas la complexité. Si 3 exécutions consécutives échouent, un alerting externe doit notifier (out of scope cette FEAT).
- BR-6: **Le scheduler est non-critique pour la disponibilité HTTP** — une exception dans `startScheduler()` ou `registerJob()` ne doit **jamais** empêcher le serveur Express de servir les requêtes API. Le module scheduler logge ses erreurs et continue ; en dernier recours, si tout le module crash, le serveur HTTP reste healthy.
- BR-7: **Pas de rattrapage au boot** (`runOnInit: false`) — un redémarrage du serveur en cours de journée ne déclenche **pas** une exécution immédiate du job. La prochaine tick aura lieu au prochain `0 1 * * *`. Décision : éviter qu'un déploiement à 14:00 cause une exécution intempestive (les Ops s'attendent à ce que le job tourne uniquement à 01:00).
- BR-8: **Timezone explicite `Europe/Paris`** — anti-derive vs UTC. Le serveur peut tourner en UTC côté OS (config Docker / cloud) ; le scheduler force l'interprétation cron en heure de Paris pour cohérence avec les employées. Le passage heure d'été ↔ heure d'hiver est géré nativement par `node-cron` via la lib `cron-parser` interne (test : le 30 octobre 2026 à 03:00 → 02:00, le job de 01:00 tourne 1× — pas de double exécution).
- BR-9: **Aucune notification utilisateur** — la bascule `1 → 2` ne déclenche aucune notification push / email / SMS aux employées ou aux parents. Les employées découvrent la bascule au prochain refresh de `/bebes`. Cohérent avec FEAT 23 SFD-17.
- BR-10: **Audit applicatif minimaliste** — le seul audit posé par cette FEAT est le log structuré pino (capturé par l'agrégateur de runtime — PM2, Docker, systemd). L'INSERT dans `dbo.JobAuditLog` est best-effort optionnel (cf. SFD-10). Aucun audit applicatif n'est posé sur les lignes individuelles `Contrat` (cohérent FEAT 23 BR-11).
- BR-11: **Aucun endpoint applicatif n'expose le déclenchement manuel** du job en v1. La recovery manuelle après downtime passe par une requête SQL directe DBA (cf. SFD-8). Décision : surface d'attaque minimisée, principe de moindre privilège (l'API HTTP ne doit pas exposer d'opérations DBA).
- BR-12: **Le scheduler ne consomme jamais le pool de connexions Prisma de manière prolongée** — chaque tick acquiert une connexion via `prisma.$executeRaw`, exécute la requête en < 1s typiquement, et libère. Le pool Prisma (taille par défaut 10 connexions sur SQL Server) reste disponible pour les requêtes HTTP entrantes pendant l'exécution du job.

## Acceptance Criteria

- AC-1: **module scheduler enregistré au boot** — au démarrage du backend Node.js avec `SCHEDULER_MODE=embedded` (défaut), le log structuré pino contient une entrée `event: 'scheduler.started', activeJobs: 1, mode: 'embedded'` dans les 100 ms suivant le `app.listen()` (vérifiable par snapshot stdout avec `vi.spyOn(logger, 'info')` en test d'intégration).
- AC-2: **job UpdateContractStatus enregistré** — un appel à `registerJob(updateContractStatusJob)` produit un log `event: 'scheduler.job.registered', jobName: 'UpdateContractStatus', cronPattern: '0 1 * * *', timezone: 'Europe/Paris'`.
- AC-3: **bascule `1 → 2` à 01:00 heure Europe/Paris** — un test d'intégration avec fixtures (3 contrats : 1× `BebeStatut = 1 AND DateEffetContrat = today`, 1× `BebeStatut = 1 AND DateEffetContrat = today + 1`, 1× `BebeStatut = 2 AND DateEffetContrat = today - 30`) appelle directement `updateContractStatus()` (sans attendre 01:00 — bypass cron pour vitesse de test). Après l'appel : 1 ligne a `BebeStatut = 2` (la première fixture), 1 ligne reste `BebeStatut = 1` (la deuxième — date future), 1 ligne reste `BebeStatut = 2` (la troisième — non touchée). Retour de la fonction : `{ rowsAffected: 1 }`.
- AC-4: **idempotence** — re-appel immédiat de `updateContractStatus()` sur les mêmes fixtures retourne `{ rowsAffected: 0 }`. Le log structuré contient `event: 'scheduler.job.tick.success', payload: { rowsAffected: 0 }`.
- AC-5: **égalité stricte `=` respectée** — un test avec fixture `BebeStatut = 1 AND DateEffetContrat = today - 1` (contrat dont le jour d'effet est passé hier) appelle `updateContractStatus()` → la ligne **n'est pas modifiée** (`BebeStatut` reste à `1`). Validation littérale de BR-3.
- AC-6: **timezone Europe/Paris dans cron-parser** — un test unit valide que `cron.validate('0 1 * * *') === true` et qu'à un instant simulé `2026-10-30T22:30:00Z` (UTC) — qui correspond à `2026-10-31T00:30:00+02:00` (Paris heure été) — l'attribut `nextDate` retourne `2026-10-31T01:00:00+02:00`, soit `2026-10-30T23:00:00Z` UTC. Test avec `cron-parser.parseExpression('0 1 * * *', { tz: 'Europe/Paris', currentDate: '2026-10-30T22:30:00Z' }).next()`.
- AC-7: **gestion d'erreur sans crash** — un test d'intégration force `prisma.$executeRaw` à throw (mock) → `updateContractStatus()` capture l'erreur, log `event: 'scheduler.job.tick.error', error: { message: ..., stack: ... }` au niveau ERROR, et re-throw. Le scheduler `node-cron` continue d'être armé (vérifiable en posant un second tick simulé qui aboutit normalement).
- AC-8: **mode `off` no-op** — démarrage du backend avec `SCHEDULER_MODE=off` → log `event: 'scheduler.started', activeJobs: 0, mode: 'off'` ; aucun timer `node-cron` n'est armé (vérifiable par `cron.getTasks().size === 0` ou équivalent inspection runtime).
- AC-9: **graceful shutdown** — envoi d'un signal SIGTERM au process → handler `stopScheduler()` invoqué → log `event: 'scheduler.stopped', stoppedJobs: 1, durationMs: < 100ms` → process exit code `0`.
- AC-10: **logs structurés pino** — chaque log produit par le scheduler est un JSON valide parseable contenant au minimum `level`, `time` (epoch ms), `event` (string namespaced `scheduler.*`), et les champs spécifiques au type d'événement (`jobName`, `durationMs`, etc.).
- AC-11: **pas de re-exécution au boot** — démarrage du backend à 14:30 heure Paris → aucun log `event: 'scheduler.job.tick.start'` n'est émis dans les 60 secondes suivant le boot (la prochaine tick est attendue à 01:00 du lendemain). Validation littérale de BR-7.
- AC-12: **pas de blocking de l'event loop** — un test de charge envoie 100 requêtes HTTP GET `/api/bebes` concurrentes pendant que `updateContractStatus()` est en cours d'exécution sur 10 000 lignes simulées → toutes les requêtes HTTP aboutissent en < 1 seconde p95 (l'event loop reste réactif grâce à l'I/O Prisma asynchrone non bloquante).
- AC-13: **table audit optionnelle best-effort** — un test avec table `JobAuditLog` absente → le scheduler logge `event: 'scheduler.audit.unavailable'` au WARN une fois, puis le job continue à exécuter ses ticks sans re-tenter d'INSERT audit (flag interne désactivé pour la session). Aucune exception n'est propagée à `node-cron`.
- AC-14: **package.json contient `node-cron@^3.0.3`** — `cat workspace/output/src/DemoBack/package.json | jq '.dependencies["node-cron"]'` retourne `"^3.0.3"`. Aucune autre dépendance scheduler n'est ajoutée (pas de `bull`, `agenda`, etc.).
- AC-15: **script `start:worker` configuré** — `cat workspace/output/src/DemoBack/package.json | jq '.scripts["start:worker"]'` retourne `"node dist/worker.js"`. Le fichier `src/worker.ts` existe et compile en `dist/worker.js`.

## Functional Deliverables

- FD-1: **Module `scheduler/`** sous `workspace/output/src/DemoBack/src/scheduler/` contenant :
  - `index.ts` — API publique `registerJob`, `startScheduler`, `stopScheduler`, types
  - `jobs/updateContractStatus.ts` — premier job concret (fonction + définition `ScheduledJob`)
  - Optionnel : `audit.ts` — helper INSERT best-effort dans `dbo.JobAuditLog`
- FD-2: **Dépendance npm** `node-cron@^3.0.3` ajoutée à `workspace/output/src/DemoBack/package.json` (section `dependencies`). Types `@types/node-cron@^3.0.11` en `devDependencies`.
- FD-3: **Entry point étendu** `src/server.ts` (mode `augment`) — appel à `registerJob(updateContractStatusJob)` + `startScheduler()` après `app.listen()`, handler SIGTERM/SIGINT pour graceful shutdown.
- FD-4: **Entry point worker** `src/worker.ts` (mode `create`) — process Node.js séparé qui ne charge que le scheduler (pas Express), pour mode `SCHEDULER_MODE=worker` (cf. SFD-11).
- FD-5: **Config env** étendue dans `src/config/env.ts` (mode `augment`) — variable `SCHEDULER_MODE: 'embedded' | 'worker' | 'off'` (défaut `embedded`), validée Zod, optionnelle `SCHEDULER_SHUTDOWN_TIMEOUT_MS: number` (défaut `30000`).
- FD-6: **Script npm** `start:worker` ajouté à `workspace/output/src/DemoBack/package.json` (section `scripts`) — `"start:worker": "node dist/worker.js"`. Aucun changement aux scripts existants `start`, `dev`, `build`, `test`.
- FD-7: **Tests d'intégration vitest** sous `workspace/output/src/DemoBack/tests/scheduler/` couvrant AC-1 à AC-15 (mocks pino logger + Prisma `$executeRaw`, fixtures déterministes en mémoire SQLite ou mocks Prisma selon stack QA actif).
- FD-8: **Suppression de FEAT 23 FD-7** (SQL Server Agent job) — cette FEAT 24 **supersedes** la livraison FEAT 23 FD-7. Si la FEAT 23 a déjà été déployée avec le job SQL Agent installé en prod beta, une étape de migration DBA est requise : (a) désactiver le job SQL Agent `nj_flip_bebe_statut_pending_to_active` (ne pas le supprimer immédiatement — garder en sauvegarde 7 jours), (b) déployer la version Node.js, (c) vérifier sur 3 nuits consécutives via les logs pino que le job Node.js tourne correctement, (d) supprimer définitivement le job SQL Agent. **Charge DBA / Ops** ; out of scope strict agent `dev-backend`.

## Dependencies

**FEAT 22 `spec-cloture-contrat`** — pré-requis schéma. La colonne `dbo.Contrat.BebeStatut TINYINT NOT NULL DEFAULT 1` doit exister (créée par FEAT 22 SFD-3). Sans cette colonne, le job SQL UPDATE échoue avec `Invalid column name 'BebeStatut'`.

**FEAT 23 `spec-bebe-dactive`** — pré-requis sémantique. Les chemins d'écriture INSERT/UPDATE étendus (FEAT 23 SFD-6, SFD-7) doivent poser correctement `BebeStatut = 1` à la création de contrats avec date future, sinon le job de cette FEAT 24 n'a rien à basculer. Cette FEAT 24 **supersedes** FEAT 23 FD-7 (SQL Server Agent) — le job Node.js remplace le job SQL Agent.

**Stack `fullstack/node-react`** — pré-requis runtime. Cette FEAT suppose un backend Node.js (TypeScript) + Express + Prisma (capability `prisma` forcée cf. `workspace/input/stack/stack.md` ligne 15). Si le stack backend bascule vers un autre runtime (.NET, Spring Boot, FastAPI), cette FEAT doit être ré-implémentée avec le scheduler natif du nouveau runtime (`HostedService` .NET, `@Scheduled` Spring, `apscheduler` Python).

## Out of Scope

- **Endpoint admin HTTP `POST /api/admin/jobs/{jobName}/run`** pour déclencher manuellement le job — utile en recovery post-downtime. Décision : reporté à une FEAT v2 dédiée admin tooling pour ne pas multiplier les surfaces d'attaque. La recovery manuelle passe par DBA en attendant (cf. SFD-8).
- **Endpoint admin HTTP `GET /api/admin/jobs`** read-only listant les jobs enregistrés + dernière exécution + statut — observabilité avancée. Décision : les logs pino structurés suffisent pour la beta, dashboard fait via Datadog / ELK out-of-app.
- **Distributed locking via Redis / SQL `sp_getapplock`** pour garantir une exécution unique en mode cluster — mitigé par le mode `worker` (1 process worker dédié). Décision : reporté à v2 si le scaling horizontal devient nécessaire.
- **Retry avec back-off exponentiel** sur exception — la simplicité du SQL UPDATE idempotent ne justifie pas. La prochaine occurrence (24h plus tard) re-tentera (cf. BR-5).
- **Alerting actif** (PagerDuty, Slack, email) sur 3 exécutions consécutives en échec — l'alerting est out-of-app, à câbler côté agrégateur log (Datadog Monitor sur `event: 'scheduler.job.tick.error'` count ≥ 3 dans une fenêtre 72h).
- **Migration vers `<=` strict** pour rattrapage automatique des jours manqués — non demandée par la spec utilisateur courante (cf. BR-3). Une future FEAT pourra arbitrer.
- **Plus d'un job scheduled** — cette FEAT introduit uniquement `UpdateContractStatus` comme premier job. L'infrastructure est extensible (registre `Map<string, ScheduledTask>`) mais aucun autre job n'est livré ici.
- **Migration du job vers une queue durable (BullMQ + Redis)** — pertinent si le volume monte ou si l'on veut visibilité opérationnelle granulaire (jobs en attente, jobs failed retryable, etc.). Out of scope beta Demo.
- **Tests E2E réels avec SQL Server Express en CI** — les tests vitest utilisent des mocks Prisma + fixtures en mémoire (cf. FD-7). Un test E2E réel (container SQL Server dans GitHub Actions) est out-of-scope cette FEAT.
- **Suppression définitive du job SQL Server Agent FEAT 23 FD-7** en prod — charge DBA séquentielle après validation 3 nuits du nouveau job Node.js (cf. FD-8). Cette FEAT 24 livre uniquement le code Node.js et la procédure de bascule documentée ; l'exécution opérationnelle reste manuelle.
