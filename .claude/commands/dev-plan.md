# /dev-plan — Génère les plans techniques d'1 FEAT sans coder

> ⚠️ **Commande interne v7.0.0** — invoquée par `/sdd-full` STEP 3.6 (conditionnel).
> Utilisateur final : préférer `/sdd-full` ou `/dev-run` (gèrent pré-conditions, idempotence, état).

Pour chaque US de la FEAT `{n}`, invoque les agents `dev-backend` et
`dev-frontend` en **mode Plan Only** : ils lisent l'US (+ mockup HTML
en lecture texte directe pour le front), planifient inline les
fichiers à produire, **écrivent le plan dans
`workspace/output/plans/{n}-{m}-{Name}.{back|front}.md`**, et s'arrêtent —
**aucun fichier de code généré, aucun build**.

L'humain peut relire et éditer ces fichiers de plan, puis lancer
`/dev-run {n}` qui détectera les plans et les consommera tels quels
au lieu de re-planifier.

**Usage :** `/dev-plan {n}` — où `{n}` est le numéro de la FEAT.

**Cas d'emploi** :
- Tu veux valider le découpage technique avant la génération
- Tu veux ajuster manuellement les fichiers à produire (retirer,
  ajouter, renommer)
- Tu veux tester un changement de stack et comparer ce que les
  agents prévoient avant d'effectivement coder

---

## STEP 1 — Valider l'argument

Argument **obligatoire** : `{n}` (entier ≥ 1).

Si absent → demander :
```
Quel est le numéro de la FEAT à planifier ? (ex. : 1)
```

Si non numérique →
```
ERROR: /dev-plan — argument invalide
CAUSE: "{argument}" n'est pas un entier
FIX: relancer /dev-plan {n} (ex. /dev-plan 1)
```

---

## STEP 2 — Lister les US à planifier

Glob `workspace/output/us/{n}-*.md` → liste `US_LIST` (basenames sans extension).

Si `US_LIST` est vide →
```
ERROR: /dev-plan — aucune US à planifier
CAUSE: aucun fichier workspace/output/us/{n}-*.md
FIX: lancer /us-generate {n} pour générer les US d'abord
```

Émettre 1 ligne :
```
FEAT {n} — {U} US à planifier (back + front en parallèle, mode Plan Only)
```

---

## STEP 3 — Vérifier les stacks actifs

Lire `workspace/input/stack/stack.md`.

- Si aucun `## Active Tech Specs` `backend-*` ET aucun `frontend-*` →
  ERROR comme dans `/dev-run`.

(Pas de validation des blocs `## Active Database` / `## Active Auth
Specs` ici — la planification ne lit pas la DB, ne se connecte à
rien.)

---

## STEP 4 — Invocation parallèle dev-backend + dev-frontend (mode Plan Only)

**CRITIQUE — exécution parallèle** : pour **chaque US** `{n}-{m}-{Name}`
de `US_LIST`, invoquer **à la fois** :
- `dev-backend {n}-{m}:plan` (suffixe `:plan` = Plan Only)
- `dev-frontend {n}-{m}:plan`

**Toutes les invocations dans un SEUL message avec plusieurs appels
d'outil Agent en parallèle** (pas de boucle séquentielle).

Pour `U` US → `2 × U` invocations parallèles.

Chaque agent en mode `:plan` :
- Charge l'US, le mockup HTML (front, texte direct), les stacks
  actifs et le CLAUDE.md projet (s'il existe)
- Construit le plan inline normal (STEPs 5/6 selon agent)
- **Écrit le plan dans `workspace/output/plans/{n}-{m}-{Name}.{back|front}.md`**
  au format défini (cf. `@.claude/rules/build-and-loop.md §7.4`)
- Émet UNE ligne :
  ```
  dev-backend {n}-{m}-{Name}: plan written → workspace/output/plans/{n}-{m}-{Name}.back.md (X fichiers)
  ```
- STOP — pas de génération de code, pas de build

Si l'US n'a pas de contrepartie pour la famille → exit silent
(`skipped (frontend-only US)` ou inverse), pas de fichier plan écrit.

---

## STEP 4.5 — Compactage des plans frontend (RETIRÉ 2026-05-22 ; script supprimé du disque)

> ⛔ **RETIRÉ** : le script `compact_front_plans.py` cassait le contrat
> plan v2 (remplaçait `## Files` YAML structuré par une liste prose,
> supprimait `## ACs Coverage Summary`, faisait échouer `validate_plan.py`
> avec `[PLAN_FILES_SECTION_MISSING]`). Désactivé en 2026-05-22, **supprimé
> du disque depuis** (audit CTO 2026-06-07 — confirmation `ls` négative).
>
> Aucune réécriture prévue : les plans v2 actuels (~30 KB max) ne
> justifient pas le risque de régression vs ~7K tokens économisés.
> Toute mention historique dans la doc framework est conservée comme
> trace d'audit (cf. `docs/hooks-and-protections.md §3.3`,
> `python/README.md §migration`) avec annotation "retiré v7.0.0-alpha".

---

## STEP 4.7 — Validation post-génération des plans (refactor v7.0.0-alpha audit P0-workflow 2026-06-05)

> **v7.0.0-alpha audit P0-workflow 2026-06-05** — historiquement appelé
> « strict-readiness ». Les variants d'agents `dev-*-strict` ont été
> retirés en v7.0.0 (cf. ADR `governance-major-auditors-trim` §3 +
> `docs/CHANGELOG.md` entrée v7.0.0), il n'y a donc
> plus de routing strict/classic. Le flag `--strict` de `validate_plan.py`
> reste accepté en CLI (no-op) pour backward-compat scripts, mais ce
> STEP ne décide plus de routing — uniquement validation structurelle
> (frontmatter v2, us-hash, AC coverage) pour détecter les plans stale
> avant matérialisation côté `/dev-run`.

