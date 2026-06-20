# SDD_Pro — Politique de gestion des orphelins

> ✅ **Status v7.0.0-alpha (2026-06-05)** — les scripts `audit_orphans.py`
> et `cleanup_orphans.py` sont **implémentés et testés** (11 tests pytest
> sous [`tests/test_audit_cleanup_orphans.py`](../python/tests/test_audit_cleanup_orphans.py)).
> Categories détectées : `us_orphans`, `plan_orphans`, `qa_orphans`,
> `direct_orphans` (FEAT supprimée → dérivés résiduels).

> **Source de vérité unique** pour la détection et le nettoyage ciblé
> des artefacts orphelins issus de renommages/suppressions de US ou FEAT.
> Cf. `ADR-20260519T183000-governance-orphan-cleanup-tool` pour la
> décision et le plan d'implémentation v7.0.0.

---

## 1. Le problème (mesuré 2026-05-19)

`/sdd-clear` a été retiré en v6.1 (cf. `@.claude/docs/CHANGELOG.md` ligne 1208) :
*"purge en masse non récupérable jugée risquée"*. Décision correcte
(mass purge dangereux) mais **sans remplacement ciblé**.

Conséquence : à chaque renommage ou suppression de US/FEAT, **les artefacts
dérivés restent sur disque** et créent des divergences silencieuses entre
la source (FEATs + US dans `workspace/input/`) et la génération (`workspace/output/`).

### 5 sources de drift identifiées

| # | Cas | Artefacts orphelins |
|---|---|---|
| 1 | **US renommée** (`1-2-Login-Page` → `1-2-Auth-Login`) | `workspace/output/us/1-2-Login-Page.md`, `workspace/output/plans/1-2-Login-Page.{back\|front}.md`, fichiers code générés `*LoginPage*` dans `workspace/output/src/{Project}/...` et `*.Tests/` |
| 2 | **US supprimée** (feature scrappée) | TOUS les artefacts dérivés (plans, services, components, endpoints, tests). `spec-compliance-reviewer` continue à scanner du code sans AC source. |
| 3 | **FEAT renumérotée** (split 1 FEAT → 2 FEATs) | TOUS les artefacts dérivés (IDs n incrémentés cascade). Cas le plus brutal. |
| 4 | **Plan partial dépassé** (US devient frontend-only mais `.back.md` reste) | `workspace/output/plans/{n}-{m}-{Name}.back.md` orphelin, sans contre-partie code (mais détection fragile : peut être intentionnel) |
| 5 | **Capability triggered devenue inutile** (AC mentionnant `excel` retirée) | Lib EPPlus reste dans `.csproj` + `using OfficeOpenXml;` reste dans le code, mais plus aucun usage |

### Mesure sur le repo courant

- US présents sous `workspace/output/us/` : **10 fichiers**
- Plans sous `workspace/output/plans/` : **14 fichiers**
- US sans `.back.md` : `1-2`, `3-2`, `3-3`, `4-3` — légitimes ou orphelins ? Pas de méthode automatisée pour distinguer.

---

## 2. Principe directeur

**Nettoyage ciblé, jamais mass purge**.

- ✅ Détection déterministe par diff de basenames (US présents vs plans/code matérialisés)
- ✅ Dry-run obligatoire avant toute suppression
- ✅ Confirmation utilisateur explicite (Tech Lead) avant `rm`
- ✅ Liste exhaustive des chemins à supprimer dans le rapport
- ✅ Backup auto sous `workspace/output/.sys/.trash/{timestamp}/` avant suppression (recovery 7 jours)
- ❌ Jamais de suppression silencieuse
- ❌ Jamais de mass purge équivalent `rm -rf workspace/output/`
- ❌ Jamais d'auto-cleanup en CI sans `--yes` explicite

---

## 3. Détection (3 catégories d'orphelins)

### 3.1 Orphelin direct (basename mismatch)

Un fichier sous `workspace/output/{us,plans}/` dont le basename
`{n}-{m}-{Name}` n'a **aucun match** dans les FEATs source
`workspace/input/feats/{n}-*.md`.

Exemple : US `2-5-OldFeature.md` existe mais FEAT 2 ne mentionne plus
SFD-5 (renumérotation). → orphelin direct.

### 3.2 Orphelin de plan (US absent)

