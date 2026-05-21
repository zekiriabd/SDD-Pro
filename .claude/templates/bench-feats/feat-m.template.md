# FEAT-{n} — Gestion des commandes (BenchM)

> **Template figé pour benchmark ROI** (`docs/benchmarks/README.md`).
> Hash SHA-256 figé au commit qui crée ce fichier — toute modification
> ultérieure invalide les comparaisons inter-runs (utiliser un nouveau
> template `feat-m-v2.template.md` si évolution).
>
> **Usage** : `cp .claude/templates/bench-feats/feat-m.template.md
> workspace/input/feats/{n}-BenchM.md` (renommer `{n}` selon
> numérotation projet).
>
> **Cible** : workflow métier representative — 3 US, 3 entités liées,
> 1 validation cross-field, 1 endpoint "business action" (≠ CRUD pur).
> Pas de file upload, pas d'auth complexe, pas d'intégration tierce
> (réservé à FEAT L).

---

## Context

Une équipe back-office a besoin de saisir des commandes clients,
ajouter des lignes (produits × quantité), valider que le total
matche, puis confirmer la commande pour passage à l'étape logistique.

Les commandes confirmées ne peuvent plus être éditées. Le statut
suit un workflow : `Draft → Confirmed → Cancelled`.

## Actors

- **Opérateur back-office** : crée et confirme les commandes
- **Manager** : consulte (read-only), peut annuler une commande confirmée
- *(implicite)* **Système** : exécute la validation cross-field

## Functional Needs

- **SFD-1** : créer une commande en statut `Draft` rattachée à un client
  existant (référence par ID, hors-scope de cette FEAT la gestion des
  clients eux-mêmes)
- **SFD-2** : ajouter / retirer / modifier des lignes (produit × quantité)
  sur une commande `Draft` ; recalculer automatiquement le total
- **SFD-3** : confirmer une commande `Draft` → passage en statut
  `Confirmed`, immutable ensuite (sauf annulation manager)
- **SFD-4** : annuler une commande `Confirmed` → passage en statut
  `Cancelled`, conservée pour audit (jamais supprimée)
- **SFD-5** : consulter la liste paginée des commandes avec filtres
  (statut, client, période)

## Functional Deliverables

- **FD-1** : entité `Order` (id, customer_id, status, total_amount,
  created_at, confirmed_at?, cancelled_at?, cancellation_reason?)
- **FD-2** : entité `OrderLine` (id, order_id, product_id, quantity,
  unit_price, line_amount)
- **FD-3** : entité `Product` (id, sku, name, current_price, is_active)
  — seed initial 5 produits de test
- **FD-4** : endpoint `GET /api/v1/orders` paginé + filtres
  `?status&customer_id&from&to&page&page_size`
- **FD-5** : endpoint `GET /api/v1/orders/{id}` (lignes incluses)
- **FD-6** : endpoint `POST /api/v1/orders` (création Draft + lignes en
  une seule transaction)
- **FD-7** : endpoint `PUT /api/v1/orders/{id}` (update Draft only,
  rejette 409 sur Confirmed/Cancelled)
- **FD-8** : endpoint `POST /api/v1/orders/{id}/confirm` (Draft → Confirmed)
- **FD-9** : endpoint `POST /api/v1/orders/{id}/cancel` (Confirmed →
  Cancelled, body `{reason: string}`)
- **FD-10** : page React `/orders` (liste paginée, filtres, action
  "Nouvelle commande")
- **FD-11** : page React `/orders/{id}` (détail + action
  "Confirmer" si Draft, "Annuler" si Confirmed)
- **FD-12** : formulaire React création/édition commande (sélection
  client, ajout/suppression lignes, total calculé client-side puis
  re-validé serveur)

## Business Rules

- **BR-1** : `Order.status` ∈ {`Draft`, `Confirmed`, `Cancelled`} —
  transitions valides : `Draft→Confirmed`, `Confirmed→Cancelled`.
  Toute autre transition → 409 Conflict.
- **BR-2** : `Order.total_amount = SUM(OrderLine.line_amount)` doit
  être **égal à 0.01 € près** au moment du `confirm`. Si écart →
  400 Bad Request `[ORDER_TOTAL_MISMATCH]`.
- **BR-3** : `OrderLine.line_amount = OrderLine.quantity × OrderLine.unit_price`
  (calculé serveur, jamais accepté du client).
- **BR-4** : `OrderLine.unit_price` est **snapshoté** depuis
  `Product.current_price` au moment de l'ajout de ligne. Changement
  ultérieur de `Product.current_price` n'affecte pas les commandes
  existantes.
