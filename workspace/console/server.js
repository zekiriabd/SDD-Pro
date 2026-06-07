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
import { existsSync, readFileSync } from "node:fs";
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

// Port par défaut : 4000 (cohérent avec docs/commands/sdd-serve.md §6).
// 5173 (ancien défaut) entre en collision avec Vite (react, vue) qui prend
// 5173 → /sdd-serve démarrait instablement quand les 2 services se
// réservaient le même port. Override via env PORT=... reste supporté pour
// compat scripts existants. Bug filé 2026-05-21 ; fix v7.0.0-alpha (cf. CHANGELOG).
const PORT = parseInt(process.env.PORT || "4000", 10);

// HTTPS dev — clé/cert auto-signés générés via openssl (cf. .certs/).
// Si la paire est absente, fallback HTTP (rétro-compat).
const CERT_KEY  = join(CONSOLE_DIR, ".certs", "dev-key.pem");
const CERT_CERT = join(CONSOLE_DIR, ".certs", "dev-cert.pem");
const HTTPS_ENABLED = existsSync(CERT_KEY) && existsSync(CERT_CERT);

// Audit P0-doc 2026-06-05 :
//  - bodyLimit: 100 KiB ceiling on POST payloads (default Fastify is 1 MiB).
//    The console accepts gate decisions + validation toggles — none should
//    legitimately exceed a few KB. Smaller ceiling = smaller DoS surface.
//  - logger redacts ANTHROPIC_API_KEY-shaped strings before they hit disk.
const fastifyOptions = {
  bodyLimit: 100 * 1024,
  logger: {
    level: "info",
    redact: {
      paths: [
        "headers.authorization",
        "headers['x-api-key']",
        "headers['anthropic-api-key']",
        "req.headers.authorization",
        'req.headers["x-api-key"]',
      ],
      remove: false,
      censor: "[REDACTED]",
    },
  },
};
if (HTTPS_ENABLED) {
  fastifyOptions.https = {
    key:  readFileSync(CERT_KEY),
    cert: readFileSync(CERT_CERT),
  };
}
const fastify = Fastify(fastifyOptions);

// Audit 2026-06-06 — defense-in-depth against CSRF / DNS rebinding /
// curl-from-evil-site. Previous version used `startsWith()` on Host/Origin
// which accepts `localhost.evil.com` and `127.0.0.1.evil.com` (CWE-1289).
// Replaced by strict URL parsing + hostname exact match + Sec-Fetch-Site
// gate + per-process CSRF nonce on mutating verbs.
const _ALLOWED_HOSTNAMES = new Set(["127.0.0.1", "localhost", "[::1]", "::1"]);
const MUTATING_VERBS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// CSRF nonce: random, per-process, rotated each restart. The browser fetches
// it via GET /api/csrf (same-origin only, returned from this same process)
// and echoes it as `X-CSRF-Token` on every mutating call. A curl from evil.com
// cannot read the nonce (cross-origin GET is blocked by Origin check below)
// so even a successful DNS rebinding cannot forge a valid mutation.
import { randomBytes } from "node:crypto";
const CSRF_NONCE = randomBytes(32).toString("hex");

function _isLocalhostUrl(rawUrl) {
  if (!rawUrl) return false;
  let url;
  try { url = new URL(rawUrl); } catch { return false; }
  // Normalize IPv6 form: URL.hostname returns "::1" without brackets.
  const hostname = url.hostname.toLowerCase();
  return _ALLOWED_HOSTNAMES.has(hostname) || _ALLOWED_HOSTNAMES.has(`[${hostname}]`);
}

function _isLocalhostHostHeader(hostHeader) {
  if (!hostHeader) return false;
  // Parse via URL to handle `host:port` + IPv6 `[::1]:4000` uniformly.
  let parsed;
  try { parsed = new URL(`http://${hostHeader}`); } catch { return false; }
  const hostname = parsed.hostname.toLowerCase();
  return _ALLOWED_HOSTNAMES.has(hostname) || _ALLOWED_HOSTNAMES.has(`[${hostname}]`);
}

