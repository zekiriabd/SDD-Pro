/* global React, ReactDOM, marked */
const { useState, useMemo, useEffect, useCallback, Fragment } = React;

// ───────── HELPERS ─────────
function getNodePath(node) {
  return node?.file || node?.source || null;
}

// ───────── ICONS ─────────
const Icon = {
  caretRight: () => <svg className="i" viewBox="0 0 16 16"><path d="M6 4l4 4-4 4"/></svg>,
  caretDown: () => <svg className="i" viewBox="0 0 16 16"><path d="M4 6l4 4 4-4"/></svg>,
  feature: () => <svg className="i" viewBox="0 0 16 16"><rect x="2.5" y="3" width="11" height="10" rx="1.5"/><path d="M2.5 6.5h11"/></svg>,
  us: () => <svg className="i" viewBox="0 0 16 16"><circle cx="6" cy="6" r="2.5"/><path d="M2 13c0-2.2 1.8-4 4-4s4 1.8 4 4"/><path d="M11 4l3 1.5L11 7"/></svg>,
  task: () => <svg className="i" viewBox="0 0 16 16"><path d="M3.5 8l2.5 2.5 6.5-6.5"/></svg>,
  search: () => <svg className="i" viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.5"/><path d="M11 11l3 3"/></svg>,
  check: () => <svg className="i" viewBox="0 0 16 16"><path d="M3.5 8.5l3 3 6-7"/></svg>,
  x: () => <svg className="i" viewBox="0 0 16 16"><path d="M4 4l8 8M12 4l-8 8"/></svg>,
  pause: () => <svg className="i" viewBox="0 0 16 16"><path d="M5.5 4v8M10.5 4v8"/></svg>,
  refresh: () => <svg className="i" viewBox="0 0 16 16"><path d="M3 8a5 5 0 0 1 9-3l1 1"/><path d="M13 3v3h-3"/><path d="M13 8a5 5 0 0 1-9 3l-1-1"/><path d="M3 13v-3h3"/></svg>,
  bell: () => <svg className="i" viewBox="0 0 16 16"><path d="M4 11V8a4 4 0 0 1 8 0v3l1 1.5H3z"/><path d="M6.5 13.5a1.5 1.5 0 0 0 3 0"/></svg>,
  settings: () => <svg className="i" viewBox="0 0 16 16"><circle cx="8" cy="8" r="2"/><path d="M8 1.5v2M8 12.5v2M14.5 8h-2M3.5 8h-2M12.6 3.4l-1.4 1.4M4.8 11.2l-1.4 1.4M12.6 12.6l-1.4-1.4M4.8 4.8L3.4 3.4"/></svg>,
  doc: () => <svg className="i" viewBox="0 0 16 16"><path d="M4 2h5l3 3v9H4z"/><path d="M9 2v3h3"/></svg>,
  help: () => <svg className="i" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6"/><path d="M6.3 6c.2-1 1-1.5 1.9-1.5 1.1 0 1.8.7 1.8 1.6 0 .8-.5 1.2-1.2 1.6-.5.3-.7.6-.7 1.1"/><circle cx="8" cy="11.5" r=".4" fill="currentColor"/></svg>,
  sun:      () => <svg className="i" viewBox="0 0 16 16"><circle cx="8" cy="8" r="3"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6L13 13M3 13l1.4-1.4M11.6 4.4L13 3"/></svg>,
  moon:     () => <svg className="i" viewBox="0 0 16 16"><path d="M13 9.5A6 6 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5z"/></svg>,
  book:     () => <svg className="i" viewBox="0 0 16 16"><path d="M3 2.5h6c1 0 1.5.5 1.5 1.5v10c0-1-1-1.5-1.5-1.5H3z"/><path d="M13 2.5H9c-1 0-1.5.5-1.5 1.5v10c0-1 .5-1.5 1.5-1.5h4z"/></svg>,
};

// Pages de documentation embarquées dans le SPA (depuis v6.10 — plus d'ouverture dans un onglet).
// Servies via /api/help/:id (server.js) puis rendues inline via iframe srcdoc.
const DOC_PAGES = [
  { id: "fonctionnelle", title: "Fonctionnelle", subtitle: "Vue d ensemble du framework SDD_Pro" },
  { id: "technique",     title: "Technique",     subtitle: "Architecture, agents, pipeline (v6.0)" },
];

// ───────── STATUS HELPERS ─────────
const STATUS_LABELS = {
  "validated":          { label: "Validé",                  cls: "ok" },
  "pending-validation": { label: "En attente de validation", cls: "warn" },
  "in-progress":        { label: "En cours",                cls: "info" },
  "rejected":           { label: "Rejeté",                  cls: "danger" },
  "not-started":        { label: "Non démarré",             cls: "muted" },
};

function StatusBadge({ status }) {
  const s = STATUS_LABELS[status] || STATUS_LABELS["not-started"];
  return <span className={`badge ${s.cls}`}><span className="d"/> {s.label}</span>;
}

function StatusDot({ status }) {
  const s = STATUS_LABELS[status] || STATUS_LABELS["not-started"];
  return <span className={`st ${s.cls}`} title={s.label}/>;
}

const GATE_LABELS = {
  afterUS:        { from: "PO",         to: "Validation readiness" },
  afterReadiness: { from: "Readiness",  to: "Plans techniques" },
  afterPlan:      { from: "Plans",      to: "Développement" },
  afterCode:      { from: "Dev",        to: "QA" },
};

// ───────── TOP BAR ─────────
function TopBar({ page, setPage, theme, toggleTheme }) {
  const logoSrc = theme === "dark" ? "/logo-dark.svg" : "/logo-light.svg";
  return (
    <header className="topbar">
      <div className="brand">
        <img className="brand-logo" src={logoSrc} alt="SDD Pro" onError={(e) => { e.currentTarget.style.display = "none"; }}/>
        <div className="brand-name">SDD Pro</div>
      </div>
      <nav className="nav-tabs" role="tablist" aria-label="Navigation principale">
        <button
          role="tab"
          className={`nav-tab ${page === "dashboard" ? "active" : ""}`}
          aria-selected={page === "dashboard"}
          onClick={() => setPage("dashboard")}>
          Dashboard
        </button>
        <button
          role="tab"
          className={`nav-tab ${page === "workspace" ? "active" : ""}`}
          aria-selected={page === "workspace"}
          onClick={() => setPage("workspace")}>
          Features
        </button>
        <DocMenu page={page} setPage={setPage}/>
      </nav>
      <div className="tb-actions" style={{alignItems: 'center', marginLeft: 'auto'}}>
        <button
          className="theme-toggle"
          title={theme === "dark" ? "Passer en thème clair" : "Passer en thème sombre"}
          onClick={toggleTheme}>
          {theme === "dark" ? <Icon.sun/> : <Icon.moon/>}
        </button>
      </div>
    </header>
  );
}