Un plan `workspace/output/plans/{n}-{m}-*.{back|front}.md` dont l'US
correspondante `workspace/output/us/{n}-{m}-*.md` n'existe plus
(ou a un `{Name}` différent).

### 3.3 Orphelin de code (plan absent)

Un fichier sous `workspace/output/src/{Project}/...` dont le nom
référence un `{n}-{m}-{Name}` non couvert par un plan actuel.

> **Détection fragile** : les fichiers de code peuvent ne pas porter
> le nom de l'US dans leur path (e.g., `Services/AuthService.cs` ne
> dit pas qu'il vient de US `1-1-Connexion`). La détection §3.3 repose
> sur :
> 1. Convention : la première ligne de chaque fichier généré contient
>    un marqueur ` // generated-by-us: {n}-{m}-{Name}` (à ajouter par
>    dev-* en v7.0.0).
> 2. Fallback : grep des préfixes US dans les commentaires/docstrings
>    générés (best effort, peut louper).

### 3.4 Orphelin de capability

Une lib `onDemand` (`.libs.json`) installée mais dont le trigger regex
ne matche plus aucune AC active (US présentes). Cf. `detect_capabilities.py`.

---

## 4. Mode d'opération du tool (v7.0.0)

Deux scripts complémentaires sous `.claude/python/sdd_admin/` (mainteneur-invoqués manuellement, déplacés depuis `sdd_scripts/` audit 2026-06-06 M3 — usage pattern manuel hors pipeline runtime) :

### 4.1 `audit_orphans.py` — détection read-only

```bash
python .claude/python/sdd_admin/audit_orphans.py [--feat N] [--json]
```

- Scan `workspace/input/feats/` (source) + `workspace/output/{us,plans,src}/`
- Diff basenames, applique les 4 règles §3
- Sortie : table par catégorie (direct / plan / code / capability)
  avec compteurs + paths exhaustifs
- **Jamais d'écriture**, jamais de `rm`
- Exit codes : 0 = clean, 1 = orphelins détectés (informational)

### 4.2 `cleanup_orphans.py` — suppression ciblée

```bash
python .claude/python/sdd_admin/cleanup_orphans.py [--feat N] [--dry-run] [--yes]
```

- Lit le rapport de `audit_orphans.py`
- **Défaut `--dry-run`** : liste ce qui serait supprimé, ne touche rien.
- `--yes` : exécute la suppression APRÈS demande confirmation interactive
  (sauf si stdin non-tty → refuse par défaut).
- Pour chaque suppression :
  1. `cp` vers `workspace/output/.sys/.trash/{ts}/{relative-path}`
  2. `rm` du fichier original
  3. Émet un événement `console.db` table `events` de type `orphan.deleted`
     avec le path + le ts trash + l'opérateur (`USERNAME` env var ou `cli`)
