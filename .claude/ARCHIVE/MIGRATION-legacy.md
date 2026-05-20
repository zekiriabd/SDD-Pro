# SDD_Pro — MIGRATION legacy (v3.x → v4.x, v4.x → v5.x)

> Versions antérieures à v6.0. Archivé le 2026-05-13 depuis `.claude/MIGRATION.md`.
> Pour migrer vers v6.x, suivre d'abord v3→v4, puis v4→v5, puis v5→v6
> (cf. `.claude/MIGRATION.md`).

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

- ✅ Tous les commands `/feat-generate`, `/us-generate`, `/dev-run`,
  `/qa-generate`, `/sdd-full`, etc. fonctionnent identiquement.
- ✅ Les artefacts `workspace/output/{us,src,context,db,qa}/` v4 sont consommés
  tels quels par v5.
- ✅ Les FEATs `workspace/input/feats/*.md` v4 sont valides v5.
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
