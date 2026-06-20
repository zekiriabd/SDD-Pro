// data-loader.js
// Fetch /api/tree au boot et expose le payload via window.SDD_DATA.
// app.jsx await window.SDD_DATA_READY avant de monter React.

window.SDD_DATA_READY = (async () => {
  try {
    const res = await fetch("/api/tree");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload = await res.json();
    window.SDD_DATA = payload;
    // Compat avec la maquette d origine (mock-data.js exposait ces 2 globals)
    window.MOCK_TREE = payload.tree;
    window.MOCK_PROJECT = payload.project;
  } catch (err) {
    console.error("[SDD Console] echec chargement /api/tree :", err);
    window.SDD_DATA = { tree: [], project: { name: "(indisponible)", pipelineSteps: [] }, status: null, activeGate: null };
    window.MOCK_TREE = [];
    window.MOCK_PROJECT = window.SDD_DATA.project;
    window.SDD_LOAD_ERROR = err.message;
  }
})();
