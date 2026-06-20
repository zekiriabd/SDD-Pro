# /us-generate — Découpe une FEAT en User Stories

<!-- @llm-only-flags-file : tous les flags CLI de cette commande slash sont interprétés par Claude. -->

> ⚠️ **Commande interne v7.0.0** — invoquée par `/sdd-full` STEP 2.
> Utilisateur final : préférer `/sdd-full` ou `/dev-run` (gèrent pré-conditions, idempotence, état).

Invoque l'agent PO pour découper une FEAT fonctionnelle en User
Stories structurées (cible 1-3, warn au-delà de `UsGranularityWarnAt`
défaut 6, hard cap `UsGranularityHardCap` défaut 10) dans `workspace/output/`.

**Usage :** `/us-generate {n}` — où `{n}` est le numéro de la FEAT

---

## STEP 1 — Valider les arguments

Arguments :
- `{n}` (entier ≥ 1, **obligatoire**)
- `--allow-large-feat` (optionnel, v7.0.0 P2 #13) — bypass conscient du
  hard cap `UsGranularityHardCap` (default 10). À utiliser pour FEATs
  métier légitimement très larges (≥ 11 flux distincts). Effet : export
  `SDD_ALLOW_LARGE_FEAT=1` avant invocation agent `po`, audit-log dans
  `workspace/output/.sys/.audit/force-bypass.log`. Préférer split FEAT.

Si `{n}` absent → demander :
```
Quel est le numéro de la FEAT à découper ? (ex. : 1 pour workspace/input/feats/1-Auth.md)
```

Si non numérique → ERROR :
```
ERROR: /us-generate — argument invalide
CAUSE: "{argument}" n'est pas un entier
FIX: relancer /us-generate {n} avec n entier (ex. /us-generate 1)
```

### Propagation `--allow-large-feat`

```bash
if [[ "$@" == *--allow-large-feat* ]]; then
    export SDD_ALLOW_LARGE_FEAT=1
    mkdir -p workspace/output/.sys/.audit
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) /us-generate {n} --allow-large-feat (bypass UsGranularityHardCap)" \
      >> workspace/output/.sys/.audit/force-bypass.log
fi
```

L'agent `po` (STEP 5) lit cette env var pour passer outre le hard cap.

---

## STEP 2 — Vérifier la FEAT existe

Glob `workspace/input/feats/{n}-*.md`.
- 0 fichier → ERROR :
  ```
  ERROR: /us-generate — FEAT introuvable
  CAUSE: aucun fichier workspace/input/feats/{n}-*.md
  FIX: créer la FEAT via /feat-generate ou la déposer manuellement
  ```
- > 1 fichier → ERROR :
  ```
  ERROR: /us-generate — numérotation invalide
  CAUSE: plusieurs fichiers commencent par {n}- dans workspace/input/feats/
  FIX: renommer pour qu'un seul fichier ait le préfixe {n}-
  ```

---

## STEP 2.5 — Checkpoint skip (v6.6.4, opt-in)

Si `CheckpointMode: resume` dans Project Config (défaut `off` =
comportement v6.6.3 strict) :

```python
from sdd_lib.checkpoint import is_phase_resumable

inputs = [
    f"workspace/input/feats/{n}-*.md",      # FEAT parent
    "workspace/input/stack/stack.md",       # Project Config + stacks actifs
]
resumable, reason = is_phase_resumable(
    feat=n, phase="us-generate", input_paths=resolved_inputs,
)
if resumable:
    print(f"⊘ /us-generate {n}: skipped (checkpoint hit)")
    # STOP avec succès, ne pas re-déléguer à l'agent PO
```

Si `CheckpointMode ∈ {off, record}` → skip ce STEP, continuer.

Émissions possibles : `[CHECKPOINT_HASH_MISMATCH]`, `[CHECKPOINT_INPUT_MISSING]`,
`[CHECKPOINT_STATE_UNREADABLE]`. Cf. `error-classification.md §1.16`.

---

## STEP 3 — Invoquer l'agent PO

Lancer l'agent `po` (défini dans `.claude/agents/po.md`) avec le numéro
`{n}` en argument. L'agent gère le découpage, la traçabilité et l'écriture
des fichiers US dans `workspace/output/`.

Attendre la fin de l'agent. Relayer sa sortie telle quelle (ligne de succès
ou bloc ERROR 3 lignes).

### STEP 3.0 — Résoudre le sentinel `Parent FEAT hash` (v7.0.0-alpha, 2026-05-22 ; refactor 2026-06-05)

Si l'agent `po` a réussi (US écrites), patcher les sentinels
`sha256:COMPUTE_REQUIRED` en hash sha256 réel **avant** STEP 3.bis.

L'agent `po` n'a pas le tool `Bash` (cf. po.md frontmatter `tools:
Read, Write, Edit, Glob, Grep`) et ne peut pas calculer le hash
lui-même. Il écrit le sentinel littéral, et cette commande le résout
en post-step déterministe (0 token LLM, ~50 ms).

> **v7.0.0-alpha audit P0-workflow 2026-06-05** — historiquement
> l'inline `python -c "..."` vivait ici. Refactor : extrait vers
> `sdd_scripts/resolve_us_hash_sentinel.py` (SSoT) + posé comme
> SubagentStop hook matcher=`po` (defense-in-depth). Le hook ferme
> le gap où `po` était invoqué standalone (hors `/us-generate`) et
> laissait le sentinel non résolu → tous les downstream émettaient
> `[FEAT_HASH_MISMATCH]`. Ce STEP reste le chemin nominal ; le hook
> est un filet de sécurité (idempotent — no-op si déjà résolu).

