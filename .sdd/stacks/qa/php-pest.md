# QA Stack — Pest 5 + Mockery + coverage Xdebug/PCOV

> §2.4 (Librairies) régénérée depuis `php-pest.libs.json` — ne pas éditer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id php-pest`).

Status: Experimental
Validation: 🟡 experimental — Stack QA construit le 2026-09-02 en accompagnement des stacks PHP (`backend/laravel`, puis `fullstack/laravel-blade` et `fullstack/symfony-twig`). Chaque paquet résolu contre Packagist avec sa contrainte `require.php`. **Jamais exécuté** : aucun `pest` n'a tourné en CI (PHP absent de l'environnement de construction). Non supporté commercialement en l'état.
QA FEAT ID: php-pest
Scope: tests unitaires, fonctionnels, d'architecture et de mutation pour les stacks PHP

---

## 1. Scope

Tests pour les projets PHP matérialisés sous `workspace/src/{BackendName}/`.

| Niveau | Outil | Cible |
|---|---|---|
| **Unitaire** | Pest | services, value objects, règles métier — sans framework |
| **Fonctionnel / HTTP** | Pest + plugin du framework | une route de bout en bout, base incluse |
| **Architecture** | `pest-plugin-arch` (capability `architecture-tests`) | règles de couches, **vérifiées par la CI** |
| **Mutation** | `infection` (capability `mutation-testing`) | qualité réelle des assertions |

> **Prérequis** : **PHP ≥ 8.4.1** (§2.5) et une extension de couverture
> (Xdebug ou PCOV) si un seuil de coverage est exigé.

---

## 2. Tooling

### 2.1 Test runner

**Pest 5** — syntaxe fonctionnelle bâtie sur PHPUnit :

```php
it('rejette une facture sans ligne', function () {
    expect(fn () => (new InvoiceService())->issue(new Invoice()))
        ->toThrow(EmptyInvoiceException::class);
});
```

Pest **embarque** PHPUnit : une classe `extends TestCase` existante reste
exécutable sans conversion. Les deux styles cohabitent dans la même suite,
ce qui rend la migration d'une base existante progressive.

### 2.2 Coverage tool — **extension PHP requise, pas un paquet Composer**

```bash
./vendor/bin/pest --coverage --min=80
```

Le coverage PHP exige **Xdebug en mode `coverage`** ou **PCOV**. Ce sont des
**extensions compilées**, installées par `pecl` ou par le paquet système —
`composer` ne peut pas les fournir. Elles n'apparaissent donc pas en §2.4,
et leur absence n'est pas détectable par `validate_libs_catalog.py`.

> **Symptôme à connaître** : sans extension, `pest --coverage` échoue sur un
> message de *driver de couverture* introuvable — pas sur une dépendance
> manquante. C'est le premier réflexe de diagnostic à avoir.
>
> **PCOV plutôt que Xdebug en CI** : PCOV ne fait que la couverture et est
> nettement plus rapide ; Xdebug ralentit l'exécution même quand seule la
> couverture est demandée.

### 2.3 Mock library

**Mockery** — PHP n'offre pas de mocking par réflexion. Mockery est aussi ce
qu'utilisent les helpers de test de Laravel (`$this->mock(...)`), donc il est
présent de fait sur ces stacks.

```php
$repo = Mockery::mock(InvoiceRepository::class);
$repo->shouldReceive('find')->once()->with(1)->andReturn($invoice);
```

Alternative sans dépendance : une classe anonyme implémentant l'interface.
Préférable quand le test n'a besoin que d'une valeur de retour fixe — c'est
plus lisible et le compilateur vérifie le contrat.

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/qa/php-pest.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id php-pest`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| pestphp/pest | 5.1.3 | Runner de tests (dev). Syntaxe fonctionnelle `it()` / `expect()`, execution parallele integree. C'est lui qui impose le plancher PHP 8.4 |
| mockery/mockery | 1.6.15 | Mocking (dev) — PHP n'a pas de mocking par reflexion sans lui ; utilise aussi par les helpers de test Laravel |
| fakerphp/faker | 1.24.1 | Generation de donnees de test (dev) — requis par les factories de modele |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| laravel-testing | pestphp/pest-plugin-laravel | 5.0.1 | laravel, artisan, eloquent, test.*http.*laravel |
| architecture-tests | pestphp/pest-plugin-arch | 5.0.0 | test.*architecture, regle.*couche, dependance.*interdite, arch.*test |
| test-fixtures | pestphp/pest-plugin-faker | 5.0.0 | faker, donnees.*aleatoires, fixture |
| type-coverage | pestphp/pest-plugin-type-coverage | 5.0.2 | type.*coverage, couverture.*typage, annotation.*type |
| watch-mode | pestphp/pest-plugin-watch | 3.0.0 | watch, re-execution.*automatique |
| phpunit-direct | phpunit/phpunit (alt) | 13.3.2 | phpunit, testcase.*classique, extends TestCase |
| mutation-testing | infection/infection | 0.35.4 | mutation.*testing, infection, msi |
| symfony-fixtures | zenstruck/foundry | 2.12.1 | symfony, doctrine, factory.*entite, foundry |
| symfony-fixtures | dama/doctrine-test-bundle | 8.6.0 | symfony, doctrine, isolation.*base.*test |
| symfony-functional | symfony/browser-kit | 8.1.5 | symfony, test.*fonctionnel, webtestcase, crawler |
| symfony-functional | symfony/css-selector | 8.1.6 | symfony, crawler, selecteur.*css, assertion.*html |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Plancher runtime — ce stack QA le fixe pour toute la chaine PHP

