// server.js — SDD Console backend
// Sert les fichiers statiques de la console + 3 endpoints :
//   GET  /api/tree    → arbo FEATs > US > Plans (mergee avec status.json)
//   GET  /api/file    → contenu brut d un MD (chemin restreint au workspace)
//   GET  /api/status  → workspace/console/status.json
//
// LOT 2 ajoutera POST /api/validate (ecrit status.json).
// LOT 4 ajoutera GET /api/explain (Anthropic SDK).

import Fastify from "fastify";
import fastifyStatic from "@fastify/static";
import { readdir, readFile, stat, watch as fsWatch } from "node:fs/promises";
import { existsSync, readFileSync, realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve, relative, sep } from "node:path";
import { execSync } from "node:child_process";

import { parseSpec, parseUs, parsePlan } from "./lib/markdown-filter.js";
import { withLockedWrite } from "./lib/atomic-write.js";
import { explain, isAvailable as explainIsAvailable } from "./lib/explain.js";
import {
  dbAvailable, dashboardOverview, featStats,
  auditTokens, stateRuns, gatesHistory,
  rawSql, // v6.10.3+ : shared SQL helper (node:sqlite or python fallback)
  recordGateDecision, // v7.0.0 P0 C2 : DB mirror for /api/gate-decide
} from "./lib/console-db.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname  = dirname(__filename);
const CONSOLE_DIR = __dirname;
const WORKSPACE   = resolve(__dirname, "..");      // workspace/
const ROOT        = resolve(WORKSPACE, "..");       // c:/DEV/SDD_Pro/

const SPECS_DIR  = join(WORKSPACE, "input",  "feats");
const US_DIR     = join(WORKSPACE, "output", "us");
const PLANS_DIR  = join(WORKSPACE, "output", "plans");
const UI_DIR     = join(WORKSPACE, "input",  "ui");
const QA_DIR     = join(WORKSPACE, "output", "qa");
const SRC_DIR    = join(WORKSPACE, "output", "src");
const SCHEMA_DIR = join(WORKSPACE, "output", "db");
const AUDIT_DIR  = join(WORKSPACE, "output", ".sys", ".audit");
const STATE_DIR  = join(WORKSPACE, "output", ".sys", ".state");
const STATUS_FILE = join(CONSOLE_DIR, "status.json");
const STACK_FILE  = join(WORKSPACE, "input", "stack", "stack.md");

// Port par défaut : 4000 (cohérent avec docs/commands/sdd-serve.md §6 +
// docs/MCP-SERVER.md). 5173 (ancien défaut) entre en collision avec Vite
// (react, vue) qui prend 5173 → /sdd-serve démarrait instablement quand
// les 2 services se réservaient le même port. Override via env PORT=...
// reste supporté pour compat scripts existants.
// Bug filé 2026-05-21 ; fix v7.0.0-alpha (cf. CHANGELOG).
const PORT = parseInt(process.env.PORT || "4000", 10);

// HTTPS dev — clé/cert auto-signés générés via openssl (cf. .certs/).
// Si la paire est absente, fallback HTTP (rétro-compat dev local).
//
// v7.0.1 audit P1 v2 (2026-06-08) — refus boot HTTP en production :
// si `NODE_ENV=production` et certs absents → exit 1. Empêche un déploiement
// accidentel sans TLS (MAJ-5 audit v2 sécurité : silent fallback HTTP
// permettait MITM-grade access via cert auto-signé arbitraire).
const CERT_KEY  = join(CONSOLE_DIR, ".certs", "dev-key.pem");
const CERT_CERT = join(CONSOLE_DIR, ".certs", "dev-cert.pem");
const HTTPS_ENABLED = existsSync(CERT_KEY) && existsSync(CERT_CERT);
const IS_PRODUCTION = (process.env.NODE_ENV || "").toLowerCase() === "production";

if (IS_PRODUCTION && !HTTPS_ENABLED) {
  // Hard-fail : on ne sert pas en clair en production sous aucun pretexte.
  // Bypass légitime : générer les certs via `npm run gen-certs` ou pointer
  // CERT_KEY / CERT_CERT vers un reverse-proxy TLS termination (nginx/traefik).
  console.error(
    "[FATAL] NODE_ENV=production but no TLS certs found at .certs/dev-{key,cert}.pem.\n" +
    "        Refusing to boot console server over plain HTTP in production.\n" +
    "        Fix: (a) generate certs via `npm run gen-certs`,\n" +
    "             (b) terminate TLS at a reverse proxy and unset NODE_ENV,\n" +
    "             (c) for dev/CI testing : NODE_ENV=development npm start"
  );
  process.exit(1);
}

const fastifyOptions = { logger: { level: "info" } };
if (HTTPS_ENABLED) {
  fastifyOptions.https = {
    key:  readFileSync(CERT_KEY),
    cert: readFileSync(CERT_CERT),
  };
} else if (!IS_PRODUCTION) {
  // Dev fallback : explicit WARN to signal we're not on TLS.
  console.warn(
    "[WARN] Console server starting in HTTP mode (no TLS certs at .certs/).\n" +
    "       OK for dev/CI on 127.0.0.1. For production, set NODE_ENV=production\n" +
    "       and provide certs or use a reverse-proxy TLS termination."
  );
}
const fastify = Fastify(fastifyOptions);