- **Recovery 7 jours** : restauration manuelle depuis
  `workspace/output/.sys/.trash/{ts}/` (commande standard `cp` ou `mv` —
  l'arborescence préserve les paths relatifs originaux). Pas de script
  d'auto-restore : la recovery reste un geste **explicite** du Tech Lead.

### 4.3 Suppression manuelle interdite

Le Tech Lead ne doit **PAS** faire `rm` à la main sur les fichiers de
`workspace/output/` car cela bypass :
- Le backup `.trash/`
- L'événement `orphan.deleted` (audit historique)
- Le check de cohérence (e.g., supprimer un plan dont le code dépend encore)

Forme rejetée : `rm workspace/output/plans/2-5-*.md` direct.
Forme acceptée : `cleanup_orphans.py --feat 2 --yes`.

---

## 5. Périmètre PROTÉGÉ (never delete)

`cleanup_orphans.py` **refuse** de supprimer :

- `workspace/input/` (sources Tech Lead, jamais touché)
- `workspace/output/.sys/.context/constitution.md` (toujours conservé)
- `workspace/output/.sys/.context/adrs/*.md` (append-only, jamais supprimé)
- `workspace/output/db/console.db` (runtime SSoT)
- `workspace/console/` (UI status)
- `workspace/output/.sys/.trash/` (trash lui-même, garde de cycle)
- Tout fichier hors `workspace/output/` (sécurité absolue)

---

## 6. Détection orphelins capability (§3.4)

`audit_orphans.py --capabilities` étend la détection aux libs installées :

1. Lit `.csproj` / `package.json` / `pyproject.toml` actifs
2. Pour chaque lib correspondant à une capability `onDemand` du
   `.libs.json` du stack actif :
   - Lit tous les US présents → concatène ACs
   - Match chaque trigger regex de la capability vs ACs
   - Si **aucun match** → lib orpheline (= peut être désinstallée)
3. Rapport seulement (la suppression de lib via `dotnet remove`/`npm uninstall`
   est laissée au Tech Lead — pas automatisée pour rester safe).

---

## 7. Intégration pipeline

### 7.1 Au démarrage de `/dev-run` (recommandation v7.0.0)

`audit_orphans.py --feat N` invoqué en STEP 0 d'orientation. Si
orphelins détectés → WARN dans le log, sans bloquer (informational).

### 7.2 Avant `/feat-validate` (recommandation v7.0.0)

Idem : `audit_orphans.py` informe le Tech Lead avant readiness gate.

### 7.3 Job CI dédié (recommandation v7.0.0)

`audit_orphans.py --strict` exit-non-zero si orphelins détectés
au niveau projet entier. Mode opt-in via Project Config
`OrphanAuditFailOn: warn | error | off` (défaut `warn`).

---

## 8. Migration v6 → v7

```markdown
## v6 → v7 — Orphan cleanup tool (remplacement /sdd-clear retiré v6.1)

### Bloquant utilisateurs

1. Avant la première utilisation, lancer :
   ```
   python .claude/python/sdd_admin/audit_orphans.py --feat all
   ```
   Le rapport peut être conséquent si le repo a accumulé des orphelins
   depuis v6.1.

2. Revoir le rapport, identifier les faux positifs (US frontend-only
   sans `.back.md` qui sont légitimes), poser les markers
   `# orphan-allowed: true` dans le frontmatter des US concernées
   pour les exclure des futurs audits.

3. Lancer `cleanup_orphans.py --feat N --dry-run` pour chaque FEAT
   ciblée, vérifier la liste, puis re-run avec `--yes` si OK.

### Backward-compat

- `/sdd-clear` n'est pas restauré. Le remplacement ciblé `cleanup_orphans.py`
  est l'unique chemin documenté.
- Le `.trash/` permet une recovery 7 jours sans intervention.
```

---

## 8.bis. Scripts Python à faible empreinte référence (audit 2026-06-05)

L'audit v7.0.0-alpha a identifié 5 scripts avec ≤ 1 référence interne :

| Script | Refs | Justification (PAS orphan) |
|---|---|---|
| `bench_run.py` | 0 internes | Outil **bench manuel** (docs/benchmarks/runbook-bench-m.md) — invocation directe par Tech Lead, pas via agents. À conserver. |
| `record_gate_decision.py` | 0 internes | Consommé par **console web Node** (`workspace/console/server.js` + `lib/console-db.js`) — invocation cross-runtime. À conserver. |
| `compute_us_complexity.py` | 1 | Validé par `framework_smoke.py` (historisé). Utilisé indirectement via tests. À conserver. |
| `dispatch_fixes.py` | 1 | Importé par `_review_report.py` + tests. À conserver. |
| `preflight_force_cumul.py` | 1 | Référencé par `sdd-full.md` (STEP 1.bis) + tests. À conserver. |

**Décision** : **aucun retrait** v7.0.0. Tous les scripts ont une raison
d'être documentable. La règle : "0 référence" ne signifie pas "orphan"
quand l'invocation est manuelle (bench), cross-runtime (console Node),
ou auditée par framework_smoke.

---

## 9. Pointers

- [`@.claude/docs/CHANGELOG.md`](./CHANGELOG.md) ligne 1208 — décision de retrait `/sdd-clear` v6.1
- [`@.claude/CLAUDE.md §3`](../CLAUDE.md) — table des commandes (futur emplacement `/cleanup-orphans` post-v7)
- `workspace/output/.sys/.context/adrs/ADR-20260519T183000-governance-orphan-cleanup-tool.md` — décision + plan v7.0.0
- [`@.claude/python/sdd_scripts/detect_capabilities.py`](.claude/python/sdd_scripts/detect_capabilities.py) — base pour §6 (détection capabilities orphelines)
- [`@.claude/python/sdd_scripts/scan_repo.py`](.claude/python/sdd_scripts/scan_repo.py) — pattern de scan existant à réutiliser
