# /dev-plan — Génère les plans techniques d'1 FEAT sans coder

> ⚠️ **Commande interne v7.0.0** — invoquée par /sdd-full STEP 3.6.
> Plans techniques pré-dev — invoqué conditionnellement.
> Utilisateur final : préférer la commande orchestrante (`/sdd-full` ou `/dev-run`)
> qui gère pré-conditions, idempotence et état. Conservée comme command pour
> debug/inspection ciblée et préservation des chaînes d'invocation documentées.

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

## STEP 4.5 — Compactage des plans frontend (idempotent)

Une fois **toutes** les invocations dev-* terminées, exécuter via Bash :

```bash
python .claude/python/sdd_scripts/compact_front_plans.py
```

Le script :
- parcourt `workspace/output/plans/*.front.md`
- pour chaque plan > 12 KB : archive l'original sous
  `workspace/output/.sys/.audit/plan-archive/{basename}.{ts}.full.md` puis
  remplace le `.front.md` par une version courte (~12 KB) contenant
  contrat d'exécution + fichiers + arbitrages essentiels
- skip silencieux pour les plans déjà ≤ 12 KB

Justification : les plans frontend non compactés (50-70 KB observés)
sont relus par `dev-frontend` à chaque US en mode From Plan → coût
tokens × N invocations. Compactage idempotent → -80% en moyenne.

Si le script échoue (exit ≠ 0) → émettre WARNING 1 ligne et continuer
(non bloquant) :
```
🟡 /dev-plan {n} — compactage front partiel (cf. stderr)
```

---

## STEP 4.7 — Validation strict-readiness des plans (depuis v6.2)

Pour chaque plan généré (back et front), invoquer `validate_plan.py`
en mode strict pour confirmer la conformité v2 (frontmatter
`plan-schema-version: 2`, `us-hash` cohérent, section `## Inline Digest`
non vide, AC coverage complète) :

```bash
python .claude/python/sdd_scripts/validate_plan.py \
  --plan-path "workspace/output/plans/{n}-{m}-{Name}.{back|front}.md" \
  --us-path "workspace/output/us/{n}-{m}-{Name}.md" \
  --strict \
  --json
```

| Exit | Comportement |
|---|---|
| `0` | Plan strict-ready → log compteur `$S_strict++` |
| `1` | Plan v1/incomplet → log compteur `$S_classic++` + WARN 1L |
| `2` | Plan stale/corrompu → ERROR + nettoyer le plan (sera regénéré au re-run) |

**Émettre un event state.jsonl** par plan validé (si `$RUN_ID` disponible) :
```bash
python .claude/python/sdd_scripts/sdd_state.py emit-event \
  --run-id $RUN_ID --event-type plan_validate_postgen \
  --payload-json '{"us":"{n}-{m}","family":"{back|front}","exit":N,"result":"ready|not_strict_ready|invalid"}'
```

**Non bloquant** : un plan exit 1 reste utilisable en mode From-Plan
classique (Opus). Exit 2 nettoie le plan pour éviter qu'un re-run
ultérieur ne le consomme à tort.

Si tous les plans sont exit 0 → émettre 1 ligne récap :
```
FEAT {n} — plans v2 strict-ready : {S_strict_back}/{P_back} back + {S_strict_front}/{P_front} front
```

Si au moins un exit 1 → émettre WARNING 1 ligne :
```
🟡 FEAT {n} — {N_not_ready} plan(s) v1 ou incomplet(s) (PlanCacheStrict aura fallback classic Opus sur ces US)
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
