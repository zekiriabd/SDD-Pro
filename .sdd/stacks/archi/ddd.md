# ARCHI_DDD

Status: Experimental
Validation: 🟡 experimental (réactivé 2026-05-20, PoC formel pending — cf. `docs/validated-combos.md §3`)
Support: ⚠ Non supporté commercialement (audit C3, 2026-06-06) — exclu du SLA produit. Voir CLAUDE.md §6 et docs/validated-combos.md.
Pattern ID: archi-ddd
Scope: **pattern d'architecture backend** — Domain-Driven Design layered (Domain → Application → Infrastructure → Interface). S'applique aux stacks `backend/*.md` lorsque `ArchiPattern: DDD`. Ne s'applique PAS aux `fullstack/*` ni aux `mobiles/*`.

META:
  type: architecture-pattern
  id: archi-ddd
  status: draft
  validation: experimental
  scope: backend-only
  allowed-app-types: backend
  forbidden-app-types: fullstack, mobile

VERSION:
  spec: SDD_Pro_v6.7.6+

---

# RULESET_CORE

DOMAIN_RULES:
  - DOMAIN_HAS_NO_EXTERNAL_DEPENDENCIES: true
  - DOMAIN_CONTAINS_BUSINESS_LOGIC: true
  - DOMAIN_CONTAINS_INVARIANTS: true
  - DOMAIN_MUST_NOT_IMPORT:
      - infrastructure
      - orm
      - framework
      - http
      - controller

APPLICATION_RULES:
  - APPLICATION_IS_ORCHESTRATION_ONLY: true
  - APPLICATION_HAS_NO_BUSINESS_RULES: true
  - APPLICATION_USES_DOMAIN: true
  - APPLICATION_CAN_USE_REPOSITORY_INTERFACES: true

INFRASTRUCTURE_RULES:
  - INFRASTRUCTURE_DEPENDS_ON_DOMAIN: true
  - INFRASTRUCTURE_DEPENDS_ON_APPLICATION: true
  - INFRASTRUCTURE_MUST_IMPLEMENT_REPOSITORIES: true
  - INFRASTRUCTURE_CONTAINS_ORM: true

PRESENTATION_RULES:
  - PRESENTATION_IS_TRANSPORT_LAYER_ONLY: true
  - PRESENTATION_MUST_NOT_CONTAIN_BUSINESS_LOGIC: true
  - PRESENTATION_DEPENDS_ON_APPLICATION_ONLY: true

---

# ARCHITECTURE_LAYERS

LAYERS_ORDER:
  - Presentation
  - Application
  - Domain
  - Infrastructure

DEPENDENCY_DIRECTION:
  Presentation -> Application
  Application -> Domain
  Infrastructure -> Domain
  Infrastructure -> Application (optional ports)

DOMAIN_IS_ROOT: true

---

# DOMAIN_MODEL

DOMAIN_COMPONENTS:
  Entity:
    immutable_identity: true
    contains_behavior: true

  ValueObject:
    immutable: true
    equality_by_value: true
    no_identity: true

  Aggregate:
    enforces_invariants: true
    transaction_boundary: true
    accessed_via_root_only: true

  AggregateRoot:
    entry_point: true
    controls_mutations: true

  DomainEvent:
    immutable: true
    past_tense_naming: true
    emitted_after_commit: true

  DomainService:
    allowed_only_if_no_entity_fit: true
    stateless: true

  RepositoryInterface:
    defined_in_domain: true
    implemented_in_infrastructure: true

---

# APPLICATION_MODEL

APPLICATION_COMPONENTS:
  UseCase:
    type: command_or_query_handler
    contains_orchestration_only: true
    no_business_logic: true

  Command:
    mutation_intent: true
    immutable: true

  Query:
    read_intent: true
    immutable: true

  DTO:
    cross_layer_transfer: true

  EventHandler:
    reacts_to_domain_events: true
    no_business_logic: true

TRANSACTION_BOUNDARY:
  defined_in_application: true

---

# INFRASTRUCTURE_MODEL

INFRASTRUCTURE_COMPONENTS:
  RepositoryImplementation:
    implements_domain_interface: true

  PersistenceModel:
    distinct_from_domain: true
    orm_mapped: true

  Mapper:
    domain_to_persistence: true
    persistence_to_domain: true

  ExternalAdapter:
    wraps_external_systems: true

  Outbox:
    optional: true
    guarantees_event_delivery: true

---

# PRESENTATION_MODEL

PRESENTATION_COMPONENTS:
  Controller:
    no_business_logic: true
    maps_http_to_application: true

  Validator:
    input_validation_only: true

  ViewModel:
    response_contract: true

---

# INVARIANTS

INVARIANT_RULES:
  - ONE_AGGREGATE_ONE_TRANSACTION: true
  - CROSS_AGGREGATE_REFERENCE_BY_ID_ONLY: true
  - AGGREGATE_ROOT_ONLY_MUTATES_STATE: true
  - VALUE_OBJECTS_ARE_IMMUTABLE: true
  - DOMAIN_EVENTS_ARE_PUBLISHED_AFTER_COMMIT: true

---

# ANTI_PATTERNS

FORBIDDEN:
  - ANEMIC_DOMAIN_MODEL: true
  - BUSINESS_LOGIC_IN_APPLICATION_LAYER: true
  - ORM_IN_DOMAIN: true
  - GENERIC_REPOSITORY_CRUD_ONLY: true
  - CROSS_AGGREGATE_OBJECT_REFERENCES: true
  - MUTABLE_VALUE_OBJECTS: true
  - DOMAIN_DEPENDS_ON_INFRASTRUCTURE: true

---

# NAMING_CONVENTIONS

PATTERNS:
  AggregateRoot: PascalCase_Singular
  Entity: PascalCase_Singular
  ValueObject: PascalCase_Singular
  DomainEvent: PastTenseVerb + Aggregate
  Command: Verb + Aggregate + Command
  Query: Get + Aggregate + Query
  Handler: Action + Aggregate + Handler
  Repository: I + Aggregate + Repository

FORBIDDEN_SUFFIXES:
  - Manager
  - Helper
  - Util
  - Impl

---

# DEPENDENCY_MATRIX

ALLOWED_IMPORTS:
  Domain:
    - NONE_EXTERNAL_ONLY_STD

  Application:
    - Domain

  Infrastructure:
    - Domain
    - Application

  Presentation:
    - Application

FORBIDDEN_IMPORTS:
  Domain:
    - ANY_OTHER_LAYER

---

# VALIDATION_OUTPUT

RULE_ENGINE_EXPECTED_OUTPUT:
  status: PASS | FAIL
  violations:
    - rule_id
    - severity: critical | major | minor
    - file_path
    - message
