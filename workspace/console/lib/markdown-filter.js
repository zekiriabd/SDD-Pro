// markdown-filter.js
// Pure functions to parse SDD_Pro markdown files (FEATs / US / plans)
// and produce PO-friendly objects for the console UI.
//
// Hides technical traceability noise (Covers, SFD-N raw refs, status
// frontmatter, out-of-scope). Keeps user-facing semantics: objective,
// acceptance criteria, business rules, scenarios.

// ─────────────────────────────────────────────
// FEAT parser (workspace/input/feats/{n}-{name}.md)
// ─────────────────────────────────────────────
export function parseSpec(raw) {
  const sections = splitSections(raw);
  const rawTitle = (raw.match(/^#\s+FEAT:\s*(.+?)$/m)?.[1] || "").trim();
  const title = rawTitle ? rawTitle.charAt(0).toUpperCase() + rawTitle.slice(1) : "";

  const objective = (sections["Objective"] || "").trim();
  const context = (sections["Context"] || "").trim();
  const actors = parseBulletList(sections["Actors"]);
  const businessRules = parseIdBullets(sections["Business Rules"], "BR");
  const acceptanceCriteria = parseIdBullets(sections["Acceptance Criteria"], "AC");
  const stakeholders = parseStakeholdersTable(sections["Parties Prenantes"]);

  return {
    title,
    summary: objective || context.split("\n")[0] || "",
    context,
    objective,
    actors,
    businessRules,        // [{ id: "BR-1", text: "..." }]
    acceptanceCriteria,   // [{ id: "AC-1", text: "..." }]
    stakeholders,         // [{ actor, role, raci }]
  };
}

// ─────────────────────────────────────────────
// US parser (workspace/output/us/{n}-{m}-{Name}.md)
// ─────────────────────────────────────────────
export function parseUs(raw) {
  const sections = splitSections(raw);
  const headerMatch = raw.match(/^#\s+US-?\d*[:\-]?\s*(.+?)$/m);
  const title = (headerMatch?.[1] || "").trim();

  const meta = parseMetaLines(raw);
  const userStory = parseUserStoryBlock(sections["User Story"]);
  const acceptanceCriteria = parseIdBullets(sections["Acceptance Criteria"], "AC");

  return {
    id: meta["ID"] || "",
    parentSpec: meta["Parent FEAT"] || "",
    technicalStatus: (meta["Status"] || "Draft"),  // technical agent status (Draft/Done)
    title,
    objective: userStory.full,
    asA: userStory.asA,
    iWant: userStory.iWant,
    soThat: userStory.soThat,
    acceptanceCriteria,
  };
}

// ─────────────────────────────────────────────
// Plan parser (workspace/output/plans/{n}-{m}-{Name}.{back|front}.md)
// ─────────────────────────────────────────────
export function parsePlan(raw) {
  const { frontmatter, body } = splitFrontmatter(raw);
  const sections = splitSections(body);
  const titleMatch = body.match(/^#\s+Plan technique\s+(\w+)\s+—\s+(.+?)$/m);

  const files = parsePlanFiles(sections["Files"] || "");
  const intro = (body.split(/^##\s+/m)[0] || "").replace(/^#.+\n/, "").trim();

  return {
    us: frontmatter.us || "",
    family: frontmatter.family || (titleMatch?.[1] || "").toLowerCase(),
    generatedAt: frontmatter["generated-at"] || "",
    stack: {
      backend: frontmatter["stack-backend"],
      frontend: frontmatter["stack-frontend"],
      ui: frontmatter["stack-ui"],
      auth: frontmatter["stack-auth"],
    },
    htmlSource: frontmatter["html-source"] || "",
    title: titleMatch?.[2] || "",
    intro,
    files,        // [{ path, operation, layer, covers_acs, ds_components, notes }]
  };
}

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

function splitFrontmatter(raw) {
  const m = raw.match(/^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$/);
  if (!m) return { frontmatter: {}, body: raw };
  const fm = {};
  m[1].split("\n").forEach((line) => {
    const kv = line.match(/^(\S+?):\s*(.*)$/);
    if (kv) fm[kv[1].trim()] = kv[2].trim();
  });
  return { frontmatter: fm, body: m[2] };
}

function splitSections(raw) {
  const out = {};
  const lines = raw.split(/\r?\n/);
  let current = null;
  let buf = [];
  for (const line of lines) {
    const h = line.match(/^##\s+(.+?)\s*$/);
    if (h) {
      if (current) out[current] = buf.join("\n").trim();
      current = h[1].trim();
      buf = [];
    } else if (current) {
      buf.push(line);
    }
  }
  if (current) out[current] = buf.join("\n").trim();
  return out;
}

function parseMetaLines(raw) {
  const out = {};
  const head = raw.split(/^##\s+/m)[0];
  head.split(/\r?\n/).forEach((line) => {
    const kv = line.match(/^(ID|Parent FEAT|Status|FEAT ID):\s*(.+?)$/);
    if (kv) out[kv[1]] = kv[2].trim();
  });
  return out;
}

function parseBulletList(section) {
  if (!section) return [];
  return section
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.startsWith("- "))
    .map((l) => l.slice(2).trim())
    .filter(Boolean);
}

// Parse list of "- ID-N: text" → [{ id, text }] ; strips the prefix on output
function parseIdBullets(section, prefix) {
  if (!section) return [];
  const out = [];
  const re = new RegExp(`^-\\s+(${prefix}-\\d+):\\s*(.+)$`);
  section.split(/\r?\n/).forEach((line) => {
    const m = line.trim().match(re);
    if (m) out.push({ id: m[1], text: m[2].trim() });
  });
  return out;
}

function parseUserStoryBlock(section) {
  if (!section) return { asA: "", iWant: "", soThat: "", full: "" };
  const lines = section.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  let asA = "", iWant = "", soThat = "";
  for (const line of lines) {
    const cl = line.toLowerCase();
    if (cl.startsWith("en tant que") || cl.startsWith("en tant qu'") || cl.startsWith("as a") || cl.startsWith("as an")) {
      asA = line;
    } else if (cl.startsWith("je veux") || cl.startsWith("i want")) {
      iWant = line;
    } else if (cl.startsWith("afin de") || cl.startsWith("afin d'") || cl.startsWith("so that") || cl.startsWith("pour ") || cl.startsWith("pour pouvoir")) {
      soThat = line;
    }
  }
  return { asA, iWant, soThat, full: lines.join(" ") };
}

function parseStakeholdersTable(section) {
  if (!section) return [];
  const out = [];
  const lines = section.split(/\r?\n/).map((l) => l.trim());
  for (const line of lines) {
    if (!line.startsWith("|")) continue;
    if (line.includes("---")) continue;
    if (/Acteur\s*\|\s*R[oô]le/i.test(line)) continue;
    const cells = line.split("|").map((c) => c.trim()).filter((_, i, a) => i > 0 && i < a.length - 1);
    if (cells.length >= 2) {
      out.push({ actor: cells[0], role: cells[1] || "", raci: cells[2] || "" });
    }
  }
  return out;
}

// Plan §Files parser : each file = block starting with "- path:" until next "- path:" or section end
function parsePlanFiles(section) {
  if (!section) return [];
  const blocks = [];
  let cur = null;
  section.split(/\r?\n/).forEach((line) => {
    if (/^-\s+path:/.test(line)) {
      if (cur) blocks.push(cur);
      cur = { raw: [line] };
    } else if (cur) {
      cur.raw.push(line);
    }
  });
  if (cur) blocks.push(cur);

  return blocks.map((b) => {
    const text = b.raw.join("\n");
    return {
      path: matchVal(text, /^-\s+path:\s*(.+)$/m),
      operation: matchVal(text, /^\s+operation:\s*(.+)$/m) || "create",
      layer: matchVal(text, /^\s+layer:\s*(.+)$/m) || "",
      coversAcs: matchVal(text, /^\s+covers_acs:\s*\[([^\]]+)\]/m)?.split(",").map((s) => s.trim()) || [],
      dsComponents: matchVal(text, /^\s+ds_components:\s*\[([^\]]+)\]/m)?.split(",").map((s) => s.trim()) || [],
      notes: extractIndentedBlock(text, "notes:"),
    };
  });
}

function matchVal(text, re) {
  const m = text.match(re);
  return m ? m[1].trim() : null;
}

function extractIndentedBlock(text, key) {
  const lines = text.split(/\r?\n/);
  const idx = lines.findIndex((l) => l.trim().startsWith(key));
  if (idx === -1) return "";
  const out = [];
  for (let i = idx + 1; i < lines.length; i++) {
    if (/^\s+- \w/.test(lines[i]) || /^-\s+path:/.test(lines[i])) break;
    out.push(lines[i].replace(/^\s{4}/, ""));
  }
  return out.join("\n").trim();
}