// Security headers (v0.4.1, audit 2026-06-08). Console is bound to 127.0.0.1
// (line ~816) so the attack surface is local — but headers still matter for
// (a) malicious npm package opening localhost in user's browser, (b) the rare
// dev who exposes the port via tunnel/reverse-proxy.
//
// CSP whitelist matches what index.html actually loads:
//   - script-src : self (dist/app.js, data-loader.js) + 2 CDNs for React/marked
//   - style-src  : self + Google Fonts CSS ('unsafe-inline' kept for SVG icons
//                  and React style={} props — would require a full audit to drop)
//   - font-src   : Google Fonts files
//   - connect-src: self (REST + SSE /api/events)
//   - frame-src  : self (iframe srcdoc for help pages via /api/help/:id)
//   - img-src    : self + data: (SVG icons embedded as data URIs)
fastify.addHook("onSend", async (req, reply, payload) => {
  reply.header(
    "Content-Security-Policy",
    [
      "default-src 'self'",
      "script-src 'self' https://unpkg.com https://cdn.jsdelivr.net",
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
      "font-src 'self' https://fonts.gstatic.com",
      "img-src 'self' data:",
      "connect-src 'self'",
      "frame-src 'self'",
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; "),
  );
  reply.header("X-Content-Type-Options", "nosniff");
  reply.header("X-Frame-Options", "SAMEORIGIN");
  reply.header("Referrer-Policy", "no-referrer");
  reply.header("Permissions-Policy", "geolocation=(), microphone=(), camera=()");
  return payload;
});

await fastify.register(fastifyStatic, {
  root: CONSOLE_DIR,
  prefix: "/",
  index: ["index.html"],
});

// Sert workspace/input/ui/ tel quel pour que les mockups HTML chargent leur CSS
// relatif (design-system.css, etc.) sans duplication. Cf. UXCarousel côté React.
await fastify.register(fastifyStatic, {
  root: UI_DIR,
  prefix: "/ui/",
  decorateReply: false,
});

// ─────────────────────────────────────────────
// Helpers FS
// ─────────────────────────────────────────────
async function listMarkdown(dir) {
  if (!existsSync(dir)) return [];
  const entries = await readdir(dir);
  return entries.filter((f) => f.endsWith(".md")).sort();
}

async function safeRead(file) {
  try { return await readFile(file, "utf8"); }
  catch { return null; }
}

async function loadStatus() {
  if (!existsSync(STATUS_FILE)) {
    return { version: 1, updatedAt: new Date().toISOString(), FEATs: {}, gates: {} };
  }
  try {
    return JSON.parse(await readFile(STATUS_FILE, "utf8"));
  } catch (e) {
    fastify.log.error({ err: e }, "status.json corrompu, fallback squelette");
    return { version: 1, updatedAt: new Date().toISOString(), FEATs: {}, gates: {} };
  }
}

async function loadProjectMeta() {
  const stack = await safeRead(STACK_FILE);
  let appName = "(projet)";
  let backendName = null;
  let libName = null;
  let qaMode = "manual";
  if (stack) {
    appName     = (stack.match(/^AppName:\s*(\S+)/m)?.[1])     || appName;
    backendName = (stack.match(/^BackendName:\s*(\S+)/m)?.[1]) || backendName;
    libName     = (stack.match(/^LibName:\s*(\S+)/m)?.[1])     || libName;
    qaMode      = (stack.match(/^QAMode:\s*(\S+)/m)?.[1])      || qaMode;
  }
  const projects = [];
  if (appName && appName !== "(projet)") projects.push({ id: appName, name: appName, type: "front" });
  if (backendName) projects.push({ id: backendName, name: backendName, type: "back" });
  return { appName, backendName, libName, qaMode, projects };
}

// ─────────────────────────────────────────────
// Tree builder
// ─────────────────────────────────────────────

function specKeyFromFile(filename) {
  // "1-FEAT-connexion.md" -> { num: 1, key: "1-FEAT-connexion" }
  const m = filename.match(/^(\d+)-(.+)\.md$/);
  if (!m) return null;
  return { num: parseInt(m[1], 10), key: `${m[1]}-${m[2]}` };
}

function usKeyFromFile(filename) {
  // "1-1-Connexion.md" -> { FeatNum: 1, usNum: 1, key: "1-1-Connexion" }
  const m = filename.match(/^(\d+)-(\d+)-(.+)\.md$/);
  if (!m) return null;
  return {
    FeatNum: parseInt(m[1], 10),
    usNum:   parseInt(m[2], 10),
    key:     `${m[1]}-${m[2]}-${m[3]}`,
  };
}

function planKeyFromFile(filename) {
  // "1-1-Connexion.front.md" -> { FeatNum: 1, usNum: 1, key: "1-1-Connexion", family: "front" }
  const m = filename.match(/^(\d+)-(\d+)-(.+)\.(back|front)\.md$/);
  if (!m) return null;
  return {
    FeatNum: parseInt(m[1], 10),
    usNum:   parseInt(m[2], 10),
    key:     `${m[1]}-${m[2]}-${m[3]}`,
    family:  m[4],
  };
}

function deriveStatus(statusEntry, fallback = "in-progress") {
  if (!statusEntry || !statusEntry.humanStatus) return fallback;
  return statusEntry.humanStatus;
}

async function buildTree(status) {
  const FeatFiles = await listMarkdown(SPECS_DIR);
  const usFiles   = await listMarkdown(US_DIR);
  const planFiles = await listMarkdown(PLANS_DIR);

  // Map FeatNum → FeatKey (basename sans extension) pour lookup status.json fiable
  const specNumToKey = new Map();
  for (const f of FeatFiles) {
    const k = specKeyFromFile(f);
    if (k) specNumToKey.set(k.num, k.key);
  }

  function lookupUsStatus(FeatNum, usKey) {
    const FeatKey = specNumToKey.get(FeatNum);
    if (!FeatKey) return null;
    return status.FEATs?.[FeatKey]?.us?.[usKey] || null;
  }
  function lookupPlanStatus(FeatNum, usKey, family) {
    const u = lookupUsStatus(FeatNum, usKey);
    return u?.plans?.[family] || null;
  }

  const usByKey = new Map();        // "1-1-Connexion" → us object
  for (const f of usFiles) {
    const k = usKeyFromFile(f);
    if (!k) continue;
    const raw = await safeRead(join(US_DIR, f));
    const parsed = raw ? parseUs(raw) : null;
    const usStatus = lookupUsStatus(k.FeatNum, k.key);
    usByKey.set(k.key, {
      id: k.key,
      kind: "us",
      title: parsed?.title || k.key,
      status: deriveStatus(usStatus, "pending-validation"),
      actor: "PO",
      objective: parsed?.objective || "",
      asA: parsed?.asA, iWant: parsed?.iWant, soThat: parsed?.soThat,
      acceptanceCriteria: parsed?.acceptanceCriteria || [],
      FeatNum: k.FeatNum,
      file: `workspace/output/us/${f}`,
      children: [],
    });
  }

  // Plans → enfants des US
  for (const f of planFiles) {
    const k = planKeyFromFile(f);
    if (!k) continue;
    const raw = await safeRead(join(PLANS_DIR, f));
    const parsed = raw ? parsePlan(raw) : null;
    const us = usByKey.get(k.key);
    if (!us) continue;
    const planStatus = lookupPlanStatus(k.FeatNum, k.key, k.family);
    us.children.push({
      id: `${k.key}.${k.family}`,
      kind: "task",
      type: k.family,                                   // "back" | "front"
      title: `Plan technique ${k.family === "front" ? "frontend" : "backend"}`,
      status: deriveStatus(planStatus, "pending-validation"),
      summary: parsed?.intro || "",
      file: `workspace/output/plans/${f}`,
      filesPlanned: parsed?.files || [],
      stack: parsed?.stack || {},
      family: k.family,
      htmlSource: parsed?.htmlSource,
    });
  }

  // Mockups UI : ajoutes comme tasks "ui" si presents
  if (existsSync(UI_DIR)) {
    const uiFiles = (await readdir(UI_DIR)).filter((f) => f.endsWith(".html"));
    for (const f of uiFiles) {
      const m = f.match(/^(\d+)-(\d+)-(.+)\.html$/);
      if (!m) continue;
      const usKey = `${m[1]}-${m[2]}-${m[3]}`;
      const us = usByKey.get(usKey);
      if (!us) continue;
      us.children.push({
        id: `${usKey}.ui`,
        kind: "task",
        type: "ui",
        title: "Maquette HTML",
        status: "validated",   // mockup depose = implicitement valide
        summary: "Mockup statique fourni par l UX Designer.",
        file: `workspace/input/ui/${f}`,
      });
    }
  }

  // Tri des plans dans l ordre logique back > front > ui > qa
  const order = { back: 0, front: 1, ui: 2, qa: 3 };
  for (const us of usByKey.values()) {
    us.children.sort((a, b) => (order[a.type] ?? 9) - (order[b.type] ?? 9));
  }

  // FEATs → racines, contiennent les US
  const tree = [];
  for (const f of FeatFiles) {
    const k = specKeyFromFile(f);
    if (!k) continue;
    const raw = await safeRead(join(SPECS_DIR, f));
    const parsed = raw ? parseSpec(raw) : null;
    const usList = [...usByKey.values()].filter((us) => us.FeatNum === k.num);
    const FeatStatus = status.FEATs?.[k.key];
    tree.push({
      id: k.key,
      kind: "feature",
      title: parsed?.title || k.key,
      status: deriveStatus(FeatStatus, usList.length > 0 ? "in-progress" : "not-started"),
      summary: parsed?.summary || "",
      context: parsed?.context || "",
      objective: parsed?.objective || "",
      actors: parsed?.actors || [],
      businessRules: parsed?.businessRules || [],
      acceptanceCriteria: parsed?.acceptanceCriteria || [],
      stakeholders: parsed?.stakeholders || [],
      source: `workspace/input/feats/${f}`,
      FeatNum: k.num,
      children: usList,
    });
  }

  tree.sort((a, b) => a.FeatNum - b.FeatNum);
  return tree;
}

function derivePipelineState(tree, status) {
  // Pipeline state heuristique pour la topbar :
  //   po       = done si au moins une US existe
  //   arch     = done si workspace/output/db/schema.json OR src/ existe
  //   back     = active si plans .back.md existent ; done si tous valides
  //   front    = active si plans .front.md existent ; done si tous valides
  //   ui       = done si mockups HTML deposes
  //   qa       = done si workspace/output/qa/feat-* existe
  const hasUS    = tree.some((s) => s.children.length > 0);
  const hasArch  = existsSync(join(SCHEMA_DIR, "schema.json")) || existsSync(SRC_DIR);
  const allTasks = tree.flatMap((s) => s.children).flatMap((u) => u.children);
  const hasBack  = allTasks.some((t) => t.type === "back");
  const hasFront = allTasks.some((t) => t.type === "front");
  const hasUI    = allTasks.some((t) => t.type === "ui");
  const hasQA    = existsSync(QA_DIR);

  return [
    { key: "po",    label: "PO",         state: hasUS    ? "done" : "pending" },
    { key: "arch",  label: "Architecte", state: hasArch  ? "done" : "pending" },
    { key: "back",  label: "Dev Back",   state: hasBack  ? "active" : "pending" },
    { key: "front", label: "Dev Front",  state: hasFront ? "active" : "pending" },
    { key: "ui",    label: "UI Design",  state: hasUI    ? "done" : "pending" },
    { key: "qa",    label: "QA",         state: hasQA    ? "done" : "pending" },
  ];
}

function deriveActiveGate(tree, status) {
  // Trouve le premier gate "pending" toutes FEATs confondues.
  for (const FEAT of tree) {
    const g = status.gates?.[String(FEAT.FeatNum)];
    if (!g) continue;
    for (const phase of ["afterUS", "afterReadiness", "afterPlan", "afterCode"]) {
      if (g[phase]?.decision === "pending") {
        return { FeatId: FEAT.id, FeatNum: FEAT.FeatNum, phase, ...g[phase] };
      }
    }
  }
  return null;
}

// ─────────────────────────────────────────────
// Routes
// ─────────────────────────────────────────────

fastify.get("/api/tree", async () => {
  const status = await loadStatus();
  const tree = await buildTree(status);
  const project = await loadProjectMeta();
  const pipelineSteps = derivePipelineState(tree, status);
  const activeGate = deriveActiveGate(tree, status);

  return {
    tree,
    project: {
      name: project.appName,
      qaMode: project.qaMode,
      projects: project.projects,
      pipelineSteps,
    },
    status,
    activeGate,
    explain: explainIsAvailable(),
  };
});

// ─────────────────────────────────────────────
// GET /api/file — read text file from workspace/
// Defense in depth (audit P0 v2 sécurité 2026-06-08, CWE-22 + CWE-59) :
//   1. relative(WORKSPACE, abs) — coarse parent traversal check
//   2. realpathSync — canonicalize symlinks (Windows + POSIX)
//   3. case-insensitive comparison sur Windows (process.platform === 'win32')
//   4. denylist `.sys/` (audit logs, validation sentinels, state files —
//      jamais exposés au front-end)
//   5. denylist explicite `workspace/input/stack/stack.md` (contient les
//      secrets Pattern B en clair : DB_PASSWORD, AUTH_JWT_SECRET, AZ_TENANTID
//      — cf. rules/library-and-stack.md §0 et ADR secrets-config-ssot-stack-md)
//   6. denylist binaires SQLite + .env + credentials.json
//   7. whitelist extensions {.md, .json, .html, .txt, .yml, .yaml}
// ─────────────────────────────────────────────
const FILE_API_DENYLIST_PATH_FRAGMENTS = [
  // workspace/.sys/ peut contenir audit logs (env-bypass.jsonl peut leak
  // commandes excerpt avec secrets non masqués), state files internes,
  // validation sentinels — jamais exposés à la console web.
  ".sys",
  // Pattern B (rules/library-and-stack.md §0) : stack.md contient secrets
  // en clair. Pas pour la console web même en localhost (defense in depth :
  // VSCode extension malveillante / npm postinstall pourrait fetch 127.0.0.1).
  "input/stack/stack.md",
  // Autres fichiers sensibles potentiels.
  ".env",
  "credentials.json",
  ".certs",
];
const FILE_API_ALLOWED_EXTENSIONS = new Set([
  ".md", ".json", ".html", ".txt", ".yml", ".yaml",
]);
const FILE_API_DENY_EXTENSIONS = new Set([
  ".db", ".sqlite", ".sqlite3",  // SQLite binaries (console.db, etc.)
  ".key", ".pem", ".crt", ".p12", ".pfx",  // certs / keys
  ".log",  // potentiellement secrets / IP
]);

function isPathDenied(absPath, rootDir) {
  // Normalize for case-insensitive comparison on Windows
  const isWin = process.platform === "win32";
  const norm = (p) => isWin ? p.toLowerCase().replace(/\\/g, "/") : p.replace(/\\/g, "/");
  const absNorm = norm(absPath);
  const rootNorm = norm(rootDir);

  // 1. Must be within rootDir (after realpath canonicalization)
  if (!absNorm.startsWith(rootNorm + "/") && absNorm !== rootNorm) {
    return { denied: true, reason: "outside workspace root" };
  }

  // 2. Denylist path fragments (case-insensitive on Windows)
  const relNorm = absNorm.slice(rootNorm.length);
  for (const fragment of FILE_API_DENYLIST_PATH_FRAGMENTS) {
    const fragNorm = norm(fragment);
    if (relNorm.includes("/" + fragNorm) || relNorm.includes("/" + fragNorm + "/")
        || relNorm.endsWith("/" + fragNorm)) {
      return { denied: true, reason: `denylist fragment '${fragment}'` };
    }
  }

  // 3. Extension checks
  const dotIdx = absNorm.lastIndexOf(".");
  const ext = dotIdx >= 0 ? absNorm.slice(dotIdx) : "";
  if (FILE_API_DENY_EXTENSIONS.has(ext)) {
    return { denied: true, reason: `extension '${ext}' denied` };
  }
  if (!FILE_API_ALLOWED_EXTENSIONS.has(ext)) {
    return { denied: true, reason: `extension '${ext}' not in allowlist` };
  }

  return { denied: false };
}

fastify.get("/api/file", async (req, reply) => {
  const path = req.query.path;
  if (typeof path !== "string" || !path) {
    return reply.code(400).send({ error: "missing path" });
  }
  // 1. Resolve relative path against ROOT (gives absolute path).
  const abs = resolve(ROOT, path);

  // 2. Coarse check : relative path traversal containment.
  const wsRel = relative(WORKSPACE, abs);
  if (wsRel.startsWith("..") || wsRel.includes(`..${sep}`)) {
    return reply.code(403).send({ error: "path hors workspace/" });
  }

  // 3. Existence check before realpath (realpathSync throws on missing).
  if (!existsSync(abs)) return reply.code(404).send({ error: "not found" });

  // 4. Canonicalize symlinks (defense vs CWE-59 link following).
  //    `realpathSync` resolves any symlink in the chain. Without this,
  //    a symlink inside workspace/ pointing to ~/.ssh/id_rsa would be
  //    served by readFile() since wsRel above is still "valid" relative.
  let canonical;
  try {
    canonical = realpathSync(abs);
  } catch (err) {
    return reply.code(500).send({ error: "realpath failed" });
  }

  // 5. Re-check after canonicalization : the symlink target must still be
  //    inside WORKSPACE. Without this, an attacker could create a symlink
  //    inside workspace/ pointing outside.
  let workspaceCanonical;
  try {
    workspaceCanonical = realpathSync(WORKSPACE);
  } catch {
    workspaceCanonical = WORKSPACE;
  }
  const canonicalWsRel = relative(workspaceCanonical, canonical);
  if (canonicalWsRel.startsWith("..") || canonicalWsRel.includes(`..${sep}`)) {
    return reply.code(403).send({ error: "symlink target hors workspace/" });
  }

  // 6. Denylist + extension whitelist check on canonical path.
  const denyResult = isPathDenied(canonical, workspaceCanonical);
  if (denyResult.denied) {
    return reply.code(403).send({ error: `forbidden (${denyResult.reason})` });
  }

  const raw = await readFile(canonical, "utf8");
  const st  = await stat(canonical);
  return { path, content: raw, size: st.size, mtime: st.mtimeMs };
});

fastify.get("/api/status", async () => loadStatus());

// ─────────────────────────────────────────────
// GET /api/audit — budget tokens agrege par agent (v6.10: depuis console.db)
// Source : workspace/output/db/console.db (tables context_budget + token_usage)
// ─────────────────────────────────────────────
fastify.get("/api/audit", async () => {
  return auditTokens();
});

// ─────────────────────────────────────────────
// GET /api/state — etat du dernier run + events recents (v6.10: depuis console.db)
// Source : workspace/output/db/console.db (tables runs + run_phases + events)
// ─────────────────────────────────────────────
fastify.get("/api/state", async () => {
  return stateRuns();
});

// ─────────────────────────────────────────────
// GET /api/dashboard — vue d ensemble agrégée pour la page Dashboard (v6.10)
// Renvoie pour chaque FEAT : api_gate, coverage, quality, security, a11y, perf, spec, run.
// ─────────────────────────────────────────────
fastify.get("/api/dashboard", async () => {
  const av = dbAvailable();
  if (!av.ok) {
    return {
      available: false,
      error: av.error || "console.db introuvable",
      path: av.path,
      feats: [],
    };
  }
  const data = dashboardOverview();
  // Enrichit chaque FEAT avec son vrai nom (depuis le filename FS workspace/input/feats/)
  if (data.feats && existsSync(SPECS_DIR)) {
    try {
      const files = (await readdir(SPECS_DIR)).filter((f) => f.endsWith(".md"));
      const byNum = new Map();
      for (const f of files) {
        const m = f.match(/^(\d+)-(.+)\.md$/);
        if (m) byNum.set(parseInt(m[1], 10), m[2]);   // ex. 1 → "FEAT-connexion"
      }
      for (const feat of data.feats) {
        const realName = byNum.get(feat.feat_n);
        if (realName) feat.name = realName;
      }
    } catch { /* ignore — fallback to DB name */ }
  }
  return { available: true, ...data };
});

// ─────────────────────────────────────────────
// GET /api/feat/:n — détail d une FEAT (consommé par le drill-down du Dashboard)
// ─────────────────────────────────────────────
fastify.get("/api/feat/:n", async (req, reply) => {
  const featN = parseInt(req.params.n, 10);
  if (!Number.isFinite(featN) || featN < 1) {
    return reply.code(400).send({ error: "feat number invalid" });
  }
  return featStats(featN);
});

// ─────────────────────────────────────────────
// GET /api/feat/:n/details — détail des issues sonar (vulnerabilities, code smells, coverage gaps)
// Servi à la demande quand l utilisateur déplie une ligne sonar.
// ─────────────────────────────────────────────
fastify.get("/api/feat/:n/details", async (req, reply) => {
  const featN = parseInt(req.params.n, 10);
  if (!Number.isFinite(featN) || featN < 1) {
    return reply.code(400).send({ error: "feat number invalid" });
  }
  // v6.10.3+ : shared SQL helper from console-db.js — uses node:sqlite
  // when available (in-process, non-blocking-ish) and Python spawn as
  // fallback. Removes the duplicated spawnSync block that used to live
  // inline here.
  const sql = rawSql;

  const vulnerabilities = sql(
    `SELECT severity, issue_class, owasp, cwe, file_path, line, message
       FROM qa_security
      WHERE feat_n = ? AND mode = 'scan' AND severity IN ('critical','serious')
      ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'serious' THEN 1 ELSE 2 END, id
      LIMIT 100`,
    [featN]
  );
  const smells = sql(
    `SELECT severity, issue_class, rule, file_path, line, message
       FROM qa_quality
      WHERE feat_n = ?
      ORDER BY CASE severity WHEN 'error' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, id
      LIMIT 200`,
    [featN]
  );
  // Fichiers sous-couverts : on prend ceux des stacks coverage récents de cette FEAT
  // (jointure manuelle via coverage_id IN derniers ids de qa_coverage)
  const coverageGaps = sql(
    `SELECT cf.file_path, cf.lines_pct, c.coverage_min, c.stack
       FROM qa_coverage_files cf
       JOIN qa_coverage c ON c.id = cf.coverage_id
      WHERE c.feat_n = ? AND cf.lines_pct < c.coverage_min
      ORDER BY cf.lines_pct ASC
      LIMIT 50`,
    [featN]
  );
  return { feat_n: featN, vulnerabilities, smells, coverage_gaps: coverageGaps };
});

// ─────────────────────────────────────────────
// GET /api/gates — historique des gates (table gates)
// ─────────────────────────────────────────────
fastify.get("/api/gates", async (req) => {
  const featN = req.query.feat ? parseInt(req.query.feat, 10) : null;
  return { gates: gatesHistory(Number.isFinite(featN) ? featN : null) };
});

// ─────────────────────────────────────────────
// GET /api/help/:id — contenu HTML d une page d aide embarquée dans le SPA
// (au lieu d ouvrir le fichier dans un onglet, on injecte dans un iframe srcdoc)
// ─────────────────────────────────────────────
const HELP_FILES = {
  "fonctionnelle": join(CONSOLE_DIR, "help", "presentation.html"),
  "technique":     join(CONSOLE_DIR, "help", "presentation-technique.html"),
};

// Extrait le contenu utile d une page HTML : body innerHTML, sans <style>/<script>
// ni attributs `style=` ou `class=` issus du theme original (on re-stylise via .doc-content).
function extractBody(raw) {
  // 1) body innerHTML uniquement
  const m = raw.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
  let body = m ? m[1] : raw;
  // 2) supprime <script>, <style>, <link> embarqués
  body = body
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<link[^>]*>/gi, "");
  // 3) supprime les attributs style="..." inline (utilisent var(--primary)/--text de la page original)
  body = body.replace(/\sstyle="[^"]*"/gi, "");
  // 4) supprime les class= sauf quelques utilitaires sémantiques. Conserve les classes
  //    "alt" / "kpi-*" / "hero-*" etc. ne servent à rien sans leur CSS — strip toutes les classes.
  body = body.replace(/\sclass="[^"]*"/gi, "");
  // 5) trim
  return body.trim();
}

