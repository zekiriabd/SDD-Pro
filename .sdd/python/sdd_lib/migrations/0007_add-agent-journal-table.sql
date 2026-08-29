-- 0007_add-agent-journal-table.sql
-- Audit 2026-08-28, correction #5 (gouvernance et traçabilité des agents).
--
-- Constat de l'audit : console.db portait 27 tables et AUCUNE colonne de
-- prompt, de contexte ou de sortie brute. Conséquence directe : impossible
-- de répondre à « pourquoi cet agent a-t-il produit cette règle métier »,
-- impossible de rejouer un run, impossible d'attribuer une régression à un
-- changement de prompt. `structured_log.py` (stderr, off par défaut, 1 seul
-- appelant) ne comblait pas le trou.
--
-- Cette table ferme la boucle demandée :
--   run_id → agent → modèle → tier → hash contexte/prompt → inputs → output
--          → tokens → coût → décision → gate → retry → résultat final.
--
-- Trois choix de conception méritent explication :
--
-- 1. APPEND-ONLY. Aucune UPDATE n'est exposée par `sdd_lib/journal.py`. Une
--    correction s'écrit comme une nouvelle entrée (`retry_of`), jamais comme
--    une réécriture. Un journal réinscriptible n'est pas une preuve.
--
-- 2. `pricing_source` EST UNE COLONNE, pas un détail. L'audit a établi que
--    toute la génération de modèles courante retombe sur FALLBACK_PRICING
--    (facteur 5 de sous-estimation sur un agent Opus). Un coût agrégé qui
--    mélange silencieusement des prix réels et des prix de repli est pire
--    qu'une absence de coût : il inspire confiance. La colonne rend le
--    mélange visible et permet d'exclure ou de marquer les lignes non fiables.
--
-- 3. LES HASHES RENDENT LE REPLAY POSSIBLE. `context_hash` + `inputs_hash`
--    identifient l'entrée d'un spawn. Deux spawns de mêmes hashes doivent
--    produire la même sortie : c'est ce qui permet (a) de servir un run
--    rejoué depuis le journal à coût nul sur les étapes inchangées, et
--    (b) de bisecter une régression de prompt. Le contenu intégral vit hors
--    base, en blobs adressés par hash sous workspace/.sys/.journal/blobs/,
--    pour ne pas transformer console.db en dépotoir de plusieurs Go.
--
-- Lecture : `sdd_scripts/journal_cli.py {show,summary,replay-plan,verify}`.

CREATE TABLE IF NOT EXISTS agent_journal (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    seq                   INTEGER,                    -- ordre monotone dans le run
    ts                    TEXT    NOT NULL,
    run_id                TEXT,                       -- FK logique runs.id
    feat_n                INTEGER,
    us_id                 TEXT,                       -- {n}-{m}
    phase                 TEXT,                       -- phase du runner (us-generate, dev-backend, ...)
    agent                 TEXT    NOT NULL,           -- nom d'agent OU nom de script déterministe
    kind                  TEXT    NOT NULL DEFAULT 'agent',  -- agent | script | gate
    model                 TEXT,
    tier                  TEXT,                       -- fast | balanced | deep | n/a
    context_hash          TEXT,                       -- sha256 du pack de contexte assemblé
    inputs_hash           TEXT,                       -- sha256 des entrées déclarées
    output_hash           TEXT,                       -- sha256 de la sortie
    input_tokens          INTEGER NOT NULL DEFAULT 0,
    output_tokens         INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens     INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd              REAL,
    pricing_source        TEXT,                       -- known | fallback | unknown
    decision              TEXT,                       -- ce que l'orchestrateur a ordonné
    gate                  TEXT,                       -- gate traversée à cette étape
    gate_verdict          TEXT,                       -- GREEN | WARN | RED | n/a
    attempt               INTEGER NOT NULL DEFAULT 1,
    retry_of              INTEGER,                    -- agent_journal.id de la tentative précédente
    outcome               TEXT,                       -- ok | fail | blocked | skipped | unknown
    error_class           TEXT,                       -- [CLASS] de error-classification.md
    blob_ref              TEXT,                       -- chemin relatif du blob principal
    duration_ms           INTEGER,
    notes                 TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_journal_run      ON agent_journal(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_agent_journal_feat     ON agent_journal(feat_n);
CREATE INDEX IF NOT EXISTS idx_agent_journal_us       ON agent_journal(us_id);
CREATE INDEX IF NOT EXISTS idx_agent_journal_agent    ON agent_journal(agent);
CREATE INDEX IF NOT EXISTS idx_agent_journal_ctx      ON agent_journal(agent, context_hash, inputs_hash);
CREATE INDEX IF NOT EXISTS idx_agent_journal_pricing  ON agent_journal(pricing_source);
CREATE INDEX IF NOT EXISTS idx_agent_journal_outcome  ON agent_journal(outcome);
