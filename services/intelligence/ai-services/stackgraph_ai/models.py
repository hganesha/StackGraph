from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from string import Template
from typing import Any, Literal, Mapping
from uuid import UUID

from stackgraph_ai.errors import PromptRenderError, PromptValidationError


MessageRole = Literal["system", "developer", "user", "assistant", "tool"]
ToolChoice = Literal["auto", "required", "none"]
PromptStatus = Literal["DRAFT", "ACTIVE", "RETIRED"]

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}$")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_key(value: Any) -> str:
    payload = value if isinstance(value, str) else canonical_json(value)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ModelMessage:
    role: MessageRole
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    strict: bool = True


@dataclass(frozen=True, slots=True)
class DataHandlingPolicy:
    """Provider-side handling requirements resolved by tenant policy."""

    store_provider_response: bool = False
    allow_provider_data_collection: bool = False
    require_zero_data_retention: bool = True


@dataclass(frozen=True, slots=True)
class ModelRequest:
    model: str
    messages: tuple[ModelMessage, ...]
    max_output_tokens: int = 1200
    temperature: float | None = None
    tools: tuple[ToolDefinition, ...] = ()
    tool_choice: ToolChoice = "auto"
    output_schema: Mapping[str, Any] | None = None
    output_schema_name: str = "stackgraph_response"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    data_policy: DataHandlingPolicy = field(default_factory=DataHandlingPolicy)

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model must not be empty")
        if not self.messages:
            raise ValueError("messages must not be empty")
        if self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")
        if self.temperature is not None and not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    actual_cost_usd: float | None = None


@dataclass(frozen=True, slots=True)
class ModelResponse:
    provider: str
    model: str
    text: str | None
    structured_output: Mapping[str, Any] | list[Any] | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str | None = None
    provider_request_id: str | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    raw_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PromptMessageTemplate:
    role: MessageRole
    content: str