fastify.get("/api/help/:id", async (req, reply) => {
  const file = HELP_FILES[req.params.id];
  if (!file || !existsSync(file)) {
    return reply.code(404).send({ error: "page d'aide inconnue" });
  }
  const raw = await readFile(file, "utf8");
  reply.header("Cache-Control", "private, max-age=60");
  return { id: req.params.id, html: raw, body: extractBody(raw) };
});

fastify.get("/api/health", async () => ({
  ok: true,
  console: "sdd-console",
  // Console-app version (Fastify server package — workspace/console/package.json).
  // Decoupled from the SDD_Pro framework version on purpose (audit M8) :
  // the console iterates on UI cadence ; the framework on DSL cadence.
  version: "0.4.1",
  // Framework version read from .claude/loader.yml line `version: "..."`.
  // Allows the UI to display "alpha / beta / GA" in a banner without
  // hard-coding it in the console source.
  framework: (() => {
    try {
      const loaderPath = join(ROOT, ".claude", "loader.yml");
      if (!existsSync(loaderPath)) return null;
      const txt = readFileSync(loaderPath, "utf8");
      const m = txt.match(/^\s*version\s*:\s*["']?([^"'\n]+)["']?/m);
      return m ? m[1].trim() : null;
    } catch {
      return null;
    }
  })(),
  explain: explainIsAvailable(),
}));