fastify.addHook("onRequest", async (req, reply) => {
  // 1. Host header — STRICT parse, exact hostname match (no startsWith).
  if (!_isLocalhostHostHeader(req.headers.host)) {
    return reply.code(403).send({ error: "console must be reached via localhost / 127.0.0.1" });
  }

  const method = req.method || "GET";

  // 2. Origin header — when present, must parse as localhost URL.
  //    A GET with Origin set means a cross-origin browser request (CORS preflight
  //    or fetch); we never expect that on a same-origin console.
  if (req.headers.origin && !_isLocalhostUrl(req.headers.origin)) {
    return reply.code(403).send({ error: "cross-origin request refused" });
  }

  // 3. Referer — when present on a mutating call, must also be localhost.
  //    Catches the case where a malicious page omits Origin but sends Referer.
  if (MUTATING_VERBS.has(method) && req.headers.referer && !_isLocalhostUrl(req.headers.referer)) {
    return reply.code(403).send({ error: "cross-origin referer refused" });
  }

  // 4. Mutating verbs MUST carry Sec-Fetch-Site=same-origin (set natively by
  //    modern browsers, unforgeable from cross-origin JS). Reject `cross-site`
  //    and `none` (top-level nav). `same-origin` and `same-site` are accepted.
  //    Curl/fetch from Node won't set this header → fall through to CSRF check.
  if (MUTATING_VERBS.has(method)) {
    const sfs = (req.headers["sec-fetch-site"] || "").toLowerCase();
    if (sfs && sfs !== "same-origin" && sfs !== "same-site") {
      return reply.code(403).send({ error: "cross-site mutation refused" });
    }
    // 5. CSRF nonce — mandatory on mutating verbs unless the request comes
    //    from a localhost CLI (no Sec-Fetch-Site, no Origin = trusted local).
    //    The double check (Sec-Fetch above OR CSRF here) means a browser-driven
    //    attack on a misconfigured DNS-rebound host still fails the nonce check.
    const hasBrowserContext = sfs || req.headers.origin;
    if (hasBrowserContext) {
      const token = req.headers["x-csrf-token"];
      if (token !== CSRF_NONCE) {
        return reply.code(403).send({ error: "missing or invalid X-CSRF-Token" });
      }
    }
  }
});

// CSRF nonce endpoint — same-origin only (the onRequest hook already enforces
// localhost Host + Origin). The browser fetches this once at boot, then echoes
// the nonce as X-CSRF-Token on each mutating call. Returned as JSON so the
// React/JSX bootstrap can store it in a module-scoped variable.
fastify.get("/api/csrf", async (_req, _reply) => ({ csrfToken: CSRF_NONCE }));

await fastify.register(fastifyStatic, {
  root: CONSOLE_DIR,
  prefix: "/",
  index: ["index.html"],
});

// Sert workspace/input/ui/ tel quel pour que les mockups HTML chargent leur CSS
// relatif (design-system.css, etc.) sans duplication. Cf. UXCarousel côté React.
// Security audit 2026-06-06 : ajouter CSP sandbox + headers défensifs côté serveur
// (en plus du sandbox iframe côté React app.jsx:955). Une URL directe /ui/foo.html
// dans une nouvelle fenêtre n'était PAS protégée. CSP sandbox neutralise scripts/forms.
await fastify.register(fastifyStatic, {
  root: UI_DIR,
  prefix: "/ui/",
  decorateReply: false,
  setHeaders: (res, path) => {
    if (path.toLowerCase().endsWith(".html")) {
      res.setHeader(
        "Content-Security-Policy",
        "sandbox allow-same-origin; default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:;"
      );
      res.setHeader("X-Content-Type-Options", "nosniff");
      res.setHeader("X-Frame-Options", "SAMEORIGIN");
      res.setHeader("Referrer-Policy", "no-referrer");
    }
  },
});

