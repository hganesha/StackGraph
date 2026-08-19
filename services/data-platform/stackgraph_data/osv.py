from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from stackgraph_data.catalog import canonical_json, sha256_key
from stackgraph_data.depsdev import PackageVersionKey


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> HttpResponse: ...


class UrlLibTransport:
    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> HttpResponse:
        request = Request(url, headers=dict(headers), data=body, method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                payload = response.read(max_response_bytes + 1)
                return HttpResponse(
                    status=response.status,
                    headers=dict(response.headers.items()),
                    body=payload,
                )
        except HTTPError as error:
            payload = error.read(max_response_bytes + 1)
            return HttpResponse(
                status=error.code,
                headers=dict(error.headers.items()) if error.headers else {},
                body=payload,
            )
        except (URLError, TimeoutError, socket.timeout) as error:
            reason = getattr(error, "reason", error)
            raise OsvTransportError(f"OSV request failed: {reason}") from error


class OsvTransportError(RuntimeError):
    pass


class OsvApiError(RuntimeError):
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
class VulnerabilityRef:
    osv_id: str
    modified: str | None


@dataclass(frozen=True, slots=True)
class QueryPage:
    request_query: JsonObject
    result: JsonObject

    def as_dict(self) -> JsonObject:
        return {
            "request": {"queries": [self.request_query]},
            "result": self.result,
        }


@dataclass(frozen=True, slots=True)
class QueryResult:
    target: PackageVersionKey
    vulnerabilities: tuple[VulnerabilityRef, ...]
    pages: tuple[QueryPage, ...]
    truncated: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OsvBundle:
    target: PackageVersionKey
    query: QueryResult
    vulnerability_documents: tuple[JsonObject, ...]
    query_uri: str
    detail_uris: tuple[str, ...]

    def as_dict(self) -> JsonObject:
        return {
            "api_version": "v1",
            "normalizer_contract": "osv-enrichment-v1",
            "target_purl": self.target.purl,
            "query_uri": self.query_uri,
            "query_pages": [page.as_dict() for page in self.query.pages],
            "vulnerabilities": list(self.vulnerability_documents),
            "detail_uris": list(self.detail_uris),
        }


class OsvClient:
    def __init__(
        self,
        *,
        base_url: str = "https://api.osv.dev",
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
            raise ValueError("OSV base URL must be credential-free HTTPS")
        if timeout_seconds <= 0 or max_response_bytes <= 0:
            raise ValueError("OSV client limits must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.transport = transport or UrlLibTransport()

    @property
    def query_uri(self) -> str:
        return f"{self.base_url}/v1/querybatch"

    def query_batch(
        self,
        targets: Sequence[PackageVersionKey],
        *,
        max_pages: int = 10,
        max_vulnerabilities: int = 1_000,
    ) -> tuple[QueryResult, ...]:
        if not targets:
            return ()
        if max_pages <= 0 or max_vulnerabilities <= 0:
            raise ValueError("OSV query limits must be positive")

        pages: list[list[QueryPage]] = [[] for _ in targets]
        refs: list[list[VulnerabilityRef]] = [[] for _ in targets]
        seen: list[set[str]] = [set() for _ in targets]
        truncated = [False for _ in targets]
        errors: list[list[str]] = [[] for _ in targets]
        pending: list[tuple[int, str | None]] = [
            (index, None) for index in range(len(targets))
        ]

        while pending:
            request_queries = [
                _query_for_target(targets[index], page_token)
                for index, page_token in pending
            ]
            response = self._request_json(
                "POST",
                self.query_uri,
                {"queries": request_queries},
            )
            results = response.get("results")
            if not isinstance(results, list) or len(results) != len(pending):
                raise ValueError("OSV batch response does not align with its queries")

            next_pending: list[tuple[int, str | None]] = []
            for position, ((target_index, _), request_query) in enumerate(
                zip(pending, request_queries, strict=True)
            ):
                raw_result = results[position]
                if not isinstance(raw_result, dict):
                    raise ValueError("OSV batch result is not an object")
                pages[target_index].append(QueryPage(request_query, raw_result))
                raw_error = raw_result.get("error")
                if raw_error is not None:
                    errors[target_index].append(
                        raw_error
                        if isinstance(raw_error, str)
                        else canonical_json(raw_error)
                    )
                raw_vulns = raw_result.get("vulns", [])
                if not isinstance(raw_vulns, list):
                    raise ValueError("OSV batch result has invalid vulnerabilities")
                for raw_ref in raw_vulns:
                    ref = _vulnerability_ref(raw_ref)
                    if ref.osv_id in seen[target_index]:
                        continue
                    if len(refs[target_index]) >= max_vulnerabilities:
                        truncated[target_index] = True
                        break
                    refs[target_index].append(ref)
                    seen[target_index].add(ref.osv_id)

                next_token = raw_result.get("next_page_token")
                if next_token is not None and not isinstance(next_token, str):
                    raise ValueError("OSV batch result has an invalid page token")
                if next_token:
                    if (
                        len(pages[target_index]) >= max_pages
                        or len(refs[target_index]) >= max_vulnerabilities
                    ):
                        truncated[target_index] = True
                    else:
                        next_pending.append((target_index, next_token))
            pending = next_pending

        return tuple(
            QueryResult(
                target=target,
                vulnerabilities=tuple(refs[index]),
                pages=tuple(pages[index]),
                truncated=truncated[index],
                errors=tuple(errors[index]),
            )
            for index, target in enumerate(targets)
        )

    def fetch_vulnerability(self, osv_id: str) -> tuple[JsonObject, str]:
        if not osv_id or "/" in osv_id:
            raise ValueError("OSV vulnerability ID is invalid")
        uri = f"{self.base_url}/v1/vulns/{quote(osv_id, safe='')}"
        document = self._request_json("GET", uri, None)
        if document.get("id") != osv_id:
            raise ValueError("OSV vulnerability detail identity does not match")
        return document, uri

    def _request_json(
        self,
        method: str,
        url: str,
        payload: JsonObject | None,
    ) -> JsonObject:
        body = canonical_json(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Accept": "application/json",
            "User-Agent": "StackGraph-OSV/1.0",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        response = self.transport.request(
            method,
            url,
            headers,
            body,
            self.timeout_seconds,
            self.max_response_bytes,
        )
        response_headers = {
            key.lower(): value for key, value in response.headers.items()
        }
        if len(response.body) > self.max_response_bytes:
            raise ValueError("OSV response exceeds max_response_bytes")
        if response.status < 200 or response.status >= 300:
            retry_after = _optional_int(response_headers.get("retry-after"))
            message = f"OSV request failed with status {response.status}"
            try:
                error_body = json.loads(response.body)
                if isinstance(error_body, dict):
                    detail = error_body.get("message") or error_body.get("error")
                    if isinstance(detail, str):
                        message = f"{message}: {detail}"
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            raise OsvApiError(
                message,
                status_code=response.status,
                retriable=response.status == 429 or response.status >= 500,
                retry_after_seconds=retry_after,
            )
        try:
            document = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("OSV returned invalid JSON") from error
        if not isinstance(document, dict):
            raise ValueError("OSV returned an unexpected JSON document")
        return document


@dataclass(frozen=True, slots=True)
class VulnerabilityRecord:
    osv_id: str
    aliases: tuple[str, ...]
    summary: str
    published: str | None
    modified: str
    withdrawn: str | None
    severity: tuple[JsonObject, ...]
    affected: tuple[JsonObject, ...]
    references: tuple[JsonObject, ...]
    raw: JsonObject
    detail_uri: str


@dataclass(frozen=True, slots=True)
class OsvEnrichment:
    target: PackageVersionKey
    vulnerabilities: tuple[VulnerabilityRecord, ...]
    completeness: str
    limitations: tuple[JsonObject, ...]
    raw_bundle: JsonObject

    @property
    def source_revision(self) -> str:
        return sha256_key(self.raw_bundle)


@dataclass(frozen=True, slots=True)
class EvidenceSpec:
    locator: JsonObject
    excerpt_hash: str
    metadata: JsonObject


@dataclass(frozen=True, slots=True)
class FactSpec:
    vulnerability: VulnerabilityRecord
    properties: JsonObject
    logical_key: str
    evidence: tuple[EvidenceSpec, ...]
    effective_from: str | None


def normalize_bundle(
    bundle: OsvBundle,
    *,
    max_vulnerabilities: int = 100,
) -> OsvEnrichment:
    if max_vulnerabilities <= 0:
        raise ValueError("max_vulnerabilities must be positive")
    document_by_id: dict[str, tuple[JsonObject, str]] = {}
    for document, uri in zip(
        bundle.vulnerability_documents,
        bundle.detail_uris,
        strict=True,
    ):
        osv_id = document.get("id")
        if not isinstance(osv_id, str) or not osv_id:
            raise ValueError("OSV vulnerability detail has no ID")
        document_by_id[osv_id] = (document, uri)

    limitations: list[JsonObject] = []
    if bundle.query.errors:
        limitations.append(
            {
                "code": "QUERY_ERROR",
                "message": "OSV reported an error for this package-version query",
                "errors": list(bundle.query.errors),
            }
        )
    selected_refs = bundle.query.vulnerabilities[:max_vulnerabilities]
    if bundle.query.truncated or len(bundle.query.vulnerabilities) > max_vulnerabilities:
        limitations.append(
            {
                "code": "VULNERABILITY_BUDGET",
                "message": (
                    "OSV results exceeded the configured vulnerability or page budget"
                ),
            }
        )

    records: list[VulnerabilityRecord] = []
    for ref in selected_refs:
        detail = document_by_id.get(ref.osv_id)
        if detail is None:
            raise ValueError(f"OSV detail is missing for {ref.osv_id}")
        document, detail_uri = detail
        modified = document.get("modified")
        if not isinstance(modified, str) or not modified:
            raise ValueError(f"OSV vulnerability {ref.osv_id} has no modified time")
        summary = document.get("summary")
        aliases = _string_tuple(document.get("aliases"))
        matching_affected = tuple(
            item
            for item in _object_tuple(document.get("affected"))
            if _affected_matches(item, bundle.target)
        )
        if not matching_affected:
            limitations.append(
                {
                    "code": "AFFECTED_PACKAGE_MISMATCH",
                    "message": (
                        f"OSV record {ref.osv_id} did not contain the queried package"
                    ),
                }
            )
        records.append(
            VulnerabilityRecord(
                osv_id=ref.osv_id,
                aliases=aliases,
                summary=summary if isinstance(summary, str) else ref.osv_id,
                published=_optional_string(document.get("published")),
                modified=modified,
                withdrawn=_optional_string(document.get("withdrawn")),
                severity=_object_tuple(document.get("severity")),
                affected=matching_affected,
                references=_object_tuple(document.get("references")),
                raw=document,
                detail_uri=detail_uri,
            )
        )

    return OsvEnrichment(
        target=bundle.target,
        vulnerabilities=tuple(records),
        completeness="PARTIAL" if limitations else "COMPLETE",
        limitations=tuple(limitations),
        raw_bundle=bundle.as_dict(),
    )


def build_fact_specs(enrichment: OsvEnrichment) -> tuple[FactSpec, ...]:
    specs: list[FactSpec] = []
    for record in enrichment.vulnerabilities:
        if record.withdrawn is not None or not record.affected:
            continue
        query_evidence = _query_evidence(enrichment, record.osv_id)
        detail_evidence = EvidenceSpec(
            locator={"uri": record.detail_uri, "json_pointer": ""},
            excerpt_hash=sha256_key(record.raw),
            metadata={"provider": "osv.dev", "record_kind": "VULNERABILITY"},
        )
        severity = record.severity or tuple(
            item
            for affected in record.affected
            for item in _object_tuple(affected.get("severity"))
        )
        specs.append(
            FactSpec(
                vulnerability=record,
                properties={
                    "provider": "osv.dev",
                    "record_kind": "KNOWN_VULNERABILITY",
                    "matched_purl": enrichment.target.purl,
                    "osv_id": record.osv_id,
                    "aliases": list(record.aliases),
                    "modified": record.modified,
                    "severity": list(severity),
                    "affected": list(record.affected),
                },
                logical_key=sha256_key(
                    "global",
                    enrichment.target.purl,
                    "AFFECTED_BY",
                    record.osv_id,
                ),
                evidence=(query_evidence, detail_evidence),
                effective_from=record.published,
            )
        )
    return tuple(specs)


def vulnerability_properties(record: VulnerabilityRecord) -> JsonObject:
    return {
        "osv_id": record.osv_id,
        "summary": record.summary,
        "aliases": list(record.aliases),
        "published": record.published,
        "modified": record.modified,
        "withdrawn": record.withdrawn,
        "severity": list(record.severity),
        "references": list(record.references),
        "schema_version": record.raw.get("schema_version"),
    }


def _query_evidence(
    enrichment: OsvEnrichment,
    osv_id: str,
) -> EvidenceSpec:
    for page_index, page in enumerate(enrichment.raw_bundle["query_pages"]):
        result = page["result"]
        for ref_index, ref in enumerate(result.get("vulns", [])):
            if isinstance(ref, dict) and ref.get("id") == osv_id:
                return EvidenceSpec(
                    locator={
                        "uri": enrichment.raw_bundle["query_uri"],
                        "method": "POST",
                        "request": page["request"],
                        "json_pointer": f"/results/0/vulns/{ref_index}",
                        "raw_pointer": (
                            f"/query_pages/{page_index}/result/vulns/{ref_index}"
                        ),
                    },
                    excerpt_hash=sha256_key(ref),
                    metadata={
                        "provider": "osv.dev",
                        "record_kind": "PACKAGE_VERSION_MATCH",
                    },
                )
    raise ValueError(f"OSV query evidence is missing for {osv_id}")


def _query_for_target(
    target: PackageVersionKey,
    page_token: str | None,
) -> JsonObject:
    query: JsonObject = {"package": {"purl": target.purl}}
    if page_token:
        query["page_token"] = page_token
    return query


def _vulnerability_ref(value: object) -> VulnerabilityRef:
    if not isinstance(value, dict):
        raise ValueError("OSV vulnerability reference is invalid")
    osv_id = value.get("id")
    modified = value.get("modified")
    if not isinstance(osv_id, str) or not osv_id:
        raise ValueError("OSV vulnerability reference has no ID")
    if modified is not None and not isinstance(modified, str):
        raise ValueError("OSV vulnerability reference has invalid modified time")
    return VulnerabilityRef(osv_id=osv_id, modified=modified)


def _affected_matches(value: JsonObject, target: PackageVersionKey) -> bool:
    package = value.get("package")
    if not isinstance(package, dict):
        return False
    purl = package.get("purl")
    if isinstance(purl, str):
        normalized = purl.split("@", 1)[0].lower()
        if normalized == target.package_purl.lower():
            return True
    ecosystem = package.get("ecosystem")
    name = package.get("name")
    expected_ecosystem = "npm" if target.system == "NPM" else "PyPI"
    if not isinstance(ecosystem, str) or not isinstance(name, str):
        return False
    try:
        normalized_name = PackageVersionKey.from_version_key(
            {
                "system": target.system,
                "name": name,
                "version": target.version,
            }
        ).name
    except ValueError:
        return False
    return ecosystem == expected_ecosystem and normalized_name == target.name


def _object_tuple(value: object) -> tuple[JsonObject, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
