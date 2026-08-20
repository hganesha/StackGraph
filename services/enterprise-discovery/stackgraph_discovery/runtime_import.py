from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


EXTRACTOR_KEY = "attested-runtime-import"
EXTRACTOR_VERSION = "1.0.0"


def import_runtime_observation(observation: Mapping[str, Any]) -> list[dict[str, Any]]:
    if observation.get("runtime_contract_version") != "1.0.0":
        raise ValueError("unsupported runtime observation contract")
    if observation.get("absence_is_unknown") is not True:
        raise ValueError("runtime observation must preserve absence as UNKNOWN")
    source = observation.get("source")
    if not isinstance(source, dict) or source.get("verified") is not True:
        raise ValueError("runtime observation attestation must be verified")
    artifact = observation.get("artifact")
    workload = observation.get("workload")
    events = observation.get("events")
    if not isinstance(artifact, dict) or not isinstance(workload, dict) or not isinstance(events, list):
        raise ValueError("runtime observation is incomplete")
    facts: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError("runtime event must be an object")
        fingerprint = _hash({"observation_id": observation.get("observation_id"), "index": index, "event": event})
        facts.append({
            "fact_contract_version": "1.0.0",
            "idempotency_key": fingerprint,
            "tenant_key": observation["tenant_key"],
            "subject": event["subject"],
            "predicate": event["predicate"],
            "object_entity": event["object_entity"],
            "assertion_class": "OBSERVED",
            "confidence": event["confidence"],
            "observed_at": observation["observed_at"],
            "source_revision": workload["source_revision"],
            "extractor": {"key": EXTRACTOR_KEY, "version": EXTRACTOR_VERSION},
            "properties": {
                **event.get("properties", {}),
                "runtime_event_kind": event["event_kind"],
                "valid_until": observation["valid_until"],
                "collector_identity": source["collector_identity"],
                "absence_is_unknown": True,
            },
            "evidence": [{
                "type": "ATTESTED_RUNTIME_OBSERVATION",
                "source_artifact": {
                    "key": artifact["key"],
                    "type": "RUNTIME_OBSERVATION",
                    "revision": artifact["revision"],
                    "content_hash": artifact["content_hash"],
                },
                "locator": {**event["locator"], "uri": artifact["blob_uri"]},
            }],
        })
    return facts


def _hash(value: object) -> str:
    content = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
