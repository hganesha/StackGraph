from __future__ import annotations

import json
import re
import socket
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen

from stackgraph_data.catalog import canonical_json, sha256_key


JsonObject = dict[str, Any]
SUPPORTED_SYSTEMS = {"NPM": "npm", "PYPI": "pypi"}
SYSTEM_BY_PURL_TYPE = {value: key for key, value in SUPPORTED_SYSTEMS.items()}
PYPI_NORMALIZE = re.compile(r"[-_.]+")


@dataclass(frozen=True, slots=True)
class PackageVersionKey:
    system: str
    name: str
    version: str

    @property
    def ecosystem(self) -> str:
        return SUPPORTED_SYSTEMS[self.system]

    @property
    def package_purl(self) -> str:
        return f"pkg:{self.ecosystem}/{_encode_name(self.system, self.name)}"

    @property
    def purl(self) -> str:
        encoded_version = quote(self.version, safe=".-_~+")
        return f"{self.package_purl}@{encoded_version}"

    @property
    def display_name(self) -> str:
        return f"{self.name}@{self.version}"

    @classmethod
    def from_purl(cls, value: str) -> PackageVersionKey:
        if "?" in value or "#" in value:
            raise ValueError("deps.dev targets cannot include purl qualifiers or subpaths")
        if not value.startswith("pkg:"):
            raise ValueError("package version must be a purl")
        purl_type, separator, coordinates = value[4:].partition("/")
        system = SYSTEM_BY_PURL_TYPE.get(purl_type.lower())
        if not separator or system is None:
            raise ValueError("only npm and PyPI package-version purls are supported")
        encoded_name, version_separator, encoded_version = coordinates.rpartition("@")
        if not version_separator or not encoded_name or not encoded_version:
            raise ValueError("purl must identify an exact package version")
        name = unquote(encoded_name)
        version = unquote(encoded_version)
        return cls.from_version_key(
            {"system": system, "name": name, "version": version}
        )

    @classmethod
    def from_version_key(cls, value: Mapping[str, object]) -> PackageVersionKey:
        system = value.get("system")
        name = value.get("name")
        version = value.get("version")
        if system not in SUPPORTED_SYSTEMS:
            raise ValueError(f"unsupported deps.dev package system: {system!r}")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("deps.dev version key has no package name")
        if not isinstance(version, str) or not version.strip():
            raise ValueError("deps.dev version key has no package version")

        normalized_name = name.strip()
        if system == "NPM":
            normalized_name = normalized_name.lower()
            if normalized_name.startswith("@"):
                if normalized_name.count("/") != 1:
                    raise ValueError("scoped npm package name must use @scope/name")
            elif "/" in normalized_name:
                raise ValueError("unscoped npm package name cannot contain a slash")
        elif system == "PYPI":
            if "/" in normalized_name:
                raise ValueError("PyPI package name cannot contain a slash")
            normalized_name = PYPI_NORMALIZE.sub("-", normalized_name).lower()
        return cls(system=system, name=normalized_name, version=version.strip())


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class HttpTransport(Protocol):
    def request(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse: ...


class UrlLibTransport:
    def request(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        request = Request(url, headers=dict(headers), method="GET")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return HttpResponse(
                    status=response.status,
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except HTTPError as error:
            return HttpResponse(
                status=error.code,
                headers=dict(error.headers.items()) if error.headers else {},
                body=error.read(),
            )
        except (URLError, TimeoutError, socket.timeout) as error:
            reason = getattr(error, "reason", error)
            raise DepsDevTransportError(f"deps.dev request failed: {reason}") from error


class DepsDevTransportError(RuntimeError):
    pass


class DepsDevApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        retriable: bool,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retriable = retriable
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True, slots=True)
class DepsDevBundle:
    requested: PackageVersionKey
    version: JsonObject
    dependencies: JsonObject
    version_uri: str
    dependencies_uri: str

    def as_dict(self) -> JsonObject:
        return {
            "api_version": "v3",
            "requested_purl": self.requested.purl,
            "version_uri": self.version_uri,
            "dependencies_uri": self.dependencies_uri,
            "version": self.version,
            "dependencies": self.dependencies,
        }


class DepsDevClient:
    def __init__(
        self,
        *,
        base_url: str = "https://api.deps.dev",
        timeout_seconds: float = 20.0,
        max_response_bytes: int = 16 * 1024 * 1024,
        transport: HttpTransport | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("deps.dev base URL must be credential-free HTTPS")
        if timeout_seconds <= 0 or max_response_bytes <= 0:
            raise ValueError("deps.dev client limits must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.transport = transport or UrlLibTransport()

    def fetch(self, target: PackageVersionKey) -> DepsDevBundle:
        system = target.system.lower()
        name = quote(target.name, safe="")
        version = quote(target.version, safe="")
        base_path = f"/v3/systems/{system}/packages/{name}/versions/{version}"
        version_uri = f"{self.base_url}{base_path}"
        dependencies_uri = f"{version_uri}:dependencies"
        return DepsDevBundle(
            requested=target,
            version=self._get_json(version_uri),
            dependencies=self._get_json(dependencies_uri),
            version_uri=version_uri,
            dependencies_uri=dependencies_uri,
        )

    def _get_json(self, url: str) -> JsonObject:
        response = self.transport.request(
            url,
            {
                "Accept": "application/json",
                "User-Agent": "StackGraph-deps-dev/1.0",
            },
            self.timeout_seconds,
        )
        headers = {key.lower(): value for key, value in response.headers.items()}
        if response.status < 200 or response.status >= 300:
            retry_after = _optional_int(headers.get("retry-after"))
            message = f"deps.dev request failed with status {response.status}"
            try:
                error_body = json.loads(response.body)
                if isinstance(error_body, dict) and isinstance(
                    error_body.get("message"), str
                ):
                    message = f"{message}: {error_body['message']}"
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            raise DepsDevApiError(
                message,
                status_code=response.status,
                retriable=response.status == 429 or response.status >= 500,
                retry_after_seconds=retry_after,
            )
        if len(response.body) > self.max_response_bytes:
            raise ValueError("deps.dev response exceeds max_response_bytes")
        try:
            document = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("deps.dev returned invalid JSON") from error
        if not isinstance(document, dict):
            raise ValueError("deps.dev returned an unexpected JSON document")
        return document


@dataclass(frozen=True, slots=True)
class DependencyNode:
    source_index: int
    key: PackageVersionKey
    relation: str
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    source_index: int
    from_key: PackageVersionKey
    to_key: PackageVersionKey
    requirement: str
    relation: str


@dataclass(frozen=True, slots=True)
class NormalizedEnrichment:
    requested: PackageVersionKey
    root: PackageVersionKey
    root_properties: JsonObject
    nodes: tuple[DependencyNode, ...]
    edges: tuple[DependencyEdge, ...]
    completeness: str
    limitations: tuple[JsonObject, ...]
    raw_bundle: JsonObject

    @property
    def source_revision(self) -> str:
        import hashlib

        content = canonical_json(self.raw_bundle).encode("utf-8")
        return f"sha256:{hashlib.sha256(content).hexdigest()}"


@dataclass(frozen=True, slots=True)
class FactSpec:
    subject: PackageVersionKey
    predicate: str
    object_entity: PackageVersionKey | None
    object_value: dict[str, Any] | None
    properties: dict[str, Any]
    logical_key: str
    evidence_pointer: str
    evidence_uri: str
    evidence_hash: str
    effective_from: str | None = None


def normalize_bundle(
    bundle: DepsDevBundle,
    *,
    max_nodes: int = 1_000,
    max_edges: int = 5_000,
) -> NormalizedEnrichment:
    if max_nodes <= 0 or max_edges <= 0:
        raise ValueError("dependency graph limits must be positive")
    root_key = PackageVersionKey.from_version_key(
        _required_object(bundle.version, "versionKey")
    )
    graph_nodes = bundle.dependencies.get("nodes")
    graph_edges = bundle.dependencies.get("edges")
    if not isinstance(graph_nodes, list) or not graph_nodes:
        raise ValueError("deps.dev dependency graph has no root node")
    if not isinstance(graph_edges, list):
        raise ValueError("deps.dev dependency graph has invalid edges")

    graph_root = _node_key(graph_nodes[0])
    if graph_root != root_key:
        raise ValueError("deps.dev version and dependency root identities disagree")

    limitations: list[JsonObject] = []
    nodes: list[DependencyNode] = []
    included: dict[int, DependencyNode] = {}
    for index, raw_node in enumerate(graph_nodes):
        if len(nodes) >= max_nodes:
            _add_limitation(
                limitations,
                "NODE_BUDGET",
                f"dependency graph exceeds max_nodes={max_nodes}",
            )
            break
        if not isinstance(raw_node, dict):
            _add_limitation(limitations, "INVALID_NODE", f"node {index} is invalid")
            continue
        if raw_node.get("bundled") is True:
            _add_limitation(
                limitations,
                "BUNDLED_DEPENDENCY_SKIPPED",
                "bundled dependencies are not treated as global package identities",
            )
            continue
        try:
            key = _node_key(raw_node)
        except ValueError as error:
            _add_limitation(limitations, "UNSUPPORTED_NODE", str(error))
            continue
        if key.system != root_key.system:
            _add_limitation(
                limitations,
                "CROSS_SYSTEM_NODE_SKIPPED",
                "dependency node belongs to a different package ecosystem",
            )
            continue
        relation = raw_node.get("relation", "SELF" if index == 0 else "INDIRECT")
        if relation not in {"SELF", "DIRECT", "INDIRECT"}:
            relation = "INDIRECT"
            _add_limitation(
                limitations,
                "UNKNOWN_RELATION",
                f"node {index} has an unknown dependency relation",
            )
        errors = raw_node.get("errors", [])
        if not isinstance(errors, list) or not all(isinstance(item, str) for item in errors):
            raise ValueError(f"deps.dev node {index} has invalid errors")
        if errors:
            _add_limitation(
                limitations,
                "NODE_ERRORS",
                "deps.dev reported one or more dependency-node errors",
            )
        node = DependencyNode(index, key, relation, tuple(errors))
        nodes.append(node)
        included[index] = node

    edges: list[DependencyEdge] = []
    for index, raw_edge in enumerate(graph_edges):
        if len(edges) >= max_edges:
            _add_limitation(
                limitations,
                "EDGE_BUDGET",
                f"dependency graph exceeds max_edges={max_edges}",
            )
            break
        if not isinstance(raw_edge, dict):
            _add_limitation(limitations, "INVALID_EDGE", f"edge {index} is invalid")
            continue
        from_index = raw_edge.get("fromNode")
        to_index = raw_edge.get("toNode")
        if not isinstance(from_index, int) or not isinstance(to_index, int):
            _add_limitation(
                limitations,
                "INVALID_EDGE",
                f"edge {index} has invalid node indexes",
            )
            continue
        if from_index not in included or to_index not in included:
            _add_limitation(
                limitations,
                "EDGE_ENDPOINT_SKIPPED",
                "one or more edges reference excluded dependency nodes",
            )
            continue
        requirement = raw_edge.get("requirement", "")
        if not isinstance(requirement, str):
            requirement = str(requirement)
        edges.append(
            DependencyEdge(
                source_index=index,
                from_key=included[from_index].key,
                to_key=included[to_index].key,
                requirement=requirement,
                relation=included[to_index].relation,
            )
        )

    graph_error = bundle.dependencies.get("error")
    if isinstance(graph_error, str) and graph_error:
        _add_limitation(
            limitations,
            "GRAPH_ERROR",
            "deps.dev reported a dependency graph error",
        )

    root_properties = {
        "ecosystem": root_key.ecosystem,
        "package_name": root_key.name,
        "version": root_key.version,
        "published_at": bundle.version.get("publishedAt"),
        "is_default": bool(bundle.version.get("isDefault", False)),
        "is_deprecated": bool(bundle.version.get("isDeprecated", False)),
        "deprecated_reason": bundle.version.get("deprecatedReason"),
        "licenses": _string_list(bundle.version.get("licenses")),
        "advisory_ids": _advisory_ids(bundle.version.get("advisoryKeys")),
        "links": _safe_object_list(bundle.version.get("links")),
        "registries": _string_list(bundle.version.get("registries")),
        "related_projects": _safe_object_list(bundle.version.get("relatedProjects")),
        "project_status": (
            bundle.version.get("projectStatus")
            if isinstance(bundle.version.get("projectStatus"), dict)
            else None
        ),
    }
    return NormalizedEnrichment(
        requested=bundle.requested,
        root=root_key,
        root_properties=root_properties,
        nodes=tuple(nodes),
        edges=tuple(edges),
        completeness="PARTIAL" if limitations else "COMPLETE",
        limitations=tuple(limitations),
        raw_bundle=bundle.as_dict(),
    )


def build_fact_specs(enrichment: NormalizedEnrichment) -> tuple[FactSpec, ...]:
    specs: list[FactSpec] = []
    published_at = enrichment.root_properties.get("published_at")
    specs.append(
        FactSpec(
            subject=enrichment.root,
            predicate="HAS_PROPERTY",
            object_entity=None,
            object_value={
                "record_kind": "deps_dev_version_metadata",
                **enrichment.root_properties,
            },
            properties={
                "provider": "deps.dev",
                "record_kind": "DEPS_DEV_VERSION_METADATA",
                "limitations": list(enrichment.limitations),
            },
            logical_key=sha256_key(
                "global", enrichment.root.purl, "HAS_PROPERTY", "deps.dev"
            ),
            evidence_pointer="",
            evidence_uri=str(enrichment.raw_bundle["version_uri"]),
            evidence_hash=sha256_key(enrichment.raw_bundle["version"]),
            effective_from=published_at if isinstance(published_at, str) else None,
        )
    )
    seen_memberships: set[str] = set()
    for node in enrichment.nodes:
        if node.key.purl in seen_memberships:
            continue
        seen_memberships.add(node.key.purl)
        specs.append(
            FactSpec(
                subject=node.key,
                predicate="HAS_VERSION",
                object_entity=node.key,
                object_value=None,
                properties={
                    "provider": "deps.dev",
                    "record_kind": "PACKAGE_VERSION_MEMBERSHIP",
                },
                logical_key=sha256_key(
                    "global", node.key.package_purl, "HAS_VERSION", node.key.purl
                ),
                evidence_pointer=f"/nodes/{node.source_index}",
                evidence_uri=str(enrichment.raw_bundle["dependencies_uri"]),
                evidence_hash=sha256_key(
                    enrichment.raw_bundle["dependencies"]["nodes"][node.source_index]
                ),
            )
        )
    dependencies_uri = str(enrichment.raw_bundle["dependencies_uri"])
    for edge in enrichment.edges:
        specs.append(
            _dependency_fact(
                edge,
                enrichment.root.purl,
                dependencies_uri,
                sha256_key(
                    enrichment.raw_bundle["dependencies"]["edges"][edge.source_index]
                ),
            )
        )
    return tuple(specs)


def _dependency_fact(
    edge: DependencyEdge,
    graph_root_purl: str,
    dependencies_uri: str,
    evidence_hash: str,
) -> FactSpec:
    return FactSpec(
        subject=edge.from_key,
        predicate="DEPENDS_ON",
        object_entity=edge.to_key,
        object_value=None,
        properties={
            "provider": "deps.dev",
            "record_kind": "RESOLVED_DEPENDENCY",
            "requirement": edge.requirement,
            "dependency_relation": edge.relation,
            "graph_root_purl": graph_root_purl,
            "resolution_environment": "generic-64-bit-linux",
        },
        logical_key=sha256_key(
            "global",
            edge.from_key.purl,
            "DEPENDS_ON",
            edge.to_key.purl,
            edge.requirement,
            graph_root_purl,
        ),
        evidence_pointer=f"/edges/{edge.source_index}",
        evidence_uri=dependencies_uri,
        evidence_hash=evidence_hash,
    )


def _encode_name(system: str, name: str) -> str:
    safe = "/" if system == "NPM" else ""
    return quote(name, safe=safe)


def _node_key(value: object) -> PackageVersionKey:
    if not isinstance(value, dict):
        raise ValueError("deps.dev dependency node is invalid")
    return PackageVersionKey.from_version_key(_required_object(value, "versionKey"))


def _required_object(value: Mapping[str, object], key: str) -> JsonObject:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"deps.dev response has no valid {key}")
    return item


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _safe_object_list(value: object) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _advisory_ids(value: object) -> list[str]:
    return [
        str(item["id"])
        for item in _safe_object_list(value)
        if isinstance(item.get("id"), str)
    ]


def _add_limitation(limitations: list[JsonObject], code: str, message: str) -> None:
    if any(item["code"] == code for item in limitations):
        return
    limitations.append({"code": code, "message": message})


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