Pour chaque plan généré (back et front), invoquer `validate_plan.py`
pour confirmer la conformité (frontmatter `plan-schema-version: 2`
recommandé, `us-hash` cohérent avec l'US source, section `## Inline Digest`
présente, AC coverage complète) :

```bash
python .claude/python/sdd_scripts/validate_plan.py \
  --plan-path "workspace/output/plans/{n}-{m}-{Name}.{back|front}.md" \
  --us-path "workspace/output/us/{n}-{m}-{Name}.md" \
  --json
```

| Exit | Sens | Comportement |
|---|---|---|
| `0` | Plan v2 valide avec `## Inline Digest` | log compteur `$S_v2++` |
| `1` | Plan v1 legacy (pas de `## Inline Digest`) | log compteur `$S_v1++` + WARN 1L (utilisable, mais incomplet) |
| `2` | Plan stale (us-hash mismatch) OU corrompu | ERROR + nettoyer le plan (sera regénéré au re-run) |

**Émettre un event state.jsonl** par plan validé (si `$RUN_ID` disponible) :
```bash
python .claude/python/sdd_scripts/sdd_state.py emit-event \
  --run-id $RUN_ID --event-type plan_validate_postgen \
  --payload-json '{"us":"{n}-{m}","family":"{back|front}","exit":N,"result":"v2|v1|invalid"}'
```

**Non bloquant** : un plan exit 1 reste utilisable par `dev-*` (Opus)
en mode From-Plan classique. Exit 2 nettoie le plan pour éviter qu'un
re-run ultérieur ne le consomme à tort.

Si tous les plans sont exit 0 → émettre 1 ligne récap :
```
FEAT {n} — plans v2 valides : {S_v2_back}/{P_back} back + {S_v2_front}/{P_front} front
```

Si au moins un exit 1 → émettre WARNING 1 ligne :
```
🟡 FEAT {n} — {N_v1} plan(s) v1 legacy (utilisables par dev-* Opus, sans Inline Digest)
```

---

## STEP 4.bis — Status flip US (v6.10.5, fix CRIT-2)

Pour chaque US dont un plan a été écrit avec succès (`.back.md` ou
`.front.md`), flipper `Ready → InProgress`. Idempotent et non-bloquant.

```bash
for plan_file in workspace/output/plans/{n}-*.{back,front}.md; do
  [ -f "$plan_file" ] || continue
  us_id=$(basename "$plan_file" | grep -oE '^[0-9]+-[0-9]+')
  python .claude/python/sdd_scripts/set_us_status.py \
    --us "$us_id" --status InProgress 2>/dev/null || true
done
```

Skip pour les US sans plan écrit (erreur isolée, cf. STEP 4).

---

## STEP 4.ter — Auto-ingest plans dans console.db (depuis 2026-05-21)

Invoquer **systématiquement** le script déterministe `ingest_plans.py`
pour populer la table `plans` de `workspace/output/db/console.db`
(parsing frontmatter v2 + count entrées section `## Files`).

```bash
python .claude/python/sdd_scripts/ingest_plans.py 2>&1 | tail -1
```

| Exit | Sens | Action caller |
|---|---|---|
| `0` | Ingest OK | continuer (log 1 ligne `[OK] ingested N plans`) |
| `1` | DB introuvable / corrompue | WARN 1 ligne, continuer (non bloquant) |

**Idempotent** : `ON CONFLICT(plan_id) DO UPDATE` — re-exécution
sans effet.

**Coût** : 0 token LLM, ~50 ms, parse YAML frontmatter + regex.

**Schéma populé** : `plan_id` (= `{us_id}-{family}`), `us_id`, `family`,
`file_path`, `schema_version` (1|2), `strict_ready` (0|1), `us_hash`
(SHA-256 US au moment du plan), `capabilities_json` (liste), `file_count`
(entrées `- path:` dans `## Files`), `generated_at`.

**Non bloquant** : un échec de l'ingest n'invalide pas la génération
des plans. Les fichiers `.back.md` / `.front.md` sur disque restent la SSoT.

---

## STEP 5 — Récap final

Émettre **un seul bloc final** :

```
✅ FEAT {n} — plans techniques écrits

Plans backend  : workspace/output/plans/{n}-*-*.back.md  ({Tb_ok} US, {Tb_skip} skipped)
Plans frontend : workspace/output/plans/{n}-*-*.front.md ({Tf_ok} US, {Tf_skip} skipped)

Prochaine étape :
  - relire et éditer si besoin workspace/output/plans/{n}-*-*.{back,front}.md
  - lancer /dev-run {n} (les plans seront détectés et consommés sans
    re-planification)
  - ou /dev-plan {n} pour régénérer les plans (idempotent)
```

Si tout passe sans accroc :
```
✅ FEAT {n} — {Tb_ok} plans backend + {Tf_ok} plans frontend écrits dans workspace/output/plans/.
```

---

## Règles de cette commande

- **Autonome** — pas de Q/R utilisateur.
- **Idempotent** — relancer écrase les plans précédents.
- **Pas de génération de code** — c'est le rôle de `/dev-run`.
- **Pas de build, pas de DB connexion, pas d'install**.
- **Erreur isolée par US** : un échec sur 1 US ne casse pas les autres.
- Le format des fichiers de plan est défini par les agents (cf.
  `agents/dev-backend.md` et `agents/dev-frontend.md`). Toute édition
  manuelle DOIT respecter ce format pour que `/dev-run` puisse le
  consommer.