| Paquet | `require.php` |
|---|---|
| `laravel/framework` 13.30.1 | `^8.3` |
| **`pestphp/pest` 5.1.3** | **`^8.4`** |
| **`phpunit/phpunit` 13.3.2** | **`>=8.4.1`** |

Le framework applicatif tolère PHP 8.3 ; **ce stack QA impose 8.4.1**. Sur un
projet PHP 8.3, `composer require laravel/framework` réussit, puis
l'installation des dépendances de développement échoue — c'est-à-dire au
moment de mettre en place les tests.

C'est pourquoi le gate runtime de `backend/laravel.md` §2.2.1 (STEP 0)
vérifie **8.4.1** et non la contrainte du framework. Ne pas rétrograder Pest
pour contourner : c'est le runner de ce stack.

---

## 3. Init Commands (idempotent)

```bash
if [ ! -f "workspace/src/{BackendName}/tests/Pest.php" ]; then
  cd workspace/src/{BackendName}

  # Runner + mocking + fixtures (cf. 2.4.a)
  composer require --dev --no-interaction \
    pestphp/pest:5.1.3 \
    mockery/mockery:1.6.15 \
    fakerphp/faker:1.24.1

  # Plugin du framework (capability laravel-testing)
  composer require --dev --no-interaction pestphp/pest-plugin-laravel:5.0.1

  ./vendor/bin/pest --init

  mkdir -p tests/Unit tests/Feature
fi

# Verification — le coverage exige Xdebug ou PCOV (cf. 2.2)
php -m | grep -Eq 'xdebug|pcov' \
  || echo "WARN: ni Xdebug ni PCOV — 'pest --coverage' echouera (cf. 2.2)"

(cd workspace/src/{BackendName} && ./vendor/bin/pest)
```

---

## 4. Project structure

```
{BackendName}/
├── tests/
│   ├── Pest.php              ── bootstrap : uses(), helpers globaux
│   ├── TestCase.php          ── TestCase de base du framework
│   ├── Unit/                 ── sans framework ni base (rapides)
│   │   └── {Name}Test.php
│   ├── Feature/              ── HTTP + base
│   │   └── {Name}Test.php
│   └── Arch/                 ── regles d'architecture (capability)
│       └── ArchTest.php
└── phpunit.xml               ── suites, variables d'env de test
```