// Vendor static route — serves React / ReactDOM / Babel / marked from local
// node_modules instead of unpkg.com / cdn.jsdelivr.net. Audit P0-security
// 2026-06-05 : the previous CDN-based loading had no Subresource Integrity
// (SRI), so a compromised CDN would result in remote code execution in the
// Tech Lead's browser. Bundling locally removes the external attack surface
// entirely. Versions are pinned in package.json — upgrade via npm + commit.
const NODE_MODULES = join(CONSOLE_DIR, "node_modules");
const VENDOR_FILES = {
  "react.development.js":     join("react", "umd", "react.development.js"),
  "react-dom.development.js": join("react-dom", "umd", "react-dom.development.js"),
  "babel.min.js":             join("@babel", "standalone", "babel.min.js"),
  "marked.min.js":            join("marked", "marked.min.js"),
  // Security audit 2026-06-06 : sanitize HTML produit par marked avant injection
  // via dangerouslySetInnerHTML (XSS surface si contenu LLM hostile).
  "purify.min.js":            join("dompurify", "dist", "purify.min.js"),
};
fastify.get("/vendor/:name", async (req, reply) => {
  const name = req.params.name;
  const rel = VENDOR_FILES[name];
  if (!rel) return reply.code(404).send({ error: "unknown vendor file" });
  const abs = join(NODE_MODULES, rel);
  if (!existsSync(abs)) {
    return reply.code(503).send({
      error: "vendor file missing — run `npm install` in workspace/console/",
      hint: `expected at: ${abs}`,
    });
  }
  // Read once per request; the OS page cache handles repeats efficiently.
  const content = await readFile(abs);
  reply
    .header("Content-Type", "application/javascript; charset=utf-8")
    .header("Cache-Control", "public, max-age=3600")
    .send(content);
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

// Whitelist of allowed subdirectories under workspace/ for /api/file reads.
// Anything outside this set is REFUSED, even if it lives under workspace/.
// Rationale (audit P0-security 2026-06-05) : the previous implementation only
// checked that the resolved path was inside workspace/, which exposed
// `workspace/input/stack/stack.md` — a file containing DB_PASSWORD,
// AUTH_JWT_SECRET, AZ_TENANTID and other secrets. Any browser extension or
// localhost-bound page could exfiltrate via GET /api/file?path=...
const ALLOWED_API_FILE_PREFIXES = [
  // FEAT / US / Plans markdown — public to the console UI
  join("input",  "feats")  + sep,
  join("output", "us")     + sep,
  join("output", "plans")  + sep,
  // QA reports + readiness gates — read-only, no secrets
  join("output", "qa")     + sep,
  join("output", ".sys", ".validation") + sep,
  // Constitution + ADRs — no secrets
  join("output", ".sys", ".context")    + sep,
  // UI mockups (already served by /ui/* static route, but allowed here too)
  join("input",  "ui")     + sep,
];

// Filename suffixes allowed by /api/file. Refuses .env, .key, .pem, etc.
const ALLOWED_API_FILE_SUFFIXES = [".md", ".json", ".html", ".txt"];

// Explicit denylist (belt + braces, even if the prefix logic regresses).
const DENIED_API_FILE_BASENAMES = new Set([
  "stack.md",          // workspace/input/stack/stack.md — secrets
  "stack.md.candidate",
  ".env", ".env.local", ".env.production",
  "credentials.json", "secrets.json",
]);

fastify.get("/api/file", async (req, reply) => {
  const path = req.query.path;
  if (typeof path !== "string" || !path) {
    return reply.code(400).send({ error: "missing path" });
  }
  // Reject absolute paths and NUL bytes outright (defense-in-depth).
  if (path.includes("\0") || /^([a-zA-Z]:|\/|\\)/.test(path)) {
    return reply.code(403).send({ error: "path must be relative to workspace/" });
  }

  const abs = resolve(WORKSPACE, path);
  const wsRel = relative(WORKSPACE, abs);
  if (wsRel.startsWith("..") || wsRel.includes(`..${sep}`)) {
    return reply.code(403).send({ error: "path hors workspace/" });
  }

  // Whitelist subdirectory check.
  const wsRelNorm = wsRel.split("/").join(sep); // normalize forward slashes
  if (!ALLOWED_API_FILE_PREFIXES.some((p) => wsRelNorm.startsWith(p))) {
    return reply.code(403).send({
      error: "path outside the whitelisted subdirectories",
      allowed: ALLOWED_API_FILE_PREFIXES.map((p) => p.replace(/\\/g, "/")),
    });
  }

  // Suffix check.
  const lower = wsRelNorm.toLowerCase();
  if (!ALLOWED_API_FILE_SUFFIXES.some((s) => lower.endsWith(s))) {
    return reply.code(403).send({
      error: "file extension not allowed",
      allowed: ALLOWED_API_FILE_SUFFIXES,
    });
  }

  // Explicit basename denylist (catches stack.md even if the prefix logic
  // somehow allows input/stack/).
  const base = wsRelNorm.split(sep).pop().toLowerCase();
  if (DENIED_API_FILE_BASENAMES.has(base)) {
    return reply.code(403).send({ error: "file explicitly denied (contains secrets or sensitive data)" });
  }

  if (!existsSync(abs)) return reply.code(404).send({ error: "not found" });
  const raw = await readFile(abs, "utf8");
  const st  = await stat(abs);
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
// Endpoint /api/help/:id RETIRÉ 2026-06-06
// ─────────────────────────────────────────────
// La console ne sert plus la documentation du framework SDD_Pro lui-même
// (séparation des responsabilités) — la doc vit dans le site MkDocs
// Material (cf. mkdocs.yml au root + .claude/docs/README.md). Lancer :
//
//   pip install -r requirements-docs.txt
//   mkdocs serve   # → http://localhost:8000
//
// La console reste DÉDIÉE aux stats des projets matérialisés (FEATs, US,
// coverage, security, runs, tokens) lues depuis console.db.

fastify.get("/api/health", async () => ({
  ok: true,
  console: "sdd-console",
  // Console-app version (Fastify server package — workspace/console/package.json).
  // Lue dynamiquement pour éviter drift (security audit 2026-06-06 : était hardcodée
  // "0.4.0" tandis que package.json disait "0.5.0"). Decoupled from the SDD_Pro
  // framework version on purpose (audit M8) : the console iterates on UI cadence ;
  // the framework on DSL cadence.
  version: (() => {
    try {
      const pkgPath = join(CONSOLE_DIR, "package.json");
      if (!existsSync(pkgPath)) return "unknown";
      const pkg = JSON.parse(readFileSync(pkgPath, "utf8"));
      return pkg.version || "unknown";
    } catch { return "unknown"; }
  })(),
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
// POST /api/explain — reformulation IA PO-friendly (LOT 4)
// Security audit 2026-06-06 (R2) : GET → POST car endpoint a effets de bord
// (appel Anthropic payant + envoi contenu fichier). POST garantit que les
// pre-flight CORS et l'Origin check (onRequest) s'appliquent strictement,
// que rien n'est mis en cache navigateur, et que les bots/preview HTML
// ne déclenchent pas accidentellement le payload.
// ─────────────────────────────────────────────
fastify.post("/api/explain", async (req, reply) => {
  // /api/explain envoie fileContent à Anthropic. Whitelist alignée sur /api/file
  // empêche l'exfiltration de stack.md, .env, secrets.json vers l'API LLM.
  const body = req.body || {};
  const path = body.path;
  const force = body.force === true || body.force === "1" || body.force === 1;
  if (typeof path !== "string" || !path) {
    return reply.code(400).send({ error: "missing path" });
  }
  // Reject absolute paths and NUL bytes outright (defense-in-depth, idem /api/file).
  if (path.includes("\0") || /^([a-zA-Z]:|\/|\\)/.test(path)) {
    return reply.code(403).send({ error: "path must be relative to workspace/" });
  }
  // Resolve under WORKSPACE (was ROOT — too wide) and check containment.
  const abs = resolve(WORKSPACE, path);
  const wsRel = relative(WORKSPACE, abs);
  if (wsRel.startsWith("..") || wsRel.includes(`..${sep}`)) {
    return reply.code(403).send({ error: "path hors workspace/" });
  }
  // Whitelist subdirectory check (réutilisation pattern /api/file).
  const wsRelNorm = wsRel.split("/").join(sep);
  if (!ALLOWED_API_FILE_PREFIXES.some((p) => wsRelNorm.startsWith(p))) {
    return reply.code(403).send({
      error: "path outside the whitelisted subdirectories (explain refuse l'exfiltration vers Anthropic API)",
      allowed: ALLOWED_API_FILE_PREFIXES.map((p) => p.replace(/\\/g, "/")),
    });
  }
  // Suffix check.
  const lower = wsRelNorm.toLowerCase();
  if (!ALLOWED_API_FILE_SUFFIXES.some((s) => lower.endsWith(s))) {
    return reply.code(403).send({
      error: "file extension not allowed for explain",
      allowed: ALLOWED_API_FILE_SUFFIXES,
    });
  }
  // Explicit basename denylist (belt + braces).
  const base = wsRelNorm.split(sep).pop().toLowerCase();
  if (DENIED_API_FILE_BASENAMES.has(base)) {
    return reply.code(403).send({ error: "file explicitly denied (secrets / sensitive data — refuse d'envoyer à Anthropic)" });
  }
  // Note : Origin check appliqué automatiquement par le hook onRequest sur POST
  // (cf. server.js début). Pas besoin de re-checker manuellement comme c'était
  // le cas pour l'ancien GET.
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
// Audit CTO 2026-06-07 — tighter regex on identifier fields. CLAUDE.md §1
// pins basename `{n}-{m}-{Name}` shape ; status.json `FeatId` = `{n}-{Name}`
// and `usId` = `{n}-{m}-{Name}`. Pre-fix, any string was accepted — opens to
// path-injection in status.json keys (e.g. `{"../../etc/passwd": ...}`).
// Lengths capped to mitigate DoS on giant payloads.
const FEAT_ID_RE = /^\d{1,4}-[A-Za-z][A-Za-z0-9-]{0,60}$/;
const US_ID_RE = /^\d{1,4}-\d{1,4}(-[A-Za-z][A-Za-z0-9-]{0,60})?$/;

fastify.post("/api/validate", async (req, reply) => {
  const body = req.body || {};
  const { kind, FeatId, usId, family, decision, comment } = body;

  // Validation arguments
  const VALID_KINDS = new Set(["us", "task"]);
  const VALID_DECISIONS = new Set(["validated", "rejected", "pending-validation"]);
  if (!VALID_KINDS.has(kind))         return reply.code(400).send({ error: "kind must be 'us' or 'task'" });
  if (!VALID_DECISIONS.has(decision)) return reply.code(400).send({ error: "decision must be 'validated' | 'rejected' | 'pending-validation'" });
  if (typeof FeatId !== "string" || !FeatId || !FEAT_ID_RE.test(FeatId)) {
    return reply.code(400).send({ error: "FeatId must match /^\\d{1,4}-[A-Za-z][A-Za-z0-9-]{0,60}$/" });
  }
  if (typeof usId !== "string" || !usId || !US_ID_RE.test(usId)) {
    return reply.code(400).send({ error: "usId must match /^\\d{1,4}-\\d{1,4}(-[A-Za-z][A-Za-z0-9-]{0,60})?$/" });
  }
  if (kind === "task" && !["back", "front", "ui", "qa"].includes(family)) {
    return reply.code(400).send({ error: "family must be 'back'|'front'|'ui'|'qa' when kind='task'" });
  }
  // Reject pathological `comment` length BEFORE slice (defense-in-depth).
  if (comment !== undefined && typeof comment === "string" && comment.length > 10000) {
    return reply.code(413).send({ error: "comment exceeds 10000 chars" });
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
  // Audit CTO 2026-06-07 — FeatNum tightened. Was: `number | string` any
  // value. Now: positive integer in [1, 9999], rejecting NaN/Infinity/zero.
  // Same DoS cap on comment length as /api/validate.
  if (typeof FeatNum !== "number" && typeof FeatNum !== "string") {
    return reply.code(400).send({ error: "FeatNum required (number|string)" });
  }
  const featNumParsed = Number(FeatNum);
  if (!Number.isInteger(featNumParsed) || featNumParsed < 1 || featNumParsed > 9999) {
    return reply.code(400).send({ error: "FeatNum must be a positive integer in [1, 9999]" });
  }
  if (!VALID_PHASES.has(phase)) {
    return reply.code(400).send({ error: `phase must be one of ${[...VALID_PHASES].join("|")}` });
  }
  if (!VALID_DECISIONS.has(decision)) {
    return reply.code(400).send({ error: `decision must be one of ${[...VALID_DECISIONS].join("|")}` });
  }
  if (comment !== undefined && typeof comment === "string" && comment.length > 10000) {
    return reply.code(413).send({ error: "comment exceeds 10000 chars" });
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