- **BR-5** : `OrderLine.quantity` ∈ [1, 999] entier. Si 0 ou négatif →
  400 Bad Request.
- **BR-6** : Une commande `Confirmed` est **strictement immutable** — ni
  lignes, ni client, ni total modifiables. Seule action : annulation manager.
- **BR-7** : Annulation requiert `cancellation_reason` non vide
  (1-500 caractères). Stocké pour audit.
- **BR-8** : Liste paginée par défaut 20 items, max 100. `total_count`
  retourné dans `PagedOutput`.

## Acceptance Criteria

- **AC-1** *(testable_strict)* : `POST /api/v1/orders` avec body valide
  → 201 Created + `Location: /api/v1/orders/{new_id}` + corps de
  réponse contient l'order créé avec ses lignes et `status: "Draft"`.
- **AC-2** *(testable_strict)* : `POST /api/v1/orders` avec
  `OrderLine.quantity = 0` → 400 Bad Request, message d'erreur
  référence `BR-5`.
- **AC-3** *(testable_strict)* : `POST /api/v1/orders/{id}/confirm`
  sur commande Draft cohérente (BR-2) → 200 OK, `status: "Confirmed"`,
  `confirmed_at` non-null.
- **AC-4** *(testable_strict)* : `POST /api/v1/orders/{id}/confirm`
  sur commande Draft avec écart `total_amount ≠ SUM(lines)` >
  0.01 € → 400 Bad Request `[ORDER_TOTAL_MISMATCH]`.
- **AC-5** *(testable_strict)* : `PUT /api/v1/orders/{id}` sur commande
  Confirmed → 409 Conflict (BR-6 violé).
- **AC-6** *(testable_strict)* : `POST /api/v1/orders/{id}/cancel`
  avec body `{reason: ""}` → 400 Bad Request (BR-7).
- **AC-7** *(testable_strict)* : `GET /api/v1/orders?status=Confirmed&page=2&page_size=10`
  → 200 OK, retourne max 10 items, `total_count` ≥ 10, tous
  `status: "Confirmed"`.
- **AC-8** *(testable_soft)* : modifier `Product.current_price` après
  création d'une commande qui contient ce produit ne change pas
  `OrderLine.unit_price` ni `Order.total_amount` (BR-4 snapshot).
- **AC-UI-1** *(ui_only)* : page `/orders` affiche un tableau paginé
  avec colonnes `Id`, `Client`, `Statut` (badge couleur), `Total`,
  `Créé le`, et un bouton "Nouvelle commande" en haut à droite.
- **AC-UI-2** *(ui_only)* : page `/orders/{id}` affiche les lignes
  dans un tableau avec totaux calculés ; boutons "Confirmer" (vert)
  si Draft, "Annuler" (rouge) si Confirmed, désactivés si Cancelled.
- **AC-UI-3** *(ui_only)* : formulaire de création affiche le total
  calculé en temps réel (client-side) au fur et à mesure de l'ajout
  de lignes.

## Dependencies

Aucune dépendance vers d'autres US/FEATs du projet (FEAT auto-suffisante
pour bench). Pré-requis runtime : schéma DB initialisé avec table
`customers` (seed 3 clients) ET table `products` (seed 5 produits).

## Notes bench

- **Découpage US attendu** (cible 3, pour bench) :
  - US-1 : Lecture (`GET` × 2, page liste + filtres) → AC-7, AC-UI-1
  - US-2 : Création/édition Draft (`POST`, `PUT`, lignes,
    validation cross-field) → AC-1, AC-2, AC-8, AC-UI-3
  - US-3 : Workflow statut (`confirm`, `cancel`, validation BR-2/BR-6/BR-7)
    → AC-3, AC-4, AC-5, AC-6, AC-UI-2
- **Mockups HTML** : 3 fichiers à déposer dans `workspace/input/ui/`
  selon US (un par US). Voir `.claude/templates/bench-feats/mockups/`.
- **Sketch DB** : 3 tables `orders`, `order_lines`, `products`,
  + 2 tables seed `customers` (référence externe). Foreign keys
  `order_lines.order_id → orders.id` (CASCADE), `order_lines.product_id →
  products.id` (RESTRICT).
- **Pas de Capabilities on-demand** déclenchées (pas d'excel/pdf/redis/cqrs).
  Mode CRUD étendu + workflow statut, suffisant pour stress-test `dev-*`
  sur validation cross-field et endpoints "business".

---

*Template figé. Hash de référence à enregistrer dans le rapport bench
au moment du run pour traçabilité.*