`tests/Pest.php` est le point de câblage : c'est là qu'on rattache le
`TestCase` du framework et les traits de base de données à un dossier.

```php
uses(Tests\TestCase::class, RefreshDatabase::class)->in('Feature');
```

---

## 5. Test patterns

### 5.1 Unitaire — sans framework

```php
it('calcule le total TTC', function () {
    $invoice = new Invoice(linesHt: [100_00, 50_00], vatRate: 0.20);

    expect($invoice->totalTtc())->toBe(180_00);
});

it('rejette un taux de TVA negatif', function () {
    expect(fn () => new Invoice(linesHt: [], vatRate: -0.1))
        ->toThrow(InvalidArgumentException::class);
});
```

> Les montants sont en **centimes entiers**, jamais en `float` : `0.1 + 0.2 !== 0.3` en flottant, et une facture fausse d'un centime est un bug métier réel.

### 5.2 Test paramétré

```php
it('rejette un email invalide', function (string $email) {
    expect(EmailValidator::isValid($email))->toBeFalse();
})->with(['', 'a@', '@b.com', 'a b@c.com']);
```

Chaque jeu est rapporté comme un cas distinct : l'échec nomme la valeur fautive.

### 5.3 Fonctionnel HTTP (capability `laravel-testing`)

```php
it('cree une facture', function () {
    $user = User::factory()->create();

    $response = $this->actingAs($user)->postJson('/api/v1/invoices', [
        'customer_id' => 1,
        'lines' => [['label' => 'Prestation', 'amount_ht' => 100_00]],
    ]);

    $response->assertCreated()
        ->assertJsonPath('data.total_ttc', 120_00);

    $this->assertDatabaseHas('invoices', ['customer_id' => 1]);
});

it('refuse un utilisateur non authentifie', function () {
    $this->postJson('/api/v1/invoices', [])->assertUnauthorized();
});
```

> **Un test d'autorisation par route protégée.** Un oubli de middleware ne se
> voit pas à la lecture du controller — seul un test à 401/403 le détecte.

### 5.4 Architecture (capability `architecture-tests`)

C'est la valeur la plus spécifique de ce stack QA : les règles de couches des
`§1.4` applicatifs deviennent **exécutables**, au lieu de rester en prose que
personne ne vérifie.

```php
arch('les controllers ne touchent pas Eloquent directement')
    ->expect('App\Http\Controllers')
    ->not->toUse('Illuminate\Database\Eloquent\Builder');

arch('les modeles ne dependent pas du HTTP')
    ->expect('App\Models')
    ->not->toUse('Illuminate\Http\Request');

arch('pas de debug committe')
    ->expect(['dd', 'dump', 'var_dump', 'ray'])
    ->not->toBeUsed();

arch('les services sont finaux')
    ->expect('App\Services')->toBeClasses()->toBeFinal();
```

### 5.5 Mutation (capability `mutation-testing`)

```bash
./vendor/bin/infection --min-msi=70 --threads=4
```

Mesure si les assertions **détectent** un changement de comportement — un
coverage de 90 % avec des assertions faibles donne un MSI médiocre. Coûteux :
à réserver à la CI nocturne, jamais à la boucle de développement. Pendant du
`qa/mutation-testing.md` pour l'écosystème PHP.

---

## 6. Run commands

### 6.1 Test command

```bash
(cd workspace/src/{BackendName} && ./vendor/bin/pest)
(cd workspace/src/{BackendName} && ./vendor/bin/pest --parallel)          # execution parallele
(cd workspace/src/{BackendName} && ./vendor/bin/pest tests/Feature)       # cible
(cd workspace/src/{BackendName} && ./vendor/bin/pest --filter=Invoice)
(cd workspace/src/{BackendName} && ./vendor/bin/pest --bail)              # stop au 1er echec
```

Sur Laravel, `php artisan test` délègue à Pest et charge l'environnement de test.

