// explain.js
// Reformulation IA opt-in (LOT 4) : Anthropic SDK + cache disque content-addressed.
// L appel n est jamais bloquant : si ANTHROPIC_API_KEY absent, lever une erreur
// 503 cote endpoint pour que l UI desactive proprement le toggle.

import Anthropic from "@anthropic-ai/sdk";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));            // workspace/console/lib
const CONSOLE_DIR = dirname(__dirname);                                // workspace/console
const WORKSPACE   = dirname(CONSOLE_DIR);                              // workspace
const ROOT        = dirname(WORKSPACE);                                // c:/DEV/SDD_Pro
const TEMPLATE_PATH = join(ROOT, ".claude", "templates", "explain-po.prompt.md");
const CACHE_DIR     = join(CONSOLE_DIR, ".cache", "explained");

const DEFAULT_MODEL = process.env.SDD_EXPLAIN_MODEL || "claude-haiku-4-5-20251001";
const MAX_TOKENS    = parseInt(process.env.SDD_EXPLAIN_MAX_TOKENS || "1500", 10);

let cachedTemplate = null;
let cachedTemplateHash = null;

async function loadTemplate() {
  if (cachedTemplate) return { content: cachedTemplate, hash: cachedTemplateHash };
  if (!existsSync(TEMPLATE_PATH)) {
    throw new Error(`prompt template not found: ${TEMPLATE_PATH}`);
  }
  cachedTemplate = await readFile(TEMPLATE_PATH, "utf8");
  cachedTemplateHash = createHash("sha256").update(cachedTemplate).digest("hex").slice(0, 16);
  return { content: cachedTemplate, hash: cachedTemplateHash };
}

function detectKind(path) {
  if (path.includes("/input/feats/") || path.includes("\\input\\FEATs\\")) return "FEAT";
  if (path.includes("/output/us/")    || path.includes("\\output\\us\\"))    return "user-story";
  if (path.includes("/output/plans/") || path.includes("\\output\\plans\\")) return "technical-plan";
  if (path.includes("/input/ui/")     || path.includes("\\input\\ui\\"))     return "ui-mockup";
  return "markdown";
}

function cacheKeyFor(content, templateHash, model) {
  const hash = createHash("sha256")
    .update(model)
    .update("|")
    .update(templateHash)
    .update("|")
    .update(content)
    .digest("hex");
  return hash.slice(0, 32);
}

async function readCache(key) {
  const path = join(CACHE_DIR, `${key}.json`);
  if (!existsSync(path)) return null;
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch {
    return null;
  }
}

async function writeCache(key, payload) {
  if (!existsSync(CACHE_DIR)) await mkdir(CACHE_DIR, { recursive: true });
  const path = join(CACHE_DIR, `${key}.json`);
  await writeFile(path, JSON.stringify(payload, null, 2), "utf8");
}

function fillTemplate(template, vars) {
  return template
    .replace(/\{\{path\}\}/g,    vars.path)
    .replace(/\{\{kind\}\}/g,    vars.kind)
    .replace(/\{\{content\}\}/g, vars.content);
}

/**
 * @param {{ filePath: string, fileContent: string, model?: string }} opts
 * @returns {Promise<{ content: string, model: string, cached: boolean, cacheKey: string }>}
 */
export async function explain({ filePath, fileContent, model = DEFAULT_MODEL }) {
  if (!process.env.ANTHROPIC_API_KEY) {
    const err = new Error("ANTHROPIC_API_KEY not set");
    err.code = "NO_API_KEY";
    throw err;
  }
  if (process.env.SDD_EXPLAIN_DISABLE === "1" || process.env.SDD_EXPLAIN_DISABLE === "true") {
    const err = new Error("explain disabled (SDD_EXPLAIN_DISABLE)");
    err.code = "DISABLED";
    throw err;
  }

  const { content: templateRaw, hash: templateHash } = await loadTemplate();
  const key = cacheKeyFor(fileContent, templateHash, model);

  const cached = await readCache(key);
  if (cached) {
    return { ...cached, cached: true, cacheKey: key };
  }

  const kind = detectKind(filePath);
  const prompt = fillTemplate(templateRaw, {
    path: relative(ROOT, filePath).replaceAll("\\", "/"),
    kind,
    content: fileContent,
  });

  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  const response = await client.messages.create({
    model,
    max_tokens: MAX_TOKENS,
    messages: [{ role: "user", content: prompt }],
  });

  const text = response.content
    .filter((b) => b.type === "text")
    .map((b) => b.text)
    .join("\n")
    .trim();

  const payload = {
    content: text,
    model,
    generatedAt: new Date().toISOString(),
    sourceFile: filePath,
    templateHash,
  };
  await writeCache(key, payload);
  return { ...payload, cached: false, cacheKey: key };
}

export function isAvailable() {
  if (!process.env.ANTHROPIC_API_KEY) return { ok: false, reason: "ANTHROPIC_API_KEY not set" };
  if (process.env.SDD_EXPLAIN_DISABLE === "1" || process.env.SDD_EXPLAIN_DISABLE === "true") {
    return { ok: false, reason: "SDD_EXPLAIN_DISABLE active" };
  }
  return { ok: true, model: DEFAULT_MODEL };
}