// ─────────────────────────────────────────────
// GET /api/explain — reformulation IA PO-friendly (LOT 4)
// ─────────────────────────────────────────────
fastify.get("/api/explain", async (req, reply) => {
  const path = req.query.path;
  const force = req.query.force === "1" || req.query.force === "true";
  if (typeof path !== "string" || !path) {
    return reply.code(400).send({ error: "missing path" });
  }
  const abs = resolve(ROOT, path);
  const wsRel = relative(WORKSPACE, abs);
  if (wsRel.startsWith("..") || wsRel.includes(`..${sep}`)) {
    return reply.code(403).send({ error: "path hors workspace/" });
  }
  if (!existsSync(abs)) return reply.code(404).send({ error: "not found" });

  const avail = explainIsAvailable();
  if (!avail.ok) {
    return reply.code(503).send({ error: avail.reason, code: "EXPLAIN_UNAVAILABLE" });
  }

  try {
    const fileContent = await readFile(abs, "utf8");
    // Si force=1, on vide le cache pour cette cle (regen forcee)
    const result = await explain({ filePath: abs, fileContent });
    if (force && result.cached) {
      // Force regen : delete cache entry et retry
      const cachePath = join(CONSOLE_DIR, ".cache", "explained", `${result.cacheKey}.json`);
      try { await (await import("node:fs/promises")).unlink(cachePath); } catch {}
      const fresh = await explain({ filePath: abs, fileContent });
      return fresh;
    }
    return result;
  } catch (err) {
    if (err.code === "NO_API_KEY")  return reply.code(503).send({ error: err.message, code: "NO_API_KEY" });
    if (err.code === "DISABLED")    return reply.code(503).send({ error: err.message, code: "DISABLED" });
    fastify.log.error({ err }, "explain failed");
    return reply.code(502).send({ error: err.message || "explain failed", code: "EXPLAIN_FAILED" });
  }
});