### 6.2 Coverage command

```bash
(cd workspace/src/{BackendName} && ./vendor/bin/pest --coverage --min=80)

# Rapport exploitable par la chaine SDD_Pro
(cd workspace/src/{BackendName} && ./vendor/bin/pest --coverage-clover=coverage.xml)
```

⚠️ Exige Xdebug ou PCOV (§2.2). `--parallel` et `--coverage` se combinent mal
sur certaines configurations : mesurer la couverture en exécution simple.

### 6.3 Mutation / architecture

```bash
(cd workspace/src/{BackendName} && ./vendor/bin/pest --group=arch)
(cd workspace/src/{BackendName} && ./vendor/bin/infection --min-msi=70)
```

---

## 7. Coverage output format

- **Fichier** : `workspace/src/{BackendName}/coverage.xml`
- **Format** : **Clover XML** (`--coverage-clover`)
- **Seuil** : `--min=N` fait échouer la commande sous le seuil ; verdict 🟢/🟡/🔴 selon `rules/quality.md §A`
- **HTML** (optionnel) : `--coverage-html=coverage/`

Clover est un format standard, consommable directement — contrairement au
JSON `xccov` de `qa/swift-testing.md`, qui demande une conversion.

Le dénominateur doit exclure `database/migrations/` et `config/` : ce sont des
fichiers de déclaration, jamais couverts par des tests, et les inclure fait
chuter le taux sans signal utile.

---

## 8. Naming conventions

| Rôle | Pattern | Exemple |
|---|---|---|
| Fichier de test | `{Sujet}Test.php` | `tests/Unit/InvoiceServiceTest.php` |
| Cas de test | `it('phrase decrivant le comportement')` | `it('rejette une facture sans ligne')` |
| Cas alternatif | `test('...')` | `test('le total est arrondi au centime')` |
| Test d'architecture | `arch('regle exprimee en clair')` | `arch('les modeles ne dependent pas du HTTP')` |
| Dataset | `->with([...])` ou `dataset('nom', [...])` | `dataset('emails invalides', [...])` |
| Factory | `{Name}Factory` | `InvoiceFactory` |
| Helper partagé | `tests/Pest.php` | — |

Les descriptions sont des **phrases**, en français, décrivant le comportement attendu — pas des noms de méthodes. C'est la sortie de `pest` qui les affiche : elles constituent la documentation vivante de la suite.

---

## 9. Forbidden patterns

- Test sans assertion, ou `expect(true)->toBeTrue()`
- `sleep()` pour attendre — restructurer le test
- Appel réseau réel — utiliser un mock ou un `Http::fake()`
- Test dépendant de l'ordre d'exécution ou de l'état laissé par un autre — `RefreshDatabase` ou transaction
- Dates figées en dur (`'2026-09-02'`) sans geler l'horloge (`travelTo`) — le test devient rouge au changement d'année
- `float` pour un montant monétaire dans un test ou dans le code testé
- `->skip()` sans ticket référencé en commentaire
- Assertions sur du HTML brut par `strpos` — utiliser le Crawler (capability `symfony-functional`) ou `assertSee`
- `--coverage` exigé en CI sans Xdebug/PCOV installé (§2.2)
- `infection` dans la boucle de développement — CI nocturne uniquement
- Mockery non fermé dans un `TestCase` PHPUnit classique (`Mockery::close()` en `tearDown`) — Pest le gère, PHPUnit non
- Route protégée sans test à 401/403

---

## 10. Rattachement aux stacks applicatifs

| Stack applicatif | Capability à activer |
|---|---|
| `backend/laravel` | `laravel-testing` |
| `fullstack/laravel-blade` | `laravel-testing` |
| `fullstack/symfony-twig` | `symfony-fixtures` + `symfony-functional` |

Les capabilities `laravel-testing` et `symfony-*` sont **mutuellement
exclusives** : un projet n'utilise qu'un seul framework.
