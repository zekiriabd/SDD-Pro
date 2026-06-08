// workspace/console/tests/smoke.test.js
//
// Pragmatic smoke test for the SDD Console (POC-only, cf. CLAUDE.md §6).
// Run via `npm test`. Verifies:
//   1. All server-side JS files parse without syntax errors.
//   2. app.jsx bundles cleanly through esbuild (catches JSX/scope errors).
//   3. The built dist/app.js exists and is non-trivial.
//   4. index.html no longer references @babel/standalone (anti-regression
//      for the 2026-06-08 CDN+Babel removal).
//
// Exit codes : 0 = SUCCESS, 1 = FAIL (any check failed).
// Deliberately minimal — this is a POC tool, not a SLA component.

import { execSync, spawnSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const CONSOLE_DIR = resolve(__dirname, "..");
const failures = [];

function check(label, fn) {
  try {
    fn();
    console.log(`  OK  ${label}`);
  } catch (err) {
    failures.push({ label, err: err.message || String(err) });
    console.error(`  FAIL ${label}: ${err.message || err}`);
  }
}

console.log("SDD Console smoke test\n");

// 1. node --check on every server-side JS file
const serverFiles = [
  "server.js",
  "data-loader.js",
  "lib/atomic-write.js",
  "lib/console-db.js",
  "lib/explain.js",
  "lib/markdown-filter.js",
];
for (const rel of serverFiles) {
  check(`node --check ${rel}`, () => {
    const abs = join(CONSOLE_DIR, rel);
    if (!existsSync(abs)) throw new Error(`missing ${rel}`);
    execSync(`node --check "${abs}"`, { stdio: "pipe" });
  });
}

// 2. esbuild build (catches JSX errors, undeclared refs, etc.)
check("esbuild bundle app.jsx", () => {
  if (!existsSync(join(CONSOLE_DIR, "node_modules", "esbuild"))) {
    throw new Error("esbuild not installed — run `npm ci` first");
  }
  const res = spawnSync("npm", ["run", "build", "--silent"], {
    cwd: CONSOLE_DIR,
    stdio: "pipe",
    shell: true,
  });
  if (res.status !== 0) {
    throw new Error(`build failed: ${res.stderr?.toString() || res.stdout?.toString()}`);
  }
});

// 3. dist/app.js exists + is non-trivial
check("dist/app.js produced and >= 50 KB", () => {
  const dist = join(CONSOLE_DIR, "dist", "app.js");
  if (!existsSync(dist)) throw new Error("dist/app.js missing");
  const sz = statSync(dist).size;
  if (sz < 50_000) throw new Error(`dist/app.js suspiciously small: ${sz} bytes`);
});

// 4. anti-regression : index.html must NOT load @babel/standalone
check("index.html drops @babel/standalone CDN", () => {
  const html = readFileSync(join(CONSOLE_DIR, "index.html"), "utf8");
  if (/babel\/standalone/i.test(html)) {
    throw new Error("@babel/standalone still referenced in index.html");
  }
  if (/type="text\/babel"/i.test(html)) {
    throw new Error('`type="text/babel"` script tag still present');
  }
});

// 5. CSP header is configured in server.js (anti-regression)
check("server.js sets Content-Security-Policy", () => {
  const srv = readFileSync(join(CONSOLE_DIR, "server.js"), "utf8");
  if (!/Content-Security-Policy/.test(srv)) {
    throw new Error("CSP header not configured");
  }
});

if (failures.length) {
  console.error(`\nSMOKE FAIL: ${failures.length}/${serverFiles.length + 4} checks failed`);
  process.exit(1);
}
console.log(`\nSMOKE OK: ${serverFiles.length + 4} checks passed`);
