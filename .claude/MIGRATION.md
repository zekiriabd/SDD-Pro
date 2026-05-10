# SDD_Pro — Migration Guide

Guide concis pour migrer un projet existant entre versions majeures.

---

## v5.0.0 → v6.0.0 (ultra-lean — suppression validator)

**Effort** : ~2 minutes. **Breaking** : agent `validator` retiré.

### Étapes

1. **Récupérer les fichiers modifiés** depuis le template :
   ```
   .claude/CLAUDE.md              (version v6.0.0, 4 cœur + 2 support)
   .claude/CHANGELOG.md           (entry v6.0)
   .claude/MIGRATION.md           (ce fichier)
   .claude/commands/spec-validate.md (réécrit, 100% déterministe)
   .claude/loader.yml             (validator retiré, version 6.0.0)
   .claude/scripts/framework-smoke.ps1 (validator retiré du check 1)
   .claude/docs/architecture.md   (validator retiré du tableau modèles)
   .claude/docs/workflow.md       (mention agent validator → déterministe)
   workspace/output/docs/presentation.html  (v6.0.0, 6 agents, section Validator retirée)
   workspace/output/docs/readme.html        (v6.0.0)
   ```

2. **Supprimer** `.claude/agents/validator.md` (plus utilisé).

3. **Si tu as un rapport readiness existant** : la section §2
   (validations sémantiques) ne sera plus régénérée. Aucune action
   requise — un nouveau `/spec-validate` produit un rapport sans §2.

4. **Vérifier la cohérence** :
   ```powershell
   .claude/scripts/framework-smoke.ps1
   ```
   Doit retourner OK=44+ (au lieu de 50 en v5, car validator retiré).

5. **(Optionnel) Mesurer le delta tokens** :
   ```powershell
   .claude/scripts/measure-batch.ps1 -Since "2026-05-XX"
   ```
   Cible : –1.4M tokens raw par `/sdd-full` vs v5.

### Compatibilité ascendante

- ✅ Tous les autres commands fonctionnent identiquement.
- ✅ Les artefacts `workspace/output/{us,src,context,db,qa}/` v5 sont consommés
  tels quels par v6.
- ✅ Les SPECs `workspace/input/specs/*.md` v5 sont valides v6.
- ✅ Les rapports readiness v5 (avec §2 sémantique) restent lisibles ;
  les nouveaux rapports v6 n'auront simplement pas de §2.

### Comportements changés

- `/spec-validate` est désormais **100% script PS, 0 token LLM**.
- Plus de détection automatique d'AC vagues, ambiguïtés cross-artefact,
  hypothèses implicites. **Review humaine PO obligatoire** pour ces
  aspects sémantiques.
- Décision finale = décision déterministe seule (plus de combinaison
  det/sem).

### Pour réintroduire le validator localement

Si tu trouves la review sémantique LLM nécessaire :
1. Restaurer `.claude/agents/validator.md` depuis git history < v6.0
2. Restaurer la STEP 4 dans `.claude/commands/spec-validate.md`
3. Restaurer la section `validator:` dans `loader.yml`
4. Ajouter `validator` à `expectedAgents` dans `framework-smoke.ps1`

---

## v4.0.0 → v5.0.0 (token-lean + robustesse)

**Effort** : ~5 minutes. **Pas de breaking change fonctionnel**, juste
des paramètres optionnels et des fichiers ajoutés.

### Étapes

1. **Récupérer les nouveaux fichiers** depuis le template :
   ```
   .claude/CHANGELOG.md           (nouveau — historique versions)
   .claude/MIGRATION.md           (ce fichier)
   .claude/CLAUDE.md              (rewrite slim 198 lignes — sauvegarder l'ancien si tu y as ajouté du custom)
   .claude/loader.yml             (rewrite v5.0.0 — bump version + standardisation)
   .claude/docs/architecture.md   (nouveau)
   .claude/docs/workflow.md       (nouveau)
   .claude/docs/conventions.md    (nouveau)
   .claude/scripts/measure-batch.ps1
   .claude/scripts/detect-capabilities.ps1
   .claude/scripts/validate-inline-rules.ps1
   .claude/rules/library-policy.md (nouveau)
   .claude/agents/po.md           (Inline Rules ajoutées)
   .claude/agents/arch.md         (STEP 12.6 + Inline Rules + politique extraite)
   .claude/agents/validator.md    (Inline Rules)
   .claude/agents/elicitor.md     (Inline Rules)
   .claude/agents/qa.md           (Inline Rules)
   .claude/agents/dev-backend.md  (HARD-GATE STEP 0 + Inline Rules)
   .claude/agents/dev-frontend.md (HARD-GATE STEP 0 + Inline Rules)
   ```