function ProjectSwitcher({ projects, currentProjectId, setCurrentProjectId, fallbackName }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onClick = (e) => {
      if (!e.target.closest(".proj-dropdown") && !e.target.closest(".proj-trigger")) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const hasProjects = projects && projects.length > 0;
  const allOption = { id: "__all__", name: "Tous", type: null };
  const items = hasProjects ? [allOption, ...projects] : [];
  const active = hasProjects
    ? (items.find(p => p.id === (currentProjectId || "__all__")) || allOption)
    : { id: null, name: fallbackName || "(projet)", type: null };

  if (!hasProjects) {
    return (
      <div className="proj">
        <kbd>projet</kbd>
        <span style={{fontWeight: 500}}>{active.name}</span>
      </div>
    );
  }

  return (
    <div style={{position: "relative"}}>
      <button
        className="proj proj-trigger"
        onClick={() => setOpen(!open)}
        title="Basculer entre les projets du workspace"
        style={{border: open ? "1px solid var(--accent)" : undefined}}>
        <kbd>projet</kbd>
        <span style={{fontWeight: 500}}>{active.name}</span>
        {active.type && <span style={{fontSize: 11, color: "var(--ink-3)"}}>· {active.type}</span>}
        <span className="proj-caret">▾</span>
      </button>
      {open && (
        <div className="proj-dropdown" style={{
          position: "absolute", top: "100%", left: 0, marginTop: 6,
          background: "var(--panel)", border: "1px solid var(--line)",
          borderRadius: 8, boxShadow: "0 8px 24px oklch(60% 0.02 250 / 0.18)",
          minWidth: 220, zIndex: 100, overflow: "hidden"
        }}>
          <div style={{padding: "10px 14px", borderBottom: "1px solid var(--line-2)", fontSize: 11, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600}}>
            Projets du workspace
          </div>
          {items.map((p) => {
            const isSel = p.id === active.id;
            return (
              <button
                key={p.id}
                onClick={() => {
                  setCurrentProjectId(p.id === "__all__" ? null : p.id);
                  setOpen(false);
                }}
                style={{
                  display: "flex", width: "100%", alignItems: "center", gap: 8,
                  padding: "10px 14px", border: 0,
                  background: isSel ? "var(--accent-soft)" : "transparent",
                  borderBottom: "1px solid var(--line-2)", cursor: "pointer", textAlign: "left",
                  color: isSel ? "var(--accent)" : "var(--ink)"
                }}
                onMouseEnter={(e) => { if (!isSel) e.currentTarget.style.background = "var(--panel-2)"; }}
                onMouseLeave={(e) => { if (!isSel) e.currentTarget.style.background = "transparent"; }}>
                <span style={{fontSize: 13, fontWeight: 500, flex: 1}}>{p.name}</span>
                {p.type && <span style={{fontSize: 11, color: "var(--ink-3)"}}>{p.type}</span>}
                {isSel && <span style={{fontSize: 11, color: "var(--accent)"}}>●</span>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ───────── DOC MENU (v6.10 — documentation embarquée inline) ─────────
function DocMenu({ page, setPage }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const onClick = (e) => {
      if (!e.target.closest(".doc-dropdown") && !e.target.closest(".doc-trigger")) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const onDocPage = page === "doc-fonctionnelle" || page === "doc-technique";

  return (
    <div style={{position: 'relative'}}>
      <button
        className={`nav-tab doc-trigger ${onDocPage ? "active" : ""}`}
        aria-expanded={open}
        onClick={() => setOpen(!open)}>
        Documentation <span style={{fontSize: 10, marginLeft: 4}}>▾</span>
      </button>
      {open && (
        <div className="doc-dropdown" style={{
          position: 'absolute', top: '100%', left: 0, marginTop: 6,
          background: 'var(--panel)', border: '1px solid var(--line)',
          borderRadius: 8, boxShadow: 'var(--shadow-md)',
          minWidth: 280, zIndex: 100, overflow: 'hidden'
        }}>
          {DOC_PAGES.map((p) => (
            <button
              key={p.id}
              onClick={() => { setPage("doc-" + p.id); setOpen(false); }}
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                padding: '12px 14px', border: 0, background: 'transparent',
                borderBottom: '1px solid var(--line-2)', cursor: 'pointer',
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'var(--panel-2)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
              <div style={{fontSize: 13, fontWeight: 500, color: 'var(--ink)'}}>{p.title}</div>
              <div style={{fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2}}>{p.subtitle}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ───────── DOC PAGE (HTML inliné, style natif du site, theme-aware) ─────────
function DocPage({ docId }) {
  const [body, setBody] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let cancelled = false;
    setBody(null); setError(null);
    fetch("/api/help/" + docId)
      .then((res) => res.ok ? res.json() : Promise.reject(new Error("HTTP " + res.status)))
      .then((payload) => { if (!cancelled) setBody(payload.body || ""); })
      .catch((err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [docId]);

  if (error) return <div className="doc-content"><div style={{color: "var(--danger)"}}>Erreur : {error}</div></div>;
  if (body === null) return <div className="doc-content"><div style={{color: "var(--ink-3)"}}>Chargement de la documentation…</div></div>;
  return (
    <article className="doc-content">
      <div dangerouslySetInnerHTML={{ __html: body }}/>
    </article>
  );
}

function HelpModal({ page, onClose }) {
  // Echap pour fermer
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="help-modal-backdrop" onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'oklch(0% 0 0 / 0.55)',
      zIndex: 200, display: 'flex', flexDirection: 'column', padding: 24
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        flex: 1, background: 'var(--panel)', borderRadius: 10,
        boxShadow: '0 24px 64px oklch(0% 0 0 / 0.4)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden'
      }}>
        <div style={{
          padding: '12px 18px', borderBottom: '1px solid var(--line)',
          display: 'flex', alignItems: 'center', gap: 14, background: 'var(--panel-2)'
        }}>
          <div style={{flex: 1}}>
            <div style={{fontSize: 14, fontWeight: 600}}>{page.title}</div>
            <div style={{fontSize: 11.5, color: 'var(--ink-3)'}}>{page.subtitle}</div>
          </div>
          <a href={page.src} target="_blank" rel="noreferrer" className="btn ghost" style={{padding: '4px 10px', fontSize: 12}}>
            <Icon.doc/> Ouvrir dans un onglet
          </a>
          <button className="btn" onClick={onClose} style={{padding: '4px 10px', fontSize: 12}}>
            <Icon.x/> Fermer (Échap)
          </button>
        </div>
        <iframe
          src={page.src}
          title={page.title}
          style={{flex: 1, width: '100%', border: 0, background: 'white'}}
          loading="lazy"
        />
      </div>
    </div>
  );
}

// ───────── GATE BANNER (conditional) ─────────
function GateBanner({ gate, onResolve }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  if (!gate) return null;
  const labels = GATE_LABELS[gate.phase] || { from: gate.phase, to: "phase suivante" };

  const decide = async (decision) => {
    setBusy(true); setError(null);
    try {
      const res = await fetch("/api/gate-decide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ FeatNum: gate.FeatNum, phase: gate.phase, decision }),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.error || `HTTP ${res.status}`);
      }
      onResolve?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="gate" role="status">
      <span className="gate-tag">Validation manuelle · FEAT {gate.FeatNum}</span>
      <div className="gate-text">
        <strong>Phase « {labels.from} » terminée.</strong> Le pipeline est en attente de votre validation
        avant de lancer la phase « {labels.to} ».
        {error && <small style={{color: 'var(--danger)'}}> · {error}</small>}
      </div>
      <div className="gate-actions">
        <button className="btn" onClick={() => decide("skipped")} disabled={busy}>
          <Icon.refresh/> Continuer sans valider
        </button>
        <button className="btn primary" onClick={() => decide("validated")} disabled={busy}>
          <Icon.check/> Valider et continuer
        </button>
      </div>
    </div>
  );
}

// ───────── TREE ─────────
function TreeNode({ node, level, expanded, setExpanded, selected, setSelected }) {
  const isOpen = expanded.has(node.id);
  const hasChildren = node.children && node.children.length > 0;
  const isSel = selected === node.id;

  const onClick = (e) => {
    e.stopPropagation();
    setSelected(node.id);
    if (hasChildren) {
      const next = new Set(expanded);
      if (next.has(node.id)) next.delete(node.id); else next.add(node.id);
      setExpanded(next);
    }
  };

  const IconC = node.kind === "feature" ? Icon.feature : node.kind === "us" ? Icon.us : Icon.task;

  // Affichage ID lisible : "1.1" pour US, "back/front/ui" pour tasks
  const idDisplay = (() => {
    if (node.kind === "feature") return `FEAT ${node.FeatNum}`;
    if (node.kind === "us") {
      const m = node.id.match(/^(\d+)-(\d+)-/);
      return m ? `US ${m[1]}.${m[2]}` : node.id;
    }
    if (node.kind === "task") return node.type ? node.type.toUpperCase() : "task";
    return node.id;
  })();

  const rows = [
    <div key={node.id} className={`node lvl-${level} ${isSel ? "selected" : ""}`} onClick={onClick}>
      <span className="caret">
        {hasChildren ? (isOpen ? <Icon.caretDown/> : <Icon.caretRight/>) : null}
      </span>
      <span className="ico"><IconC/></span>
      <span className="id">{idDisplay}</span>
      <span className="label">{node.title}</span>
      <StatusDot status={node.status}/>
    </div>
  ];
  if (isOpen && hasChildren) {
    node.children.forEach((c) => {
      rows.push(
        <TreeNode
          key={c.id}
          node={c}
          level={level + 1}
          expanded={expanded} setExpanded={setExpanded}
          selected={selected} setSelected={setSelected}
        />
      );
    });
  }
  return rows;
}

function Tree({ tree, selected, setSelected }) {
  const [tab, setTab] = useState("structure");
  const [expanded, setExpanded] = useState(new Set(tree.map((n) => n.id)));   // toutes FEATs ouvertes par defaut
  const [filters, setFilters] = useState(new Set());                           // pas de filtre = tout afficher

  // Filtrage : si filters non-vide, on garde uniquement les noeuds dont le statut matche (ou qui ont un descendant matching)
  const filteredTree = useMemo(() => {
    if (filters.size === 0) return tree;
    function keep(node) {
      const self = filters.has(node.status);
      const kids = (node.children || []).map(keep).filter(Boolean);
      if (self || kids.length > 0) return { ...node, children: kids };
      return null;
    }
    return tree.map(keep).filter(Boolean);
  }, [tree, filters]);

  return (
    <aside className="tree-pane">
      <div className="tree-head" style={{padding: "10px 14px"}}>
        <div className="tree-search">
          <Icon.search/>
          <input placeholder="Rechercher feature, US…"/>
          <kbd>⌘K</kbd>
        </div>
      </div>
      <div className="tree-scroll">
        <div className="tree-section-label">Spécifications · {tree.length} feature{tree.length > 1 ? "s" : ""}</div>
        {filteredTree.map((n) => (
          <TreeNode
            key={n.id}
            node={n}
            level={1}
            expanded={expanded} setExpanded={setExpanded}
            selected={selected} setSelected={setSelected}
          />
        ))}
        {filteredTree.length === 0 && (
          <div style={{padding: '20px 14px', color: 'var(--ink-3)', fontSize: 12.5}}>
            Aucun élément ne correspond aux filtres actifs.
          </div>
        )}
      </div>
    </aside>
  );
}

// ───────── DETAIL PANELS ─────────
function findNode(id, nodes, parents = []) {
  for (const n of nodes) {
    if (n.id === id) return { node: n, parents };
    if (n.children) {
      const r = findNode(id, n.children, [...parents, n]);
      if (r) return r;
    }
  }
  return null;
}

function Crumb({ project, parents, node }) {
  return (
    <div className="crumb">
      <a href="#">Workspace</a>
      <span className="sep">/</span>
      <a href="#">{project.name}</a>
      <span className="sep">/</span>
      {parents.map((p) => (
        <span key={p.id} style={{display: 'inline-flex', alignItems: 'center', gap: 6}}>
          <a href="#">{p.title}</a>
          <span className="sep">/</span>
        </span>
      ))}
      <span className="here">{node.title}</span>
    </div>
  );
}

function ActorOf({ kind }) {
  if (kind === "feature") return "Spécification — consultation seule";
  if (kind === "us") return "User Story — validée par le PO";
  if (kind === "task") return "Plan technique — validé par l'Architecte / Tech Lead";
  return "";
}

function prettyId(node) {
  if (node.kind === "feature") return `FEAT ${node.FeatNum}`;
  if (node.kind === "us") {
    const m = node.id.match(/^(\d+)-(\d+)-/);
    return m ? `US ${m[1]}.${m[2]}` : node.id;
  }
  if (node.kind === "task") {
    const m = node.id.match(/^(\d+)-(\d+)-/);
    const tag = node.type === "ui" ? "Maquette" : `Plan ${node.type}`;
    return m ? `${tag} ${m[1]}.${m[2]}` : tag;
  }
  return node.id;
}

function FeatureDetail({ node, viewMode, explainAvailable }) {
  const total = node.children?.length || 0;
  const validated = node.children?.filter(c => c.status === "validated").length || 0;
  const isPO = viewMode === "po";

  return (
    <div className="detail-body">
      {isPO && <IAReformulateBar path={node.source} explainAvailable={explainAvailable}/>}

      {node.objective && (
        <div className="section">
          <div className="section-h">{isPO ? "Objectif" : "Résumé fonctionnel"}</div>
          <div className="objectif"><p>{node.objective || node.summary}</p></div>
        </div>
      )}

      {!isPO && node.context && (
        <div className="section">
          <div className="section-h">Contexte</div>
          <div className="objectif"><p>{node.context}</p></div>
        </div>
      )}

      {node.actors?.length > 0 && (
        <div className="section">
          <div className="section-h">{isPO ? "Pour qui" : "Acteurs"}</div>
          <div className="objectif">
            <ul style={{margin: 0, paddingLeft: 20}}>
              {node.actors.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          </div>
        </div>
      )}

      {node.businessRules?.length > 0 && (
        <div className="section">
          <div className="section-h">{isPO ? "Règles à respecter" : "Règles métier"} · {node.businessRules.length}</div>
          <div className="tasks-list">
            {node.businessRules.map((br, i) => (
              <div key={br.id} className="task-card" style={{gridTemplateColumns: 'auto 1fr'}}>
                <span className="tc-id">#{i + 1}</span>
                <div className="tc-title" style={{fontWeight: 400}}>{br.text}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {node.children?.length > 0 && (
        <div className="section">
          <div className="section-h">{isPO ? "Histoires utilisateur" : "User stories rattachées"} · {validated}/{total} validées</div>
          <div className="tasks-list">
            {node.children.map(us => {
              const m = us.id.match(/^(\d+)-(\d+)-/);
              const tag = m ? `US ${m[1]}.${m[2]}` : us.id;
              return (
                <div key={us.id} className="task-card">
                  <span className="tc-id">{tag}</span>
                  <div>
                    <div className="tc-title">{us.title}</div>
                    {!isPO && <div className="tc-sub">{us.children?.length || 0} plan{us.children?.length > 1 ? "s" : ""} technique{us.children?.length > 1 ? "s" : ""}</div>}
                  </div>
                  <StatusBadge status={us.status}/>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!isPO && (
        <div className="section">
          <div className="section-h">Source</div>
          <div className="linked">
            <div className="link-card">
              <div className="lk-key">fichier source</div>
              <div className="lk-val">{node.source}</div>
            </div>
            <div className="link-card">
              <div className="lk-key">acteur validateur</div>
              <div className="lk-val">PO Humain (consultation)</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function USDetail({ node, viewMode, explainAvailable }) {
  const isPO = viewMode === "po";
  return (
    <div className="detail-body">
      {isPO && <IAReformulateBar path={node.file} explainAvailable={explainAvailable}/>}

      <div className="section">
        <div className="section-h">Histoire utilisateur</div>
        <div className="objectif">
          {node.asA && <p><b>{node.asA}</b></p>}
          {node.iWant && <p>{node.iWant}</p>}
          {node.soThat && <p style={{color: 'var(--ink-2)'}}>{node.soThat}</p>}
          {!node.asA && !node.iWant && node.objective && <p>{node.objective}</p>}
        </div>
      </div>

      {node.acceptanceCriteria?.length > 0 && (
        <div className="section">
          <div className="section-h">{isPO ? "Critères de validation" : "Critères d'acceptation"} · {node.acceptanceCriteria.length}</div>
          <div className="tasks-list">
            {node.acceptanceCriteria.map((ac, i) => (
              <div key={ac.id} className="task-card" style={{gridTemplateColumns: 'auto 1fr'}}>
                <span className="tc-id">#{i + 1}</span>
                <div className="tc-title" style={{fontWeight: 400}}>{ac.text}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!isPO && node.children?.length > 0 && (
        <div className="section">
          <div className="section-h">Plans techniques liés · {node.children.length}</div>
          <div className="tasks-list">
            {node.children.map(t => (
              <div key={t.id} className="task-card">
                <span className="tc-id">{(t.type || "").toUpperCase()}</span>
                <div>
                  <div className="tc-title">
                    <span className={`task-tag ${t.type}`}>{t.type}</span>
                    {t.title}
                  </div>
                  {t.summary && <div className="tc-sub">{t.summary.slice(0, 160)}{t.summary.length > 160 ? "…" : ""}</div>}
                </div>
                <StatusBadge status={t.status}/>
              </div>
            ))}
          </div>
        </div>
      )}

      {isPO && node.children?.length > 0 && (
        <div className="section">
          <div className="section-h">Statut technique</div>
          <div className="objectif" style={{color: 'var(--ink-3)'}}>
            <p>
              Cette histoire utilisateur sera implémentée par {node.children.filter(c => c.type !== "ui").length}
              {" plan"}{node.children.filter(c => c.type !== "ui").length > 1 ? "s" : ""}
              {" technique"}{node.children.filter(c => c.type !== "ui").length > 1 ? "s" : ""}.
              {node.children.some(c => c.type === "ui") && <> Une maquette HTML est disponible.</>}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function TaskDetail({ node, viewMode, explainAvailable }) {
  const isUI = node.type === "ui";
  const isPO = viewMode === "po";

  if (isPO && !isUI) {
    return (
      <div className="detail-body">
        <IAReformulateBar path={node.file} explainAvailable={explainAvailable}/>
        <div className="section">
          <div className="section-h">Plan technique pour développeurs</div>
          <div className="objectif" style={{color: 'var(--ink-2)'}}>
            <p>
              Ce document décrit comment l'équipe technique ({node.type === "back" ? "développement back-end" : "développement front-end"})
              implémentera la fonctionnalité.
            </p>
            <p style={{color: 'var(--ink-3)', fontSize: 13.5}}>
              Cette vue PO masque les détails techniques (chemins de fichiers, librairies, composants).
              Bascule en <b>Vue technique</b> pour les voir, ou demande à un développeur de te les expliquer.
            </p>
          </div>
        </div>
        <div className="section">
          <div className="section-h">Périmètre du plan</div>
          <div className="linked">
            <div className="link-card">
              <div className="lk-key">type</div>
              <div className="lk-val">{node.type === "back" ? "Back-end (serveur)" : "Front-end (interface)"}</div>
            </div>
            <div className="link-card">
              <div className="lk-key">nombre de fichiers à produire</div>
              <div className="lk-val">{node.filesPlanned?.length || 0}</div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (isUI) {
    return (
      <div className="detail-body">
        <div className="section">
          <div className="section-h">Maquette HTML</div>
          <div className="objectif">
            <p>{node.summary || "Mockup statique deposé par l'UX Designer."}</p>
            <p style={{marginTop: 16}}>
              <a href={`/file/${node.file}`} target="_blank" rel="noreferrer" style={{color: 'var(--accent)'}}>
                Ouvrir la maquette dans un nouvel onglet ↗
              </a>
            </p>
          </div>
        </div>
        <div className="section">
          <div className="section-h">Source</div>
          <div className="linked">
            <div className="link-card">
              <div className="lk-key">fichier</div>
              <div className="lk-val">{node.file}</div>
            </div>
            <div className="link-card">
              <div className="lk-key">propriétaire</div>
              <div className="lk-val">UX Designer Humain</div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="detail-body">
      {node.summary && (
        <div className="section">
          <div className="section-h">Vue d'ensemble du plan</div>
          <div className="objectif"><p>{node.summary}</p></div>
        </div>
      )}

      {node.stack && Object.values(node.stack).some(Boolean) && (
        <div className="section">
          <div className="section-h">Stack technique cible</div>
          <div className="linked">
            {Object.entries(node.stack).filter(([_, v]) => v).map(([k, v]) => (
              <div key={k} className="link-card">
                <div className="lk-key">{k}</div>
                <div className="lk-val">{v}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {node.filesPlanned?.length > 0 && (
        <div className="section">
          <div className="section-h">Fichiers à produire · {node.filesPlanned.length}</div>
          <div className="tasks-list">
            {node.filesPlanned.map((f, i) => (
              <div key={i} className="scenario">
                <div className="scenario-head">
                  <span className="num">{f.operation || "create"}</span>
                  <span style={{fontFamily: 'var(--font-mono)', fontSize: 12}}>{f.path}</span>
                </div>
                <div className="gwt">
                  {f.layer && (
                    <div className="gwt-row">
                      <div className="gwt-key">couche</div>
                      <div className="gwt-val">{f.layer}</div>
                    </div>
                  )}
                  {f.coversAcs?.length > 0 && (
                    <div className="gwt-row">
                      <div className="gwt-key">couvre</div>
                      <div className="gwt-val">{f.coversAcs.join(", ")}</div>
                    </div>
                  )}
                  {f.dsComponents?.length > 0 && (
                    <div className="gwt-row">
                      <div className="gwt-key">composants UI</div>
                      <div className="gwt-val" style={{fontFamily: 'var(--font-mono)', fontSize: 12}}>
                        {f.dsComponents.join(", ")}
                      </div>
                    </div>
                  )}
                  {f.notes && (
                    <div className="gwt-row">
                      <div className="gwt-key">notes</div>
                      <div className="gwt-val" style={{whiteSpace: 'pre-wrap', fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.6}}>
                        {f.notes}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {node.htmlSource && (
        <div className="section">
          <div className="section-h">Source visuelle</div>
          <div className="link-card">
            <div className="lk-key">mockup HTML</div>
            <div className="lk-val">{node.htmlSource}</div>
          </div>
        </div>
      )}
    </div>
  );
}

function Detail({ tree, project, selected, onValidate, explainAvailable, viewMode, setViewMode }) {
  const r = findNode(selected, tree) || (tree.length > 0 ? { node: tree[0], parents: [] } : null);
  if (!r) {
    return (
      <main className="detail">
        <div className="detail-body">
          <div className="section">
            <div className="section-h">Workspace vide</div>
            <div className="objectif">
              <p>Aucune spécification trouvée dans <code>workspace/input/feats/</code>.</p>
              <p>Crée une FEAT via <code>/feat-generate</code> puis recharge cette page.</p>
            </div>
          </div>
        </div>
      </main>
    );
  }
  const { node, parents } = r;
  const nodePath = getNodePath(node);

  // Vue UX : carrousel des maquettes HTML pour la FEAT courante
  // Si on est sur une US ou une task en vue UX, on remonte à la FEAT parente pour
  // afficher TOUS ses mockups (carrousel niveau FEAT).
  let body;
  if (viewMode === "ux") {
    const FeatNode = node.kind === "feature" ? node : (parents.find(p => p.kind === "feature") || node);
    body = <UXCarousel FeatNode={FeatNode}/>;
  } else if (node.kind === "feature") {
    body = <FeatureDetail node={node} viewMode={viewMode} explainAvailable={explainAvailable}/>;
  } else if (node.kind === "us") {
    body = <USDetail node={node} viewMode={viewMode} explainAvailable={explainAvailable}/>;
  } else {
    body = <TaskDetail node={node} viewMode={viewMode} explainAvailable={explainAvailable}/>;
  }

  return (
    <main className="detail">
      <Crumb project={project} parents={parents} node={node}/>
      <div className="detail-head">
        <div className="dh-row1" style={{justifyContent: 'space-between'}}>
          <div style={{display: 'flex', alignItems: 'center', gap: 10}}>
            <span className="dh-id">{prettyId(node)}</span>
            <span>·</span>
            <span>{ActorOf({ kind: node.kind })}</span>
          </div>
          <ViewToggle viewMode={viewMode} setViewMode={setViewMode} explainAvailable={explainAvailable}/>
        </div>
        <h1 className="dh-title">{node.title}</h1>
        <div className="dh-meta">
          <StatusBadge status={node.status}/>
          {node.kind === "us" && <span><b>Validateur</b> : Product Owner</span>}
          {node.kind === "task" && node.type !== "ui" && <span><b>Validateur</b> : Tech Lead / Architecte</span>}
          {node.kind === "task" && node.type === "ui" && <span><b>Source</b> : UX Designer (consultation)</span>}
        </div>
      </div>
      {body}
      {node.kind !== "feature" && node.type !== "ui" && (
        <ActionBar node={node} parents={parents} onValidate={onValidate}/>
      )}
    </main>
  );
}

// ───────── FEATURES HEADER (Features page : source + refresh) ─────────
function FeaturesHeader({ tree, onRefresh }) {
  const [refreshedAt, setRefreshedAt] = useState(new Date());
  const [busy, setBusy] = useState(false);
  const featsCount = tree?.length || 0;
  const usCount    = (tree || []).reduce((s, f) => s + (f.children || []).length, 0);
  const handle = async () => {
    setBusy(true);
    try { await onRefresh(); } finally {
      setBusy(false);
      setRefreshedAt(new Date());
    }
  };
  return (
    <div className="features-header">
      <div className="fh-info">
        Source : <code>workspace/input/feats/</code> · <code>workspace/output/us/</code> · <code>workspace/input/ui/</code>
        <span style={{marginLeft: 10, color: "var(--ink-3)"}}>· {featsCount} FEAT(s) · {usCount} US · synchro {formatRelative(refreshedAt.toISOString())}</span>
      </div>
      <button className="btn" onClick={handle} disabled={busy}>{busy ? "…" : "Rafraîchir"}</button>
    </div>
  );
}

// ───────── UX CAROUSEL (HTML mockups par FEAT) ─────────
function UXCarousel({ FeatNode }) {
  const [idx, setIdx] = useState(0);
  // Récupère toutes les maquettes UI (tasks de type ui) des US enfants de la FEAT
  const slides = useMemo(() => {
    const out = [];
    for (const us of (FeatNode?.children || [])) {
      for (const t of (us?.children || [])) {
        if (t.type === "ui" && t.file) {
          out.push({ key: t.id, title: us.title, label: t.title, file: t.file, usId: us.id });
        }
      }
    }
    return out;
  }, [FeatNode]);

  // reset index when slides change (refresh after new HTML files dropped)
  useEffect(() => { if (idx >= slides.length) setIdx(0); }, [slides.length, idx]);

  if (!FeatNode) return <div style={{padding: 24, color: "var(--ink-3)"}}>Sélectionnez une FEAT.</div>;
  if (slides.length === 0) {
    return (
      <div style={{padding: 24, color: "var(--ink-3)"}}>
        Aucune maquette HTML pour <strong>{FeatNode.title}</strong>.
        <div style={{marginTop: 8, fontSize: 12}}>
          Déposer les fichiers dans <code>workspace/input/ui/{`{n}-{m}-{Name}.html`}</code> puis cliquer <em>Rafraîchir</em>.
        </div>
      </div>
    );
  }
  const current = slides[idx];
  const prev = () => setIdx((idx - 1 + slides.length) % slides.length);
  const next = () => setIdx((idx + 1) % slides.length);

  // Le serveur expose workspace/input/ui/ sous /ui/* (cf. server.js fastifyStatic).
  // On charge le mockup via src= pour que les références relatives
  // (design-system.css, autres liens .html, images) résolvent correctement.
  // Pas de fetch JSON, pas de duplication HTML.
  const fileName = current.file.replace(/^workspace\/input\/ui\//, "");
  const src = "/ui/" + fileName;

  return (
    <div className="ux-carousel">
      <div className="ux-toolbar">
        <button className="btn ghost" onClick={prev} disabled={slides.length < 2} title="Précédente">‹</button>
        <div className="ux-thumbs">
          {slides.map((s, i) => (
            <button key={s.key} className={"ux-thumb " + (i === idx ? "active" : "")} onClick={() => setIdx(i)} title={s.title}>
              <span className="ux-thumb-idx">{i + 1}</span>
              <span className="ux-thumb-label">{s.title}</span>
            </button>
          ))}
        </div>
        <button className="btn ghost" onClick={next} disabled={slides.length < 2} title="Suivante">›</button>
        <span style={{fontSize: 12, color: "var(--ink-3)", marginLeft: 8}}>
          {idx + 1}/{slides.length} · <code style={{fontSize: 11}}>{current.file}</code>
        </span>
      </div>
      <div className="ux-stage">
        {/*
          Security : mockups in workspace/input/ui/ are user-supplied HTML
          served on the same origin as the console. `allow-same-origin` +
          `allow-scripts` would let a hostile mockup read window.parent
          and call internal APIs (e.g. /api/gate-decide). We drop
          `allow-same-origin` so the iframe runs in an opaque-origin
          context : scripts execute (hover, etc.) but cannot touch the
          console's storage or fetch its endpoints. Relative CSS loads
          (design-system.css) work without it.
        */}
        <iframe
          key={current.key}
          src={src}
          title={current.title}
          className="ux-frame"
          sandbox="allow-scripts allow-popups allow-forms"/>
      </div>
    </div>
  );
}

function ViewToggle({ viewMode, setViewMode }) {
  return (
    <div className="tree-tabs" style={{minWidth: 320, fontSize: 12}}>
      <button
        className={`tree-tab ${viewMode === "po" ? "active" : ""}`}
        onClick={() => setViewMode("po")}
        title="FEAT → US (vue Product Owner)">
        Vue PO
      </button>
      <button
        className={`tree-tab ${viewMode === "technical" ? "active" : ""}`}
        onClick={() => setViewMode("technical")}
        title="FEAT → Task (plans techniques back / front)">
        Vue technique
      </button>
      <button
        className={`tree-tab ${viewMode === "ux" ? "active" : ""}`}
        onClick={() => setViewMode("ux")}
        title="Maquettes HTML par FEAT (carrousel)">
        Vue UX
      </button>
    </div>
  );
}

function IAReformulateBar({ path, explainAvailable }) {
  const [open, setOpen] = useState(false);
  if (!explainAvailable?.ok) return null;   // pas de cle API → on n affiche meme pas
  if (!path) return null;
  if (open) return <ExplainView path={path}/>;
  return (
    <div className="link-card" style={{display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', marginBottom: 16, background: 'var(--accent-soft)', borderColor: 'var(--accent)'}}>
      <span style={{fontSize: 13, color: 'var(--ink-2)'}}>
        💡 Tu peux <b>améliorer cette vue avec l'IA</b> pour une reformulation encore plus simple ({explainAvailable.model}).
      </span>
      <span style={{flex: 1}}/>
      <button className="btn primary" onClick={() => setOpen(true)} style={{padding: '4px 12px', fontSize: 12}}>
        <Icon.refresh/> Reformuler avec IA
      </button>
    </div>
  );
}

function ExplainView({ path }) {
  const [state, setState] = useState({ status: "loading", content: null, meta: null, error: null });

  const load = useCallback(async (force = false) => {
    setState({ status: "loading", content: null, meta: null, error: null });
    try {
      const url = `/api/explain?path=${encodeURIComponent(path)}${force ? "&force=1" : ""}`;
      const res = await fetch(url);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || `HTTP ${res.status}`);
      setState({ status: "ok", content: json.content, meta: json, error: null });
    } catch (err) {
      setState({ status: "error", content: null, meta: null, error: err.message });
    }
  }, [path]);

  useEffect(() => { load(false); }, [load]);

  if (state.status === "loading") {
    return (
      <div className="detail-body">
        <div className="section">
          <div className="section-h">Reformulation IA en cours…</div>
          <div className="objectif" style={{color: 'var(--ink-3)'}}>
            <p>Génération d'une vue PO-friendly via Claude. Première lecture : ~3-8 s. Les suivantes seront servies depuis le cache.</p>
          </div>
        </div>
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="detail-body">
        <div className="section">
          <div className="section-h">Reformulation indisponible</div>
          <div className="objectif" style={{color: 'var(--danger)'}}>
            <p>{state.error}</p>
          </div>
          <button className="btn ghost" onClick={() => load(false)} style={{marginTop: 12}}>
            <Icon.refresh/> Réessayer
          </button>
        </div>
      </div>
    );
  }

  // marked.parse() est synchrone et safe sur du markdown emis par Claude (pas de raw HTML demande)
  const html = window.marked ? window.marked.parse(state.content || "", { breaks: false, gfm: true }) : state.content;

  return (
    <div className="detail-body">
      <div className="section">
        <div className="section-h">Vue PO · reformulation IA</div>
        <div className="objectif" dangerouslySetInnerHTML={{ __html: html }}/>
      </div>
      <div className="section" style={{marginTop: 0}}>
        <div className="link-card" style={{display: 'flex', alignItems: 'center', gap: 16, padding: '10px 14px'}}>
          <span style={{fontSize: 11, color: 'var(--ink-3)'}}>
            Reformulé par <b style={{color: 'var(--ink)'}}>{state.meta?.model}</b>
            {" · "}
            {state.meta?.cached ? "depuis cache" : "généré à l'instant"}
            {state.meta?.cacheKey && <span style={{fontFamily: 'var(--font-mono)', marginLeft: 6}}>#{state.meta.cacheKey.slice(0, 8)}</span>}
          </span>
          <span style={{flex: 1}}/>
          <button className="btn ghost" onClick={() => load(true)} style={{padding: '4px 10px', fontSize: 12}}>
            <Icon.refresh/> Régénérer
          </button>
        </div>
      </div>
    </div>
  );
}

function ActionBar({ node, parents, onValidate }) {
  const isUS = node.kind === "us";
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [comment, setComment] = useState("");
  const [error, setError] = useState(null);

  // Derive FeatId / usId / family from parents chain
  const ctx = useMemo(() => {
    if (isUS) {
      const FEAT = parents[0];
      return { kind: "us", FeatId: FEAT?.id, usId: node.id };
    }
    const FEAT = parents[0];
    const us = parents[1];
    return { kind: "task", FeatId: FEAT?.id, usId: us?.id, family: node.type };
  }, [node, parents, isUS]);

  const meta = node.status === "validated" || node.status === "rejected"
    ? findValidationMeta(node, ctx)
    : null;

  const submit = useCallback(async (decision, commentText) => {
    setBusy(true); setError(null);
    try {
      const res = await fetch("/api/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...ctx, decision, comment: commentText }),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.error || `HTTP ${res.status}`);
      }
      onValidate?.();   // trigger parent refresh
      setRejecting(false); setComment("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }, [ctx, onValidate]);

  if (rejecting) {
    return (
      <div className="actions-bar" style={{flexWrap: 'wrap', gap: 12}}>
        <textarea
          autoFocus
          rows={2}
          placeholder="Commentaire de révision (visible côté pipeline et console)…"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          style={{
            flex: '1 1 100%',
            minHeight: 56,
            padding: '8px 12px',
            border: '1px solid var(--line)',
            borderRadius: 6,
            font: 'inherit',
            color: 'var(--ink)',
            background: 'var(--panel-2)',
            resize: 'vertical',
          }}
        />
        {error && <span style={{color: 'var(--danger)', fontSize: 12}}>{error}</span>}
        <div className="actions-spacer"/>
        <button className="btn ghost" onClick={() => { setRejecting(false); setComment(""); setError(null); }} disabled={busy}>
          Annuler
        </button>
        <button className="btn" onClick={() => submit("rejected", comment.trim() || undefined)} disabled={busy}>
          <Icon.x/> Confirmer le refus
        </button>
      </div>
    );
  }

  return (
    <div className="actions-bar">
      <div className="actions-info">
        {node.status === "validated" && (
          <span>
            <span className="badge ok"><span className="d"/> Validé</span>
            {meta?.validatedBy && <span> par <b style={{color:'var(--ink)'}}>{meta.validatedBy}</b></span>}
            {meta?.validatedAt && <span> · {formatRelative(meta.validatedAt)}</span>}
          </span>
        )}
        {node.status === "rejected" && (
          <span>
            <span className="badge danger"><span className="d"/> Refusé</span>
            {meta?.validatedBy && <span> par <b style={{color:'var(--ink)'}}>{meta.validatedBy}</b></span>}
            {meta?.comment && <span title={meta.comment}> · « {meta.comment.slice(0, 80)}{meta.comment.length > 80 ? "…" : ""} »</span>}
          </span>
        )}
        {(node.status === "pending-validation" || node.status === "in-progress" || node.status === "not-started") && (
          <span>Cette {isUS ? "user story" : "tâche technique"} attend votre validation manuelle.</span>
        )}
        {error && <span style={{color: 'var(--danger)', fontSize: 12, marginLeft: 8}}>{error}</span>}
      </div>
      <div className="actions-spacer"/>
      {(node.status === "validated" || node.status === "rejected") ? (
        <button className="btn ghost" onClick={() => submit("pending-validation")} disabled={busy}>
          <Icon.refresh/> Annuler la décision
        </button>
      ) : (
        <>
          <button className="btn" onClick={() => setRejecting(true)} disabled={busy}>
            <Icon.x/> Refuser
          </button>
          <button className="btn success" onClick={() => submit("validated")} disabled={busy}>
            <Icon.check/> Valider et continuer
          </button>
        </>
      )}
    </div>
  );
}

function findValidationMeta(node, ctx) {
  const status = window.SDD_DATA?.status;
  if (!status?.FEATs?.[ctx.FeatId]?.us?.[ctx.usId]) return null;
  if (ctx.kind === "us") {
    const u = status.FEATs[ctx.FeatId].us[ctx.usId];
    return { validatedBy: u.validatedBy, validatedAt: u.validatedAt, comment: u.comment };
  }
  const p = status.FEATs[ctx.FeatId].us[ctx.usId].plans?.[ctx.family];
  return p ? { validatedBy: p.validatedBy, validatedAt: p.validatedAt, comment: p.comment } : null;
}

function formatRelative(iso) {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "à l'instant";
  if (ms < 3_600_000) return `il y a ${Math.floor(ms / 60_000)} min`;
  if (ms < 86_400_000) return `il y a ${Math.floor(ms / 3_600_000)} h`;
  return `le ${new Date(iso).toLocaleDateString("fr-FR")}`;
}

// ───────── DASHBOARD (v6.10 — données depuis workspace/output/db/console.db) ─────────

function pctBar(value, max, grad = "info") {
  const w = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="bar-track" title={`${value} / ${max}`}>
      <div className={`bar-fill grad-${grad}`} style={{width: `${w}%`}}/>
    </div>
  );
}

function VerdictBadge({ verdict, fallback = "—" }) {
  if (!verdict) return <span className="verdict-pill muted">{fallback}</span>;
  const v = String(verdict).toLowerCase();
  const cls = v.includes("green") || v === "pass" || v === "success" ? "ok"
            : v.includes("red") || v === "fail" || v === "failed" ? "danger"
            : v.includes("warn") || v.includes("yellow") || v === "partial" ? "warn"
            : "info";
  const label = String(verdict).replace(/[🟢🟡🔴]/g, "").trim() || verdict;
  return <span className={`verdict-pill ${cls}`}>{label}</span>;
}

const SEV_COLORS = {
  critical: "var(--chart-4)",
  serious:  "var(--chart-3)",
  moderate: "var(--chart-7)",
  minor:    "var(--ink-4)",
};

function severityBar(sev) {
  const total = (sev.critical||0)+(sev.serious||0)+(sev.moderate||0)+(sev.minor||0);
  if (total === 0) return <span className="empty-cell">—</span>;
  const segs = ["critical","serious","moderate","minor"]
    .map(k => ({ key: k, n: sev[k] || 0 }))
    .filter(s => s.n > 0);
  return (
    <div style={{display:"flex", alignItems:"center", gap:8}}>
      <div className="bar-stack" style={{flex: 1}}>
        {segs.map(s => (
          <span key={s.key} style={{flex: s.n, background: SEV_COLORS[s.key]}} title={`${s.key}: ${s.n}`}/>
        ))}
      </div>
      <span style={{fontSize: 12, color: "var(--ink-3)", minWidth: 28, textAlign: "right", fontWeight: 600}}>
        {total}
      </span>
    </div>
  );
}

// SVG donut chart : segments colorés + total au centre
function DonutChart({ segments, size = 140 }) {
  const total = segments.reduce((s, x) => s + x.value, 0);
  const radius = size / 2 - 14;
  const cx = size / 2, cy = size / 2;
  const stroke = 18;
  const circumference = 2 * Math.PI * radius;
  let acc = 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img">
      <circle cx={cx} cy={cy} r={radius} fill="none" stroke="var(--chart-grid)" strokeWidth={stroke}/>
      {total > 0 && segments.map((s, i) => {
        const len = (s.value / total) * circumference;
        const offset = circumference - acc;
        acc += len;
        return (
          <circle key={i}
            cx={cx} cy={cy} r={radius}
            fill="none" stroke={s.color} strokeWidth={stroke}
            strokeDasharray={`${len} ${circumference - len}`}
            strokeDashoffset={offset}
            transform={`rotate(-90 ${cx} ${cy})`}
            style={{transition: "stroke-dasharray .4s ease"}}/>
        );
      })}
      <text x={cx} y={cy + 4} textAnchor="middle" className="donut-center">{total}</text>
      <text x={cx} y={cy + 22} textAnchor="middle" className="donut-center-sub">total</text>
    </svg>
  );
}

// Sparkline SVG basique (mini-tendance pour KPI cards)
function Sparkline({ values, color = "var(--chart-1)", width = 70, height = 22 }) {
  if (!values || values.length < 2) return null;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const step = width / (values.length - 1);
  const points = values.map((v, i) => `${i * step},${height - ((v - min) / range) * height}`).join(" ");
  return (
    <svg className="kpi-sparkline" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <polyline fill="none" stroke={color} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" points={points}/>
    </svg>
  );
}

// ───────── LOADING SPINNER (SVG animé, sans dépendance) ─────────
function LoadingSpinner({ label = "Chargement…" }) {
  return (
    <div className="loading-wrap">
      <div className="loading-card">
        <svg className="spinner" viewBox="0 0 64 64" width="64" height="64" aria-hidden="true">
          <defs>
            <linearGradient id="spin-grad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="var(--chart-1)" stopOpacity="0"/>
              <stop offset="50%" stopColor="var(--chart-1)" stopOpacity="0.6"/>
              <stop offset="100%" stopColor="var(--chart-2)"/>
            </linearGradient>
          </defs>
          <circle cx="32" cy="32" r="26" fill="none" stroke="var(--line)" strokeWidth="4"/>
          <circle cx="32" cy="32" r="26" fill="none" stroke="url(#spin-grad)" strokeWidth="4"
                  strokeLinecap="round" strokeDasharray="120 200" strokeDashoffset="0"/>
        </svg>
        <div className="loading-dots" aria-hidden="true">
          <span/><span/><span/>
        </div>
        <div className="loading-label">{label}</div>
      </div>
    </div>
  );
}

function DashboardPage({ projectName }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/dashboard");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = await res.json();
      setData(payload);
      setError(null);
    } catch (e) {
      setError(e.message || "fetch failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading && !data) return <LoadingSpinner label="Chargement du dashboard…"/>;
  if (error && !data)   return <div className="dash" style={{color:"var(--danger)"}}>Erreur : {error}</div>;
  if (!data?.available) {
    return (
      <div className="dash">
        <h2>Dashboard indisponible</h2>
        <p style={{color:"var(--ink-3)"}}>{data?.error || "workspace/output/db/console.db introuvable."}</p>
        <p><code>python -m sdd_scripts.init_console_db</code></p>
      </div>
    );
  }

  const feats = data.feats || [];
  const title = projectName && projectName !== "(projet)" ? projectName : "Dashboard SDD_Pro";

  // Agrégats globaux
  const apiTotalTests   = feats.reduce((s,f) => s + (f.stats?.api_gate?.tests_total  || 0), 0);
  const apiTotalFailed  = feats.reduce((s,f) => s + (f.stats?.api_gate?.tests_failed || 0), 0);
  const apiGreen        = feats.filter(f => f.stats?.api_gate?.gate_passed).length;
  const secCritical     = feats.reduce((s,f) => s + (f.stats?.security?.scan_critical || 0), 0);
  const secSerious      = feats.reduce((s,f) => s + (f.stats?.security?.scan_serious  || 0), 0);
  const secModerate     = feats.reduce((s,f) => s + (f.stats?.security?.scan_moderate || 0), 0);
  const secMinor        = feats.reduce((s,f) => s + (f.stats?.security?.scan_minor    || 0), 0);
  const secTotalIssues  = secCritical + secSerious + secModerate + secMinor;
  const threatsTotal    = feats.reduce((s,f) => s + (f.stats?.security?.threats_total || 0), 0);
  const qErrors         = feats.reduce((s,f) => s + (f.stats?.quality?.errors   || 0), 0);
  const qWarnings       = feats.reduce((s,f) => s + (f.stats?.quality?.warnings || 0), 0);
  const qInfo           = feats.reduce((s,f) => s + (f.stats?.quality?.info     || 0), 0);

  const coverageData = feats.filter(f => f.stats?.coverage?.present)
    .map(f => ({ label:f.name || `FEAT ${f.feat_n}`, value: f.stats.coverage.lines_pct_avg, min: f.stats.coverage.coverage_min }));
  const qualityData = feats.filter(f => f.stats?.quality?.present)
    .map(f => ({ label:f.name || `FEAT ${f.feat_n}`, errors: f.stats.quality.errors||0, warnings: f.stats.quality.warnings||0, info: f.stats.quality.info||0 }));

  // Sparklines = coverage par FEAT (séries courtes)
  const coverageSpark = coverageData.map(d => d.value);
  const apiSpark = feats.filter(f => f.stats?.api_gate?.present).map(f => f.stats.api_gate.tests_passed);
  const secSpark = feats.filter(f => f.stats?.security?.present).map(f => (f.stats.security.scan_critical||0)+(f.stats.security.scan_serious||0));

  return (
    <div className="dash">
      <div className="dash-header">
        <div>
          <h1 className="dash-title">{title}</h1>
          <div className="dash-subtitle">
            {feats.length} FEAT(s) · données généré{feats.length>1?"es":""} {formatRelative(data.generated_at)}
            {" · "}<code style={{fontSize:11, color:"var(--ink-4)"}}>{data.db_path}</code>
          </div>
        </div>
        <button className="btn" onClick={fetchData} disabled={loading}>{loading ? "…" : "Rafraîchir"}</button>
      </div>

      {/* KPI cards modernes */}
      <div className="kpi-grid">
        <KpiCard title="FEATs" value={feats.length} sub={`${apiGreen} API Gate verts`}/>
        <KpiCard
          title="Tests API"
          value={apiTotalTests}
          sub={apiTotalFailed === 0 ? "tous verts" : `${apiTotalFailed} échec(s)`}
          mood={apiTotalFailed === 0 ? "ok" : "danger"}
          spark={<Sparkline values={apiSpark} color="var(--chart-5)"/>}/>
        <KpiCard
          title="Issues sécurité"
          value={secTotalIssues}
          sub={`${threatsTotal} threats modèle`}
          mood={secCritical > 0 ? "danger" : secTotalIssues > 0 ? "warn" : "ok"}
          spark={<Sparkline values={secSpark.length ? secSpark : [0,0]} color="var(--chart-4)"/>}/>
        <KpiCard
          title="Quality issues"
          value={qErrors + qWarnings}
          sub={`${qInfo} info`}
          mood={qErrors > 0 ? "danger" : qWarnings > 0 ? "warn" : "ok"}
          spark={<Sparkline values={coverageSpark.length ? coverageSpark : [0,0]} color="var(--chart-3)"/>}/>
      </div>

      {/* Grille principale */}
      <section style={{marginBottom: 24}}>
        <h2 className="chart-title" style={{marginBottom: 10}}>Statuts par FEAT</h2>
        <div className="feat-table-wrap">
          <table className="feat-table">
            <thead>
              <tr>
                <th>FEAT</th>
                <th>Run</th>
                <th>API Gate</th>
                <th>Coverage</th>
                <th>Quality</th>
                <th>Sécurité</th>
              </tr>
            </thead>
            <tbody>
              {feats.map(f => {
                const s = f.stats || {};
                const apiG = s.api_gate || {};
                const cov = s.coverage || {};
                const q = s.quality || {};
                const sec = s.security || {};
                const a = s.a11y || {};
                const p = s.perf || {};
                const sp = s.spec || {};
                const run = s.run || {};
                return (
                  <tr key={f.feat_n}>
                    <td>
                      <div className="feat-cell-title">{f.name || f.name || `FEAT ${f.feat_n}`}</div>
                      <div className="feat-cell-sub">#{f.feat_n}</div>
                    </td>
                    <td>{run.present ? <VerdictBadge verdict={run.status}/> : <span className="empty-cell">—</span>}</td>
                    <td>
                      {apiG.present ? (
                        <div>
                          <VerdictBadge verdict={apiG.gate_passed ? "green" : "red"}/>
                          <div className="feat-cell-sub">{apiG.tests_passed}/{apiG.tests_total} · {apiG.endpoints_total} endpoints</div>
                        </div>
                      ) : <span className="empty-cell">—</span>}
                    </td>
                    <td>
                      {cov.present ? (
                        <div style={{minWidth: 130}}>
                          {pctBar(cov.lines_pct_avg||0, 100, cov.coverage_passed ? "ok" : "danger")}
                          <div className="feat-cell-sub" style={{marginTop:4}}>
                            <strong style={{color: cov.coverage_passed ? "var(--ok)" : "var(--danger)"}}>{cov.lines_pct_avg}%</strong> / seuil {cov.coverage_min}%
                          </div>
                        </div>
                      ) : <span className="empty-cell">—</span>}
                    </td>
                    <td>
                      {q.present ? (
                        <div style={{fontSize:12}}>
                          <span style={{color:"var(--danger)", fontWeight:600}}>{q.errors} err</span>
                          {"  ·  "}
                          <span style={{color:"var(--chart-3)"}}>{q.warnings} warn</span>
                          {"  ·  "}
                          <span style={{color:"var(--ink-3)"}}>{q.info} info</span>
                        </div>
                      ) : <span className="empty-cell">—</span>}
                    </td>
                    <td>
                      {sec.present ? (
                        <div style={{minWidth: 160}}>
                          {severityBar({critical:sec.scan_critical, serious:sec.scan_serious, moderate:sec.scan_moderate, minor:sec.scan_minor})}
                          <div className="feat-cell-sub" style={{marginTop:4}}>
                            {sec.threats_total} threats · <VerdictBadge verdict={sec.scan_verdict || "—"}/>
                          </div>
                        </div>
                      ) : <span className="empty-cell">—</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Audit qualité — style SonarQube : 1 ligne par FEAT, uniquement les métriques avec données */}
      <SonarMetricsSection feats={feats}/>

      {/* Graphes modernes */}
      <div className="chart-grid">
        <ChartCoverage data={coverageData}/>
        <ChartQualityStack data={qualityData}/>
        <ChartApiGate feats={feats}/>
        <ChartSecurityDonut critical={secCritical} serious={secSerious} moderate={secModerate} minor={secMinor}/>
      </div>
    </div>
  );
}

// ───────── SONAR METRICS (audit qualité par FEAT) ─────────
// N'inclut une métrique que si la table DB correspondante a des données pour la FEAT
// (consigne utilisateur : "si y a pas les info ne ajoute rien" = pas de placeholder vide).

function ratingVuln(n)     { return n === 0 ? "A" : n <= 1 ? "B" : n <= 5 ? "C" : n <= 10 ? "D" : "E"; }
function ratingSmells(n)   { return n < 5  ? "A" : n < 20 ? "B" : n < 50 ? "C" : n < 100 ? "D" : "E"; }
function ratingCoverage(p) { return p >= 80 ? "A" : p >= 70 ? "B" : p >= 50 ? "C" : p >= 30 ? "D" : "E"; }

function SonarIcon({ kind }) {
  switch (kind) {
    case "vuln":
      return <svg viewBox="0 0 24 24" width="18" height="18"><path d="M12 2l8 4v6c0 5-4 8.5-8 10-4-1.5-8-5-8-10V6l8-4z" fill="none" stroke="currentColor" strokeWidth="1.6"/></svg>;
    case "smell":
      return <svg viewBox="0 0 24 24" width="18" height="18"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.6"/><path d="M9 14c1 1 5 1 6 0M9 9h.01M15 9h.01" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round"/></svg>;
    case "cov":
      return <svg viewBox="0 0 24 24" width="18" height="18"><path d="M3 13l4-4 4 4 8-8" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/><path d="M14 5h5v5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>;
    default: return null;
  }
}

function SonarMetric({ kind, label, value, rating, sub }) {
  return (
    <div className="sonar-metric">
      <span className="sonar-metric-icon"><SonarIcon kind={kind}/></span>
      <div className="sonar-metric-text">
        <div className="sonar-metric-label">{label}</div>
        <div className="sonar-metric-value">
          {value}{sub && <span className="sonar-metric-sub"> · {sub}</span>}
        </div>
      </div>
      <span className={`sonar-rating sonar-rating-${rating}`} title={`Rating ${rating}`}>{rating}</span>
    </div>
  );
}

function SonarRow({ feat }) {
  const s    = feat.stats || {};
  const sec  = s.security;
  const q    = s.quality;
  const cov  = s.coverage;

  const vulnCount  = sec?.present ? ((sec.scan_critical || 0) + (sec.scan_serious || 0)) : null;
  const smellCount = q?.present   ? ((q.warnings || 0) + (q.info || 0)) : null;
  const covPct     = cov?.present ? cov.lines_pct_avg : null;

  // Verdict global : "Passed" si toutes les métriques disponibles sont dans le vert
  const checks = [];
  if (vulnCount !== null)  checks.push(vulnCount === 0);
  if (covPct    !== null)  checks.push(cov.coverage_passed);
  if (smellCount !== null) checks.push((q.errors || 0) === 0);
  const passed = checks.length > 0 && checks.every(Boolean);

  const name = feat.name || `FEAT ${feat.feat_n}`;

  // Expand state + lazy fetch des détails
  const [open, setOpen] = useState(false);
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const toggle = useCallback(() => {
    const next = !open;
    setOpen(next);
    if (next && !details && !loading) {
      setLoading(true);
      fetch(`/api/feat/${feat.feat_n}/details`)
        .then(r => r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)))
        .then(j => setDetails(j))
        .catch(e => setError(e.message))
        .finally(() => setLoading(false));
    }
  }, [open, details, loading, feat.feat_n]);

  return (
    <div className={`sonar-row ${open ? "open" : ""}`}>
      <div className="sonar-row-head" onClick={toggle} role="button" aria-expanded={open}>
        <span className="sonar-row-name">★ {name}</span>
        <div style={{display: "flex", alignItems: "center", gap: 10}}>
          <span className={`verdict-pill ${passed ? "ok" : "warn"}`}>{passed ? "Passed" : "À revoir"}</span>
          <span className={`sonar-caret ${open ? "open" : ""}`} aria-hidden="true">▾</span>
        </div>
      </div>
      <div className="sonar-metrics">
        {sec?.present && (
          <SonarMetric
            kind="vuln" label="Vulnerabilities" value={vulnCount}
            sub={sec.threats_total > 0 ? `${sec.threats_total} threats` : null}
            rating={ratingVuln(vulnCount)}/>
        )}
        {q?.present && (
          <SonarMetric
            kind="smell" label="Code Smells" value={smellCount}
            sub={q.errors > 0 ? `${q.errors} errors` : null}
            rating={ratingSmells(smellCount)}/>
        )}
        {cov?.present && (
          <SonarMetric
            kind="cov" label="Coverage" value={covPct + "%"}
            sub={`seuil ${cov.coverage_min}%`}
            rating={ratingCoverage(covPct)}/>
        )}
      </div>
      {open && (
        <div className="sonar-detail">
          {loading && <div style={{color: "var(--ink-3)", padding: 14}}>Chargement du détail…</div>}
          {error && <div style={{color: "var(--danger)", padding: 14}}>Erreur : {error}</div>}
          {details && <SonarDetailBlocks details={details}/>}
        </div>
      )}
    </div>
  );
}

function SonarDetailBlocks({ details }) {
  const vulns  = details.vulnerabilities || [];
  const smells = details.smells || [];
  const gaps   = details.coverage_gaps || [];
  const empty  = vulns.length === 0 && smells.length === 0 && gaps.length === 0;
  if (empty) return <div style={{padding: 14, color: "var(--ink-3)"}}>Aucun détail disponible.</div>;
  return (
    <div className="sonar-detail-grid">
      {vulns.length > 0 && (
        <SonarDetailTable
          title={`Vulnerabilities (${vulns.length})`}
          color="var(--chart-4)"
          columns={["Sev.", "Class", "OWASP/CWE", "Fichier:Ligne", "Message"]}
          rows={vulns.map(v => [
            <SevDot key="s" sev={v.severity}/>,
            <code key="c">{v.issue_class}</code>,
            <span key="o" style={{fontSize: 11}}>{[v.owasp, v.cwe].filter(Boolean).join(" / ") || "—"}</span>,
            <code key="f" style={{fontSize: 11}}>{v.file_path}{v.line ? ":" + v.line : ""}</code>,
            <span key="m">{v.message}</span>,
          ])}/>
      )}
      {smells.length > 0 && (
        <SonarDetailTable
          title={`Code Smells (${smells.length})`}
          color="var(--chart-3)"
          columns={["Sev.", "Règle", "Fichier:Ligne", "Message"]}
          rows={smells.map(s => [
            <SevDot key="s" sev={s.severity}/>,
            <code key="r">{s.rule || s.issue_class}</code>,
            <code key="f" style={{fontSize: 11}}>{s.file_path}{s.line ? ":" + s.line : ""}</code>,
            <span key="m">{s.message}</span>,
          ])}/>
      )}
      {gaps.length > 0 && (
        <SonarDetailTable
          title={`Coverage gaps (${gaps.length})`}
          color="var(--chart-5)"
          columns={["%", "Stack", "Fichier"]}
          rows={gaps.map(g => [
            <span key="p" style={{fontWeight: 600, color: g.lines_pct < 30 ? "var(--danger)" : "var(--chart-3)"}}>{g.lines_pct}%</span>,
            <span key="s" style={{fontSize: 11, color: "var(--ink-3)"}}>{g.stack}</span>,
            <code key="f" style={{fontSize: 11}}>{g.file_path}</code>,
          ])}/>
      )}
    </div>
  );
}

function SonarDetailTable({ title, color, columns, rows }) {
  const MAX = 50;
  const display = rows.slice(0, MAX);
  return (
    <div className="sonar-detail-card">
      <div className="sonar-detail-title" style={{borderLeftColor: color}}>{title}</div>
      <table className="sonar-detail-table">
        <thead>
          <tr>{columns.map((c, i) => <th key={i}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {display.map((r, i) => (
            <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>
          ))}
        </tbody>
      </table>
      {rows.length > MAX && <div className="sonar-detail-more">… {rows.length - MAX} de plus tronqués</div>}
    </div>
  );
}

function SevDot({ sev }) {
  const colors = { critical: "var(--chart-4)", serious: "var(--chart-3)", error: "var(--chart-4)", warning: "var(--chart-3)", moderate: "var(--chart-7)", minor: "var(--ink-4)", info: "var(--ink-4)" };
  const c = colors[sev] || "var(--ink-4)";
  return <span title={sev} style={{display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: c}}/>;
}

function SonarMetricsSection({ feats }) {
  // N'affiche que les FEATs avec ≥ 1 métrique disponible (security|quality|coverage)
  const rows = (feats || []).filter(f =>
    f.stats?.security?.present || f.stats?.quality?.present || f.stats?.coverage?.present
  );
  if (rows.length === 0) return null;
  return (
    <section style={{marginTop: 28, marginBottom: 24}}>
      <h2 className="chart-title">Audit qualité (style Sonar)</h2>
      <div className="sonar-rows">
        {rows.map(f => <SonarRow key={f.feat_n} feat={f}/>)}
      </div>
    </section>
  );
}

function KpiCard({ title, value, sub, mood, spark }) {
  return (
    <div className={`kpi ${mood || ""}`}>
      <div className="kpi-label">{title}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
      {spark}
    </div>
  );
}

function ChartCoverage({ data }) {
  return (
    <div className="chart-card">
      <h3 className="chart-title">Code coverage (% lignes)</h3>
      {data.length === 0 ? (
        <div className="chart-empty">Aucune donnée — lancer /qa-generate</div>
      ) : (
        <div style={{display:"flex", flexDirection:"column", gap:12}}>
          {data.map(d => (
            <div key={d.label}>
              <div style={{display:"flex", justifyContent:"space-between", fontSize:12, marginBottom:5, color:"var(--ink-2)"}}>
                <span style={{fontWeight:500}}>{d.label}</span>
                <span style={{color: d.value >= d.min ? "var(--ok)" : "var(--danger)", fontWeight:600}}>
                  {d.value}% <span style={{color:"var(--ink-4)", fontWeight:400}}>/ {d.min}%</span>
                </span>
              </div>
              {pctBar(d.value, 100, d.value >= d.min ? "ok" : "danger")}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ChartQualityStack({ data }) {
  return (
    <div className="chart-card">
      <h3 className="chart-title">Quality issues par FEAT</h3>
      {data.length === 0 ? (
        <div className="chart-empty">Aucune donnée</div>
      ) : (
        <div style={{display:"flex", flexDirection:"column", gap:10}}>
          {data.map(d => {
            const total = d.errors + d.warnings + d.info;
            const w = (n) => total > 0 ? `${(n/total)*100}%` : "0%";
            return (
              <div key={d.label}>
                <div style={{display:"flex", justifyContent:"space-between", fontSize:12, marginBottom:5, color:"var(--ink-2)"}}>
                  <span style={{fontWeight:500}}>{d.label}</span>
                  <span style={{color:"var(--ink-3)"}}>{total}</span>
                </div>
                <div className="bar-stack">
                  {d.errors > 0    && <span style={{width: w(d.errors),    background: "var(--chart-4)"}} title={`${d.errors} errors`}/>}
                  {d.warnings > 0  && <span style={{width: w(d.warnings),  background: "var(--chart-3)"}} title={`${d.warnings} warnings`}/>}
                  {d.info > 0      && <span style={{width: w(d.info),      background: "var(--chart-2)"}} title={`${d.info} info`}/>}
                </div>
              </div>
            );
          })}
          <Legend items={[
            {c:"var(--chart-4)", l:"errors"},
            {c:"var(--chart-3)", l:"warnings"},
            {c:"var(--chart-2)", l:"info"},
          ]}/>
        </div>
      )}
    </div>
  );
}

function ChartApiGate({ feats }) {
  const data = feats.filter(f => f.stats?.api_gate?.present)
    .map(f => ({ label:f.name || `FEAT ${f.feat_n}`, passed:f.stats.api_gate.tests_passed, failed:f.stats.api_gate.tests_failed }));
  return (
    <div className="chart-card">
      <h3 className="chart-title">Tests API par FEAT</h3>
      {data.length === 0 ? (
        <div className="chart-empty">Aucune donnée</div>
      ) : (
        <div style={{display:"flex", flexDirection:"column", gap:10}}>
          {data.map(d => {
            const total = d.passed + d.failed;
            const w = (n) => total > 0 ? `${(n/total)*100}%` : "0%";
            return (
              <div key={d.label}>
                <div style={{display:"flex", justifyContent:"space-between", fontSize:12, marginBottom:5, color:"var(--ink-2)"}}>
                  <span style={{fontWeight:500}}>{d.label}</span>
                  <span style={{color: d.failed === 0 ? "var(--ok)" : "var(--danger)", fontWeight:600}}>{d.passed}/{total}</span>
                </div>
                <div className="bar-stack">
                  {d.passed > 0 && <span style={{width: w(d.passed), background: "var(--chart-5)"}} title={`${d.passed} passed`}/>}
                  {d.failed > 0 && <span style={{width: w(d.failed), background: "var(--chart-4)"}} title={`${d.failed} failed`}/>}
                </div>
              </div>
            );
          })}
          <Legend items={[
            {c:"var(--chart-5)", l:"passed"},
            {c:"var(--chart-4)", l:"failed"},
          ]}/>
        </div>
      )}
    </div>
  );
}

function ChartSecurityDonut({ critical, serious, moderate, minor }) {
  const segments = [
    { label: "critical", value: critical, color: "var(--chart-4)" },
    { label: "serious",  value: serious,  color: "var(--chart-3)" },
    { label: "moderate", value: moderate, color: "var(--chart-7)" },
    { label: "minor",    value: minor,    color: "var(--ink-4)" },
  ];
  return (
    <div className="chart-card">
      <h3 className="chart-title">Sécurité (OWASP scan)</h3>
      <div className="donut">
        <DonutChart segments={segments}/>
        <div style={{flex: 1, display:"flex", flexDirection:"column", gap:6}}>
          {segments.map(s => (
            <div key={s.label} style={{display:"flex", justifyContent:"space-between", alignItems:"center", fontSize:13}}>
              <span style={{display:"flex", alignItems:"center", gap:8}}>
                <span style={{width:10, height:10, borderRadius:2, background: s.color}}/>
                <span style={{color:"var(--ink-2)"}}>{s.label}</span>
              </span>
              <strong style={{color:"var(--ink)"}}>{s.value}</strong>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Legend({ items }) {
  return (
    <div className="legend">
      {items.map(it => (
        <div key={it.l}>
          <span className="swatch" style={{background: it.c}}/>
          {it.l}
        </div>
      ))}
    </div>
  );
}

// ───────── APP ─────────
function App() {
  const [data, setData] = useState(window.SDD_DATA);
  const tree = data?.tree || [];
  const project = data?.project || { name: "(indisponible)", pipelineSteps: [], projects: [] };
  const activeGate = data?.activeGate || null;

  // Page nav + project filter (persisted in localStorage)
  const [page, setPage] = useState(() => {
    try {
      const saved = window.localStorage.getItem("sdd:page");
      // v6.10: "home" is gone — fold legacy users back onto the dashboard.
      if (!saved || saved === "home") return "dashboard";
      return saved;
    } catch { return "dashboard"; }
  });
  // Theme (light/dark) — persists in localStorage + applies data-theme on <html>
  const [theme, setTheme] = useState(() => {
    try {
      const saved = window.localStorage.getItem("sdd:theme");
      if (saved === "light" || saved === "dark") return saved;
      return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark" : "light";
    } catch { return "light"; }
  });
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try { window.localStorage.setItem("sdd:theme", theme); } catch {}
  }, [theme]);
  const toggleTheme = useCallback(() => {
    setTheme((t) => t === "dark" ? "light" : "dark");
  }, []);
  const [viewMode, setViewMode] = useState(() => {
    try { return window.localStorage.getItem("sdd:viewMode") || "technical"; } catch { return "technical"; }
  });
  useEffect(() => { try { window.localStorage.setItem("sdd:page", page); } catch {} }, [page]);
  useEffect(() => { try { window.localStorage.setItem("sdd:viewMode", viewMode); } catch {} }, [viewMode]);

  // Filter the tree by viewMode :
  //  - "po"        → FEAT → US (aucune tâche technique)
  //  - "technical" → FEAT → US → plans back/front (= PO + plans)
  //  - "ux"        → FEAT → US → mockups UI uniquement
  const filteredTree = useMemo(() => {
    const isPO  = viewMode === "po";
    const isUX  = viewMode === "ux";

    const keepTask = (t) => {
      if (isPO) return false;                              // PO : aucun plan
      if (isUX) return t.type === "ui";                    // UX : mockups uniquement
      return t.type === "back" || t.type === "front";      // technical : plans back/front
    };

    // PO et Technical → on conserve toutes les US (l'US est l'unité de lecture/validation)
    // UX → on garde uniquement les US qui ont au moins un mockup
    const keepUs = (us, keptTasks) => {
      if (isUX) return keptTasks.length > 0;
      return true;
    };

    return tree
      .map(FEAT => {
        const keptUs = (FEAT.children || [])
          .map(us => {
            const keptTasks = (us.children || []).filter(keepTask);
            return keepUs(us, keptTasks) ? { ...us, children: keptTasks } : null;
          })
          .filter(Boolean);
        return keptUs.length > 0 ? { ...FEAT, children: keptUs } : null;
      })
      .filter(Boolean);
  }, [tree, viewMode]);

  const initialId = filteredTree[0]?.children?.[0]?.id || filteredTree[0]?.id || null;
  const [selected, setSelected] = useState(initialId);
  const [liveStatus, setLiveStatus] = useState("connecting"); // connecting | live | offline

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/tree");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = await res.json();
      window.SDD_DATA = payload;
      window.MOCK_TREE = payload.tree;
      window.MOCK_PROJECT = payload.project;
      setData(payload);
    } catch (err) {
      console.warn("[SDD] refresh failed:", err);
    }
  }, []);

  // SSE hot-reload
  useEffect(() => {
    let es;
    let reconnectTimer;
    let cancelled = false;
    const open = () => {
      es = new EventSource("/api/events");
      es.onopen    = () => { if (!cancelled) setLiveStatus("live"); };
      es.onerror   = () => {
        if (!cancelled) {
          setLiveStatus("offline");
          es.close();
          reconnectTimer = setTimeout(open, 3000);
        }
      };
      es.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data);
          if (["status", "status-file", "tree", "gate"].includes(ev.type)) {
            refresh();
          }
        } catch { /* heartbeat or malformed */ }
      };
    };
    open();
    return () => { cancelled = true; clearTimeout(reconnectTimer); es?.close(); };
  }, [refresh]);

  if (window.SDD_LOAD_ERROR) {
    return (
      <div style={{padding: 40, fontFamily: 'Inter, sans-serif'}}>
        <h2 style={{color: '#c00'}}>Console indisponible</h2>
        <p>Impossible de charger /api/tree : <code>{window.SDD_LOAD_ERROR}</code></p>
        <p>Le serveur Fastify est-il démarré ? Lance <code>node server.js</code> dans <code>workspace/console/</code>.</p>
      </div>
    );
  }

  return (
    <div className="app">
      <TopBar
        page={page} setPage={setPage}
        theme={theme} toggleTheme={toggleTheme}/>
      {page === "dashboard" ? (
        <DashboardPage projectName={project?.name}/>
      ) : page === "doc-fonctionnelle" ? (
        <DocPage docId="fonctionnelle"/>
      ) : page === "doc-technique" ? (
        <DocPage docId="technique"/>
      ) : (
        <>
          <FeaturesHeader tree={filteredTree} onRefresh={refresh}/>
          <GateBanner gate={activeGate} onResolve={refresh}/>
          <div className="main">
            <Tree tree={filteredTree} selected={selected} setSelected={setSelected}/>
            <Detail
              tree={filteredTree}
              project={project}
              selected={selected}
              onValidate={refresh}
              explainAvailable={data?.explain || { ok: false, reason: "indisponible" }}
              viewMode={viewMode}
              setViewMode={setViewMode}
            />
          </div>
        </>
      )}
    </div>
  );
}

window.SDD_DATA_READY.then(() => {
  ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
});