**Invocation** (déterministe, 0 token LLM, ~50 ms, cross-platform) :

```bash
python .claude/python/sdd_scripts/resolve_us_hash_sentinel.py --feat-number {n}
```

**Garanties** (préservées vs implémentation inline) :
- Aucune dépendance externe (`sed`/`pwsh`/Git Bash) — Python stdlib seulement
- UTF-8 sans BOM (compatible parser frontmatter YAML cross-OS)
- Line endings préservés (`newline=''` → conserve LF original, pas de CRLF Windows)
- Idempotent : re-exécution sur US déjà patchées → 0 patch

| Exit | Sens | Action caller |
|---|---|---|
| `0` | succès (N US patchées OU rien à faire) | continuer STEP 3.bis |
| `2` | sentinel persiste après patch (corruption FS) | STOP + ERROR `[PO_HASH_PLACEHOLDER]` |
| `3` | erreur infra (FEAT file missing, FS perms) | STOP + ERROR `[INFRA_BLOCKED]` |

**Format ERROR (exit 2)** :
```
ERROR: /us-generate {n} — sentinel hash non résolu
CAUSE: [PO_HASH_PLACEHOLDER] sha256:COMPUTE_REQUIRED persiste dans {N} fichier(s) US après patch
FIX: vérifier permissions FS sur workspace/output/us/, relancer /us-generate {n} (idempotent)
```

### STEP 3.bis — Checkpoint record (v6.6.4, opt-in)

Si l'agent PO a réussi (US écrites) ET `CheckpointMode ∈ {record, resume}` :

```python
from sdd_lib.checkpoint import record_input_hash

record_input_hash(
    run_id=$RUN_ID,
    phase="us-generate",
    input_paths=resolved_inputs,    # FEAT + stack.md
)
```

Erreur silencieuse si state.json absent → WARN, non bloquant.

---

### STEP 3.ter — Auto-ingest FEAT/US dans console.db (depuis 2026-05-21)

Si l'agent PO a réussi (US écrites), invoquer **systématiquement** le script
déterministe `ingest_feats_us.py` pour populer correctement les tables
`feats` et `us` de `workspace/output/db/console.db` (cf. gap framework
identifié 2026-05-21 — auparavant seules les colonnes skeleton `feat_n` +
`feat-{n}` étaient remplies par les auditors via `ensure_feat_skeleton()`,
laissant `name`, `actors_json`, `ac_count`, `sfd_count`, `br_count`,
`fd_count`, `covers_json`, `status` à null/zéro et brisant l'affichage
de la console web dashboard).

```bash
python .claude/python/sdd_scripts/ingest_feats_us.py 2>&1 | tail -1
```

| Exit | Sens | Action caller |
|---|---|---|
| `0` | Ingest OK | continuer (log 1 ligne `[OK] ingested N FEATs + M US`) |
| `1` | DB introuvable / corrompue | WARN 1 ligne, continuer (non bloquant) |

**Idempotent** : utilise `ON CONFLICT(feat_n|us_id) DO UPDATE` — re-exécution
sans effet sur les counts (ré-écrit avec mêmes valeurs).

**Coût** : 0 token LLM, ~50 ms, parse markdown déterministe (regex SFD-N /
BR-N / AC-N / FD-N / `## Actors` / `Covers:`).

**Non bloquant** : un échec de l'ingest n'invalide pas le succès du PO.
Les US sur disque restent la SSoT ; le DB n'est qu'un cache projeté pour
la console web.

---

## STEP 4 — Inventaire des mockups HTML (depuis v4)

Glob `workspace/input/ui/{n}-*.html` pour détecter les mockups déjà déposés.

Glob `workspace/output/us/{n}-*.md` pour récupérer les basenames d'US.

Cross-check :
- HTML dont basename matche une US → couvert
- HTML dont basename ne matche aucune US → orphelin (WARN)
- US sans HTML → info (frontend possible sans mockup OU backend-only)

Émettre la liste compactement (1 ligne par US et 1 ligne par orphelin).

Si aucun HTML détecté ET au moins une US a une composante UI attendue,
émettre une info non bloquante invitant à déposer les mockups
(convention `{n}-{m}-{Name}.html`).

---

## STEP 5 — Confirmation finale

Si l'agent PO réussit, ajouter le récap final :
```
✅ FEAT {n}-{FeatName} — planification terminée

US générées      : {U} fichiers dans workspace/output/us/
Mockups HTML     : {H} fichiers dans workspace/input/ui/ (ou "aucun")
HTML orphelins   : {O} (à corriger ou retirer)
US sans mockup   : {U-H}

Prochaine étape :
  - (optionnel) déposer/réviser les mockups HTML (workspace/input/ui/{n}-{m}-{Name}.html)
  - /dev-run {n} pour matérialiser le code (arch + db + back + front en parallèle)
  - ou /sdd-full {n} pour pipeline complet
```

Si l'agent échoue, ne rien ajouter (l'ERROR 3 lignes de l'agent suffit).

---

## Règles de cette commande

- Pas de Q/R utilisateur après le STEP 1 (l'agent est autonome)
- Pas de modification de la FEAT parente
- Pas de génération de code (réservé à `/dev-backend`, `/dev-frontend`, `/dev-run`)
- Pas de lecture des mockups HTML ou du stack (réservé aux agents dev-*)
