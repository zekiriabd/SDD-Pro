#!/usr/bin/env node
// Smoke test : validate that app.jsx contains all expected top-level
// components. Catches accidental deletion / rename without requiring
// a full JS test runner (we stay "no build step").
//
// Usage : node tests/structure.smoke.test.js
// Exit 0 = OK, exit 1 = missing components.
//
// v7.0.0-alpha (audit 2026-06-05) — premier test côté console web.
// Roadmap #25 : refactor app.jsx en composants ES modules + Vitest.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname  = dirname(__filename);
const APP_JSX    = join(__dirname, "..", "app.jsx");

// Composants critiques attendus dans app.jsx — la liste reflète l'état
// au moment du refactor v7.0.0. Toute suppression doit être intentionnelle
// et accompagnée d'une mise à jour de ce test.
const EXPECTED_COMPONENTS = [
  // Shell
  "TopBar", "ProjectSwitcher", "DocMenu", "HelpModal",
  // Navigation
  "Tree", "TreeNode", "Crumb",
  // Detail panes
  "FeatureDetail", "USDetail", "TaskDetail", "Detail",
  // Features
  "FeaturesHeader", "UXCarousel", "ViewToggle",
  // IA
  "IAReformulateBar", "ExplainView",
  // Charts
  "DonutChart", "Sparkline", "KpiCard",
  "ChartCoverage", "ChartQualityStack", "ChartApiGate", "ChartSecurityDonut",
  // Dashboard
  "DashboardPage", "SonarRow", "SonarMetric", "SonarMetricsSection",
  // Gates
  "GateBanner",
  // Action
  "ActionBar",
  // Status
  "StatusBadge", "StatusDot", "VerdictBadge",
  // Loading
  "LoadingSpinner",
];

// Endpoints API critiques attendus (anti-régression — vérifier que le code
// consomme bien les endpoints exposés par server.js).
const EXPECTED_ENDPOINTS = [
  "/api/tree",
  "/api/dashboard",
  "/api/validate",
  "/api/gate-decide",
  "/api/help/",
  "/api/events",
];

function fail(msg) {
  console.error(`❌ ${msg}`);
  process.exit(1);
}

function main() {
  let src;
  try {
    src = readFileSync(APP_JSX, "utf-8");
  } catch (e) {
    fail(`Cannot read ${APP_JSX}: ${e.message}`);
  }

  const missing = [];
  for (const name of EXPECTED_COMPONENTS) {
    // Match `function Name(` OR `const Name = (` OR `const Name = function`
    const re = new RegExp(
      `(function\\s+${name}\\s*\\(|const\\s+${name}\\s*=\\s*[\\(f])`
    );
    if (!re.test(src)) missing.push(name);
  }

  const missingEndpoints = [];
  for (const ep of EXPECTED_ENDPOINTS) {
    if (!src.includes(ep)) missingEndpoints.push(ep);
  }

  if (missing.length === 0 && missingEndpoints.length === 0) {
    console.log(`✅ app.jsx structure OK`);
    console.log(`   ${EXPECTED_COMPONENTS.length} expected components found`);
    console.log(`   ${EXPECTED_ENDPOINTS.length} expected endpoints consumed`);
    console.log(`   size: ${(src.length / 1024).toFixed(1)} KB`);
    process.exit(0);
  }

  console.error(`❌ app.jsx structure check failed:`);
  if (missing.length) {
    console.error(`   Missing components (${missing.length}):`);
    missing.forEach((c) => console.error(`     - ${c}`));
  }
  if (missingEndpoints.length) {
    console.error(`   Missing endpoint references (${missingEndpoints.length}):`);
    missingEndpoints.forEach((e) => console.error(`     - ${e}`));
  }
  process.exit(1);
}

main();