// ─────────────────────────────────────────────
// User identification (validatedBy)
// ─────────────────────────────────────────────
function resolveUserEmail() {
  if (process.env.SDD_USER_EMAIL) return process.env.SDD_USER_EMAIL;
  try {
    const out = execSync("git config user.email", { stdio: ["ignore", "pipe", "ignore"] }).toString().trim();
    if (out) return out;
  } catch { /* git absent or no config */ }
  return "anonymous@local";
}

// ─────────────────────────────────────────────
// POST /api/validate — write status.json (atomic)
// ─────────────────────────────────────────────
fastify.post("/api/validate", async (req, reply) => {
  const body = req.body || {};
  const { kind, FeatId, usId, family, decision, comment } = body;

  // Validation arguments
  const VALID_KINDS = new Set(["us", "task"]);
  const VALID_DECISIONS = new Set(["validated", "rejected", "pending-validation"]);
  if (!VALID_KINDS.has(kind))         return reply.code(400).send({ error: "kind must be 'us' or 'task'" });
  if (!VALID_DECISIONS.has(decision)) return reply.code(400).send({ error: "decision must be 'validated' | 'rejected' | 'pending-validation'" });
  if (typeof FeatId !== "string" || !FeatId) return reply.code(400).send({ error: "FeatId required" });
  if (typeof usId !== "string" || !usId)     return reply.code(400).send({ error: "usId required" });
  if (kind === "task" && !["back", "front", "ui", "qa"].includes(family)) {
    return reply.code(400).send({ error: "family must be 'back'|'front'|'ui'|'qa' when kind='task'" });
  }

  const validatedBy = resolveUserEmail();
  const validatedAt = new Date().toISOString();

  let updated;
  try {
    updated = await withLockedWrite(STATUS_FILE, (cur) => {
      cur.FEATs ??= {};
      cur.FEATs[FeatId] ??= { humanStatus: "in-progress", us: {} };
      cur.FEATs[FeatId].us ??= {};
      cur.FEATs[FeatId].us[usId] ??= { humanStatus: "in-progress" };

      const target = (kind === "us")
        ? cur.FEATs[FeatId].us[usId]
        : ((cur.FEATs[FeatId].us[usId].plans ??= {})[family] ??= { humanStatus: "in-progress" });

      target.humanStatus = decision;
      if (decision === "pending-validation") {
        delete target.validatedBy;
        delete target.validatedAt;
        delete target.comment;
      } else {
        target.validatedBy = validatedBy;
        target.validatedAt = validatedAt;
        if (comment && typeof comment === "string") target.comment = comment.slice(0, 1000);
        else delete target.comment;
      }
      return cur;
    }, `console:${validatedBy}`);
  } catch (err) {
    fastify.log.error({ err }, "validate failed");
    return reply.code(500).send({ error: err.message });
  }

  broadcast({ type: "status", payload: { kind, FeatId, usId, family, decision, validatedBy, validatedAt } });
  return { ok: true, status: updated };
});

