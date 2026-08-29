-- 0008_add-detector-column-qa-findings.sql
-- Audit 2026-08-28, correction #6 — régression détectée et fermée le jour même.
--
-- Le problème
-- -----------
-- `scan_patterns.py` (scan déterministe) et `ingest_agent_report.py` (findings
-- des reviewers LLM) écrivent dans LES MÊMES tables `qa_code_review` et
-- `qa_security(mode='scan')`, et tous deux appelaient
-- `replace_qa_auditor_for_feat()` — un DELETE de TOUTES les lignes de la FEAT
-- avant réinsertion.
--
-- Sur `/sdd-full`, la séquence est : STEP 6.4.B (les agents code-reviewer et
-- security-reviewer produisent leurs findings) PUIS STEP 4.8 (`/sdd-review`,
-- qui déclenche désormais le scan déterministe). Le scan effaçait donc les
-- findings des agents avant que le verdict consolidé ne soit calculé.
--
-- Conséquence : le verdict devenait strictement plus faible que la réalité —
-- un FAUX VERT sur une gate BLOQUANTE par défaut (`ReviewFailOnSddFull`).
-- Exactement la classe de défaut que cet audit reproche au framework, et
-- introduite en la corrigeant. Reproduite avant correction : 1 finding LLM
-- `serious` avant le scan, 0 après.
--
-- La correction
-- -------------
-- Une colonne `detector` sépare les deux producteurs, et chacun ne remplace
-- QUE ses propres lignes :
--
--     detector='agent'          reviewers LLM (via ingest_agent_report)
--     detector='deterministic'  scan de patterns (via scan_patterns)
--
-- Le défaut `'agent'` préserve la sémantique de toutes les lignes existantes :
-- une base déjà peuplée voit ses findings attribués aux agents, ce qui est
-- exact — le scan déterministe n'existait pas avant ce lot.
--
-- Les deux jeux de findings COEXISTENT désormais et alimentent ensemble le
-- verdict. `_review_fetch.deduplicate_findings()` fusionne les doublons sur
-- (file, line, classe), donc un défaut trouvé par les deux ne compte qu'une
-- fois — c'est le comportement voulu : le déterministe garantit le plancher de
-- rappel, l'agent ajoute ce qu'une regex ne peut pas voir.

ALTER TABLE qa_code_review ADD COLUMN detector TEXT NOT NULL DEFAULT 'agent';
ALTER TABLE qa_security    ADD COLUMN detector TEXT NOT NULL DEFAULT 'agent';

CREATE INDEX IF NOT EXISTS idx_qa_code_review_detector ON qa_code_review(feat_n, detector);
CREATE INDEX IF NOT EXISTS idx_qa_security_detector    ON qa_security(feat_n, mode, detector);
