# /dev-plan — Génère les plans techniques d'1 SPEC sans coder

Pour chaque US de la SPEC `{n}`, invoque les agents `dev-backend` et
`dev-frontend` en **mode Plan Only** : ils lisent l'US (+ mockup HTML
en lecture texte directe pour le front), planifient inline les
fichiers à produire, **écrivent le plan dans
`workspace/output/plans/{n}-{m}-{Name}.{back|front}.md`**, et s'arrêtent —
**aucun fichier de code généré, aucun build**.

L'humain peut relire et éditer ces fichiers de plan, puis lancer
`/dev-run {n}` qui détectera les plans et les consommera tels quels
au lieu de re-planifier.

**Usage :** `/dev-plan {n}` — où `{n}` est le numéro de la SPEC.

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
Quel est le numéro de la SPEC à planifier ? (ex. : 1)
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
SPEC {n} — {U} US à planifier (back + front en parallèle, mode Plan Only)
```

---

## STEP 3 — Vérifier les stacks actifs

Lire `workspace/input/stack/stack.md`.

- Si aucun `## Active Tech Specs` `backend-*` ET aucun `frontend-*` →
  ERROR comme dans `/dev-run`.

(Pas de validation env vars ici — la planification ne lit pas la DB,
ne se connecte à rien.)

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
  au format défini (cf. `agents/dev-backend.md §STEP 5.5` et
  `agents/dev-frontend.md §STEP 6.5`)
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
powershell -NoProfile -ExecutionPolicy Bypass -File .claude/scripts/compact-front-plans.ps1
```

Le script :
- parcourt `workspace/output/plans/*.front.md`
- pour chaque plan > 12 KB : archive l'original sous
  `workspace/output/.audit/plan-archive/{basename}.{ts}.full.md` puis
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

## STEP 5 — Récap final

Émettre **un seul bloc final** :

```
✅ SPEC {n} — plans techniques écrits

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
✅ SPEC {n} — {Tb_ok} plans backend + {Tf_ok} plans frontend écrits dans workspace/output/plans/.
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