// ─────────────────────────────────────────────
// POST /api/gate-decide — resoudre un gate manuel (LOT 3)
// ─────────────────────────────────────────────
fastify.post("/api/gate-decide", async (req, reply) => {
  const body = req.body || {};
  const { FeatNum, phase, decision, comment } = body;

  const VALID_PHASES = new Set(["afterUS", "afterReadiness", "afterPlan", "afterCode"]);
  const VALID_DECISIONS = new Set(["validated", "skipped", "pending"]);
  if (typeof FeatNum !== "number" && typeof FeatNum !== "string") {
    return reply.code(400).send({ error: "FeatNum required (number|string)" });
  }
  if (!VALID_PHASES.has(phase)) {
    return reply.code(400).send({ error: `phase must be one of ${[...VALID_PHASES].join("|")}` });
  }
  if (!VALID_DECISIONS.has(decision)) {
    return reply.code(400).send({ error: `decision must be one of ${[...VALID_DECISIONS].join("|")}` });
  }

  const answeredBy = resolveUserEmail();
  const answeredAt = new Date().toISOString();
  const FeatKey = String(FeatNum);

  let updated;
  try {
    updated = await withLockedWrite(STATUS_FILE, (cur) => {
      cur.gates ??= {};
      cur.gates[FeatKey] ??= {};
      cur.gates[FeatKey][phase] ??= {};
      const gate = cur.gates[FeatKey][phase];
      gate.decision = decision;
      if (decision === "pending") {
        gate.askedAt = answeredAt;
        delete gate.answeredAt;
        delete gate.answeredBy;
      } else {
        gate.answeredAt = answeredAt;
        gate.answeredBy = answeredBy;
        if (comment && typeof comment === "string") gate.comment = comment.slice(0, 1000);
      }
      return cur;
    }, `console-gate:${answeredBy}`);
  } catch (err) {
    fastify.log.error({ err }, "gate-decide failed");
    return reply.code(500).send({ error: err.message });
  }

  // v7.0.0 P0 C2 fix : mirror the decision into console.db `gates` table for
  // historical analytics (cross-FEAT queries, /api/gates endpoint). Best-effort :
  // status.json is the live source of truth so a DB write failure does NOT fail
  // the HTTP response. Pending decisions are NOT mirrored (no final answer yet).
  if (decision !== "pending") {
    // Map API phase → canonical gate_name (cf. record_gate_decision.py VALID_GATE_NAMES).
    const PHASE_TO_GATE = {
      afterUS:        "us",
      afterReadiness: "readiness",
      afterPlan:      "plan",
      afterCode:      "code",
    };
    const featNumeric = Number(FeatKey);
    if (Number.isFinite(featNumeric)) {
      const dbRes = recordGateDecision({
        featN:     featNumeric,
        gateName:  PHASE_TO_GATE[phase],
        decision,
        byUser:    answeredBy,
        decidedAt: answeredAt,
        comment:   comment && typeof comment === "string" ? comment : null,
      });
      if (!dbRes.ok) {
        fastify.log.warn(
          { featN: featNumeric, phase, decision, err: dbRes.error },
          "gate-decide: console.db mirror failed (status.json still canonical)",
        );
      }
    }
  }

  broadcast({ type: "gate", payload: { FeatNum: FeatKey, phase, decision, answeredBy, answeredAt } });
  return { ok: true, status: updated };
});