@dataclass(frozen=True, slots=True)
class PromptDefinition:
    key: str
    version: str
    status: PromptStatus
    messages: tuple[PromptMessageTemplate, ...]
    input_variables: tuple[str, ...] = ()
    output_schema: Mapping[str, Any] | None = None
    model_parameters: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    tenant_id: UUID | None = None
    catalog_id: UUID | None = None
    content_hash: str | None = None

    def __post_init__(self) -> None:
        if not _KEY_PATTERN.fullmatch(self.key):
            raise PromptValidationError(f"Invalid prompt key: {self.key!r}")
        if not _VERSION_PATTERN.fullmatch(self.version):
            raise PromptValidationError(f"Invalid prompt version: {self.version!r}")
        if self.status not in {"DRAFT", "ACTIVE", "RETIRED"}:
            raise PromptValidationError(f"Invalid prompt status: {self.status!r}")
        if not self.messages:
            raise PromptValidationError("A prompt must contain at least one message")
        if len(set(self.input_variables)) != len(self.input_variables):
            raise PromptValidationError("Prompt input_variables must be unique")
        for variable in self.input_variables:
            if not variable.isidentifier():
                raise PromptValidationError(f"Invalid prompt variable: {variable!r}")
        placeholders: set[str] = set()
        for message in self.messages:
            for match in Template.pattern.finditer(message.content):
                if match.group("invalid") is not None:
                    raise PromptValidationError(
                        f"Prompt {self.key!r} contains an invalid template placeholder"
                    )
                name = match.group("named") or match.group("braced")
                if name:
                    placeholders.add(name)
        declared = set(self.input_variables)
        if placeholders != declared:
            missing = sorted(placeholders - declared)
            unused = sorted(declared - placeholders)
            details = []
            if missing:
                details.append(f"undeclared placeholders: {', '.join(missing)}")
            if unused:
                details.append(f"unused variables: {', '.join(unused)}")
            raise PromptValidationError(f"Prompt {self.key!r} has {'; '.join(details)}")
        expected_hash = self.calculate_content_hash()
        if self.content_hash is not None and self.content_hash != expected_hash:
            raise PromptValidationError(
                f"Prompt {self.key!r} content_hash does not match its persisted content"
            )
        object.__setattr__(self, "content_hash", expected_hash)

    def calculate_content_hash(self) -> str:
        return sha256_key(
            {
                "key": self.key,
                "version": self.version,
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in self.messages
                ],
                "input_variables": list(self.input_variables),
                "output_schema": self.output_schema,
                "model_parameters": self.model_parameters,
                "metadata": self.metadata,
            }
        )

    def render(self, variables: Mapping[str, Any]) -> tuple[ModelMessage, ...]:
        expected = set(self.input_variables)
        supplied = set(variables)
        missing = sorted(expected - supplied)
        unexpected = sorted(supplied - expected)
        if missing or unexpected:
            parts = []
            if missing:
                parts.append(f"missing variables: {', '.join(missing)}")
            if unexpected:
                parts.append(f"unexpected variables: {', '.join(unexpected)}")
            raise PromptRenderError(f"Cannot render {self.key!r}: {'; '.join(parts)}")

        substitutions = {
            key: value if isinstance(value, str) else canonical_json(value)
            for key, value in variables.items()
        }
        rendered: list[ModelMessage] = []
        try:
            for message in self.messages:
                rendered.append(
                    ModelMessage(
                        role=message.role,
                        content=Template(message.content).substitute(substitutions),
                    )
                )
        except (KeyError, ValueError) as error:
            raise PromptRenderError(f"Cannot render {self.key!r}: {error}") from error
        return tuple(rendered)

    def as_record(self) -> dict[str, Any]:
        return {
            "prompt_key": self.key,
            "version": self.version,
            "status": self.status,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in self.messages
            ],
            "input_variables": list(self.input_variables),
            "output_schema": self.output_schema,
            "model_parameters": dict(self.model_parameters),
            "metadata": dict(self.metadata),
            "content_hash": self.content_hash,
            "tenant_id": self.tenant_id,
            "id": self.catalog_id,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "PromptDefinition":
        raw_messages = record.get("messages")
        if not isinstance(raw_messages, list):
            raise PromptValidationError("Prompt messages must be a JSON array")
        try:
            messages = tuple(
                PromptMessageTemplate(role=message["role"], content=message["content"])
                for message in raw_messages
            )
        except (KeyError, TypeError) as error:
            raise PromptValidationError("Each prompt message requires role and content") from error
        raw_tenant = record.get("tenant_id")
        return cls(
            key=str(record.get("prompt_key") or record.get("key") or ""),
            version=str(record.get("version") or ""),
            status=str(record.get("status") or "ACTIVE").upper(),  # type: ignore[arg-type]
            messages=messages,
            input_variables=tuple(record.get("input_variables") or ()),
            output_schema=record.get("output_schema"),
            model_parameters=record.get("model_parameters") or {},
            metadata=record.get("metadata") or {},
            tenant_id=UUID(str(raw_tenant)) if raw_tenant else None,
            catalog_id=UUID(str(record["id"])) if record.get("id") else None,
            content_hash=record.get("content_hash"),
        )


@dataclass(frozen=True, slots=True)
class ModelRoute:
    name: str
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class PromptInvocation:
    prompt: PromptDefinition
    route: ModelRoute
    input_fingerprint: str
    response: ModelResponse
    invocation_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def provenance(self) -> dict[str, Any]:
        return {
            "provider": self.response.provider,
            "model": self.response.model,
            "promptKey": self.prompt.key,
            "promptVersion": self.prompt.version,
            "promptContentHash": self.prompt.content_hash,
            "policyVersion": self.prompt.metadata.get("policy_version"),
            "inputFingerprint": self.input_fingerprint,
            "createdAt": self.created_at.isoformat(),
        }