2. **Ajouter (optionnel) les nouveaux paramètres** dans
   `workspace/input/stack/stack.md ## Project Config` :
   ```yaml
   BuildLoopMaxIter: 3       # défaut 3, range 1-10 (cascades complexes : 5)
   HexToleranceMaxPct: 5     # défaut 5, range 0-20 (strict pixel-perfect : 0)
   ```
   Si absents → comportement v4 préservé.

3. **Vérifier la cohérence** :
   ```powershell
   .claude/scripts/validate-inline-rules.ps1
   ```
   Doit retourner `OK=21+ DRIFT=0 MISSING=0`. Si DRIFT détecté, un
   rule file a été modifié après l'agent qui l'inline → relire l'agent.

4. **(Optionnel) Mesurer le delta tokens** :
   ```powershell
   .claude/scripts/measure-batch.ps1 -Since "2026-05-XX"
   ```

### Compatibilité ascendante

- ✅ Tous les commands `/spec-generate`, `/us-generate`, `/dev-run`,
  `/qa-generate`, `/sdd-full`, etc. fonctionnent identiquement.
- ✅ Les artefacts `workspace/output/{us,src,context,db,qa}/` v4 sont consommés
  tels quels par v5.
- ✅ Les SPECs `workspace/input/specs/*.md` v4 sont valides v5.
- ✅ Les `workspace/input/ui/*.html` mockups v4 fonctionnent identiquement.

### Comportements changés (transparents pour l'utilisateur)

- Build loop default reste 3 itérations (changement seulement si tu
  configures `BuildLoopMaxIter`).
- Fidelity check accepte maintenant les variations hex ±5% (avant : strict
  exact OR primitive DS). Pour retrouver le strict v4, mettre
  `HexToleranceMaxPct: 0`.
- arch valide ses writes constitution.md (STEP 12.6) — un Edit qui aurait
  silencieusement échoué en v4 est maintenant détecté en v5.

---

## v3.x.x → v4.0.0 (HTML direct)

**Effort** : variable selon la profondeur d'utilisation des PNG mockups.

### Breaking

- L'agent UI et la phase 3 (UI) **n'existent plus**.
- `workspace/output/ui/` n'est plus produit.
- `/ui-generate` est supprimée.
- Les mockups PNG (`workspace/input/ui/*.png`) doivent être convertis en HTML
  statiques (`workspace/input/ui/{n}-{m}-{Name}.html`).

### Étapes

1. Pour chaque PNG mockup, produire un HTML statique avec les libellés
   exacts, structure DOM, classes CSS, couleurs inline. Plusieurs
   approches :
   - Export Figma → HTML
   - Édition manuelle
   - LLM externe pour générer le HTML à partir du PNG
2. Renommer pour respecter `workspace/input/ui/{n}-{m}-{Name}.html` (basename
   identique aux US `workspace/output/us/{n}-{m}-{Name}.md`).
3. Supprimer `workspace/output/ui/` (plus produit en v4).
4. Vérifier que le stack UI actif a une section §7 « Mapping HTML →
   composant DS » (`radzen-blazor.md`, `shadcn.md`, `vuetify.md`).

### Migration assistée

Pas de migration auto disponible — la conversion PNG → HTML est manuelle
ou semi-automatique selon ton outillage.

---

## Versions antérieures

Voir l'historique git pour les migrations v2.x → v3.x (constitution +
ADRs, readiness gate, élicitation, QA agent).
