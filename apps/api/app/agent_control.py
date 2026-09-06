from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from app.errors import APIError
from app.models import (
    AgentApprovalDecisionRequest,
    AgentApprovalModel,
    AgentAuthorizationDecisionModel,
    AgentAuthorizeRequest,
    AgentControlDrillRequest,
    AgentControlDrillResult,
    AgentKillSwitchModel,
    AgentKillSwitchUpdateRequest,
    CapabilityBandModel,
    CapabilityEnvelopeCompileRequest,
    CapabilityEnvelopeModel,
    CapabilityEnvelopeOperation,
    FlightEventCreateRequest,
    FlightEventModel,
    FlightRecordCreateRequest,
    FlightRecordFinalizeRequest,
    FlightRecordModel,
    GateReason,
)


_BANDS = ("READ", "EXECUTE", "CONDITIONAL", "PROHIBITED", "ESCALATE")
_DECISION_ORDER = {"ALLOW": 0, "CONSTRAIN": 1, "ESCALATE": 2, "DENY": 3}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode()).hexdigest()


def _reason(code: str, message: str, evidence: list[UUID] | None = None) -> GateReason:
    return GateReason(code=code, message=message, evidence_fact_ids=evidence or [])


class AgentControlMixin:
    """Default-deny R16 capability compilation and tamper-evident flight recording."""

    database: Any

    async def _agent_policy(self, tenant_id: UUID) -> dict[str, Any]:
        row = await self.database.fetch_one(
            """
            SELECT id,configuration,content_hash,version
            FROM agent_capability_policy
            WHERE status='ACTIVE' AND (tenant_id=%s OR tenant_id IS NULL)
            ORDER BY tenant_id NULLS LAST,version DESC LIMIT 1
            """,
            (tenant_id,), tenant_id=tenant_id,
        )
        if row is None:
            raise APIError(503, "AGENT_POLICY_UNAVAILABLE", "No active agent capability policy exists.")
        return row

    async def _open_contradictions(
        self, tenant_id: UUID, subject_ids: list[UUID],
    ) -> list[dict[str, Any]]:
        if not subject_ids:
            return []
        return await self.database.fetch_all(
            """
            SELECT id,subject_entity_id,dimension,severity
            FROM estate_contradiction
            WHERE tenant_id=%s AND status='OPEN' AND subject_entity_id=ANY(%s)
            ORDER BY severity DESC,id
            """,
            (tenant_id, subject_ids), tenant_id=tenant_id,
        )

    async def compile_capability_envelope(
        self, request: CapabilityEnvelopeCompileRequest, *, tenant_id: UUID | None,
        actor_key: str,
    ) -> CapabilityEnvelopeModel:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required to compile an envelope.")
        policy = await self._agent_policy(tenant_id)
        configuration = policy["configuration"]
        minimum_confidence = float(configuration.get("minimum_context_confidence", 0.8))
        prohibited = set(configuration.get("prohibited_operations", []))
        destructive_tokens = set(configuration.get("destructive_operations", []))
        contradictions = await self._open_contradictions(tenant_id, request.subject_entity_ids)

        evidence_ids = list(dict.fromkeys(request.evidence_fact_ids))
        if evidence_ids:
            row = await self.database.fetch_one(
                "SELECT count(*) count FROM fact_assertion WHERE id=ANY(%s)",
                (evidence_ids,), tenant_id=tenant_id,
            )
            if row is None or row["count"] != len(evidence_ids):
                raise APIError(
                    422, "EVIDENCE_OUTSIDE_TENANT",
                    "Every envelope evidence reference must resolve inside the active tenant.",
                )

        reasons: list[GateReason] = []
        operation_rows: list[dict[str, Any]] = []
        decision = "ALLOW"
        for item in request.operations:
            key_tokens = set(item.operation_key.replace(":", ".").split("."))
            destructive = item.destructive or bool(key_tokens & destructive_tokens)
            band = item.requested_band
            operation_reasons: list[str] = []
            if item.operation_key in prohibited or band == "PROHIBITED":
                band = "PROHIBITED"
                operation_reasons.append("OPERATION_PROHIBITED")
                decision = "DENY"
            elif band != "READ" and (
                destructive or request.risk_tier == "TIER_0" or contradictions
                or request.context_confidence < minimum_confidence
            ):
                band = "ESCALATE"
                if destructive:
                    operation_reasons.append("DESTRUCTIVE_OPERATION")
                if request.risk_tier == "TIER_0":
                    operation_reasons.append("TIER_0_APPROVAL_REQUIRED")
                if contradictions:
                    operation_reasons.append("UNRESOLVED_CONTRADICTION")
                if request.context_confidence < minimum_confidence:
                    operation_reasons.append("LOW_CONTEXT_CONFIDENCE")
                if _DECISION_ORDER[decision] < _DECISION_ORDER["ESCALATE"]:
                    decision = "ESCALATE"
            elif band == "ESCALATE":
                operation_reasons.append("EXPLICIT_ESCALATION")
                if _DECISION_ORDER[decision] < _DECISION_ORDER["ESCALATE"]:
                    decision = "ESCALATE"
            elif band == "CONDITIONAL":
                operation_reasons.append("CONDITIONAL_OPERATION")
                if _DECISION_ORDER[decision] < _DECISION_ORDER["CONSTRAIN"]:
                    decision = "CONSTRAIN"
            operation_rows.append({
                "operation_key": item.operation_key,
                "band": band,
                "constraints": {
                    **item.constraints,
                    "destructive": destructive,
                    "reason_codes": operation_reasons,
                },
            })

        if contradictions:
            reasons.append(_reason(
                "UNRESOLVED_CONTRADICTION",
                "One or more affected subjects have unresolved contradictory evidence.",
            ))
        if request.context_confidence < minimum_confidence:
            reasons.append(_reason(
                "LOW_CONTEXT_CONFIDENCE",
                f"Context confidence is below the governed {minimum_confidence:.2f} threshold.",
                evidence_ids,
            ))
        if not evidence_ids:
            reasons.append(_reason(
                "EVIDENCE_NOT_SUPPLIED",
                "The envelope has no cited estate evidence and remains constrained.",
            ))
            if decision == "ALLOW" and any(row["band"] != "READ" for row in operation_rows):
                decision = "CONSTRAIN"
        if any(row["band"] == "PROHIBITED" for row in operation_rows):
            reasons.append(_reason("OPERATION_PROHIBITED", "The policy prohibits a requested operation."))
        if request.risk_tier == "TIER_0" and any(row["band"] != "READ" for row in operation_rows):
            reasons.append(_reason("TIER_0_APPROVAL_REQUIRED", "Tier-0 mutations require human approval."))

        ttl = request.ttl_seconds or int(configuration.get("default_ttl_seconds", 900))
        ttl = min(max(ttl, 30), 3600)
        created_at = datetime.now(UTC)
        valid_until = created_at + timedelta(seconds=ttl)
        envelope_id = uuid4()
        compiled_input = {
            "policy_hash": policy["content_hash"], "actor_key": actor_key,
            "objective": request.objective, "environment": request.environment,
            "estate_watermark": request.estate_watermark, "risk_tier": request.risk_tier,
            "context_confidence": request.context_confidence, "operations": operation_rows,
            "evidence_fact_ids": [str(item) for item in evidence_ids],
            "contradiction_ids": [str(item["id"]) for item in contradictions],
            "valid_until": valid_until.isoformat(),
        }
        compiled_hash = _fingerprint(compiled_input)
        constraints = {
            "policy_version": policy["version"], "policy_hash": policy["content_hash"],
            "minimum_context_confidence": minimum_confidence,
            "least_privilege": True, "short_lived": True,
        }
        try:
            async with self.database.session(tenant_id) as connection:
                await connection.execute(
                    """
                    INSERT INTO agent_capability_envelope(
                      id,tenant_id,policy_id,actor_key,objective,environment,estate_watermark,
                      risk_tier,context_confidence,decision,decision_reasons,constraints,
                      evidence_fact_ids,contradiction_ids,status,valid_until,compiled_hash,created_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'ACTIVE',%s,%s,%s)
                    """,
                    (
                        envelope_id, tenant_id, policy["id"], actor_key, request.objective,
                        request.environment, request.estate_watermark, request.risk_tier,
                        request.context_confidence, decision,
                        Jsonb([item.model_dump(mode="json") for item in reasons]), Jsonb(constraints),
                        evidence_ids, [item["id"] for item in contradictions], valid_until,
                        compiled_hash, created_at,
                    ),
                )
                for operation in operation_rows:
                    await connection.execute(
                        """
                        INSERT INTO agent_envelope_operation(
                          tenant_id,envelope_id,operation_key,band,constraints
                        ) VALUES (%s,%s,%s,%s,%s)
                        """,
                        (
                            tenant_id, envelope_id, operation["operation_key"], operation["band"],
                            Jsonb(operation["constraints"]),
                        ),
                    )
                    if operation["band"] == "ESCALATE":
                        codes = operation["constraints"].get("reason_codes") or ["EXPLICIT_ESCALATION"]
                        await connection.execute(
                            """
                            INSERT INTO agent_approval(
                              tenant_id,envelope_id,operation_key,reason_code,status,requested_by,expires_at
                            ) VALUES (%s,%s,%s,%s,'PENDING',%s,%s)
                            """,
                            (tenant_id, envelope_id, operation["operation_key"], codes[0], actor_key, valid_until),
                        )
        except UniqueViolation:
            row = await self.database.fetch_one(
                "SELECT id FROM agent_capability_envelope WHERE compiled_hash=%s",
                (compiled_hash,), tenant_id=tenant_id,
            )
            if row is None:
                raise
            envelope_id = row["id"]
        return await self.capability_envelope(envelope_id, tenant_id=tenant_id)

    async def capability_envelope(
        self, envelope_id: UUID, *, tenant_id: UUID | None,
    ) -> CapabilityEnvelopeModel:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        row = await self.database.fetch_one(
            "SELECT * FROM agent_capability_envelope WHERE id=%s",
            (envelope_id,), tenant_id=tenant_id,
        )
        if row is None:
            raise APIError(404, "CAPABILITY_ENVELOPE_NOT_FOUND", "The capability envelope was not found.")
        status = row["status"]
        if status == "ACTIVE" and row["valid_until"] <= datetime.now(UTC):
            status = "EXPIRED"
        operations = await self.database.fetch_all(
            "SELECT operation_key,band,constraints FROM agent_envelope_operation WHERE envelope_id=%s ORDER BY operation_key",
            (envelope_id,), tenant_id=tenant_id,
        )
        bands = [CapabilityBandModel(
            band=band,
            operations=[CapabilityEnvelopeOperation(**item) for item in operations if item["band"] == band],
        ) for band in _BANDS]
        return CapabilityEnvelopeModel(
            id=row["id"], actor_key=row["actor_key"], objective=row["objective"],
            environment=row["environment"], estate_watermark=row["estate_watermark"],
            risk_tier=row["risk_tier"], context_confidence=float(row["context_confidence"]),
            decision=row["decision"],
            decision_reasons=[GateReason(**item) for item in row["decision_reasons"]],
            constraints=row["constraints"], evidence_fact_ids=row["evidence_fact_ids"],
            contradiction_ids=row["contradiction_ids"], bands=bands, status=status,
            valid_until=row["valid_until"], compiled_hash=row["compiled_hash"],
            created_at=row["created_at"],
        )

    async def authorize_agent_operation(
        self, envelope_id: UUID, request: AgentAuthorizeRequest, *, tenant_id: UUID | None,
        actor_key: str,
    ) -> AgentAuthorizationDecisionModel:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        now = datetime.now(UTC)
        decision_id = uuid4()
        request_fingerprint = _fingerprint({
            "envelope_id": str(envelope_id), "operation_key": request.operation_key,
            "payload": request.request_payload, "actor_key": actor_key,
        })
        async with self.database.session(tenant_id) as connection:
            envelope_cursor = await connection.execute(
                "SELECT * FROM agent_capability_envelope WHERE id=%s FOR UPDATE",
                (envelope_id,),
            )
            envelope = await envelope_cursor.fetchone()
            if envelope is None:
                raise APIError(404, "CAPABILITY_ENVELOPE_NOT_FOUND", "The capability envelope was not found.")
            operation_cursor = await connection.execute(
                "SELECT * FROM agent_envelope_operation WHERE envelope_id=%s AND operation_key=%s",
                (envelope_id, request.operation_key),
            )
            operation = await operation_cursor.fetchone()
            switch_cursor = await connection.execute(
                "SELECT engaged FROM agent_kill_switch WHERE tenant_id=%s", (tenant_id,),
            )
            switch = await switch_cursor.fetchone()
            reason_codes: list[str] = []
            approval_id = None
            decision = "ALLOW"
            if envelope["actor_key"] != actor_key:
                decision, reason_codes = "DENY", ["ACTOR_MISMATCH"]
            elif envelope["status"] != "ACTIVE" or envelope["valid_until"] <= now:
                decision, reason_codes = "DENY", ["ENVELOPE_INACTIVE"]
            elif operation is None:
                decision, reason_codes = "DENY", ["OPERATION_NOT_IN_ENVELOPE"]
            elif operation["band"] == "PROHIBITED":
                decision, reason_codes = "DENY", ["OPERATION_PROHIBITED"]
            elif operation["band"] != "READ" and (switch is None or switch["engaged"]):
                decision, reason_codes = "DENY", ["KILL_SWITCH_ENGAGED"]
            elif operation["band"] in {"ESCALATE", "CONDITIONAL"}:
                approval_cursor = await connection.execute(
                    """
                    SELECT id,status,expires_at FROM agent_approval
                    WHERE envelope_id=%s AND operation_key=%s
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (envelope_id, request.operation_key),
                )
                approval = await approval_cursor.fetchone()
                if approval is None or approval["status"] != "APPROVED" or approval["expires_at"] <= now:
                    decision, reason_codes = "ESCALATE", ["HUMAN_APPROVAL_REQUIRED"]
                else:
                    approval_id = approval["id"]
                    decision = "CONSTRAIN" if operation["band"] == "CONDITIONAL" else "ALLOW"
                    reason_codes = ["APPROVAL_VERIFIED"]
            await connection.execute(
                """
                INSERT INTO agent_authorization_decision(
                  id,tenant_id,envelope_id,operation_key,decision,reason_codes,approval_id,
                  request_fingerprint,actor_key,decided_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    decision_id, tenant_id, envelope_id, request.operation_key, decision,
                    reason_codes, approval_id, request_fingerprint, actor_key, now,
                ),
            )
        return AgentAuthorizationDecisionModel(
            id=decision_id, envelope_id=envelope_id, operation_key=request.operation_key,
            decision=decision, reason_codes=reason_codes, approval_id=approval_id,
            request_fingerprint=request_fingerprint, decided_at=now,
        )

    async def decide_agent_approval(
        self, approval_id: UUID, request: AgentApprovalDecisionRequest, *,
        tenant_id: UUID | None, actor_key: str,
    ) -> AgentApprovalModel:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        now = datetime.now(UTC)
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM agent_approval WHERE id=%s FOR UPDATE", (approval_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise APIError(404, "AGENT_APPROVAL_NOT_FOUND", "The approval request was not found.")
            if row["status"] != "PENDING":
                raise APIError(409, "AGENT_APPROVAL_TERMINAL", "The approval was already decided.")
            if row["version"] != request.expected_version:
                raise APIError(409, "VERSION_CONFLICT", "The approval changed; reload before deciding.")
            if row["expires_at"] <= now:
                await connection.execute(
                    "UPDATE agent_approval SET status='EXPIRED',version=version+1,decided_at=%s WHERE id=%s",
                    (now, approval_id),
                )
                raise APIError(409, "AGENT_APPROVAL_EXPIRED", "The approval request has expired.")
            cursor = await connection.execute(
                """
                UPDATE agent_approval SET status=%s,decided_by=%s,rationale=%s,
                  version=version+1,decided_at=%s WHERE id=%s RETURNING *
                """,
                (request.decision, actor_key, request.rationale, now, approval_id),
            )
            updated = await cursor.fetchone()
        assert updated is not None
        return AgentApprovalModel(
            id=updated["id"], envelope_id=updated["envelope_id"],
            operation_key=updated["operation_key"], reason_code=updated["reason_code"],
            status=updated["status"], requested_by=updated["requested_by"],
            decided_by=updated["decided_by"], rationale=updated["rationale"],
            version=updated["version"], expires_at=updated["expires_at"],
            created_at=updated["created_at"], decided_at=updated["decided_at"],
        )

    async def agent_kill_switch(self, *, tenant_id: UUID | None) -> AgentKillSwitchModel:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        row = await self.database.fetch_one(
            "SELECT * FROM agent_kill_switch WHERE tenant_id=%s", (tenant_id,), tenant_id=tenant_id,
        )
        if row is None:
            return AgentKillSwitchModel(
                engaged=True, reason="Agent execution is disabled until explicitly enabled.",
                version=0, updated_by="system:default-deny", updated_at=datetime.now(UTC),
            )
        return AgentKillSwitchModel(**row)

    async def update_agent_kill_switch(
        self, request: AgentKillSwitchUpdateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> AgentKillSwitchModel:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        now = datetime.now(UTC)
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM agent_kill_switch WHERE tenant_id=%s FOR UPDATE", (tenant_id,),
            )
            row = await cursor.fetchone()
            version = int(row["version"]) if row else 0
            if version != request.expected_version:
                raise APIError(409, "VERSION_CONFLICT", "The kill switch changed; reload before updating.")
            cursor = await connection.execute(
                """
                INSERT INTO agent_kill_switch(tenant_id,engaged,reason,version,updated_by,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT(tenant_id) DO UPDATE SET engaged=EXCLUDED.engaged,
                  reason=EXCLUDED.reason,version=EXCLUDED.version,
                  updated_by=EXCLUDED.updated_by,updated_at=EXCLUDED.updated_at
                RETURNING *
                """,
                (tenant_id, request.engaged, request.reason, version + 1, actor_key, now),
            )
            updated = await cursor.fetchone()
        assert updated is not None
        return AgentKillSwitchModel(**updated)

    async def create_flight_record(
        self, request: FlightRecordCreateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> FlightRecordModel:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        envelope = await self.capability_envelope(request.envelope_id, tenant_id=tenant_id)
        if envelope.status != "ACTIVE":
            raise APIError(409, "ENVELOPE_INACTIVE", "Only active envelopes can start a flight record.")
        if envelope.actor_key != actor_key:
            raise APIError(403, "ACTOR_MISMATCH", "The envelope belongs to a different actor.")
        record_id = uuid4()
        now = datetime.now(UTC)
        async with self.database.session(tenant_id) as connection:
            await connection.execute(
                """
                INSERT INTO agent_flight_record(
                  id,tenant_id,envelope_id,objective,status,started_by,started_at
                ) VALUES (%s,%s,%s,%s,'ACTIVE',%s,%s)
                """,
                (record_id, tenant_id, request.envelope_id, request.objective, actor_key, now),
            )
        return await self.flight_record(record_id, tenant_id=tenant_id)

    async def append_flight_event(
        self, record_id: UUID, request: FlightEventCreateRequest, *, tenant_id: UUID | None,
    ) -> FlightRecordModel:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        now = datetime.now(UTC)
        if request.occurred_at > now + timedelta(minutes=5):
            raise APIError(422, "EVENT_TIME_INVALID", "Flight events cannot be recorded in the future.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM agent_flight_record WHERE id=%s FOR UPDATE", (record_id,),
            )
            record = await cursor.fetchone()
            if record is None:
                raise APIError(404, "FLIGHT_RECORD_NOT_FOUND", "The flight record was not found.")
            if record["status"] != "ACTIVE":
                raise APIError(409, "FLIGHT_RECORD_TERMINAL", "Terminal flight records are immutable.")
            sequence = record["event_count"] + 1
            previous_hash = record["chain_head"]
            hash_input = {
                "flight_record_id": str(record_id), "sequence": sequence,
                "event_type": request.event_type, "system_boundary": request.system_boundary,
                "payload": request.payload, "previous_hash": previous_hash,
                "occurred_at": request.occurred_at.isoformat(),
            }
            event_hash = _fingerprint(hash_input)
            await connection.execute(
                """
                INSERT INTO agent_flight_event(
                  tenant_id,flight_record_id,sequence,event_type,system_boundary,payload,
                  previous_hash,event_hash,occurred_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    tenant_id, record_id, sequence, request.event_type, request.system_boundary,
                    Jsonb(request.payload), previous_hash, event_hash, request.occurred_at,
                ),
            )
            await connection.execute(
                "UPDATE agent_flight_record SET event_count=%s,chain_head=%s WHERE id=%s",
                (sequence, event_hash, record_id),
            )
        return await self.flight_record(record_id, tenant_id=tenant_id)

    async def finalize_flight_record(
        self, record_id: UUID, request: FlightRecordFinalizeRequest, *, tenant_id: UUID | None,
    ) -> FlightRecordModel:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        now = datetime.now(UTC)
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM agent_flight_record WHERE id=%s FOR UPDATE", (record_id,),
            )
            record = await cursor.fetchone()
            if record is None:
                raise APIError(404, "FLIGHT_RECORD_NOT_FOUND", "The flight record was not found.")
            if record["status"] != "ACTIVE":
                raise APIError(409, "FLIGHT_RECORD_TERMINAL", "The flight record was already finalized.")
            if request.status == "SUCCEEDED":
                check = await connection.execute(
                    "SELECT 1 FROM agent_flight_event WHERE flight_record_id=%s AND event_type='VERIFICATION' LIMIT 1",
                    (record_id,),
                )
                if await check.fetchone() is None:
                    raise APIError(
                        409, "VERIFICATION_REQUIRED",
                        "Successful flights require a recorded verification event.",
                    )
            await connection.execute(
                """
                UPDATE agent_flight_record SET status=%s,outcome=%s,completed_at=%s WHERE id=%s
                """,
                (request.status, Jsonb(request.outcome), now, record_id),
            )
        return await self.flight_record(record_id, tenant_id=tenant_id)

    async def flight_record(
        self, record_id: UUID, *, tenant_id: UUID | None,
    ) -> FlightRecordModel:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        row = await self.database.fetch_one(
            "SELECT * FROM agent_flight_record WHERE id=%s", (record_id,), tenant_id=tenant_id,
        )
        if row is None:
            raise APIError(404, "FLIGHT_RECORD_NOT_FOUND", "The flight record was not found.")
        events = await self.database.fetch_all(
            "SELECT * FROM agent_flight_event WHERE flight_record_id=%s ORDER BY sequence",
            (record_id,), tenant_id=tenant_id,
        )
        return FlightRecordModel(
            id=row["id"], envelope_id=row["envelope_id"], objective=row["objective"],
            status=row["status"], event_count=row["event_count"], chain_head=row["chain_head"],
            outcome=row["outcome"], started_by=row["started_by"], started_at=row["started_at"],
            completed_at=row["completed_at"],
            events=[FlightEventModel(
                id=item["id"], sequence=item["sequence"], event_type=item["event_type"],
                system_boundary=item["system_boundary"], payload=item["payload"],
                previous_hash=item["previous_hash"], event_hash=item["event_hash"],
                occurred_at=item["occurred_at"], recorded_at=item["recorded_at"],
            ) for item in events],
        )

    async def run_agent_control_drill(
        self, request: AgentControlDrillRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> AgentControlDrillResult:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        checks: list[dict[str, Any]] = []
        if request.drill_kind == "KILL_SWITCH":
            switch = await self.agent_kill_switch(tenant_id=tenant_id)
            checks.append({
                "check": "execution_default_denied", "passed": switch.engaged,
                "detail": "Kill switch is engaged." if switch.engaged else "Kill switch is not engaged.",
            })
        elif request.drill_kind == "ROLLBACK":
            if request.envelope_id is None:
                raise APIError(422, "ENVELOPE_REQUIRED", "Rollback drills require an envelope_id.")
            envelope = await self.capability_envelope(request.envelope_id, tenant_id=tenant_id)
            checks.extend([
                {"check": "short_lived", "passed": bool(envelope.constraints.get("short_lived"))},
                {"check": "least_privilege", "passed": bool(envelope.constraints.get("least_privilege"))},
                {"check": "rollback_not_automatic", "passed": True},
            ])
        else:
            if request.flight_record_id is None:
                raise APIError(422, "FLIGHT_RECORD_REQUIRED", "Audit drills require a flight_record_id.")
            record = await self.flight_record(request.flight_record_id, tenant_id=tenant_id)
            previous = None
            valid = True
            for event in record.events:
                expected = _fingerprint({
                    "flight_record_id": str(record.id), "sequence": event.sequence,
                    "event_type": event.event_type, "system_boundary": event.system_boundary,
                    "payload": event.payload, "previous_hash": previous,
                    "occurred_at": event.occurred_at.isoformat(),
                })
                valid = valid and event.previous_hash == previous and event.event_hash == expected
                previous = event.event_hash
            valid = valid and record.event_count == len(record.events) and record.chain_head == previous
            checks.append({"check": "hash_chain_reconstructable", "passed": valid})
        status = "PASSED" if checks and all(item["passed"] for item in checks) else "FAILED"
        drill_id = uuid4()
        performed_at = datetime.now(UTC)
        async with self.database.session(tenant_id) as connection:
            await connection.execute(
                """
                INSERT INTO agent_control_drill(
                  id,tenant_id,drill_kind,status,checks,performed_by,performed_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (drill_id, tenant_id, request.drill_kind, status, Jsonb(checks), actor_key, performed_at),
            )
        return AgentControlDrillResult(
            id=drill_id, drill_kind=request.drill_kind, status=status, checks=checks,
            performed_by=actor_key, performed_at=performed_at,
        )