// ─────────────────────────────────────────────
// SSE broadcasting
// ─────────────────────────────────────────────
const sseClients = new Set();

function broadcast(event) {
  const data = `data: ${JSON.stringify(event)}\n\n`;
  for (const client of sseClients) {
    try { client.write(data); } catch { /* client gone */ }
  }
}

fastify.get("/api/events", (req, reply) => {
  reply.raw.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
  });
  reply.raw.write(`: connected\n\n`);
  sseClients.add(reply.raw);

  const heartbeat = setInterval(() => {
    try { reply.raw.write(`: ping\n\n`); } catch { /* gone */ }
  }, 25_000);

  req.raw.on("close", () => {
    clearInterval(heartbeat);
    sseClients.delete(reply.raw);
  });
});

// ─────────────────────────────────────────────
// FS watcher → push tree-changed events
// ─────────────────────────────────────────────
const WATCH_DIRS = [SPECS_DIR, US_DIR, PLANS_DIR, UI_DIR];

async function watchDir(dir) {
  if (!existsSync(dir)) return;
  try {
    const watcher = fsWatch(dir, { recursive: false });
    for await (const event of watcher) {
      if (!event.filename) continue;
      // Debounce identique a la SSE : envoie un signal generique, le client refetch /api/tree
      broadcast({ type: "tree", payload: { dir: relative(WORKSPACE, dir), filename: event.filename } });
    }
  } catch (err) {
    fastify.log.warn({ err, dir }, "watcher arrete");
  }
}

async function watchStatusFile() {
  if (!existsSync(STATUS_FILE)) return;
  try {
    const watcher = fsWatch(STATUS_FILE);
    for await (const _event of watcher) {
      try {
        const payload = await loadStatus();
        broadcast({ type: "status-file", payload });
      } catch { /* corrupt mid-write, prochain event corrigera */ }
    }
  } catch (err) {
    fastify.log.warn({ err }, "status watcher arrete");
  }
}

// Lance les watchers sans bloquer le boot
WATCH_DIRS.forEach((d) => { watchDir(d); });
watchStatusFile();

// ─────────────────────────────────────────────
// Boot
// ─────────────────────────────────────────────
try {
  await fastify.listen({ port: PORT, host: "127.0.0.1" });
  const scheme = HTTPS_ENABLED ? "https" : "http";
  fastify.log.info(`SDD Console ${scheme}://127.0.0.1:${PORT}`);
} catch (err) {
  fastify.log.error(err);
  process.exit(1);
}
