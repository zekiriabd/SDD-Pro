"""class_role_classifier.py — Heuristic role classification for legacy classes (L0).

Answers the question the Tech Lead actually cares about during reverse
engineering: *"this class — what does it do?"* (repository / DTO / service /
code-behind / controller / complex / classic, …).

Pure, deterministic, 0-token. Consumed by `code_graph_builder.py` which parses
the raw source into `ClassInfo` records, then asks this module for the role.
Kept separate so the classification heuristics are independently unit-testable
(cf. user requirement: "récupère chaque classe, elle fait quoi").

Roles (closed enum — `ROLES`):
    code-behind   : ASP.NET / WPF / WinForms UI behind a view (Page/UserControl/Window/Form)
    controller    : MVC / Web API controller
    repository    : data-access layer (touches SQL / EF DbContext / Dapper / *Repository/*Dao)
    entity        : persisted domain entity (EF DbSet / [Table] / mapped to a DB table)
    service        : business-logic layer (*Service/*Manager/*Handler/*Provider/…)
    dto           : data-transfer / view-model / POCO (auto-properties, no behaviour)
    interface      : C# interface
    enum           : C# enum
    static-helper : static utility class (*Helper/*Utils/*Extensions)
    complex       : otherwise-classic class that is large (God-class smell)
    classic       : plain class with behaviour, none of the above

The classifier is intentionally conservative: a class that touches SQL is a
repository even if its name does not end in `Repository`, because data-access
fidelity is load-bearing for the migration target.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ROLES: frozenset[str] = frozenset({
    "code-behind", "controller", "repository", "entity", "service",
    "dto", "interface", "enum", "static-helper", "complex", "classic",
})

# A class is flagged "complex" (God-class smell) when otherwise-classic AND
# exceeds either threshold. Tunable via the two module constants.
COMPLEX_METHOD_THRESHOLD = 15
COMPLEX_LOC_THRESHOLD = 300

# Base types that mark a UI code-behind across the .NET UI stacks we target.
_CODE_BEHIND_BASES = frozenset({
    "Page", "UserControl", "MasterPage",          # ASP.NET WebForms
    "Window", "ContentPage", "PhoneApplicationPage",  # WPF / Xamarin
    "Form",                                        # WinForms
    "ComponentBase",                               # Blazor (rare in legacy)
})

_CONTROLLER_BASES = frozenset({"Controller", "ControllerBase", "ApiController"})

_DBCONTEXT_BASES = frozenset({"DbContext", "IdentityDbContext"})

# Name-suffix signatures (matched case-insensitively on the simple class name).
_SERVICE_SUFFIXES = (
    "service", "manager", "handler", "provider", "businesslogic", "bll", "bl",
    "engine", "processor", "validator", "mapper", "facade", "gateway",
    "worker", "orchestrator", "coordinator",
)
_REPOSITORY_SUFFIXES = ("repository", "repo", "dao", "dataaccess", "store", "context")
_DTO_SUFFIXES = (
    "dto", "viewmodel", "vm", "model", "request", "response", "args", "result",
    "info", "options", "settings", "config", "payload", "record", "input", "output",
)
_HELPER_SUFFIXES = ("helper", "helpers", "util", "utils", "utility", "utilities",
                    "extensions", "tools", "constants", "const")

# Regex evidence that a class performs data access (→ repository).
_SQL_TOUCH_RE = re.compile(
    r"\b(?:SqlConnection|SqlCommand|SqlDataReader|SqlDataAdapter|OracleCommand|"
    r"MySqlCommand|NpgsqlCommand|OdbcCommand|OleDbCommand|IDbConnection|IDbCommand|"
    r"DbContext|ExecuteReader|ExecuteScalar|ExecuteNonQuery|CommandText|"
    r"FromSqlRaw|ExecuteSqlRaw|BeginTransaction)\b"
    r"|\bDapper\b|\.Query<|\.QueryAsync<|\.Execute\(|\.ExecuteAsync\(",
    re.IGNORECASE,
)

# Regex evidence that a class performs outbound HTTP / API calls.
_HTTP_TOUCH_RE = re.compile(
    r"\b(?:HttpClient|WebClient|HttpWebRequest|WebRequest|RestClient|"
    r"HttpRequestMessage|RestRequest)\b"
    r"|\.GetAsync\(|\.PostAsync\(|\.PutAsync\(|\.DeleteAsync\(|\.SendAsync\(",
    re.IGNORECASE,
)


@dataclass
class ClassInfo:
    """Parsed declaration of one legacy class/interface/enum/struct/record."""

    name: str
    kind: str                       # class | interface | enum | struct | record
    file: str                       # path relative to project root, posix
    namespace: str = ""
    base_types: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)
    is_static: bool = False
    is_partial: bool = False
    is_abstract: bool = False
    method_count: int = 0
    property_count: int = 0
    loc_total: int = 0
    line_start: int = 0
    line_end: int = 0
    touches_sql: bool = False
    touches_http: bool = False
    # references[] = simple names of OTHER project classes referenced in this
    # class body (populated by code_graph_builder, not by parsing alone).
    references: list[str] = field(default_factory=list)
    role: str = "classic"
    # transient — class body text, used for SQL/HTTP detection & references;
    # never serialized to code-graph.json.
    _body: str = ""

    def to_public_dict(self) -> dict:
        """Serializable view (excludes transient `_body`)."""
        return {
            "name": self.name,
            "kind": self.kind,
            "role": self.role,
            "file": self.file,
            "namespace": self.namespace,
            "baseTypes": self.base_types,
            "attributes": self.attributes,
            "isStatic": self.is_static,
            "isPartial": self.is_partial,
            "isAbstract": self.is_abstract,
            "methodCount": self.method_count,
            "propertyCount": self.property_count,
            "locTotal": self.loc_total,
            "lines": f"{self.line_start}-{self.line_end}",
            "touchesSql": self.touches_sql,
            "touchesHttp": self.touches_http,
            "references": sorted(set(self.references)),
        }


def _name_ends_with_any(name: str, suffixes: tuple[str, ...]) -> bool:
    low = name.lower()
    return any(low.endswith(s) for s in suffixes)


def _has_attribute(attributes: list[str], *needles: str) -> bool:
    blob = " ".join(attributes).lower()
    return any(n.lower() in blob for n in needles)


def classify_role(ci: ClassInfo, known_entity_names: frozenset[str] | None = None) -> str:
    """Return the role of `ci` (one of ROLES). First match wins.

    `known_entity_names` (optional) lets the caller inject the entity names
    discovered by `db_schema_extractor` so a class matching a DB table is
    tagged `entity` even without an explicit `[Table]` attribute.
    """
    known_entity_names = known_entity_names or frozenset()

    if ci.kind == "interface":
        return "interface"
    if ci.kind == "enum":
        return "enum"

    base_set = set(ci.base_types)

    # 1. UI code-behind — strongest signal (base type or filename convention).
    if base_set & _CODE_BEHIND_BASES or _is_code_behind_file(ci.file):
        return "code-behind"

    # 2. MVC / Web API controller.
    if (
        base_set & _CONTROLLER_BASES
        or ci.name.endswith("Controller")
        or _has_attribute(ci.attributes, "ApiController", "Route")
    ):
        return "controller"

    # 3. Repository / data-access — name OR behavioural SQL evidence.
    if (
        ci.touches_sql
        or base_set & _DBCONTEXT_BASES
        or _name_ends_with_any(ci.name, _REPOSITORY_SUFFIXES)
    ):
        # A DbContext subclass that is mostly DbSet<> is still a repository-ish
        # gateway; entities are the DbSet<T> generic args, handled elsewhere.
        return "repository"

    # 4. Persisted entity.
    if (
        ci.name in known_entity_names
        or _has_attribute(ci.attributes, "Table", "Entity")
    ):
        return "entity"

    # 5. Business-logic service layer.
    if _name_ends_with_any(ci.name, _SERVICE_SUFFIXES):
        return "service"

    # 6. Static utility helper.
    if ci.is_static and _name_ends_with_any(ci.name, _HELPER_SUFFIXES):
        return "static-helper"

    # 7. DTO / POCO — by name suffix OR shape (properties, ~no methods).
    if _name_ends_with_any(ci.name, _DTO_SUFFIXES) or (
        ci.property_count > 0 and ci.method_count == 0
    ):
        return "dto"

    # 8. Complex (God-class) — otherwise-classic but oversized.
    if (
        ci.method_count >= COMPLEX_METHOD_THRESHOLD
        or ci.loc_total >= COMPLEX_LOC_THRESHOLD
    ):
        return "complex"

    # 9. Remaining static class with no helper suffix.
    if ci.is_static:
        return "static-helper"

    return "classic"


def _is_code_behind_file(file_rel: str) -> bool:
    low = file_rel.lower()
    return low.endswith((
        ".aspx.cs", ".ascx.cs", ".master.cs", ".aspx.vb", ".ascx.vb",
        ".xaml.cs", ".xaml.vb",
    ))


def detect_touches_sql(body: str) -> bool:
    return bool(_SQL_TOUCH_RE.search(body))


def detect_touches_http(body: str) -> bool:
    return bool(_HTTP_TOUCH_RE.search(body))
