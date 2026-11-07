-- 0009_add-delivery-evidence-table.sql
-- Audit 2026-11-07 — gates de livraison réellement bloquantes.
--
-- Le problème
-- -----------
-- `buildVerified=false` et `qa.executed=false` produisaient un WARN, et un
-- WARN laissait tout passer. Pire : les statuts de `run_phases` sont
-- AUTO-DÉCLARÉS par l'orchestrateur LLM (`sdd_full_planner.py record`) — la
-- livraison reposait sur l'auto-certification de celui qui livre.
--
-- La correction
-- -------------
-- Une table de PREUVES, écrite uniquement par les scripts qui exécutent ou
-- lisent eux-mêmes la source vérifiée (`verify_build.py`, `verify_tests.py`,
-- `delivery_gate.py record-spec|record-readiness`). `sdd_lib.delivery_gate.
-- authorize_delivery()` lit CETTE table et jamais `run_phases`.
--
-- Trois colonnes portent le contrat :
--   tree_hash : sha256 des sources au moment de la preuve — une preuve ne
--               vaut que pour cet état exact (modifier une source = périmé) ;
--   hmac      : HMAC-SHA256 (clé locale hors dépôt, ~/.sdd/) sur le contenu
--               de la ligne — une ligne insérée à la main ne vaut rien ;
--   producer  : script producteur (traçabilité).
--
-- APPEND-ONLY : une relance ajoute une ligne, n'en réécrit aucune. Un échec
-- et un succès sur le même tree_hash coexistent et bloquent (résultat
-- instable) — une relance opportuniste ne peut pas « écraser » un échec.

CREATE TABLE IF NOT EXISTS delivery_evidence (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT    NOT NULL,
    feat_n        INTEGER NOT NULL,
    run_id        TEXT,
    check_name    TEXT    NOT NULL,      -- build | tests | coverage | spec_compliance | readiness
    passed        INTEGER NOT NULL,      -- 0 | 1 (aucun état intermédiaire)
    exit_code     INTEGER NOT NULL,
    command       TEXT    NOT NULL,
    details_json  TEXT    NOT NULL,
    tree_hash     TEXT    NOT NULL,
    producer      TEXT    NOT NULL,
    hmac          TEXT
);

CREATE INDEX IF NOT EXISTS idx_delivery_evidence_feat_check ON delivery_evidence(feat_n, check_name, id);
CREATE INDEX IF NOT EXISTS idx_delivery_evidence_run        ON delivery_evidence(run_id);
