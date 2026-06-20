# /sdd-status — Diagnostic du pipeline SDD

Affiche l'état du projet SDD : FEATs présentes, US générées, mockups
HTML, code généré, métriques QA. **Lecture seule**, aucune écriture,
aucune invocation d'agent.

> v7.0.0-alpha (audit MAJ-3, 2026-06-04) — refactor « thin orchestrator » :
> 173 L → ~70 L. La logique de calcul d'état vit dans les scripts
> déterministes `sdd_state.py` (FEATs/US/HTML) et `query_console_db.py`
> (QA metrics). Cette commande se contente d'orchestrer leur invocation
> et d'imprimer le résultat.

**Usage :**
- `/sdd-status` — toutes les FEATs
- `/sdd-status {n}` — une seule FEAT

---

## STEP 1 — Détection de la portée

Si argument `{n}` fourni → mode mono-FEAT. Sinon → mode multi (toutes
les FEATs sous `workspace/input/feats/`). Si aucune FEAT trouvée :

```
Aucune FEAT dans workspace/input/feats/. Lancer /feat-generate pour démarrer.
```

STOP.

---

## STEP 2 — Invoquer les scripts déterministes

**Source de vérité unique** : pas de Glob/Read manuel ici (réinventait
ce que les scripts font déjà avec moins de bugs).

```bash
# État global (runs + phases + last_run agrégés depuis console.db)
python .claude/python/sdd_scripts/sdd_state.py status [--feat-number {n}]

# Métriques QA persistées dans console.db (tables qa_coverage / qa_quality / qa_api_tests / …)
python .claude/python/sdd_scripts/query_console_db.py feat-stats --feat {n}
```

Les scripts renvoient JSON (déterministe, 0 token LLM, ~50 ms cumulés).
Détails :
- `sdd_state.py` — FEATs/US/HTML, ARCH, DB, CLAUDE.md projets (calculs Glob)
- `query_console_db.py` — `qa_coverage`, `qa_quality`, `qa_api_tests`,
  `qa_spec_compliance`, `qa_security` (mode `feat-stats` agrège tout)

---

## STEP 3 — Émettre le rapport (tree ASCII compact)

Parser le JSON et rendre en tree ASCII :

```
État global :
  [ARCH ✗]  aucun projet initialisé dans workspace/output/src/ — lancer /arch-init
  [DB ✗]    DatabaseType=SqlServer mais workspace/output/db/schema.json absent
  [CONTEXT ✗] aucun CLAUDE.md projet sous workspace/output/src/*/

FEAT 1-Auth (workspace/input/feats/1-Auth.md)
├─ US (2) :
│  ├─ 1-1-Login           [US ✓] [HTML ✓]
│  └─ 1-2-Reset-Password  [US ✓] [HTML —]
├─ Mockups : 1 HTML (1 US sans mockup — backend-only OK)
├─ QA :
│  ├─ Tests       : 47/47 passants ✓
│  ├─ Coverage    : 82.3% (seuil 80%) ✓
│  ├─ Quality     : 0 errors / 5 warnings / 12 info
│  └─ Décision    : 🟢 GREEN
└─ À faire : pipeline complet (inspecter workspace/output/src/)
```

Cas d'incohérence à flagger explicitement (`⚠️`) :
- Mockup HTML orphelin → `⚠️ HTML orphelin {n}-X-Foo.html (renommer ou retirer)`
- US sans HTML quand `appType == back-front` avec routes UI → WARN informatif

Si une section QA renvoie `"present": false` → `QA : non exécuté (lancer /qa-generate {n})`.

À la fin du rapport :
```
Total : {S} FEAT(s), {U} US, {H} mockup(s) HTML, {Q} rapport(s) QA
```

---

## STEP 4 — Suggestions concrètes (1 ligne)

Si `[ARCH ✗]` ou `[DB ✗]` :
```
Pour matérialiser une FEAT : /dev-run {n} (arch + db + code) ou /sdd-full {n}.
```

Sinon :
```
Pipeline complet. Inspecter workspace/output/src/ pour le code généré.
```

---

## Règles de cette commande

- **Lecture seule.** Aucun Write/Edit, aucune invocation d'agent.
- **Délégation pure** vers `sdd_state.py` + `query_console_db.py`
  (déterministes, 0 token LLM).
- **Pas de Q/R utilisateur.** Sortie déterministe en 1 passe.
- **Format compact** : tree ASCII lisible, pas de récap verbeux.

---

## Chat Output Protocol

Applique `@.claude/rules/output-protocol.md`. Label `[ANALYSIS]`
(diagnostic read-only). Sortie 1 passe (snapshot, pas chunking).
Le tree ASCII final est considéré comme "rendu" — sans préfixe
`[ANALYSIS]`. Erreurs : 1L `🔴 [ANALYSIS/FAIL] résumé`. Bypass
`SDD_CHAT_VERBOSE=1`.
