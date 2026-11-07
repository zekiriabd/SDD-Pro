# ADR-20261107T180000-b7e4 — Écritures shell soumises aux hooks de protection

- **Statut** : Proposed
- **Date** : 2026-11-07
- **Auteur** : Tech Lead (incident de session 2026-11-07)
- **Phase** : gouvernance (protections runtime)

---

## Context

`enforce_tdd` n'écoutait que `Edit|Write|MultiEdit`. Un sous-agent a créé
19 fichiers `.cs` de production sans aucun test en passant par des heredocs
Bash (`cat > X.cs <<'EOF'`) : le contrat test-first (invariant
`tdd-test-first-no-prod-code-without-failing-test`) a été contourné sans
qu'aucun hook ne se déclenche. Un autre sous-agent a écrit sous `.sdd/` par
shell des fichiers que `protect_framework` refusait en mode fichier.

`protect_framework` et `block_secret_access` avaient déjà un mode shell, mais
chacun avec son propre découpage de la commande. Ce découpage ne gérait ni
les heredocs (le corps d'un heredoc de données était lu comme une commande,
d'où des faux positifs), ni les here-strings PowerShell, ni `cd X && …`, ni
`bash -c`, ni `[IO.File]::WriteAllText`, ni la redirection `1>`.

## Decision

1. Créer `sdd_lib/shell_write_targets.py`, un module partagé qui extrait de
   façon conservatrice les cibles d'écriture, de suppression et de
   déplacement d'une commande Bash ou PowerShell. Il ne prend aucune
   décision : il renvoie des `WriteTarget` (chemin, opération, `cwd`
   effectif, contenu quand il est connu, sources d'une copie).
2. `protect_framework` (mode shell) applique sur chaque cible **la même
   décision que son mode fichier** (`_decide_framework`, et
   `_decide_gate_artifact` avec l'exception `loader.yml writes:`). Les
   modes, les bypass et la classe `[FRAMEWORK_PROTECTED]` ne changent pas.
3. `enforce_tdd` est câblé sur `Bash|PowerShell` dans `.claude/settings.json`.
   Il applique la même décision que son mode fichier (`[TDD_NO_TEST_FIRST]`,
   avec `SDD_TDD_MODE` et `SDD_DISABLE_TDD`) :
   - **contenu connu** : il passe la regex de détection des symboles ;
   - **copie** : le contenu lu est celui du fichier source ;
   - **contenu inconnu** : refus seulement si le fichier est nouveau
     (fail-closed) ;
   - un test qui contient de vrais cas et qui est écrit par la **même**
     commande compte comme test compagnon.
4. `block_secret_access` reprend le découpage partagé. Le corps d'un heredoc
   n'est analysé que lorsque ce corps est du code donné à un interpréteur.
   Les globs passés à une commande de lecture (`cat .en*`) sont développés
   contre des noms de fichiers secrets.

## Consequences

- Ce mécanisme reste une heuristique, pas une sandbox. Il ne détecte ni les
  chemins dynamiques (`$VAR`, `Path(a) / b`), ni la substitution `$(…)`, ni
  un script intermédiaire qui écrit lui-même.
- Copier un fichier **depuis** `.sdd/` n'est plus refusé : seule la
  destination d'une copie compte comme une écriture.
- `.claude/worktrees/` est exempté du mode shell (copies de travail
  d'isolation).
- Couverture : `tests/test_shell_write_bypass.py`. Inventaire :
  `hooks-and-protections.md §1.1, §1.3, §1.9, §1.14`.
