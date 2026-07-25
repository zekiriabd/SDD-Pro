# Recette — PHP procédural (sans framework)

## Quand l'utiliser

Détection `php-procedural` dans `inventory.json.languagesDetected`. Présence `.php` sans namespace Laravel/Symfony/CodeIgniter. Souvent legacy 2000s.

## Pré-conditions

- Fichiers `.php` lisibles
- Idéalement schéma SQL (`*.sql` ou commentaires `CREATE TABLE` inline)
- `.htaccess` ou config Apache si routes URL rewrites

## Pièges connus

| Piège | Mitigation Phase 3 |
|---|---|
| **SQL injection partout** : `$sql = "SELECT * FROM x WHERE name='" . $_POST['n'] . "'"` | Capturer comme BR observable + flag security (sera durci Phase 6) |
| **Sessions cookies non chiffrés** : `$_SESSION['user_id'] = ...` brut | BR observable, à durcir Phase 6 |
| **Includes en cascade** : `require_once 'config.php'` | Phase 2 audit : tracer la chaîne d'includes |
| **State global** : `$GLOBALS`, `$_SESSION`, `$_REQUEST` partout | Capturer dans BR comme état partagé observable |
| **Pas d'autoloading** | Chaque fichier `.php` accessible directement par URL → souvent 1 fichier = 1 page = 1 unité |
| **Mélange logique + HTML** | Bias toward present : capturer les `echo`/`<?= ?>` comme outputs FD-N |
| **Confidence cap = `medium`** | Toujours — qualité variable, jamais `high` |

## Heuristiques d'extraction

1. **1 fichier `.php` URL-accessible ≈ 1 unité** (sauf fichiers `inc.php` ou `_helpers.php` = composants)
2. AC depuis :
   - `if ($_POST[...])` → 1 AC par branche
   - `if ($_SESSION[...])` → AC sur état authentifié
   - `header("Location: ...")` → AC sur redirection
   - `echo "..."` ou `<?= ?>` → FD sur l'affichage
3. BR depuis :
   - SQL inline (extraire `WHERE`, `INSERT`, `UPDATE`)
   - Validation manuelle (`if (empty(...)) ... else if (strlen(...) < 5) ...`)
   - Hashing : `md5()` vs `password_hash()` (md5 = legacy vulnérable)
4. Entities : extraites du SQL inline + éventuels `CREATE TABLE` dans `*.sql`

## Recommandations Phase 5

- ⚠️ Sécurité **critique** : revue manuelle de chaque BR pour identifier les vulnérabilités SQL injection / XSS
- `## Project Config` cible : `php-framework` (Laravel/Symfony) ou complète migration vers `node-express` / `python-fastapi`
- Cap `medium` propagé → gate `check_reverse_feat_for_full.py` exit 1 par défaut

## Exemple

Legacy `login.php` :
```php
<?php
session_start();
require_once 'db.php';
if (isset($_POST['user'])) {
    $u = $_POST['user'];
    $p = md5($_POST['pass']);
    $r = mysql_query("SELECT id FROM users WHERE name='$u' AND pwd='$p'");
    if (mysql_num_rows($r) > 0) {
        $row = mysql_fetch_assoc($r);
        $_SESSION['uid'] = $row['id'];
        header("Location: home.php");
        exit;
    }
    $msg = "Identifiants incorrects";
}
?>
<form method="post"><input name="user"><input type="password" name="pass"><button>Se connecter</button><?= $msg ?? '' ?></form>
```

Extrait FEAT :
```markdown
> ⚠️ FEAT générée par reverse engineering avec confiance MEDIUM (cap langage PHP procédural).
> Revue humaine obligatoire avant /sdd-full.

- **AC-1** Given user + pass remplis dans le formulaire, when POST login.php, then mysql_query lance SELECT contre table users. <!-- evidence: login.php:4-7 --> <!-- confidence: medium -->
- **AC-2** Given match en base, when résultat trouvé, then $_SESSION['uid'] est créée et redirect home.php. <!-- evidence: login.php:8-12 --> <!-- confidence: medium -->
- **AC-3** Given aucun match, when résultat vide, then $msg = "Identifiants incorrects" affiché. <!-- evidence: login.php:14 --> <!-- confidence: medium -->
- **BR-1** Password hashé en MD5 (⚠️ algorithme cryptographiquement cassé). <!-- evidence: login.php:6 --> <!-- confidence: high -->
- **BR-2** SQL inline concaténé : vulnérabilité SQL injection (⚠️ priorité haute Phase 6). <!-- evidence: login.php:7 --> <!-- confidence: high -->
- **BR-3** Session via cookie PHP standard ($_SESSION), sans regenerate_id post-login. <!-- evidence: login.php:9-10 --> <!-- confidence: high -->
```

Cap : `medium` (PHP procédural cap forcé par `language_signatures.yml`).
