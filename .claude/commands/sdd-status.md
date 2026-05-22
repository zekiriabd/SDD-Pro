# /sdd-status — Diagnostic du pipeline SDD

Affiche l'état du projet SDD : FEATs présentes, US générées, mockups
HTML, code généré. **Lecture seule**, aucune écriture, aucune invocation
d'agent.

**Usage :**
- `/sdd-status` — toutes les FEATs
- `/sdd-status {n}` — une seule FEAT

---

## STEP 1 — Lister les FEATs

Glob `workspace/input/feats/*.md`. Pour chaque fichier :
- extraire le préfixe numérique `{n}` avant le premier `-`
- extraire le `{FeatName}` (suffixe après `{n}-`, sans `.md`)

Si argument `{n}` fourni, ne traiter que cette FEAT. Si aucune FEAT
trouvée → afficher :
```
Aucune FEAT dans workspace/input/feats/. Lancer /feat-generate pour démarrer.
```
et STOP.

---

## STEP 2 — Pour chaque FEAT, calculer l'état

Pour `{n}-{FeatName}`, exécuter en parallèle :

1. **US générées** : Glob `workspace/output/us/{n}-*.md` → lister `{n}-{m}-{Name}`
2. **Mockups HTML** : Glob `workspace/input/ui/{n}-*.html` → lister

Indexer chaque ensemble par `{n}-{m}-{Name}` (basename sans extension).

---

## STEP 2.bis — État global (1 fois, indépendant des FEATs)

Avant le détail par FEAT, calculer en parallèle :

- **Arch** : Glob `workspace/output/src/**/*.csproj`, `workspace/output/src/**/package.json`,
  `workspace/output/src/**/pyproject.toml`. Si au moins un fichier projet trouvé,
  marquer `[ARCH ✓]`. Sinon `[ARCH ✗]`.
- **CLAUDE.md projets** (v2.5) : Glob `workspace/output/src/*/CLAUDE.md`. Lister
  par projet — un par `{BackendName}`, `{AppName}`, `{LibName}`. Si
  au moins un projet a son CLAUDE.md, marquer `[CONTEXT ✓]` ; si tous
  manquent, `[CONTEXT ✗]` (Arch n'a pas tourné en v2.5+).
- **DB schema** : Glob `workspace/output/db/schema.json`. Si présent, marquer
  `[DB ✓]` (extraire `extracted_at` pour info). Sinon, lire
  `workspace/input/stack/stack.md` → si `## Active Database` contient
  `DatabaseType: none` (ou bloc absent) marquer `[DB —]`, sinon `[DB ✗]`.
  Mentionner `workspace/output/db/schema.diff.md` si présent (montre les
  changements depuis le dernier run).

---

## STEP 3 — Cross-check par US

Pour chaque US trouvée en STEP 2.1, vérifier :

| État              | Symbole | Test                                                   |
|-------------------|---------|--------------------------------------------------------|
| US présente       | `[US ✓]`| (toujours vrai si on est ici)                          |
| Mockup HTML       | `[HTML ✓]` ou `[HTML —]` | basename présent dans STEP 2.2 ? sinon `—` (US backend-only ou frontend sans mockup) |

Cas d'incohérence à flagger explicitement (ligne `⚠️`) :
- Mockup HTML orphelin (pas d'US correspondante) → `⚠️ HTML orphelin {n}-X-Foo.html (renommer ou retirer)`

---

## STEP 4 — Émettre le rapport

Format de sortie en arbre ASCII. Commencer par le bloc **État global**
(arch + DB) avant les FEATs :

```
État global :
  [ARCH ✗]  aucun projet initialisé dans workspace/output/src/ — lancer /arch-init (ou /dev-run {n})
  [DB ✗]    DatabaseType=SqlServer mais workspace/output/db/schema.json absent — lancer /arch-init (ou /dev-run {n})

FEAT 1-Layout-Menu (workspace/input/feats/1-Layout-Menu.md)
├─ US (2) :
│  ├─ 1-1-Page-Accueil       [US ✓] [HTML —]
│  └─ 1-2-Menu-Navigation    [US ✓] [HTML ✓]
├─ Mockups : 1 HTML
└─ À faire : /dev-run 1 (lance arch + db + dev-back + dev-front en chaîne)
```

Si tout est complet pour une FEAT (US + mockups HTML pour les US à composante UI) :
```
✅ FEAT 1-Layout-Menu — planification complète (2 US, 1 mockup HTML)
```

### 4.bis — Bloc QA (depuis SDD_Pro v3.1.0)

Si `workspace/output/qa/feat-{n}/` existe, ajouter un bloc QA par FEAT :

```
QA :
  ├─ Tests       : 47/47 passants (✓)
  ├─ Coverage    : 82.3% (seuil 80%) (✓)
  ├─ Quality     : 0 errors / 5 warnings / 12 info
  └─ Décision    : 🟢 GREEN
```

Source de vérité (v6.10) :
- `workspace/output/db/console.db` tables `qa_coverage` / `qa_quality` /
  `qa_api_tests` — interrogées via :
  ```bash
  python .claude/python/sdd_scripts/query_console_db.py feat-stats --feat {n}
  ```

Si la query retourne `"present": false` pour toutes les sections QA :
```
QA : non exécuté (lancer /qa-generate {n})
```

À la fin du rapport, ligne récapitulative globale :
```
Total : {S} FEAT(s), {U} US, {H} mockup(s) HTML, {Q} rapport(s) QA
```

---

## STEP 5 — Suggestions concrètes (1 ligne)

Si `[ARCH ✗]` ou `[DB ✗]` → terminer par :
```
Pour matérialiser une FEAT : /dev-run {n} (arch + db + code en chaîne) ou /sdd-full {n}.
```

Sinon (tout le code semble en place) :
```
Pipeline complet. Inspecter workspace/output/src/ pour le code généré.
```

---

## Règles de cette commande

- **Lecture seule.** Aucun Write/Edit, aucune invocation d'agent.
- **Pas de Q/R utilisateur.** Sortie déterministe en 1 passe.
- **Format compact** : tree ASCII lisible, pas de récap verbeux.
- **Pas de coût agent** — uniquement Glob et formatage.
- **Pas de référence aux tâches techniques** — la phase TASKS n'existe
  plus en v2 (les agents dev planifient inline depuis l'US).

---

## Chat Output Protocol

> Cette commande applique strictement `@.claude/rules/output-protocol.md`.
> Substance non dupliquée — la règle est SSoT.

**Labels canoniques émis** : `[ANALYSIS]` (label diagnostic read-only)
**Plage de progression couverte** : `0-100%` (snapshot, pas progression
réelle — affichage tree ASCII compact en 1 passe)

**Granularité cible** : sortie déterministe 1 passe. Pas de chunking
multi-update. Format final = tree ASCII compact lisible (cf. règles
existantes de la commande) sans préfixe `[ANALYSIS]` (sortie tabulaire
considérée comme "rendu" plutôt que "log de progression").

**Interdits stricts** (cf. §5 du protocole) :
- pas d'invocation d'agent ni de tool log
- pas de stdout/stderr de bash autre que le tree final
- pas de "Reading…", "Globbing…" avant le rendu

**Erreurs** : si Glob échoue → 1 ligne `🔴 [ANALYSIS/FAIL] {résumé}.`.

**Bypass debug** : `SDD_CHAT_VERBOSE=1` → mode legacy verbose (§10).
